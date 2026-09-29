#!/usr/bin/env python3
"""Hand/tool-route the main board's leftovers: what Freerouting could not route.

Given a KiCad board that has the router's SES imported (a partial route), this
lists the unrouted connections and routes each with an obstacle-aware grid A*
search over the signal copper layers (F.Cu, In2.Cu, In3.Cu, B.Cu; In1 and In4
are the GND and +3V3 planes) with through vias to change layer. It never
weakens a rule: a connection with no legal path is reported with its blocker
and a proposed minimal fix, and nothing is emitted for it.

    python3 hw/boards/main_handroute.py list  BOARD.kicad_pcb
    python3 hw/boards/main_handroute.py route BOARD.kicad_pcb [--out OUT.kicad_pcb]
            [--seed-out hw/boards/main-handroute-seed.json] [--report report.json]
            [--drc] [--baseline drc.json] [--nets /A,/B] [--max-connections N]
            [--through-pour] [--power-width 0.3]
    python3 hw/boards/main_handroute.py apply BOARD.kicad_pcb [seed.json]

`route` writes OUT (default: BOARD.kicad_pcb, in place: give --out to keep the
input), the seed-format JSON (`main_seed.py` line format: ["track", net, layer,
ax, ay, bx, by, width_nm] and ["via", net, x, y, dia_nm, drill_nm], nm) and a
JSON report. `apply` puts a seed file's items on a board (locked), so a build
reproduces the hand routes deterministically after the SES import
(`main_seed.apply` is not used for this: its 0.2 mm conflict test would drop
0.1 mm-clearance routes laid next to the fan-out copper).

Rules honoured (main.py / kicadgen.py): the net classes are read from the
board's .kicad_pro (DenseSignal 0.1 / 0.1, Fine 0.15 / 0.15, Default 0.2 / 0.2,
Power and FinePower 0.3 wide by --power-width), vias 0.6 / 0.3 mm; the larger
of two nets' clearances applies between them; hole clearance 0.25, hole to
hole 0.5, copper to edge 0.3 (JLC limits, from the .kicad_pro's rules: never
weakened); no via in an SMD pad; keep-out areas (no tracks / no vias);
non-plane pours (the +1V2 island) are solid for other nets; all existing copper,
locked or not, is an obstacle to every other net. Every emitted piece is
re-checked at nominal clearance with exact geometry before it is kept, and the
KiCad DRC (`--drc`) is the authority.

SI: the search pays extra within 0.6 mm of a CPU-bus / slow-bus / TMDS / USB net's copper
(SI_CRITICAL, name patterns) and the report lists the leftover nets that are themselves on
one (`si_critical_leftovers`; each result carries `si_critical`, its length and vias).
--through-pour lets other nets' vias cross the +1V2 island pour on B.Cu (off by default: the
DRC after a refill shows whether the island is still one piece).

Limits: pads are rectangles/stadiums/circles from their bounding boxes (exact
for 0/90 degree pads, conservative for 45 degree and custom pads); the grid is
0.05 mm with a 0.035 mm safety margin on foreign copper, so a channel narrower
than track + 2 * (clearance + 0.035) is refused even where KiCad would allow
it; a plane pour is assumed to reach every pad and via of its net inside its
outline (the DRC's connectivity check after a refill settles that); a connection is searched in a
window of 3, 8, then 20 mm round its nearest pad pair (a detour beyond that is not found); pieces
of one net that only overlap count as joined, as KiCad's DRC counts them; an SES import that
left a pad without its fan-out via and stub at 0.5 mm pitch is reported walled in, not forced.
"""

import argparse
import collections
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_OUT = os.path.join(HERE, "main-handroute-seed.json")

GRID = 0.05                 # mm
MARGIN = 0.035              # mm added to every foreign clearance: half a grid diagonal
VIA_D, VIA_DRILL = 0.6, 0.3
HOLE_CLEARANCE, HOLE_TO_HOLE, EDGE_CLEARANCE = 0.25, 0.5, 0.3
NO_VIA_IN_PAD = 0.1         # via edge to its own SMD pad (main_fanout.py's last rung)
POUR_NETS = ("/GND", "/+3V3")
# nets to keep clear of and to report (name patterns; * and ? only)
SI_CRITICAL = ("/CPU_A*", "/CPU_D*", "/CPU_CLK", "/CPU_RW", "/CPU_SYNC", "/CPU_nRDY", "/CPU_nSTB", "/CPU_nRST",
               "/CPU_IRQ*", "/CPU_HALTED", "/CPU_WAITING", "/HD_*", "/HDMI*", "/TMDS*", "/USB_CONN_D*",
               "/SPI_*", "/FL*_MISO", "/FL*_MOSI", "/FL*_SCK", "/FL*_nCS", "/BR_*", "/MEM_*", "/SLOT*_CS_n")
SI_KEEPAWAY = 0.6           # mm: cells this close to an SI-critical net's copper cost extra
VIA_COST, SI_COST = 500, 6   # units of 0.005 mm of track (an orthogonal step is 10): a via costs 2.5 mm of track
EXPAND_LIMIT = 2_500_000


def _glob(pattern):
    return re.compile("^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$")


# ----------------------------------------------------------------- the board
class Pad:
    __slots__ = ("net", "layers", "kind", "cx", "cy", "hw", "hh", "hole", "smd", "ref", "num")

    def sd(self, X, Y):
        """Signed distance to the pad's copper edge (negative inside)."""
        dx, dy = np.abs(X - self.cx), np.abs(Y - self.cy)
        if self.kind == "circle":
            return np.hypot(dx, dy) - self.hw
        if self.kind == "oval":
            if self.hw >= self.hh:
                return np.hypot(np.maximum(dx - (self.hw - self.hh), 0), dy) - self.hh
            return np.hypot(dx, np.maximum(dy - (self.hh - self.hw), 0)) - self.hw
        ex, ey = dx - self.hw, dy - self.hh
        return np.hypot(np.maximum(ex, 0), np.maximum(ey, 0)) + np.minimum(np.maximum(ex, ey), 0)

    def dist(self, X, Y):
        """Distance from points to the pad's copper (0 inside)."""
        dx, dy = np.abs(X - self.cx), np.abs(Y - self.cy)
        if self.kind == "circle":
            return np.maximum(np.hypot(dx, dy) - self.hw, 0)
        if self.kind == "oval":
            if self.hw >= self.hh:
                return np.maximum(np.hypot(np.maximum(dx - (self.hw - self.hh), 0), dy) - self.hh, 0)
            return np.maximum(np.hypot(dx, np.maximum(dy - (self.hh - self.hw), 0)) - self.hw, 0)
        return np.hypot(np.maximum(dx - self.hw, 0), np.maximum(dy - self.hh, 0))


def seg_dist(X, Y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    sq = dx * dx + dy * dy
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / sq, 0, 1) if sq > 0 else 0
    return np.hypot(X - ax - t * dx, Y - ay - t * dy)


def in_polygon(X, Y, poly):
    """Even-odd point in polygon for arrays."""
    inside = np.zeros(np.broadcast(X, Y).shape, dtype=bool)
    n = len(poly)
    for k in range(n):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % n]
        if y1 == y2:
            continue
        cross = ((Y < y1) != (Y < y2)) & (X < (x2 - x1) * (Y - y1) / (y2 - y1) + x1)
        inside ^= cross
    return inside


class Board:
    """Everything the router needs, in mm. Segments: (net, layer, ax, ay, bx, by, w, locked)."""

    def __init__(self, path, power_width=0.3, pour_vias=False):
        import pcbnew
        self.pcbnew = pcbnew
        self.path = path
        self.pour_vias = pour_vias                    # may another net's via cross a non-plane pour (the +1V2 island)?
        self.b = pcbnew.LoadBoard(path)
        b = self.b
        self.cu = list(b.GetEnabledLayers().CuStack())
        self.name = {l: b.GetLayerName(l) for l in self.cu}
        self.layer_id = {n: l for l, n in self.name.items()}
        self.route_layers = [n for l, n in self.name.items() if b.GetLayerType(l) != pcbnew.LT_POWER]
        self._classes(power_width)
        rules = self.pro.get("board", {}).get("design_settings", {}).get("rules", {})
        self.min_track = rules.get("min_track_width", 0.1)
        self.min_clear = rules.get("min_clearance", 0.1)
        self.hole_clear = max(HOLE_CLEARANCE, rules.get("min_hole_clearance", 0))
        self.hole_hole = max(HOLE_TO_HOLE, rules.get("min_hole_to_hole", 0))
        self.edge_clear = max(EDGE_CLEARANCE, rules.get("min_copper_edge_clearance", 0))
        mm = pcbnew.ToMM
        self.pads = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if not p.IsOnCopperLayer() and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                    continue
                q = Pad()
                q.net, q.ref, q.num = str(p.GetNetname()), fp.GetReference(), p.GetNumber()
                q.layers = frozenset(self.name[l] for l in p.GetLayerSet().Seq() if l in self.name)
                bb = p.GetBoundingBox()
                q.cx, q.cy = mm((bb.GetLeft() + bb.GetRight()) / 2), mm((bb.GetTop() + bb.GetBottom()) / 2)
                q.hw, q.hh = mm(bb.GetWidth()) / 2, mm(bb.GetHeight()) / 2
                shape = p.GetShape()
                q.kind = "circle" if shape == pcbnew.PAD_SHAPE_CIRCLE and abs(q.hw - q.hh) < 1e-6 else \
                    "oval" if shape in (pcbnew.PAD_SHAPE_OVAL, pcbnew.PAD_SHAPE_CIRCLE) and \
                    round(p.GetOrientationDegrees()) % 90 == 0 else "rect"
                q.smd = p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                d = p.GetDrillSize()
                q.hole = mm(max(d.x, d.y)) if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) else 0
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    q.net, q.layers = "", frozenset()
                self.pads.append(q)
        self.segs, self.vias = [], []
        tracks = b.Tracks()
        for i in range(len(tracks)):
            t = tracks[i].Cast()
            if t.Type() == pcbnew.PCB_VIA_T:
                p = t.GetPosition()
                self.vias.append((str(t.GetNetname()), mm(p.x), mm(p.y), mm(t.GetWidth(pcbnew.F_Cu)),
                                  mm(t.GetDrillValue()), t.IsLocked()))
            elif t.Type() == pcbnew.PCB_TRACE_T:
                a, e = t.GetStart(), t.GetEnd()
                self.segs.append((str(t.GetNetname()), self.name[t.GetLayer()], mm(a.x), mm(a.y), mm(e.x), mm(e.y),
                                  mm(t.GetWidth()), t.IsLocked()))
        self.zones, self.keepouts, self.solid = [], [], []
        for i in range(b.GetAreaCount()):
            z = b.GetArea(i)
            ol = z.Outline()
            if ol.OutlineCount() == 0:
                continue
            ch = ol.Outline(0)
            poly = [(mm(ch.CPoint(k).x), mm(ch.CPoint(k).y)) for k in range(ch.PointCount())]
            layers = [self.name[l] for l in z.GetLayerSet().Seq() if l in self.name]
            if z.GetIsRuleArea():
                self.keepouts.append({"name": str(z.GetZoneName()), "layers": layers, "poly": poly,
                                      "tracks": z.GetDoNotAllowTracks(), "vias": z.GetDoNotAllowVias()})
            else:
                self.zones.append({"net": str(z.GetNetname()), "layers": layers, "poly": poly})
        self.solid = [z for z in self.zones if z["net"] not in POUR_NETS]
        self.si = [_glob(p) for p in SI_CRITICAL]
        ps = pcbnew.SHAPE_POLY_SET()
        b.GetBoardPolygonOutlines(ps, False)
        ch = ps.Outline(0)
        self.outline = [(mm(ch.CPoint(k).x), mm(ch.CPoint(k).y)) for k in range(ch.PointCount())]
        self.new = []                                 # what this run added: seed-format items (nm)
        self.nets = sorted({p.net for p in self.pads if p.net} | {s[0] for s in self.segs})

    # -- net classes, from the project file
    def _classes(self, power_width):
        pro_path = os.path.splitext(self.path)[0] + ".kicad_pro"
        self.pro = {}
        if os.path.exists(pro_path):
            with open(pro_path) as f:
                self.pro = json.load(f)
        ns = self.pro.get("net_settings", {})
        self.classes = {c["name"]: c for c in ns.get("classes", [])}
        self.patterns = [(_glob(p["pattern"]), p["netclass"]) for p in ns.get("netclass_patterns", [])]
        self.power_width = power_width
        self._cls = {}

    def netclass(self, net):
        if net not in self._cls:
            name = next((c for rx, c in self.patterns if rx.match(net)), "Default")
            c = self.classes.get(name, {"track_width": 0.2, "clearance": 0.2})
            width = min(c["track_width"], self.power_width) if name in ("Power", "FinePower") else c["track_width"]
            self._cls[net] = (name, width, c["clearance"])
        return self._cls[net]

    def clearance(self, net):
        """A netless item (a lone pad, an NPTH) is judged at the Default clearance."""
        return self.netclass(net)[2] if net else self.classes.get("Default", {}).get("clearance", 0.2)


# --------------------------------------------------------------- connectivity
def _pt_in_seg(x, y, s, eps=1e-4):
    return float(seg_dist(np.array(x), np.array(y), *s[2:6])) <= s[6] / 2 + eps


def components(board):
    """{net: [component]}, a component = {"pads": [Pad], "segs": [i], "vias": [i], "zones": [i]}: KiCad's rule
    (an item's anchor inside another's shape, on a common layer), zones by anchor inside their outline."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)
    per_net = collections.defaultdict(list)          # net -> [(kind, index)]
    for i, p in enumerate(board.pads):
        if p.net and p.layers:
            per_net[p.net].append(("pad", i))
    for i, s in enumerate(board.segs):
        per_net[s[0]].append(("seg", i))
    for i, v in enumerate(board.vias):
        per_net[v[0]].append(("via", i))
    for i, z in enumerate(board.zones):
        for l in z["layers"]:
            per_net[z["net"]].append(("zone", (i, l)))
    allv = set(board.name.values())
    for net, items in per_net.items():
        cell = collections.defaultdict(list)
        boxes = {}
        for it in items:
            k, i = it
            if k == "pad":
                p = board.pads[i]
                bx = (p.cx - p.hw, p.cy - p.hh, p.cx + p.hw, p.cy + p.hh)
            elif k == "seg":
                s = board.segs[i]
                bx = (min(s[2], s[4]) - s[6] / 2, min(s[3], s[5]) - s[6] / 2, max(s[2], s[4]) + s[6] / 2,
                      max(s[3], s[5]) + s[6] / 2)
            elif k == "via":
                v = board.vias[i]
                bx = (v[1] - v[3] / 2, v[2] - v[3] / 2, v[1] + v[3] / 2, v[2] + v[3] / 2)
            else:
                bx = None
            boxes[it] = bx
            if bx is None:
                continue
            for cx in range(int(bx[0] // 2), int(bx[2] // 2) + 1):
                for cy in range(int(bx[1] // 2), int(bx[3] // 2) + 1):
                    cell[(cx, cy)].append(it)
        seen = set()
        for lst in cell.values():
            for a in lst:
                for b in lst:
                    if a < b and (a, b) not in seen:
                        seen.add((a, b))
                        if _touch(board, a, b, allv):
                            union(a, b)
        for it in items:                                # zones: an anchor of any item inside the outline
            if it[0] != "zone":
                continue
            zi, layer = it[1]
            poly = board.zones[zi]["poly"]
            for o in items:
                if o[0] == "zone":
                    continue
                for (x, y), ls in _anchors(board, o, allv):
                    if layer in ls and bool(in_polygon(np.array(x), np.array(y), poly)):
                        union(it, o)
                        break
    result = collections.defaultdict(lambda: collections.defaultdict(lambda: {"pads": [], "segs": [], "vias": [],
                                                                               "zones": []}))
    for net, items in per_net.items():
        for it in items:
            c = result[net][find(it)]
            k, i = it
            c[{"pad": "pads", "seg": "segs", "via": "vias", "zone": "zones"}[k]].append(i)
    out = {}
    for net, comps in result.items():
        real = [c for c in comps.values() if c["pads"]]          # a component with no pad needs no connection
        if len(real) > 1:
            out[net] = real
    return out


def _anchors(board, it, allv):
    k, i = it
    if k == "pad":
        p = board.pads[i]
        return [((p.cx, p.cy), p.layers)]
    if k == "seg":
        s = board.segs[i]
        return [((s[2], s[3]), {s[1]}), ((s[4], s[5]), {s[1]})]
    v = board.vias[i]
    return [((v[1], v[2]), allv)]


def _touch(board, a, b, allv):
    """KiCad's rule as far as the boards show it (the DRC counted an eFuse-corner pad joined by a 2 mm track whose
    end only overlaps it): copper shapes that overlap on a common layer are one net piece; two tracks meet at
    an end (an end inside the other's width)."""
    ka, kb = a[0], b[0]
    if ka > kb:
        a, b, ka, kb = b, a, kb, ka
    ia, ib = a[1], b[1]
    if (ka, kb) == ("seg", "seg"):
        s, t = board.segs[ia], board.segs[ib]
        if s[1] != t[1]:
            return False
        return any(_pt_in_seg(x, y, t) for x, y in ((s[2], s[3]), (s[4], s[5]))) or \
            any(_pt_in_seg(x, y, s) for x, y in ((t[2], t[3]), (t[4], t[5])))
    if (ka, kb) == ("pad", "seg"):
        p, s = board.pads[ia], board.segs[ib]
        if s[1] not in p.layers:
            return False
        n = max(2, int(math.hypot(s[4] - s[2], s[5] - s[3]) / 0.05) + 1)
        t = np.linspace(0, 1, n)
        return bool((p.dist(s[2] + (s[4] - s[2]) * t, s[3] + (s[5] - s[3]) * t) - s[6] / 2 <= 1e-4).any())
    if (ka, kb) == ("pad", "via"):
        p, v = board.pads[ia], board.vias[ib]
        return float(p.dist(np.array(v[1]), np.array(v[2]))) <= v[3] / 2 + 1e-4
    if (ka, kb) == ("seg", "via"):
        s, v = board.segs[ia], board.vias[ib]
        return float(seg_dist(np.array(v[1]), np.array(v[2]), *s[2:6])) <= v[3] / 2 + s[6] / 2 + 1e-4
    if (ka, kb) == ("via", "via"):
        v, w = board.vias[ia], board.vias[ib]
        return math.hypot(v[1] - w[1], v[2] - w[2]) <= (v[3] + w[3]) / 2 + 1e-4
    return False


def leftovers(board):
    """[(net, [components])] of nets with more than one piece."""
    return sorted(components(board).items())


def comp_center_dist(board, ca, cb):
    return min(math.hypot(p.cx - q.cx, p.cy - q.cy) for p in (board.pads[i] for i in ca["pads"])
               for q in (board.pads[j] for j in cb["pads"]))


# --------------------------------------------------------------- the grid
class Window:
    def __init__(self, bbox, g=GRID):
        self.g = g
        x0, y0, x1, y1 = bbox
        self.x0, self.y0 = math.floor(x0 / g) * g, math.floor(y0 / g) * g
        self.W = int((x1 - self.x0) / g) + 3
        self.H = int((y1 - self.y0) / g) + 3
        self.xs = self.x0 + np.arange(self.W) * g
        self.ys = self.y0 + np.arange(self.H) * g
        self.S = self.W * self.H
        self._inside = {}

    def box(self, x0, y0, x1, y1):
        i0, i1 = max(int(math.floor((x0 - self.x0) / self.g)), 0), min(int(math.ceil((x1 - self.x0) / self.g)) + 1, self.W)
        j0, j1 = max(int(math.floor((y0 - self.y0) / self.g)), 0), min(int(math.ceil((y1 - self.y0) / self.g)) + 1, self.H)
        if i0 >= i1 or j0 >= j1:
            return None
        return i0, i1, j0, j1

    def grid(self, i0, i1, j0, j1):
        return self.xs[None, i0:i1], self.ys[j0:j1, None]

    def node(self, x, y):
        return int(round((x - self.x0) / self.g)), int(round((y - self.y0) / self.g))

    def inside(self, poly):
        key = id(poly)
        if key not in self._inside:
            self._inside[key] = in_polygon(self.xs[None, :], self.ys[:, None], poly)
        return self._inside[key]

    def poly_raster(self, poly):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        out = np.zeros((self.H, self.W), dtype=bool)
        rng = self.box(min(xs), min(ys), max(xs), max(ys))
        if rng:
            i0, i1, j0, j1 = rng
            out[j0:j1, i0:i1] = in_polygon(*self.grid(*rng), poly)
        return out


class Mask:
    """A blocked-node raster and, per node, what blocks it (an index into `who`)."""

    def __init__(self, win):
        self.win = win
        self.a = np.zeros((win.H, win.W), dtype=bool)
        self.lab = np.zeros((win.H, win.W), dtype=np.int32)
        self.who = [None]

    def _set(self, what, rng, hit):
        if hit.any():
            i0, i1, j0, j1 = rng
            self.who.append(what)
            self.a[j0:j1, i0:i1] |= hit
            self.lab[j0:j1, i0:i1][hit] = len(self.who) - 1

    def add(self, what, dist_fn, bbox, r):
        rng = self.win.box(bbox[0] - r, bbox[1] - r, bbox[2] + r, bbox[3] + r)
        if rng is not None:
            self._set(what, rng, dist_fn(*self.win.grid(*rng)) < r)

    def poly(self, what, poly, grow):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        rng = self.win.box(min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)
        if rng is None:
            return
        X, Y = self.win.grid(*rng)
        hit = in_polygon(X, Y, poly)
        for k in range(len(poly)):
            hit |= seg_dist(X, Y, *poly[k], *poly[(k + 1) % len(poly)]) < grow
        self._set(what, rng, hit)


def build(board, win, net, width, clr, margin=MARGIN, via_d=VIA_D, drill=VIA_DRILL):
    """The obstacles of routing `net` (a `width` track at clearance `clr`, a via_d/drill via):
    ({route layer: track Mask}, via Mask, {route layer: SI keep-away cost})."""
    h, hv, M = width / 2, via_d / 2, margin
    tracks = {l: Mask(win) for l in board.route_layers}
    via = Mask(win)
    pen = {l: np.zeros((win.H, win.W), dtype=np.uint8) for l in board.route_layers}
    lo, hi = (win.xs[0], win.ys[0]), (win.xs[-1], win.ys[-1])

    def near(box, r):
        return not (box[2] + r < lo[0] or box[0] - r > hi[0] or box[3] + r < lo[1] or box[1] - r > hi[1])

    def keepaway(layers, fn, box):
        rng = win.box(box[0] - SI_KEEPAWAY, box[1] - SI_KEEPAWAY, box[2] + SI_KEEPAWAY, box[3] + SI_KEEPAWAY)
        if rng:
            i0, i1, j0, j1 = rng
            hit = fn(*win.grid(*rng)) < SI_KEEPAWAY
            for l in layers:
                pen[l][j0:j1, i0:i1][hit] = SI_COST

    for n, l, ax, ay, bx, by, w, _ in board.segs:
        if n and n == net:
            continue
        box = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        c = max(clr, board.clearance(n))
        rt = w / 2 + c + h + M
        rv = max(w / 2 + c + hv, w / 2 + board.hole_clear + drill / 2) + M
        if not near(box, max(rt, rv, SI_KEEPAWAY)):
            continue
        what = ("track", n, l, (round(ax, 3), round(ay, 3)), (round(bx, 3), round(by, 3)))
        fn = lambda X, Y, a=(ax, ay, bx, by): seg_dist(X, Y, *a)
        if l in tracks:
            tracks[l].add(what, fn, box, rt)
            if n and any(rx.match(n) for rx in board.si):
                keepaway([l], fn, box)
        via.add(what, fn, box, rv)
    for n, x, y, d, dr, _ in board.vias:
        c = max(clr, board.clearance(n))
        rt = d / 2 + c + h + M
        rv = max(d / 2 + c + hv + M if n != net else 0, dr / 2 + drill / 2 + board.hole_hole + M)
        box = (x, y, x, y)
        if not near(box, max(rt, rv, SI_KEEPAWAY)):
            continue
        what = ("via", n, "all", (round(x, 3), round(y, 3)))
        fn = lambda X, Y, x=x, y=y: np.hypot(X - x, Y - y)
        if n != net:
            for m in tracks.values():
                m.add(what, fn, box, rt)
            if n and any(rx.match(n) for rx in board.si):
                keepaway(list(tracks), fn, box)
        via.add(what, fn, box, rv)
    for p in board.pads:
        box = (p.cx - p.hw, p.cy - p.hh, p.cx + p.hw, p.cy + p.hh)
        c = max(clr, board.clearance(p.net))
        own = bool(p.net) and p.net == net
        rt = 0 if own else c + h + M
        if own:
            rv = (NO_VIA_IN_PAD + hv) if p.smd else 0     # no via in its own SMD pad
        else:
            rv = max(c + hv, board.hole_clear + drill / 2) + M
        if not p.layers and p.hole:                       # an NPTH: hole edge to copper, from the hole edge
            rt = board.hole_clear + h + M
            rv = board.hole_clear + hv + M
        rh = p.hole / 2 + drill / 2 + board.hole_hole + M if p.hole else 0
        if not near(box, max(rt, rv, rh)):
            continue
        what = ("pad", p.net, "%s.%s" % (p.ref, p.num), (round(p.cx, 3), round(p.cy, 3)))
        if p.layers:
            fn = lambda X, Y, p=p: p.dist(X, Y)
        else:                                             # an NPTH has no copper: only its hole counts
            fn = lambda X, Y, p=p: np.maximum(np.hypot(X - p.cx, Y - p.cy) - p.hole / 2, 0)
            box = (p.cx - p.hole / 2, p.cy - p.hole / 2, p.cx + p.hole / 2, p.cy + p.hole / 2)
        if rt:
            for l in (p.layers if p.layers else tracks):
                if l in tracks:
                    tracks[l].add(what, fn, box, rt)
        if rv:
            via.add(what, fn, box, rv)
        if rh:
            via.add(what, lambda X, Y, p=p: np.hypot(X - p.cx, Y - p.cy), (p.cx, p.cy, p.cx, p.cy), rh)
    inside = win.inside(board.outline)                    # the board edge
    for r, masks in ((h + board.edge_clear + M, list(tracks.values())), (hv + board.edge_clear + M, [via])):
        for m in masks:
            m.who.append(("edge",))
            m.a |= ~inside
            m.lab[~inside] = len(m.who) - 1
            for k in range(len(board.outline)):
                a, e = board.outline[k], board.outline[(k + 1) % len(board.outline)]
                m.add(("edge",), lambda X, Y, a=a, e=e: seg_dist(X, Y, *a, *e),
                      (min(a[0], e[0]), min(a[1], e[1]), max(a[0], e[0]), max(a[1], e[1])), r)
    for k in board.keepouts:
        for l in k["layers"]:
            what = ("keepout", k["name"], l)
            if k["tracks"] and l in tracks:
                tracks[l].poly(what, k["poly"], h + M)
            if k["vias"]:
                via.poly(what, k["poly"], hv + M)
    for z in board.solid:                                 # a non-plane pour is solid for every other net
        if z["net"] != net:
            for l in z["layers"]:
                if l in tracks:
                    tracks[l].poly(("pour", z["net"], l), z["poly"], h + 0.3 + M)
                if not board.pour_vias:
                    via.poly(("pour", z["net"], l), z["poly"], hv + 0.3 + M)
    return tracks, via, pen


# ------------------------------------------------------------------- search
def comp_nodes(board, win, comp, layers):
    """{layer: raster of the nodes on the component's copper}, strictly inside it (a track end on an edge
    is not a connection). A pad no node falls well inside gets the nodes within 0.7 grid of it (the emitted
    track then starts with a short connector from the pad centre)."""
    nodes = {l: np.zeros((win.H, win.W), dtype=bool) for l in layers}
    tol = 0.7 * win.g
    for i in comp["pads"]:
        p = board.pads[i]
        rng = win.box(p.cx - p.hw - tol, p.cy - p.hh - tol, p.cx + p.hw + tol, p.cy + p.hh + tol)
        if rng is None:
            continue
        i0, i1, j0, j1 = rng
        sd = p.sd(*win.grid(*rng))
        hit = sd <= -0.03
        if not hit.any():
            hit = sd <= -0.005
        if not hit.any():
            hit = sd <= tol
        for l in p.layers & set(layers):
            nodes[l][j0:j1, i0:i1] |= hit
    for i in comp["segs"]:
        n, l, ax, ay, bx, by, w, _ = board.segs[i]
        rng = win.box(min(ax, bx) - w, min(ay, by) - w, max(ax, bx) + w, max(ay, by) + w)
        if l in nodes and rng:
            i0, i1, j0, j1 = rng
            nodes[l][j0:j1, i0:i1] |= seg_dist(*win.grid(*rng), ax, ay, bx, by) <= max(w / 2 - 0.015, 0.03)
    for i in comp["vias"]:
        n, x, y, dm, dr, _ = board.vias[i]
        rng = win.box(x - dm / 2, y - dm / 2, x + dm / 2, y + dm / 2)
        if rng:
            i0, i1, j0, j1 = rng
            hit = np.hypot(*(a - b for a, b in zip(win.grid(*rng), (x, y)))) <= dm / 2 - 0.02
            for l in layers:
                nodes[l][j0:j1, i0:i1] |= hit
    return nodes


def plane_goal(board, win, net, comp):
    """Nodes where a via reaches the component's plane pour (a same-net plane zone the component lies in)."""
    goal = np.zeros((win.H, win.W), dtype=bool)
    for zi, layer in comp["zones"]:
        if layer not in board.route_layers:
            goal |= win.poly_raster(board.zones[zi]["poly"])
    return goal


BEND = (0, 3, 8, 14, 14)          # extra cost of a turn of 0, 45, 90, 135, 180 degrees (units of 0.005 mm)


def _prep(win, blocked, via_ok, src, dst):
    """Flat byte arrays for the search: node states (0 free, 1 blocked, walls separately), the sources
    and targets made free (their own copper)."""
    W, H, S, L = win.W, win.H, win.S, len(blocked)
    wall = np.zeros((H, W), dtype=bool)
    wall[0, :] = wall[-1, :] = wall[:, 0] = wall[:, -1] = True
    blk = bytearray()
    for l in range(L):
        blk += (blocked[l] & ~wall).astype(np.uint8).tobytes()
    starts = []
    for l in range(L):
        for j, i in zip(*np.nonzero(src[l] & ~wall)):
            k = l * S + int(j) * W + int(i)
            blk[k] = 0
            starts.append(k)
        for j, i in zip(*np.nonzero(dst[l] & ~wall)):
            blk[l * S + int(j) * W + int(i)] = 0
    return blk, wall.astype(np.uint8).tobytes(), bytearray((via_ok & ~wall).astype(np.uint8).tobytes()), starts


def escapes(win, blocked, via_ok, src, reach=3.0, cap=60000):
    """Can the copper `src` get `reach` mm away from itself (through free nodes and vias)? A pad walled in
    by other copper cannot: no route to it exists, however long the search."""
    W, S, L = win.W, win.S, len(blocked)
    blk, walls, vok, starts = _prep(win, blocked, via_ok, src, [np.zeros_like(src[0])] * L)
    if not starts:
        return False
    cells = int(reach / win.g)
    xs = [k % S % W for k in starts]
    ys = [k % S // W for k in starts]
    x0, x1 = max(min(xs) - cells, 3), min(max(xs) + cells, win.W - 4)
    y0, y1 = max(min(ys) - cells, 3), min(max(ys) + cells, win.H - 4)
    seen = set(starts)
    todo = collections.deque(starts)
    offs = (1, -1, W, -W, W + 1, W - 1, -W + 1, -W - 1)
    while todo and len(seen) < cap:
        k = todo.popleft()
        lay, r = divmod(k, S)
        x, y = r % W, r // W
        if x <= x0 or x >= x1 or y <= y0 or y >= y1:
            return True
        for d in offs:
            n = k + d
            if n not in seen and not blk[n] and not walls[n % S]:
                seen.add(n)
                todo.append(n)
        if vok[r] and not walls[r]:
            for l2 in range(L):
                n = l2 * S + r
                if n not in seen and not blk[n]:
                    seen.add(n)
                    todo.append(n)
    return len(seen) >= cap


def reachable(win, blocked, via_ok, src, dst, goal):
    """Direction-free flood fill: can the source copper reach the target copper (or a via to the plane) at all?"""
    W, S, L = win.W, win.S, len(blocked)
    blk, walls, vok, starts = _prep(win, blocked, via_ok, src, dst)
    tg = bytearray().join(d.astype(np.uint8).tobytes() for d in dst)
    gl = (goal & via_ok).ravel().tolist()
    seen = bytearray(len(blk))
    todo = collections.deque(starts)
    for k in starts:
        seen[k] = 1
    offs = (1, -1, W, -W, W + 1, W - 1, -W + 1, -W - 1)
    while todo:
        k = todo.popleft()
        r = k % S
        if tg[k] or gl[r]:
            return True
        for d in offs:
            n = k + d
            if not seen[n] and not blk[n] and not walls[n % S]:
                seen[n] = 1
                todo.append(n)
        if vok[r]:
            for l2 in range(L):
                n = l2 * S + r
                if not seen[n] and not blk[n]:
                    seen[n] = 1
                    todo.append(n)
    return False


def search(win, blocked, via_ok, pen, src, dst, goal, relaxed=False, limit=EXPAND_LIMIT, bends=True):
    """Weighted octilinear A* (with a turn cost, so paths run straight) over the layers of `blocked` (a bool
    raster per layer), with a through via at any `via_ok` node. `goal`: a via at these nodes finishes the
    connection (the plane pour). relaxed: a blocked node may be crossed at a heavy cost (to find the cheapest
    blockers). Returns (path [(layer, i, j)], via_at_end, None) or (None, False, reason)."""
    W, H, S, L = win.W, win.H, win.S, len(blocked)
    blk, walls, vok, starts = _prep(win, blocked, via_ok, src, dst)
    pn = bytearray().join(p.tobytes() for p in pen)
    gl = (goal & via_ok).ravel().tolist()
    tg = bytearray().join(d.astype(np.uint8).tobytes() for d in dst)
    if not starts:
        return None, False, "no start node on the connection's own copper (pad enclosed by other copper)"
    tj, ti = np.nonzero(np.logical_or.reduce(dst) | (goal & via_ok))
    if len(ti) == 0:
        return None, False, "no target node on the connection's own copper (pad enclosed by other copper)"
    tx0, tx1, ty0, ty1 = int(ti.min()), int(ti.max()), int(tj.min()), int(tj.max())
    BLOCK = 3000 if relaxed else 0
    offs = (1, -W + 1, -W, -W - 1, -1, W - 1, W, W + 1)           # E NE N NW W SW S SE
    costs = (10, 14, 10, 14, 10, 14, 10, 14)
    import heapq
    g, parent, heap = {}, {}, []
    wt = 1.2

    def hfun(k):
        r = k % S
        x, y = r % W, r // W
        dx = tx0 - x if x < tx0 else x - tx1 if x > tx1 else 0
        dy = ty0 - y if y < ty0 else y - ty1 if y > ty1 else 0
        return wt * (10 * max(dx, dy) + 4 * min(dx, dy))
    for k in starts:
        st = k * 9 + 8
        g[st], parent[st] = 0, None
        heapq.heappush(heap, (hfun(k), 0, st))
    expanded = 0
    while heap:
        f, gc, st = heapq.heappop(heap)
        if gc > g.get(st, 1 << 60):
            continue
        if st == -1 or tg[st // 9]:
            path, s2 = [], st
            while s2 is not None:
                if s2 >= 0:
                    k2 = s2 // 9
                    path.append((k2 // S, (k2 % S) % W, (k2 % S) // W))
                s2 = parent[s2]
            return path[::-1], st == -1, None
        expanded += 1
        if expanded > limit:
            return None, False, "search limit (%d expansions)" % limit
        k, pd = divmod(st, 9)
        lay, r = divmod(k, S)
        for di in range(8):
            n = k + offs[di]
            b = blk[n]
            if walls[n % S] or (b and not BLOCK):
                continue
            ng = gc + costs[di] + pn[n] + (BLOCK if b else 0)
            if pd < 8 and bends and not relaxed:
                ng += BEND[min((di - pd) % 8, (pd - di) % 8)]
            ns = n * 9 + (di if bends and not relaxed else 8)
            if ng < g.get(ns, 1 << 60):
                g[ns], parent[ns] = ng, st
                heapq.heappush(heap, (ng + hfun(n), ng, ns))
        if walls[r]:
            continue
        if vok[r] or BLOCK:
            vcost = VIA_COST + (0 if vok[r] else BLOCK)
            if gl[r]:
                ng = gc + vcost
                if ng < g.get(-1, 1 << 60):
                    g[-1], parent[-1] = ng, st
                    heapq.heappush(heap, (ng, ng, -1))
            for l2 in range(L):
                n = l2 * S + r
                if l2 == lay or (blk[n] and not BLOCK):
                    continue
                ng = gc + vcost + pn[n] + (BLOCK if blk[n] else 0)
                ns = n * 9 + 8
                if ng < g.get(ns, 1 << 60):
                    g[ns], parent[ns] = ng, st
                    heapq.heappush(heap, (ng + hfun(n), ng, ns))
    return None, False, "no path (search exhausted after %d expansions)" % expanded


# ------------------------------------------------------------ one connection
def _free_run(free, a, b):
    """Are all grid nodes on the straight (orthogonal or 45 degree) run a -> b free? a, b: (i, j)."""
    (i0, j0), (i1, j1) = a, b
    n = max(abs(i1 - i0), abs(j1 - j0))
    if n == 0:
        return True
    ii = i0 + (i1 - i0) // n * np.arange(n + 1)
    jj = j0 + (j1 - j0) // n * np.arange(n + 1)
    return bool(free[jj, ii].all())


def smooth(path, free):
    """Shortcut a grid path: replace the stretch between two nodes of one layer by at most two straight
    octilinear runs when every node on them is free (the staircases a weighted search leaves). `free`: one
    raster per layer, True where the route may go."""
    n = len(path)
    out = [path[0]]
    i = 0
    while i < n - 1:
        end = i
        while end + 1 < n and path[end + 1][0] == path[i][0]:
            end += 1
        step, add = i + 1, [path[i + 1]]
        for j in range(min(end, i + 200), i + 1, -1):
            (l, x0, y0), (_, x1, y1) = path[i], path[j]
            dx, dy = x1 - x0, y1 - y0
            m = min(abs(dx), abs(dy))
            sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
            if dx == 0 or dy == 0 or abs(dx) == abs(dy):
                corners = [None]
            else:
                corners = [(x0 + sx * m, y0 + sy * m), (x1 - sx * m, y1 - sy * m)]
            for corner in corners:
                if corner is None:
                    ok = _free_run(free[l], (x0, y0), (x1, y1))
                else:
                    ok = _free_run(free[l], (x0, y0), corner) and _free_run(free[l], corner, (x1, y1))
                if ok:
                    step, add = j, ([] if corner is None else [(l, corner[0], corner[1])]) + [path[j]]
                    break
            if step == j:
                break
        out += add
        i = step
    return out


def shapes(path, via_at_end, win, layers):
    """Path nodes to ([(layer, x0, y0, x1, y1)], [(x, y)]): straight runs and layer changes."""
    segs, vias = [], []
    run = [path[0]]
    for a, b in zip(path, path[1:]):
        if b[0] != a[0]:
            vias.append((float(win.xs[a[1]]), float(win.ys[a[2]])))
            _flush(run, segs, win, layers)
            run = [b]
        else:
            if len(run) >= 2 and (run[-1][1] - run[-2][1], run[-1][2] - run[-2][2]) != (b[1] - a[1], b[2] - a[2]):
                _flush(run, segs, win, layers)
                run = [a]
            run.append(b)
    _flush(run, segs, win, layers)
    if via_at_end:
        vias.append((float(win.xs[path[-1][1]]), float(win.ys[path[-1][2]])))
    return segs, vias


def _flush(run, segs, win, layers):
    if len(run) >= 2:
        a, b = run[0], run[-1]
        segs.append((layers[a[0]], float(win.xs[a[1]]), float(win.ys[a[2]]), float(win.xs[b[1]]), float(win.ys[b[2]])))


def _own_dist(board, comp, layer, x, y):
    """Distance from a point to the component's copper on `layer` and the nearest pad centre."""
    best, centre = 1e9, None
    P, Q = np.array(x), np.array(y)
    for i in comp["pads"]:
        p = board.pads[i]
        if layer in p.layers:
            d = float(p.dist(P, Q))
            if d < best:
                best, centre = d, (p.cx, p.cy)
    for i in comp["segs"]:
        s = board.segs[i]
        if s[1] == layer:
            best = min(best, float(seg_dist(P, Q, *s[2:6])) - s[6] / 2)
    for i in comp["vias"]:
        v = board.vias[i]
        best = min(best, math.hypot(x - v[1], y - v[2]) - v[3] / 2)
    return max(best, 0), centre


def check_exact(board, net, width, clr, segs, vias):
    """Re-check emitted pieces on a fine grid at the nominal clearance (margin 0.008 mm: the grid's own).
    Returns [] or the reasons."""
    bad = []
    for layer, ax, ay, bx, by in segs:
        win = Window((min(ax, bx) - 1.5, min(ay, by) - 1.5, max(ax, bx) + 1.5, max(ay, by) + 1.5), g=0.01)
        tracks, via, _ = build(board, win, net, width, clr, margin=0.008)
        n = max(2, int(math.hypot(bx - ax, by - ay) / 0.01) + 1)
        for t in np.linspace(0, 1, n):
            i, j = win.node(ax + (bx - ax) * t, ay + (by - ay) * t)
            if tracks[layer].a[j, i]:
                bad.append(("track", layer, round(ax, 3), round(ay, 3), round(bx, 3), round(by, 3),
                            tracks[layer].who[tracks[layer].lab[j, i]]))
                break
    for x, y in vias:
        win = Window((x - 1.5, y - 1.5, x + 1.5, y + 1.5), g=0.01)
        tracks, via, _ = build(board, win, net, width, clr, margin=0.008)
        i, j = win.node(x, y)
        if via.a[j, i]:
            bad.append(("via", round(x, 3), round(y, 3), via.who[via.lab[j, i]]))
    return bad


def _blockers(path, via_at_end, win, tracks, via, layers):
    """What a relaxed path crosses: unique blockers in path order."""
    out = []
    for lay, i, j in path:
        for m in (tracks[layers[lay]],):
            if m.a[j, i] and m.who[m.lab[j, i]] not in out:
                out.append(m.who[m.lab[j, i]])
    for a, b in zip(path, path[1:]):
        if a[0] != b[0] and via.a[a[2], a[1]] and via.who[via.lab[a[2], a[1]]] not in out:
            out.append(via.who[via.lab[a[2], a[1]]])
    return out


def _propose(blockers):
    """A minimal fix for each thing in the way of a connection."""
    fixes = []
    for b in blockers:
        if b[0] == "track":
            fixes.append("reroute or shorten the %s track on %s %s-%s (or hand-route it round the connection)" % (b[1], b[2], b[3], b[4]))
        elif b[0] == "via":
            fixes.append("move the %s via at %s (it blocks copper on every layer)" % (b[1], b[3]))
        elif b[0] == "pad":
            fixes.append("pad %s (%s) closes the only corridor found: only moving that part (or its neighbours) opens it" % (b[2], b[1] or "no net"))
        elif b[0] == "keepout":
            fixes.append("rule area '%s' forbids copper on %s here: shrink it if the rule allows" % (b[1], b[2]))
        elif b[0] == "pour":
            fixes.append("the %s pour on %s is solid here" % (b[1], b[2]))
        else:
            fixes.append("board edge / outline: no room (0.3 mm copper to edge)")
    return fixes or ["no single obstruction: the connection is enclosed (see the endpoints' notes)"]


def route_connection(board, net, ca, cb, log=print, margins=(3.0, 8.0, 20.0)):
    """Route component `ca` to `cb` of `net`. Returns a result dict; on success the copper has been added to
    the model (and board.new)."""
    name, width, clr = board.netclass(net)
    layers = board.route_layers
    if width < board.min_track - 1e-9 or clr < board.min_clear - 1e-9:
        raise ValueError("%s: class %s (%.3f wide, %.3f clearance) is under the board's manufacturer minimums (%.3f, %.3f)"
                         % (net, name, width, clr, board.min_track, board.min_clear))
    res = {"net": net, "class": name, "width": width, "clearance": clr, "si_critical": any(rx.match(net) for rx in board.si)}
    pa = [board.pads[i] for i in ca["pads"]]
    pb = [board.pads[i] for i in cb["pads"]]
    a, b = min(((p, q) for p in pa for q in pb), key=lambda pq: math.hypot(pq[0].cx - pq[1].cx, pq[0].cy - pq[1].cy))
    res["from"], res["to"] = "%s.%s" % (a.ref, a.num), "%s.%s" % (b.ref, b.num)
    res["distance_mm"] = round(math.hypot(a.cx - b.cx, a.cy - b.cy), 2)
    lo = (min(a.cx, b.cx), min(a.cy, b.cy))
    hi = (max(a.cx, b.cx), max(a.cy, b.cy))
    ol = board.outline
    bb = (min(p[0] for p in ol), min(p[1] for p in ol), max(p[0] for p in ol), max(p[1] for p in ol))
    last = None
    for m in margins:
        win = Window((max(lo[0] - m, bb[0]), max(lo[1] - m, bb[1]), min(hi[0] + m, bb[2]), min(hi[1] + m, bb[3])))
        tracks, via, pen = build(board, win, net, width, clr)
        blocked = [tracks[l].a for l in layers]
        # a component is the source; the other one (with a plane pour, if either has one) the target
        s, d = (ca, cb) if not ca["zones"] or cb["zones"] else (cb, ca)
        src, dst = comp_nodes(board, win, s, layers), comp_nodes(board, win, d, layers)
        for nodes in (src, dst):                          # own copper is free of other copper's clearance, never of a pour or rule area
            for l in layers:
                kinds = np.array([w[0] if w else "" for w in tracks[l].who])[tracks[l].lab]
                nodes[l] &= ~np.isin(kinds, ("pour", "keepout", "edge"))
        goal = plane_goal(board, win, net, d)
        t0 = time.time()
        vok = ~via.a
        walled = [name for name, nodes in (("start", src), ("target", dst)) if not escapes(
            win, blocked, vok, [nodes[l] for l in layers], reach=min(3.0, m - 0.5))]
        if walled:
            last = (win, tracks, via, pen, src, dst, goal, blocked, s, d)
            res["why"] = "%s pad walled in: no copper-free way out within 3 mm on any layer" % " and ".join(walled)
            path = None
            break
        if not reachable(win, blocked, vok, [src[l] for l in layers], [dst[l] for l in layers], goal):
            path, at_end, why = None, False, "no path: the two pads are cut off from each other by other copper" + \
                (" (window %.0f mm round them)" % m)
        else:
            args = (win, blocked, vok, [pen[l] for l in layers], [src[l] for l in layers], [dst[l] for l in layers], goal)
            path, at_end, why = search(*args, limit=EXPAND_LIMIT // 2)
            if not path and why.startswith("search limit"):       # a long detour: without the turn cost the state space is 9x smaller
                path, at_end, why = search(*args, bends=False, limit=8_000_000)
        res["search_s"] = round(time.time() - t0, 1)
        last = (win, tracks, via, pen, src, dst, goal, blocked, s, d)
        if path:
            break
        res["why"] = why
    if not path:
        win, tracks, via, pen, src, dst, goal, blocked, s, d = last
        rpath, rend, rwhy = search(win, blocked, ~via.a, [pen[l] for l in layers], [src[l] for l in layers],
                                   [dst[l] for l in layers], goal, relaxed=True, limit=EXPAND_LIMIT // 3)
        res["status"] = "blocked"
        if rpath:
            blockers = _blockers(rpath, rend, win, tracks, via, layers)
            res["blockers"] = [list(map(str, x)) for x in blockers]
            res["proposed_fix"] = _propose(blockers)
            res["cheapest_path_crossings"] = len(blockers)
        else:
            res["blockers"] = []
            res["proposed_fix"] = ["endpoint enclosed: %s" % rwhy]
        return res
    win, tracks, via, pen, src, dst, goal, blocked, s, d = last
    if len(path) == 1 and not at_end:                     # the two pieces' copper already touches
        d.update({k: d[k] + s[k] for k in d})
        res.update(status="routed", segments=0, vias=0, length_mm=0, note="copper already touches")
        return res
    free = [~blocked[k] | src[layers[k]] | dst[layers[k]] for k in range(len(layers))]
    path = smooth(path, free)
    segs, vias = shapes(path, at_end, win, layers)
    # connectors: a start/end node that lies just outside its pad gets a short stub from the pad centre
    ends = ((path[0], s, True), (path[-1], d, False))
    for (lay, i, j), comp, first in ends:
        x, y = float(win.xs[i]), float(win.ys[j])
        dist, centre = _own_dist(board, comp, layers[lay], x, y)
        if dist > 1e-6 and centre:
            segs.append((layers[lay], centre[0], centre[1], x, y))
    bad = check_exact(board, net, width, clr, segs, vias)
    if bad:
        res.update(status="blocked", why="the grid path failed the exact re-check", blockers=[str(x) for x in bad],
                   proposed_fix=["the path only fits by the grid's margin: hand-route or nudge the obstacle named"])
        return res
    for layer, ax, ay, bx, by in segs:
        board.segs.append((net, layer, ax, ay, bx, by, width, True))
        board.new.append(["track", net, layer] + [round(v * 1e6) for v in (ax, ay, bx, by, width)])
        d["segs"].append(len(board.segs) - 1)
    for x, y in vias:
        board.vias.append((net, x, y, VIA_D, VIA_DRILL, True))
        board.new.append(["via", net] + [round(v * 1e6) for v in (x, y, VIA_D, VIA_DRILL)])
        d["vias"].append(len(board.vias) - 1)
    res.update(status="routed", segments=len(segs), vias=len(vias),
               length_mm=round(sum(math.hypot(x1 - x0, y1 - y0) for _, x0, y0, x1, y1 in segs), 2))
    return res


def _log(*a):
    print(*a, flush=True)


def route_all(board, only=None, max_connections=None, log=_log):
    """Route every leftover connection; returns the list of result dicts."""
    results = []
    todo = leftovers(board)
    if only:
        todo = [(n, c) for n, c in todo if n in only]
    log("%d nets with unrouted connections (%d connections)" % (len(todo), sum(len(c) - 1 for _, c in todo)))
    count = 0
    for net, comps in todo:
        comps = list(comps)
        tried = set()
        while len(comps) > 1:
            key = lambda i, j: (tuple(comps[i]["pads"]), tuple(comps[j]["pads"]))
            pairs = sorted(((comp_center_dist(board, comps[i], comps[j]), i, j) for i in range(len(comps))
                            for j in range(i + 1, len(comps)) if key(i, j) not in tried))
            if not pairs or (max_connections and count >= max_connections):
                break
            _, i, j = pairs[0]
            res = route_connection(board, net, comps[i], comps[j])
            count += 1
            results.append(res)
            log("  %-28s %s -> %s %5.1f mm: %s%s" % (net, res["from"], res["to"], res["distance_mm"], res["status"],
                                                     "" if res["status"] == "routed" else " (%s)" % (res.get("why") or "; ".join(res["proposed_fix"][:1]))))
            if res["status"] == "routed":
                a, b = comps[i], comps[j]
                merged = {k: a[k] + b[k] for k in a}
                comps = [c for k, c in enumerate(comps) if k not in (i, j)] + [merged]
            else:
                tried.add(key(i, j))
    return results


# ---------------------------------------------------------------- outputs
def write_seed(items, path, source, digest):
    lines = [list(it) for it in items]
    lines.sort(key=json.dumps)
    with open(path, "w") as f:
        f.write(json.dumps({"source": os.path.basename(source), "source_sha256": digest, "items": len(lines),
                            "kind": "main hand-route"}) + "\n")
        for it in lines:
            f.write(json.dumps(it, separators=(",", ":")) + "\n")
    return len(lines)


def apply(board_or_path, seed=SEED_OUT):
    """Add a hand-route seed's items to a pcbnew board (locked). Deterministic; an item whose net is not on the
    board, or that already exists, is skipped. Returns (added, skipped)."""
    import pcbnew
    board = pcbnew.LoadBoard(board_or_path) if isinstance(board_or_path, str) else board_or_path
    with open(seed) as f:
        head = json.loads(f.readline())
        items = [json.loads(line) for line in f if line.strip()]
    if len(items) != head["items"]:
        raise ValueError("hand-route seed truncated: %d of %d items" % (len(items), head["items"]))
    _add(board, items)
    return board, len(items)


def _add(board, items):
    import pcbnew
    nets = board.GetNetsByName()
    ids = {board.GetLayerName(l): l for l in board.GetEnabledLayers().CuStack()}
    tracks = board.Tracks()
    have = set()
    for k in range(len(tracks)):
        t = tracks[k].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            have.add(("via", str(t.GetNetname()), t.GetPosition().x, t.GetPosition().y))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, e = t.GetStart(), t.GetEnd()
            have.add(("track", str(t.GetNetname()), board.GetLayerName(t.GetLayer()), a.x, a.y, e.x, e.y))
    for it in items:
        net = nets[it[1]] if nets.has_key(it[1]) else None
        if net is None:
            raise ValueError("net %s is not on the board" % it[1])
        if it[0] == "via":
            if ("via", it[1], it[2], it[3]) in have:
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(it[2], it[3]))
            v.SetWidth(it[4])
            v.SetDrill(it[5])
            v.SetNet(net)
            v.SetLocked(True)
            board.Add(v)
        else:
            if ("track", it[1], it[2], it[3], it[4], it[5], it[6]) in have:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(it[3], it[4]))
            t.SetEnd(pcbnew.VECTOR2I(it[5], it[6]))
            t.SetWidth(it[7])
            t.SetLayer(ids[it[2]])
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)


def run_drc(pcb, out):
    if not os.path.exists(os.path.splitext(pcb)[0] + ".kicad_pro"):
        raise SystemExit("DRC needs %s next to the board" % (os.path.splitext(pcb)[0] + ".kicad_pro"))
    subprocess.run(["nice", "-n", "19", "kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                    "--refill-zones", "-o", out, pcb], capture_output=True, check=False)
    with open(out) as f:
        return json.load(f)


def _keys(drc, section):
    keys = collections.Counter()
    for v in drc.get(section, []):
        items = tuple(sorted((re.sub(r", length [\d.]+ mm", "", i["description"]), round(i["pos"]["x"], 2),
                              round(i["pos"]["y"], 2)) for i in v["items"]))
        keys[(v["type"], v["severity"], re.sub(r"[\d.]+ ?mm", "#", v["description"]), items)] += 1
    return keys


def _unconnected_nets(drc):
    """Missing connections per net: the ratsnest pairs change as copper is added, the counts per net do not."""
    count = collections.Counter()
    for v in drc.get("unconnected_items", []):
        nets = {m for i in v["items"] for m in re.findall(r"\[([^\]]*)\]", i["description"])}
        count[",".join(sorted(nets))] += 1
    return count


def diff_drc(before, after):
    """{violations: new ones by (type, severity, description, items); unconnected_items: per-net changes}."""
    b, a = _keys(before, "violations"), _keys(after, "violations")
    ub, ua = _unconnected_nets(before), _unconnected_nets(after)
    return {"violations": {"before": sum(b.values()), "after": sum(a.values()),
                           "new": [{"type": k[0], "severity": k[1], "description": k[2], "items": [list(i) for i in k[3]]}
                                   for k in (a - b)],
                           "fixed": sum((b - a).values())},
            "unconnected_items": {"before": sum(ub.values()), "after": sum(ua.values()),
                                  "new": sorted(n for n in ua if ua[n] > ub[n]),
                                  "fixed": sum((ub - ua).values())}}


# ---------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("list", "route", "apply"))
    ap.add_argument("board")
    ap.add_argument("seed", nargs="?", default=SEED_OUT)
    ap.add_argument("--out")
    ap.add_argument("--seed-out", default=SEED_OUT)
    ap.add_argument("--report")
    ap.add_argument("--drc", action="store_true", help="run kicad-cli DRC before and after and diff them")
    ap.add_argument("--baseline", help="a DRC json of the input board (skips the 'before' run)")
    ap.add_argument("--nets", help="comma-separated nets to route (default: every leftover)")
    ap.add_argument("--max-connections", type=int)
    ap.add_argument("--power-width", type=float, default=0.3)
    ap.add_argument("--through-pour", action="store_true",
                    help="let other nets' vias cross the +1V2 island pour (the refill leaves a clearance hole round each; "
                         "the DRC then shows whether the island is still one piece)")
    args = ap.parse_args(argv)
    if args.cmd == "apply":
        board, n = apply(args.board, args.seed)
        import pcbnew
        pcbnew.SaveBoard(args.out or args.board, board)
        print("applied %d hand-route items to %s" % (n, args.out or args.board))
        return 0
    t0 = time.time()
    board = Board(args.board, args.power_width, args.through_pour)
    print("loaded %d pads, %d tracks, %d vias, %d zones in %.1f s" % (len(board.pads), len(board.segs),
                                                                       len(board.vias), len(board.zones), time.time() - t0))
    if args.cmd == "list":
        for net, comps in leftovers(board):
            print("%-30s %d pieces  %s%s" % (net, len(comps), " ".join("%s.%s" % (board.pads[c["pads"][0]].ref, board.pads[c["pads"][0]].num)
                                                                       for c in comps),
                                            "   SI-CRITICAL" if any(rx.match(net) for rx in board.si) else ""))
        return 0
    out = args.out or args.board
    with open(args.board, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if args.drc and not args.baseline:
        before = run_drc(args.board, (args.report or out) + ".before.drc.json")
    elif args.baseline:
        before = json.load(open(args.baseline))
    results = route_all(board, set(args.nets.split(",")) if args.nets else None, args.max_connections)
    _add(board.b, board.new)
    import pcbnew
    pcbnew.SaveBoard(out, board.b)
    if out != args.board:
        for ext in (".kicad_pro", ".kicad_prl"):
            src = os.path.splitext(args.board)[0] + ext
            dst = os.path.splitext(out)[0] + ext
            if os.path.exists(src) and not os.path.exists(dst):
                with open(src, "rb") as f, open(dst, "wb") as g:
                    g.write(f.read())
    report = {"board": args.board, "out": out, "results": results,
              "routed": sum(r["status"] == "routed" for r in results),
              "blocked": sum(r["status"] != "routed" for r in results),
              "new_items": len(board.new), "si_critical_leftovers": sorted({r["net"] for r in results if r["si_critical"]})}
    if board.new:
        report["seed"] = args.seed_out
        write_seed(board.new, args.seed_out, args.board, digest)
    if args.drc:
        after = run_drc(out, (args.report or out) + ".after.drc.json")
        report["drc"] = diff_drc(before, after)
    with open(args.report or out + ".handroute.json", "w") as f:
        json.dump(report, f, indent=1)
    print("routed %d, blocked %d, %d new items, %.0f s" % (report["routed"], report["blocked"], len(board.new), time.time() - t0))
    if report["si_critical_leftovers"]:
        print("SI-critical nets among the leftovers:", ", ".join(report["si_critical_leftovers"]))
    if "drc" in report:
        for sec, v in report["drc"].items():
            print("DRC %s: %d before, %d after, %d new, %d fixed" % (sec, v["before"], v["after"], len(v["new"]), v["fixed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
