"""The geometry half of hw/mech/fit.py, run under FreeCAD's freecadcmd:

    MECH_JOB=build/mech/job.json freecadcmd hw/mech/fc_check.py

Reads the job fit.py wrote (boards, their STEP files, where each socket is
and how a card sits in it), places every card in every slot it fits, and
measures: collisions and clearances, the CEM component envelope, the plug
envelopes above top-edge connectors, the rail keep-out through the M3
holes, and the Wi-Fi antenna cable route. Writes build/mech/geometry.json
(lines per check) and build/mech/overview.png.

Frames. World: the main board's top at z = its thickness, x/y as KiCad's
STEP export (KiCad y flipped). Card: the card's own STEP export. fit.py's
transforms take card to world: world = R p + t - tz * z_mid, where z_mid is
the card's board mid-plane in its STEP (found here from the board body).
"""

import json
import math
import os
import traceback

import FreeCAD as App
import Part

JOB = json.load(open(os.environ["MECH_JOB"]))
OUT = JOB["out"]
CHECKS = {"MECH-%03d" % i: [] for i in range(1, 9)}
ROW = ("cpu", "io")        # the cards in the one row (slot.md, Mechanical)
EPS_VOL = 1e-3            # mm^3: less than this in common is touching, not a collision


def add(cid, ok, text):
    CHECKS[cid].append([bool(ok), text])


def note(cid, text):
    CHECKS[cid].append([None, text])


def V(*p):
    return App.Vector(*p)


def step_xy(p):
    return (p[0], -p[1])


def rot(v, deg):
    """A footprint-local vector (KiCad, y down) turned by the footprint's orientation."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (v[0] * c + v[1] * s, -v[0] * s + v[1] * c)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def matrix(tr, z_mid):
    R, t, tz = tr["R"], tr["t"], tr["tz"]
    tt = [t[i] - tz[i] * z_mid for i in range(3)]
    return App.Matrix(R[0][0], R[0][1], R[0][2], tt[0],
                      R[1][0], R[1][1], R[1][2], tt[1],
                      R[2][0], R[2][1], R[2][2], tt[2],
                      0, 0, 0, 1)


def moved(shape, m):
    s = shape.copy()
    s.transformShape(m)
    return s


def bb_gap(a, b):
    dx = max(a.XMin - b.XMax, b.XMin - a.XMax, 0)
    dy = max(a.YMin - b.YMax, b.YMin - a.YMax, 0)
    dz = max(a.ZMin - b.ZMax, b.ZMin - a.ZMax, 0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def closest(items_a, items_b, limit=1e9):
    """Min distance between two lists of (name, shape): (d, name_a, name_b,
    pa, pb, overlap volume). Bounding boxes first, so only the near pairs get
    the exact distance."""
    # collisions: by volume, where the boxes overlap (a part wholly inside
    # another has a surface distance > 0)
    worst = None
    for na, sa in items_a:
        for nb, sb in items_b:
            if bb_gap(sa.BoundBox, sb.BoundBox) == 0:
                common = sa.common(sb)
                if common.Volume >= EPS_VOL and (worst is None or common.Volume > worst[5]):
                    c = common.BoundBox.Center
                    worst = (0.0, na, nb, c, c, common.Volume)
    if worst:
        return worst
    # otherwise the exact distance, nearest boxes first: a pair whose boxes
    # are further apart than the best so far can't beat it
    pairs = sorted(((bb_gap(sa.BoundBox, sb.BoundBox), na, sa, nb, sb)
                    for na, sa in items_a for nb, sb in items_b), key=lambda p: p[0])
    best = (limit, None, None, None, None, 0.0)
    for g, na, sa, nb, sb in pairs:
        if g >= best[0]:
            break
        d, pts, _ = sa.distToShape(sb)
        if d < best[0]:
            best = (d, na, nb, pts[0][0], pts[0][1], 0.0)
    return best


# ------------------------------------------------------------------- cards
def read_assembly(path):
    """KiCad's STEP: one assembly node per footprint, placed at the
    footprint's position (x, -y, board surface), plus the board body.
    Returns (body solid, [(node position, shape)])."""
    import Import
    doc = App.newDocument("m%d" % len(App.listDocuments()))
    Import.insert(path, doc.Name)
    roots = [o for o in doc.Objects if o.TypeId == "App::Part" and not o.InList]
    bodies, comps = [], []
    for root in roots:
        for o in root.Group:
            if o.TypeId == "App::Part":
                # markings are solids 1 um thick (the module's printed
                # label): they cost seconds per distance and move nothing
                solids = [x for x in o.Shape.Solids if min(x.BoundBox.XLength, x.BoundBox.YLength,
                                                           x.BoundBox.ZLength) > 0.005]
                if solids:
                    comps.append((o.Placement.Base, Part.makeCompound(solids)))
            elif o.TypeId == "Part::Feature" and o.Shape.Solids:
                bodies += o.Shape.Solids
    body = max(bodies, key=lambda s: s.Volume)
    App.closeDocument(doc.Name)
    return body, comps


def assign(comps, fps, mid):
    """{ref: shape}: each assembly node to the footprint at its position."""
    parts = {}
    for pos, shape in comps:
        side = "F" if pos.z > mid else "B"
        same = [fp for fp in fps if fp["side"] == side] or fps

        def miss(f):
            return min(math.dist(a, (pos.x, pos.y)) for a in f["model_at"] + [step_xy(f["pos"])])
        fp = min(same, key=miss)
        if miss(fp) > 0.01:
            raise SystemExit("3D model at (%.2f, %.2f) matches no footprint" % (pos.x, pos.y))
        parts[fp["ref"]] = Part.makeCompound([parts[fp["ref"]], shape]) if fp["ref"] in parts else shape
    return parts


class Card:
    def __init__(self, name, c):
        self.name, self.c = name, c
        body, comps = read_assembly(c["step"])
        bb = body.BoundBox
        self.mid = (bb.ZMin + bb.ZMax) / 2
        self.T = c["thickness"]
        self.top, self.bot = self.mid + self.T / 2, self.mid - self.T / 2
        base = max((f for f in body.Faces if f.Surface.__class__.__name__ == "Plane"
                    and abs(f.normalAt(0, 0).z) > 0.999 and abs(f.CenterOfMass.z - bb.ZMin) < 1e-3),
                   key=lambda f: f.Area)
        self.slab = base.extrude(V(0, 0, self.T))
        self.slab.translate(V(0, 0, self.bot - bb.ZMin))
        self.fps = c["fps"]
        self.parts = assign(comps, self.fps, self.mid)
        self.by_ref = {fp["ref"]: fp for fp in self.fps}
        b1, a, d = c["edge"]
        self.b1, self.a, self.d = b1, a, d
        self.a_s, self.d_s = step_xy(a), step_xy(d)
        self.up_s = (-self.d_s[0], -self.d_s[1])

    def local_to_step(self, x, y):
        """CEM/footprint frame (B1 at 0, y towards the edge) -> card STEP x, y."""
        p = (self.b1[0] + x * self.a[0] + y * self.d[0], self.b1[1] + x * self.a[1] + y * self.d[1])
        return step_xy(p)

    def items(self):
        return [("board", self.slab)] + sorted(self.parts.items())

    def envelope(self):
        """(component side height, ref), (solder side depth, ref)."""
        up = max(((s.BoundBox.ZMax - self.top, r) for r, s in self.parts.items()), default=(0, "-"))
        down = max(((self.bot - s.BoundBox.ZMin, r) for r, s in self.parts.items()), default=(0, "-"))
        return up, (down if down[0] > 0 else (0.0, "nothing below the board"))

    def top_edge(self):
        """How far 'up' (away from the fingers) the card reaches, in STEP x, y."""
        return max(dot((v.Point.x, v.Point.y), self.up_s) for v in self.slab.Vertexes)

    def edge(self, d):
        """How far the card reaches along direction d (STEP x, y)."""
        return max(dot((v.Point.x, v.Point.y), d) for v in self.slab.Vertexes)


cards = {}
for name, c in JOB["cards"].items():
    c["edge_ref"] = next((fp["ref"] for fp in c["fps"] if "PCBEdge:BUS_PCIexpress" in fp["fpid"]), None)
    cards[name] = Card(name, c)


# ---------------------------------------------------------------- sockets
def frame_matrix(f, z0):
    u, n = f["u"], f["n"]
    m = (-n[0], -n[1], -n[2])            # u x (-n) = z: right handed
    o = f["b1"]
    return App.Matrix(u[0], m[0], 0, o[0], u[1], m[1], 0, o[1], u[2], m[2], 1, z0, 0, 0, 0, 1)


def socket_shape(f):
    s = JOB["sockets"][f["lcsc"]]
    dim_b = {"x1": 8.15, "x4": 22.15, "x8": 39.15}[s["width"]]
    main_top = f["b1"][2] - (s["height"] - s["depth"])
    u0 = -JOB["housing_before_b1"]
    house = Part.makeBox(s["length"], s["wide"], s["height"], V(u0, -s["wide"] / 2, 0))
    slot_u1 = 11.5 + dim_b + JOB["slot_after_tab"]
    slot = Part.makeBox(slot_u1 + JOB["slot_before_b1"], s["slot_w"], s["depth"] + 1,
                        V(-JOB["slot_before_b1"], -s["slot_w"] / 2, s["height"] - s["depth"]))
    return moved(house.cut(slot), frame_matrix(f, main_top)), main_top


frames = [f for f in JOB["frames"] if "error" not in f]
sockets = {}
main_top = None
for f in frames:
    sockets[f["ref"]], main_top = socket_shape(f)

main_items = []
main_plate = None
if JOB["main"]:
    body, comps = read_assembly(JOB["main"]["step"])
    mid = (body.BoundBox.ZMin + body.BoundBox.ZMax) / 2
    shift = V(0, 0, JOB["main"]["thickness"] / 2 - mid)      # its top at z = thickness
    main_plate = body.copy()
    main_plate.translate(shift)
    for ref, shape in sorted(assign(comps, JOB["main"]["fps"], mid).items()):
        shape = shape.copy()
        shape.translate(shift)
        main_items.append(("main board " + ref, shape))
elif frames:
    t = JOB["standin_cfg"]["main_t"]
    bb = None
    for sk in sockets.values():
        if bb is None:
            bb = sk.BoundBox
        else:
            bb.add(sk.BoundBox)
    main_plate = Part.makeBox(bb.XLength + 30, bb.YLength + 30, t, V(bb.XMin - 15, bb.YMin - 15, 0))


# -------------------------------------------------------------- placements
class Placed:
    def __init__(self, p):
        self.card = cards[p["card"]]
        self.slot = p["slot"]
        self.kind = self.card.c["kind"]
        self.m = matrix(p["tr"], self.card.mid)
        self.items = [(n, moved(s, self.m)) for n, s in self.card.items()]
        bb = self.items[0][1].BoundBox
        for _, s in self.items[1:]:
            bb.add(s.BoundBox)
        self.bb = bb

    def at(self, x, y, z):
        return self.m.multVec(V(x, y, z))

    def label(self):
        return "%s in %s" % (self.card.name, self.slot)


placed = [Placed(p) for p in JOB["placements"]]
frame_by_ref = {f["ref"]: f for f in frames}


def n_coord(p, f0):
    return dot((p.x, p.y, p.z), f0["n"])


# ---------------------------------------------------------------- MECH-001
def mech_001():
    cem = JOB["cem"]
    for p in placed:
        own = sockets[p.slot]
        vol = p.items[0][1].common(own).Volume
        s = JOB["sockets"][frame_by_ref[p.slot]["lcsc"]]
        if p is next(q for q in placed if q.card is p.card):
            add("MECH-001", vol < EPS_VOL, "%s: the finger tab in the %s's slot: %.4f mm^3 of board inside the housing"
                % (p.label(), s["part"], vol))
    for c in cards.values():
        tab = c.c["tab"]
        corners = [c.local_to_step(x, y) for x, y in ((tab["left"], tab["shoulder"]),
                                                      (tab["right"], tab["shoulder"]),
                                                      (tab["right"], tab["shoulder"] - JOB["tab_zone"]),
                                                      (tab["left"], tab["shoulder"] - JOB["tab_zone"]))]
        poly = Part.makePolygon([V(x, y, c.bot - 20) for x, y in corners] + [V(corners[0][0], corners[0][1], c.bot - 20)])
        zone = Part.Face(poly).extrude(V(0, 0, c.T + 40))
        hits = sorted(r for r, s in c.parts.items() if s.common(zone).Volume > EPS_VOL)
        add("MECH-001", not hits, "%s: parts within %.1f mm above the tab (slot.md: none): %s"
            % (c.name, JOB["tab_zone"], ", ".join(hits) or "none"))


# ---------------------------------------------------------------- MECH-003 / 008
def mech_003_008():
    cem = JOB["cem"]
    for c in cards.values():
        (up, ru), (down, rd) = c.envelope()
        cid = "MECH-003" if c.c["kind"] in ROW else "MECH-008"
        add(cid, up <= cem["comp_side_max"] + 1e-6,
            "%s: tallest on the component side %.2f mm (%s), CEM Fig. 9-1 max %.2f" % (c.name, up, ru, cem["comp_side_max"]))
        add(cid, down <= cem["solder_side_max"] + 1e-6,
            "%s: deepest on the solder side %.2f mm (%s), CEM max %.2f" % (c.name, down, rd, cem["solder_side_max"]))
    worst = {}
    pair_cache = {}
    for i, p in enumerate(placed):
        for q in placed[i + 1:]:
            if p.slot == q.slot or bb_gap(p.bb, q.bb) > 25:
                continue
            rel = p.m.inverse().multiply(q.m)
            ck = (p.card.name, q.card.name, tuple(round(v, 4) for v in rel.A))
            if ck not in pair_cache:
                pair_cache[ck] = closest(p.items, q.items)
            d, na, nb, pa, pb, vol = pair_cache[ck]
            cid = "MECH-003" if p.kind in ROW and q.kind in ROW else "MECH-008"
            key = (cid,) + tuple(sorted((p.card.name, q.card.name)))
            if key not in worst or d < worst[key][0]:
                worst[key] = (d, p, na, q, nb, vol, pa, pb)
    gaps = []
    for key, (d, p, na, q, nb, vol, pa, pb) in sorted(worst.items()):
        cid = key[0]
        add(cid, vol < EPS_VOL and d >= JOB["min_gap"],
            "%s %s vs %s %s: %.2f mm%s (need >= %.1f: two cards' bow, IPC-6012 0.75%%)"
            % (p.label(), na, q.label(), nb, d, ", COLLISION %.2f mm^3" % vol if vol >= EPS_VOL else "", JOB["min_gap"]))
        gaps.append((d, pa, pb))
    # every card against the sockets it is not in, and the main board's parts
    for p in placed:
        others = [(r, s) for r, s in sockets.items() if r != p.slot]
        near = [(r, s) for r, s in others if bb_gap(p.bb, s.BoundBox) < 25]
        if near:
            d, na, nb, _, _, vol = closest(p.items, near)
            p.sock_gap = (d, na, nb, vol)
        if main_items:
            d, na, nb, _, _, vol = closest(p.items, main_items)
            p.main_gap = (d, na, nb, vol)
    for kind, cid in (("io", "MECH-003"), ("cpu", "MECH-003"), ("system", "MECH-008")):
        ps = [p for p in placed if p.kind == kind]
        for attr, what in (("sock_gap", "a neighbouring socket"), ("main_gap", "the main board's parts")):
            got = [(getattr(p, attr), p) for p in ps if hasattr(p, attr)]
            if not got:
                continue
            (d, na, nb, vol), p = min(got, key=lambda g: g[0][0])
            add(cid, vol < EPS_VOL and d >= JOB["min_gap"] / 2,
                "%s: closest to %s: %s %s to %s, %.2f mm%s" % (kind, what, p.label(), na, nb, d,
                                                             ", COLLISION" if vol >= EPS_VOL else ""))
    return gaps


# ---------------------------------------------------------------- MECH-004
plug_envelopes = []           # (placed, ref, world shape)


def mech_004():
    any_conn = False
    for c in cards.values():
        top = c.top_edge()
        conns = [fp for fp in c.fps if fp["ref"] != c.c.get("edge_ref") and
                 (fp["lcsc"] in JOB["plugs"] or fp["ref"].startswith("J"))]
        for fp in conns:
            any_conn = True
            part = c.parts.get(fp["ref"])
            if part is None:
                add("MECH-004", False, "%s %s: no 3D model, so its overhang can't be checked" % (c.name, fp["ref"]))
                continue
            # a connector faces out of the top edge, or out of the back edge
            # (the B1 end, slot.md Mechanical): whichever it reaches past more
            back_s = (-c.a_s[0], -c.a_s[1])
            ups = [(max(dot((v.Point.x, v.Point.y), d) for v in part.Vertexes) - c.edge(d), d, side, across)
                   for d, side, across in ((c.up_s, "top", c.a_s), (back_s, "back", c.up_s))]
            over, out_s, side, across_s = max(ups, key=lambda u: u[0])
            face = over + c.edge(out_s)
            add("MECH-004", over >= JOB["min_overhang"],
                "%s %s (%s): mating face %+.2f mm past the %s edge (>= %.1f: flush within routing tolerance)"
                % (c.name, fp["ref"], fp["value"], over, side, JOB["min_overhang"]))
            plug = JOB["plugs"].get(fp["lcsc"])
            if not plug:
                note("MECH-004", "%s %s: no plug envelope known for %s" % (c.name, fp["ref"], fp["lcsc"] or fp["value"]))
                continue
            what, w, t = plug
            bb = part.BoundBox
            cx = dot((bb.Center.x, bb.Center.y), across_s)
            cz = (max(bb.ZMin, c.top) + bb.ZMax) / 2
            # a box in the card's frame: along the edge (across_s), out of it (out_s), across the card (z)
            loc = Part.makeBox(w, 40, t, V(-w / 2, 0, -t / 2))
            m = App.Matrix(across_s[0], out_s[0], 0, cx * across_s[0] + face * out_s[0],
                           across_s[1], out_s[1], 0, cx * across_s[1] + face * out_s[1],
                           0, 0, 1, cz, 0, 0, 0, 1)
            env = moved(loc, m)
            for p in placed:
                if p.card is c:
                    plug_envelopes.append((p, fp["ref"], what, moved(env, p.m)))
    if not any_conn:
        add("MECH-004", True, "no top- or back-edge connectors on %s (the Wi-Fi antenna plug is MECH-007)"
            % ", ".join(cards) if cards else "no cards")
        return
    for p, ref, what, env in plug_envelopes:
        others = [(q.label() + " " + n, s) for q in placed if q is not p for n, s in q.items]
        others += [(q.label() + " " + r + " plug", e) for q, r, _, e in plug_envelopes if q is not p]
        others += [("socket " + r, s) for r, s in sockets.items()] + main_items
        d, _, nb, _, _, vol = closest([("plug", env)], others)
        p.plug_gap = getattr(p, "plug_gap", [])
        p.plug_gap.append((d, ref, what, nb, vol))
    seen = set()
    for p, ref, what, env in plug_envelopes:
        key = (p.card.name, ref)
        if key in seen:
            continue
        seen.add(key)
        allg = [g for q in placed if q.card is p.card for g in getattr(q, "plug_gap", []) if g[1] == ref]
        d, _, _, nb, vol = min(allg, key=lambda g: g[0])
        add("MECH-004", vol < EPS_VOL, "%s %s: %s clear of everything in every slot, closest %.2f mm (%s)"
            % (p.card.name, ref, what, d, nb))


# ---------------------------------------------------------------- MECH-005
rails = []


def mech_005():
    io = [p for p in placed if p.kind in ROW]
    if not io:
        return
    f0 = frame_by_ref[io[0].slot]
    ends = [n_coord(V(*frame_by_ref[p.slot]["b1"]), f0) for p in io]
    lo, hi = min(ends) - 12, max(ends) + 12
    axes = {}
    for p in io:
        if not p.card.c.get("hole"):
            continue
        hx, hy = p.card.local_to_step(*p.card.c["hole"])        # where the card has it
        w = p.at(hx, hy, p.card.mid)
        axes.setdefault(p.card.name, []).append((dot((w.x, w.y, w.z), f0["u"]), w.z, p.slot, w, p.kind))
    # the rail axis from an I/O card's hole where there is one (slot.md's spot)
    allpts = sorted((a for v in axes.values() for a in v), key=lambda a: a[4] != "io")
    if not allpts:
        add("MECH-005", False, "no M3 hole on any card in the row")
        return
    su = max(a[0] for a in allpts) - min(a[0] for a in allpts)
    sz = max(a[1] for a in allpts) - min(a[1] for a in allpts)
    add("MECH-005", su <= 0.05 and sz <= 0.05,
        "M3 holes of %s in all %d row positions on one line: spread %.3f mm along the row, %.3f mm in height (<= 0.05)"
        % (", ".join(axes), len({a[2] for a in allpts}), su, sz))
    u0, z0, _, w0, _ = allpts[0]
    note("MECH-005", "the rail axis: %.2f mm along the row from finger B1, %.2f mm above the main board's top"
         % (u0 - dot(f0["b1"], f0["u"]), z0 - (main_top or 0)))
    # the rail standoffs: a 6.4 mm keep-out cylinder through the whole stack
    n = V(*f0["n"])
    base = w0 + n * (lo - n_coord(w0, f0))
    cyl = Part.makeCylinder(JOB["rail_keepout"] / 2, hi - lo, base, n)
    rails.append(("rail keep-out", cyl))
    hits = []
    for p in io:
        for n, s in p.items[1:]:
            if bb_gap(s.BoundBox, cyl.BoundBox) == 0 and s.common(cyl).Volume > EPS_VOL:
                hits.append("%s %s" % (p.label(), n))
    add("MECH-005", not hits, "rail keep-out (%.1f mm) through all slots: parts inside: %s"
        % (JOB["rail_keepout"], ", ".join(sorted(set(hits))) or "none"))


# ---------------------------------------------------------------- MECH-006
def mech_006():
    io = [p for p in placed if p.kind in ROW]
    if not io:
        return
    f0 = frame_by_ref[io[0].slot]
    # top edges: the board's highest line, and its ends along the row
    tops = []
    for p in io:
        slab = p.items[0][1]
        zt = slab.BoundBox.ZMax
        us = [dot((v.Point.x, v.Point.y, v.Point.z), f0["u"]) for v in slab.Vertexes if abs(v.Point.z - zt) < 1e-3]
        tops.append((zt, min(us), max(us), p.label()))
    sz = max(t[0] for t in tops) - min(t[0] for t in tops)
    s0 = max(t[1] for t in tops) - min(t[1] for t in tops)
    s1 = max(t[2] for t in tops) - min(t[2] for t in tops)
    add("MECH-006", sz <= 0.01 and s0 <= 0.01 and s1 <= 0.01,
        "top edges of %d card placements (%s) in line: spread %.3f in height, %.3f / %.3f at the two ends "
        "(<= 0.01); %.2f mm above the main board, %.2f mm long"
        % (len(tops), ", ".join(sorted({p.card.name for p in io})), sz, s0, s1, tops[0][0] - (main_top or 0),
           tops[0][2] - tops[0][1]))
    pts = []
    for p in io:
        ref = p.card.c.get("pwr_led")
        if not ref:
            continue
        fp = p.card.by_ref[ref]
        x, y = step_xy(fp["pos"])
        w = p.at(x, y, p.card.top)
        rel = n_coord(w, f0) - n_coord(V(*frame_by_ref[p.slot]["b1"]), f0)
        pts.append((dot((w.x, w.y, w.z), f0["u"]), w.z, rel, p.label()))
    if not pts:
        return
    su = max(a[0] for a in pts) - min(a[0] for a in pts)
    sz = max(a[1] for a in pts) - min(a[1] for a in pts)
    sr = max(a[2] for a in pts) - min(a[2] for a in pts)
    add("MECH-006", su <= 0.01 and sz <= 0.01 and sr <= 0.01,
        "power LEDs of %d card placements in one row: spread %.3f along the row, %.3f in height, "
        "%.3f off each slot's plane (<= 0.01); %.2f mm above the main board"
        % (len(pts), su, sz, sr, pts[0][1] - (main_top or 0)))


# ---------------------------------------------------------------- MECH-007
cables = []


def mech_007():
    ant = JOB["antennas"].get(JOB["antenna"] or "")
    found = False
    for c in cards.values():
        for fp in c.fps:
            mod = JOB["modules"].get(fp["lcsc"])
            if not mod:
                continue
            found = True
            if ant is None:
                add("MECH-007", False, "parts.md's Wi-Fi antenna %s is not in fit.py's ANTENNAS table" % JOB["antenna"])
                continue
            add("MECH-007", ant["conn_kind"] == mod["conn_kind"],
                "%s %s (%s) has a %s receptacle (Espressif datasheet v1.7 10.2); antenna %s %s has %s (%s)"
                % (c.name, fp["ref"], mod["name"], mod["conn_kind"], JOB["antenna"], ant["part"], ant["conn_kind"],
                   ant["ds"]))
            w, h = mod["size"]
            lx, ly = -w / 2 + mod["conn"][0], -h / 2 + mod["conn"][1]
            dx, dy = rot((lx, ly), fp["rot"])
            conn = step_xy((fp["pos"][0] + dx, fp["pos"][1] + dy))
            part = c.parts.get(fp["ref"])
            mtop = part.BoundBox.ZMax if part else c.top + 2.4
            od = ant["od"]
            zc = mtop + mod["mated_h"] - od / 2
            top = c.top_edge()
            inside = top - dot(conn, c.up_s)
            start = V(conn[0], conn[1], zc)
            plug = Part.makeCylinder(1.0, mod["mated_h"], V(conn[0], conn[1], mtop))
            cable = Part.makeCylinder(od / 2, inside + 20, start, V(c.up_s[0], c.up_s[1], 0))
            route = plug.fuse(cable)
            b1 = c.local_to_step(0, 0)
            rel = (conn[0] - b1[0], conn[1] - b1[1])
            note("MECH-007", "%s: connector at (%.2f, %.2f) from finger B1 (slot.md frame), %.2f mm below the top edge; "
                 "cable %.2f mm OD straight up, centre %.2f mm above the board"
                 % (c.name, dot(rel, c.a_s), -dot(rel, c.up_s), inside, od, zc - c.top))
            worst = None
            for p in [p for p in placed if p.card is c]:
                r = moved(route, p.m)
                cables.append((p, r))
                # its own card's parts it passes over, not the board it lies along
                others = [(n, s) for n, s in p.items if n not in (fp["ref"], "board")]
                others += [(q.label() + " " + n, s) for q in placed if q is not p and bb_gap(q.bb, r.BoundBox) < 5
                           for n, s in q.items]
                others += rails + [("socket " + k, s) for k, s in sockets.items()] + main_items
                others += [(q.label() + " " + rr + " plug", e) for q, rr, _, e in plug_envelopes]
                d, _, nb, _, _, vol = closest([("cable", r)], others)
                if worst is None or d < worst[0]:
                    worst = (d, nb, vol, p.label())
            if worst:
                d, nb, vol, where = worst
                add("MECH-007", vol < EPS_VOL and d >= JOB["cable_min_gap"],
                    "%s: plug and cable route to the top edge clear in every slot, closest %.2f mm (%s, %s; need >= %.1f)"
                    % (c.name, d, nb, where, JOB["cable_min_gap"]))
            add("MECH-007", ant["length"] - inside > 50,
                "%s: %.0f mm antenna cable leaves %.0f mm past the card's top edge for the antenna (> 50)"
                % (c.name, ant["length"], ant["length"] - inside))
    if not found:
        add("MECH-007", False, "no Wi-Fi module (%s) on any card" % ", ".join(JOB["modules"]))


# ---------------------------------------------------------------- render
def render(gaps):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from matplotlib.collections import PolyCollection

    # one configuration: the I/O cards in turn along the slots, plus the CPU/system cards
    io_slots = [f["ref"] for f in frames if f["width"] == "x1"]
    names = sorted({p.card.name for p in placed if p.kind == "io"})
    # the other I/O cards follow in turn along slots 1-6
    show = []
    for k, slot in enumerate(io_slots):
        if names:
            show += [p for p in placed if p.slot == slot and p.card.name == names[k % len(names)]]
    show += [p for p in placed if p.kind != "io"]
    layers = []                          # (shape, colour, alpha)
    if main_plate is not None:
        layers.append((main_plate, "#1f5130", 0.35))
    for s in sockets.values():
        layers.append((s, "#222222", 0.9))
    for p in show:
        for n, s in p.items:
            layers.append((s, "#2e7d4f" if n == "board" else "#555566", 0.95 if n != "board" else 0.8))
    for _, s in main_items:
        layers.append((s, "#555566", 0.9))
    for _, s in rails:
        layers.append((s, "#d04040", 0.25))
    shown = {p.card.name for p in show}
    for p, _, _, e in plug_envelopes:
        if p in show:
            layers.append((e, "#4070d0", 0.15))
    for p, s in cables:
        if p in show:
            layers.append((s, "#e08020", 1.0))
    tris = []
    for shape, col, alpha in layers:
        try:
            pts, faces = shape.tessellate(0.25)
        except Exception:
            continue
        tris.append(([[(pts[i].x, pts[i].y, pts[i].z) for i in f] for f in faces], col, alpha))

    fig = plt.figure(figsize=(16, 8), dpi=110)
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for polys, col, alpha in tris:
        if not polys:
            continue
        pc = Poly3DCollection(polys, facecolor=col, edgecolor="none", alpha=alpha)
        ax.add_collection3d(pc)
        for tri in polys:
            for v in tri:
                for i in range(3):
                    lo[i], hi[i] = min(lo[i], v[i]), max(hi[i], v[i])
    span = max(h - l for l, h in zip(lo, hi)) / 2
    ctr = [(l + h) / 2 for l, h in zip(lo, hi)]
    ax.set_xlim(ctr[0] - span, ctr[0] + span)
    ax.set_ylim(ctr[1] - span, ctr[1] + span)
    ax.set_zlim(ctr[2] - span, ctr[2] + span)
    ax.view_init(elev=22, azim=-58)
    ax.set_xlabel("x mm")
    ax.set_ylabel("y mm")
    ax.set_zlabel("z mm")
    ax.set_title("CUPC/8 slots: %s%s" % (", ".join(sorted(shown)) or "no cards",
                                         " (stand-in main board)" if JOB["standin"] else ""))

    # side elevation: looking along the row (u), the stack in (n, z)
    ax2 = fig.add_subplot(1, 2, 2)
    f0 = frames[0] if frames else {"u": (1, 0, 0), "n": (0, -1, 0)}
    for polys, col, alpha in tris:
        flat = [[(dot(v, f0["n"]), v[2]) for v in tri] for tri in polys]
        ax2.add_collection(PolyCollection(flat, facecolor=col, edgecolor="none", alpha=min(1, alpha + 0.05)))
    if gaps:
        d, pa, pb = min(gaps, key=lambda g: g[0])
        a2 = (dot((pa.x, pa.y, pa.z), f0["n"]), pa.z)
        b2 = (dot((pb.x, pb.y, pb.z), f0["n"]), pb.z)
        ax2.annotate("", xy=b2, xytext=a2, arrowprops=dict(arrowstyle="<->", color="#c00000"))
        ax2.text((a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2 + 2, "min card-to-card %.2f mm" % d,
                 color="#c00000", ha="center", fontsize=9)
    ax2.autoscale()
    ax2.set_aspect("equal")
    ax2.set_xlabel("across the slots (card normal) mm")
    ax2.set_ylabel("height above the main board's underside mm")
    ax2.set_title("looking along the slot row")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "overview.png"))


try:
    import time
    t0 = time.time()
    mech_001()
    gaps = mech_003_008()
    mech_004()
    mech_005()
    mech_006()
    mech_007()
    t1 = time.time()
    render(gaps)
    print("geometry %.1f s, render %.1f s" % (t1 - t0, time.time() - t1))
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
with open(os.path.join(OUT, "geometry.json"), "w") as fh:
    json.dump({"checks": CHECKS}, fh, indent=1)
