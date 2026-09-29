"""MB-051 routing prep: a fixed fan-out via and stub on every bare SMD pad.

Freerouting's own fan-out stage took 6.5-11 minutes a pass on the seeded main
board and left the same ~68 pins unrouted pass after pass (2026-09-29, David:
place them ourselves). Every connected SMD pad that the route seed and the
board's own locked copper leave with no track or via on it gets a short locked
stub on its own layer to a locked through via, at the nearest legal spot: a
via that keeps its class clearance (+ MARGIN, Freerouting's octagon and hole
rules, as kicadgen.ground_fanout) from every other net's copper on any layer,
no via-in-pad (it keeps a via's clearance off its own net's pads too), the
hole spacing JLC needs, and out of every no-via rule area; a stub that keeps
its class clearance from other nets' copper on its layer.

`bare_pads` is the audit: main.py raises if any connected SMD pad is still
bare and not in EXEMPT, so the pass cannot silently be dropped.

    fan_out_bare_pads(board, clearance) -> ([placed], [unplaced])
    bare_pads(board)                    -> [(ref, pad, net)]
"""

import math

import numpy as np
import pcbnew

VIA, DRILL, STUB_MAX = 0.6, 0.3, 0.3
MARGIN = 0.05                   # kicadgen FANOUT_MARGIN: the router's octagon round a via
# strictest first: (margin on other nets' copper, via centre to own pad edge beyond VIA / 2).
# The first is kicadgen.ground_fanout's proven convention; the last only keeps the via out of its pad.
LADDER = [(MARGIN, 0.2 + MARGIN), (0.0, 0.2), (0.0, 0.1)]
HOLE_SPACING = 0.85             # via centre to via centre: JLC's 0.5 mm hole to hole + 0.25 (ground_fanout)
EDGE = 0.8                      # keep vias this far inside the board's bounding box
NPTH_KEEPOUT = 0.3              # a via's extra distance from an unplated hole
RINGS = [0.9 + 0.1 * k for k in range(28)]              # pad centre to via centre, mm
FAN = [0] + [s * d for d in range(10, 181, 10) for s in (1, -1)]

# (ref, pad number): why it may stay bare. Empty: every connected SMD pad has a fixed via or track.
EXEMPT = {
    ("U19", "2"): "SLOT1_RST_n: 0.65 mm-pitch TSSOP row under the seed's inner-layer diagonal bundle; once the row's "
                  "other vias are down no legal via spot is left within 3.6 mm (2026-09-29). The hand-router (main_handroute.py) routes it.",
    ("U2", "9"): "EFUSE_ILM: 0.45 mm-pitch QFN pad between the GND via lane and the input corner's locked copper, "
                 "no legal spot within 3.6 mm (2026-09-29); it goes to R3 at the Fine class. The hand-router routes it.",
    ("U7", "39"): "SPI_nCS2_SRC: TQ144 pad with every fan-out spot blocked by other nets' pads and tracks of the "
                  "DeepPCB copper in the seed (2026-09-29). The hand-router (main_handroute.py) routes it.",
    ("U7", "91"): "MEM_D4: TQ144 pad walled in by the seed's /MEM_A16 In3 diagonal (2026-09-29); the hand-router "
                  "(main_handroute.py) routes it.",
}


def _mm(v):
    return pcbnew.ToMM(v)


def _edge_part(fp):
    return str(fp.GetFPID().GetLibNickname()).startswith("Connector_PCBEdge")


def _connected_smd_pads(board):
    """[(footprint, pad)] of every SMD pad on a net that has another copper pad."""
    count = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() and p.IsOnCopperLayer():
                count[p.GetNetname()] = count.get(p.GetNetname(), 0) + 1
    return [(fp, p) for fp in board.GetFootprints() if not _edge_part(fp) for p in fp.Pads()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.GetNetname()
            and not p.GetNetname().startswith("unconnected-") and count[p.GetNetname()] > 1]


def _copper(board):
    """(track endpoints [(x, y, layer, net)], vias [(x, y, net)]), nm."""
    ends, vias = [], []
    tracks = board.Tracks()
    for i in range(len(tracks)):
        t = tracks[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            vias.append((t.GetPosition().x, t.GetPosition().y, t.GetNetname()))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            for e in (t.GetStart(), t.GetEnd()):
                ends.append((e.x, e.y, t.GetLayer(), t.GetNetname()))
    return ends, vias


def bare_pads(board, include_exempt=False):
    """Connected SMD pads with no same-net via on them and no same-net track
    that goes anywhere (a stub whose far end meets nothing is bare, as is a
    pad with nothing on it), and no same-net pad overlapping them, less
    EXEMPT unless asked: [(ref, pad number, net)]."""
    tracks, vias = [], []
    ts = board.Tracks()
    for i in range(len(ts)):
        t = ts[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            vias.append((t.GetPosition().x, t.GetPosition().y, t.GetNetname()))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            tracks.append((t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer(), t.GetNetname(), t.GetWidth()))
    by_net = {}                                # net -> [(track index, x0, y0, x1, y1, half width)]
    for k, (a, b, c, d, _, net, w) in enumerate(tracks):
        by_net.setdefault(net, []).append((k, a, b, c, d, w / 2))
    via_at = {(net, x, y) for x, y, net in vias}
    # every copper point that could be on a pad: (x, y, track index or -1 for a via, far end x, far end y)
    rows = [(t[0], t[1], k, t[2], t[3]) for k, t in enumerate(tracks)] + \
           [(t[2], t[3], k, t[0], t[1]) for k, t in enumerate(tracks)] + [(v[0], v[1], -1 - n, v[0], v[1]) for n, v in enumerate(vias)]
    pts = np.array([r[:2] for r in rows], float).reshape(-1, 2)
    same_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() and p.IsOnCopperLayer():
                same_net.setdefault(p.GetNetname(), []).append((fp.GetReference(), p))

    def continues(net, ti, x, y):
        """Another same-net track (end or body), via or pad is at this point."""
        for k, a, b, c, d, r in by_net.get(net, ()):
            if k != ti and min(a, c) - r - 1000 <= x <= max(a, c) + r + 1000 and \
                    min(b, d) - r - 1000 <= y <= max(b, d) + r + 1000:
                dx, dy = c - a, d - b
                u = max(0.0, min(1.0, ((x - a) * dx + (y - b) * dy) / (dx * dx + dy * dy or 1.0)))
                if math.hypot(x - a - u * dx, y - b - u * dy) <= r + 1000:
                    return True
        return False

    def on_pad(net, x, y, exclude):
        return any(p.HitTest(pcbnew.VECTOR2I(x, y), 1000) for r, p in same_net[net] if (r, p.GetNumber()) != exclude)

    out = []
    for fp, p in _connected_smd_pads(board):
        ref, num, net = fp.GetReference(), p.GetNumber(), p.GetNetname()
        if (ref, num) in EXEMPT and not include_exempt:
            continue
        bb = p.GetBoundingBox()
        bb.Inflate(pcbnew.FromMM(0.5))
        near = np.nonzero((pts[:, 0] >= bb.GetLeft()) & (pts[:, 0] <= bb.GetRight()) &
                          (pts[:, 1] >= bb.GetTop()) & (pts[:, 1] <= bb.GetBottom()))[0] if len(pts) else []
        touched = False
        for k in near:
            x, y, ti, fx, fy = rows[k]
            if not p.HitTest(pcbnew.VECTOR2I(int(x), int(y)), 1000):
                continue
            if ti < 0:
                touched = touched or vias[-1 - ti][2] == net
            else:
                layer, tnet = tracks[ti][4], tracks[ti][5]
                # a track on the pad's layer whose far end meets another track, a via or a pad
                if tnet == net and p.IsOnLayer(layer) and ((net, fx, fy) in via_at or continues(net, ti, fx, fy)
                                                           or on_pad(net, int(fx), int(fy), (ref, num))):
                    touched = True
        if not touched:
            own = p.GetBoundingBox()
            touched = any(own.Intersects(q.GetBoundingBox()) for r, q in same_net[net]
                          if (r, q.GetNumber()) != (ref, num))
        if not touched:
            out.append((ref, num, net))
    return sorted(out)


def _seg_dist(px, py, s):
    """Distance from points (n,) to segments s (m, 4) -> (m, n)."""
    x0, y0, x1, y1 = (s[:, k][:, None] for k in range(4))
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy + 1e-12), 0, 1)
    return np.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _rect_dist(px, py, r):
    """Distance from points (n,) to rectangles r (m, 4) -> (m, n)."""
    dx = np.maximum(np.maximum(r[:, 0][:, None] - px, px - r[:, 2][:, None]), 0)
    dy = np.maximum(np.maximum(r[:, 1][:, None] - py, py - r[:, 3][:, None]), 0)
    return np.hypot(dx, dy)


def fan_out_bare_pads(board, clearance, track_width=lambda net: STUB_MAX):
    """Place a locked stub + via on every bare pad. `clearance(net)` is the
    net class's clearance (mm), `track_width(net)` the stub's width. Returns ([(ref, pad, net, via x, via y, ladder level)],
    [(ref, pad, net, main reasons)] for the pads no spot was found for)."""
    layers = board.GetEnabledLayers().CuStack()
    pads = []          # x0, y0, x1, y1, net, on-layer set, keepout extra
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not (p.IsOnCopperLayer() or p.GetDrillSize().x > 0):
                continue                                # paste-only apertures: no copper, no hole
            bb = p.GetBoundingBox()
            pads.append((_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()),
                         p.GetNetname(), frozenset(l for l in layers if p.IsOnLayer(l)),
                         NPTH_KEEPOUT if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else 0.0))
    segs, vias = [], []    # (x0, y0, x1, y1, width, net, layer) ; (x, y, radius, net)
    tracks = board.Tracks()
    for i in range(len(tracks)):
        t = tracks[i].Cast()
        if t.Type() == pcbnew.PCB_VIA_T:
            vias.append((_mm(t.GetPosition().x), _mm(t.GetPosition().y), _mm(t.GetWidth(pcbnew.F_Cu)) / 2,
                         t.GetNetname()))
        elif t.Type() == pcbnew.PCB_TRACE_T:
            a, b = t.GetStart(), t.GetEnd()
            segs.append((_mm(a.x), _mm(a.y), _mm(b.x), _mm(b.y), _mm(t.GetWidth()), t.GetNetname(), t.GetLayer()))
    no_via = []
    zones = board.Zones()
    for z in [zones[i] for i in range(len(zones))]:
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            bb = z.GetBoundingBox()
            no_via.append((_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())))
    edge = board.GetBoardEdgesBoundingBox()
    ex0, ey0 = _mm(edge.GetLeft()) + EDGE, _mm(edge.GetTop()) + EDGE
    ex1, ey1 = _mm(edge.GetRight()) - EDGE, _mm(edge.GetBottom()) - EDGE

    todo = {(r, n) for r, n, _ in bare_pads(board, include_exempt=True)}
    reach = RINGS[-1] + 1.0
    order = [(fp, p) for fp, p in sorted(_connected_smd_pads(board),
                                         key=lambda fp_p: (fp_p[0].GetReference(), fp_p[1].GetNumber()))
             if (fp.GetReference(), p.GetNumber()) in todo]
    n_segs, n_vias = len(segs), len(vias)

    def rings(far_first):
        """Pad centre to via centre distances, nearest first; far_first tries the long stubs first
        (a row of pads at 0.65 mm pitch needs its vias staggered: short and long stubs alternate)."""
        return [r for r in RINGS if r >= 1.9] + [r for r in RINGS if r < 1.9] if far_first else RINGS

    def place(fp, p, far_first):
        """(via x, y, ladder level, stub width, layer) or the reasons it has no spot."""
        ref, num, net = fp.GetReference(), p.GetNumber(), p.GetNetname()
        cx, cy = _mm(p.GetPosition().x), _mm(p.GetPosition().y)
        pb = p.GetBoundingBox()
        own = (_mm(pb.GetLeft()), _mm(pb.GetTop()), _mm(pb.GetRight()), _mm(pb.GetBottom()))
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        # a custom-shape pad (U2's corner pads) has a 0.005 mm anchor for its size: its box is what a stub can be
        size = (pb.GetWidth(), pb.GetHeight()) if p.GetShape() == pcbnew.PAD_SHAPE_CUSTOM else (p.GetSize().x, p.GetSize().y)
        width = min(track_width(net), _mm(min(size)))
        fx, fy = _mm(fp.GetPosition().x), _mm(fp.GetPosition().y)
        base = math.atan2(cy - fy, cx - fx) if math.hypot(cx - fx, cy - fy) > 0.1 else -math.pi / 2
        if len(fp.Pads()) > 8:
            base += math.pi                       # a big part: in under it, as ground_fanout
        lane = (math.pi / 2 if p.GetSize().y > p.GetSize().x else 0.0) + p.GetOrientation().AsRadians()
        if math.cos(lane - base) < 0:
            lane += math.pi
        # the obstacles near this pad
        P = [q for q in pads if q[2] >= cx - reach and q[0] <= cx + reach and q[3] >= cy - reach and q[1] <= cy + reach]
        # the box of a track is its centre line's plus half its width: a 7.5 mm inner-layer trunk
        # reaches 3.75 mm past its line (the /+5V trunk beside R4's via)
        S = [s for s in segs if max(s[0], s[2]) + s[4] / 2 >= cx - reach and min(s[0], s[2]) - s[4] / 2 <= cx + reach and
             max(s[1], s[3]) + s[4] / 2 >= cy - reach and min(s[1], s[3]) - s[4] / 2 <= cy + reach]
        V = [v for v in vias if abs(v[0] - cx) <= reach and abs(v[1] - cy) <= reach]
        c_own = clearance(net)
        other_p = [q for q in P if q[4] != net]
        rects = np.array([q[:4] for q in other_p], float).reshape(-1, 4)
        # a via holds its own class' clearance against each other pad's class
        need_p = np.array([max(c_own, clearance(q[4])) + q[6] for q in other_p], float)
        own_pads = np.array([q[:4] for q in P if q[4] == net], float).reshape(-1, 4)
        other_s = [s for s in S if s[5] != net]
        sa = np.array([s[:4] for s in other_s], float).reshape(-1, 4)
        sw = np.array([s[4] for s in other_s], float)
        s_need = np.array([max(c_own, clearance(s[5])) for s in other_s], float)
        s_layer = [s[6] for s in other_s]
        va = np.array([v[:2] for v in V], float).reshape(-1, 2)
        vr = np.array([v[2] for v in V], float)
        v_same = np.array([v[3] == net for v in V], bool)
        v_need = np.array([max(c_own, clearance(v[3])) for v in V], float)
        pad_layers = [q[5] for q in other_p]

        def via_bad(vx, vy, margin, own_gap):
            """Why a via can't go here (None: it can)."""
            if not (ex0 < vx < ex1 and ey0 < vy < ey1):
                return "board edge"
            if any(b[0] - VIA / 2 < vx < b[2] + VIA / 2 and b[1] - VIA / 2 < vy < b[3] + VIA / 2 for b in no_via):
                return "no-via rule area"
            x, y = np.array([vx]), np.array([vy])
            if len(rects) and (_rect_dist(x, y, rects)[:, 0] < VIA / 2 + need_p + margin).any():
                return "other net's pad"
            if len(own_pads) and (_rect_dist(x, y, own_pads)[:, 0] < VIA / 2 + own_gap).any():
                return "own net's pad"                   # no via-in-pad; the router holds a hole off own pads too
            if len(sa) and (_seg_dist(x, y, sa)[:, 0] - sw / 2 < VIA / 2 + s_need + margin).any():
                return "other net's track"
            if len(va):
                d = np.hypot(va[:, 0] - vx, va[:, 1] - vy)
                if (d - vr < VIA / 2 + v_need + margin)[~v_same].any():
                    return "other net's via"
                if (d < HOLE_SPACING).any():
                    return "via hole spacing"
            return None

        def stub_bad(vx, vy):
            """Why the stub to a via there can't be drawn (None: it can)."""
            n = max(2, int(math.hypot(vx - cx, vy - cy) / 0.05))
            xs = np.array([cx + (vx - cx) * i / n for i in range(n + 1)])
            ys = np.array([cy + (vy - cy) * i / n for i in range(n + 1)])
            out = ~((xs > own[0] - 0.02) & (xs < own[2] + 0.02) & (ys > own[1] - 0.02) & (ys < own[3] + 0.02))
            xs, ys = xs[out], ys[out]
            if not len(xs):
                return None
            on = [i for i, ls in enumerate(pad_layers) if layer in ls]
            if on and (_rect_dist(xs, ys, rects[on]).T < width / 2 + need_p[on]).any():
                return "stub: other net's pad"
            ons = [i for i, l in enumerate(s_layer) if l == layer]
            if ons and (_seg_dist(xs, ys, sa[ons]) - sw[ons][:, None] / 2 < width / 2 + s_need[ons][:, None]).any():
                return "stub: other net's track"
            other_v = ~v_same
            if other_v.any():
                d = np.hypot(xs[:, None] - va[other_v][:, 0], ys[:, None] - va[other_v][:, 1])
                if (d - vr[other_v] < width / 2 + v_need[other_v]).any():
                    return "stub: other net's via"
            return None

        found, why = None, {}
        for level, (margin, own_gap) in enumerate(LADDER):
            for r in rings(far_first):
                for a in [base + math.radians(d) for d in FAN] + [lane, lane + math.pi]:
                    vx, vy = cx + r * math.cos(a), cy + r * math.sin(a)
                    bad = via_bad(vx, vy, margin, own_gap) or stub_bad(vx, vy)
                    if bad is None:
                        found = (round(vx, 3), round(vy, 3))
                        break
                    why[bad] = why.get(bad, 0) + 1
                if found:
                    break
            if found:
                break
        if found is None:
            return None, sorted(why.items(), key=lambda kv: -kv[1])[:3]
        return (found[0], found[1], level, width, layer, cx, cy), None

    # a row of fine-pitch pads can defeat a greedy order (each stub walls in its
    # neighbours): the pads that failed go first in the next round
    for stagger in (0, 1, 2):
        for _ in range(4):
            del segs[n_segs:], vias[n_vias:]
            result, failed = {}, []
            for k, (fp, p) in enumerate(order):
                # stagger 1 and 2: every other pad of a footprint's row takes the long stub first
                far = stagger > 0 and (int(p.GetNumber() or 0) + stagger) % 2 == 0 \
                    if str(p.GetNumber()).isdigit() else False
                res, why = place(fp, p, far)
                if res is None:
                    failed.append((fp, p, why))
                    continue
                x, y, level, width, layer, cx, cy = res
                net = p.GetNetname()
                segs.append((cx, cy, x, y, width, net, layer))
                vias.append((x, y, VIA / 2, net))
                result[(fp.GetReference(), p.GetNumber())] = res
            if not failed:
                break
            first = {(fp.GetReference(), p.GetNumber()) for fp, p, _ in failed}
            order = [fp_p for fp_p in order if (fp_p[0].GetReference(), fp_p[1].GetNumber()) in first] + \
                    [fp_p for fp_p in order if (fp_p[0].GetReference(), fp_p[1].GetNumber()) not in first]
        if not failed:
            break
    placed = []
    for fp, p in order:
        res = result.get((fp.GetReference(), p.GetNumber()))
        if res is None:
            continue
        x, y, level, width, layer, cx, cy = res
        net_item = p.GetNet()
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(p.GetPosition())
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net_item)
        t.SetLocked(True)
        board.Add(t)
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        v.SetWidth(pcbnew.FromMM(VIA))
        v.SetDrill(pcbnew.FromMM(DRILL))
        v.SetNet(net_item)
        v.SetLocked(True)
        board.Add(v)
        placed.append((fp.GetReference(), p.GetNumber(), p.GetNetname(), x, y, level))
    unplaced = [(fp.GetReference(), p.GetNumber(), p.GetNetname(), why) for fp, p, why in failed]

    return placed, unplaced
