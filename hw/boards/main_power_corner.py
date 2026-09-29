#!/usr/bin/env python3
"""MB-005: the main board's input copper, J1 -> F1 -> U2 -> 5V_SYS (David, 2026-09-28).

The requirement (doc/hardware/mb005-loop-requirement-derivation.md): the
board-side input loop <= 60 mOhm at the hottest corner, and every
full-current conductor <= 20 C above its surroundings at the eFuse's
3.213 A limit (>= 1.75 mm drawn outer 1 oz, or the equivalent). U2 is turned
half round from the earlier boards, so its IN bar escapes towards F1 and its
OUT bar towards the loads: the whole positive path stays on the outer layers.

  J1 A4B9 -- F.Cu 2.6 mm -------------------------------- F1:1
  J1 B4A9 -- vias -- B.Cu 1.6 / 2.6 mm -- vias ----------/   (tied to F.Cu along the way)
  F1:2 -- F.Cu 2.6 mm -- U2 IN (0.3 mm escape, 0.5 mm long)
  U2 OUT -- F.Cu 2.0 mm -- R4 (the slots' +5V link) and C3 (bulk)
          \\- vias -- B.Cu 2.0 mm -- C5 and the buck (U3 VIN)
  J1 A1B12 / B1A12 (GND) -- F.Cu to J1's shell pads, whose plated slots
          reach every GND plane (the return)

Every locked item here is checked by KiCad's DRC and connectivity after
routing; the geometry guards below fail the build if the parts it is drawn
against move. Returns the nets for the post-route connectivity check.
"""


def lay(board):
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM

    def pad(ref, num):
        p = next(q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num)
        return p, (to(p.GetPosition().x), to(p.GetPosition().y))

    def track(pts, width, net, layer=pcbnew.F_Cu):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)

    def via(at, net):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(net)
        v.SetLocked(True)
        board.Add(v)

    expect = {("J1", "A4B9"): (27.6, 180.95), ("J1", "B4A9"): (32.4, 180.95),
              ("J1", "A1B12"): (26.8, 180.95), ("J1", "B1A12"): (33.2, 180.95),
              ("J1", "4"): (25.67, 181.71), ("J1", "1"): (34.33, 181.71),
              ("F1", "1"): (18.0, 172.137), ("F1", "2"): (18.0, 167.863),
              ("U2", "5"): (18.23, 160.0), ("U2", "6"): (17.74, 160.0),
              ("R4", "1"): (9.537, 152.0), ("U3", "1"): (39.15, 160.95), ("U3", "4"): (36.85, 159.05)}
    for (ref, num), (x, y) in expect.items():
        _, (px, py) = pad(ref, num)
        if abs(px - x) > 0.02 or abs(py - y) > 0.02:
            raise SystemExit("main_power_corner: %s:%s at (%.3f, %.3f), drawn for (%.3f, %.3f); "
                             "lay the input copper again" % (ref, num, px, py, x, y))
    vbus = pad("J1", "A4B9")[0].GetNet()
    vbus_f = pad("F1", "2")[0].GetNet()
    v5 = pad("U2", "6")[0].GetNet()
    gnd = pad("J1", "A1B12")[0].GetNet()
    _, c1 = pad("C1", "1")
    _, c3 = pad("C3", "1")
    _, c5 = pad("C5", "1")

    # J1's signal-ground pads to its shell pads, clear of the VBUS copper; the
    # fan-out's vias for them (north, where VBUS now runs) are removed
    tracks = board.Tracks()
    stale = []
    for i in range(len(tracks)):
        t = tracks[i]
        if t.GetNetname() != gnd.GetNetname():
            continue
        pts = [t.GetStart()] + ([t.GetEnd()] if t.Type() == pcbnew.PCB_TRACE_T else [])
        if any(25.5 < to(p.x) < 34.5 and 177.0 < to(p.y) < 180.5 for p in pts):
            stale.append(t)
    for t in stale:
        board.Remove(t)
    track([(26.8, 181.3), (25.9, 181.3)], 0.6, gnd)
    track([(33.2, 181.3), (34.1, 181.3)], 0.6, gnd)

    # VBUS: A4B9 on F.Cu, B4A9 on B.Cu, tied by vias along the diagonal
    track([(27.6, 180.95), (27.6, 179.5), (26.2, 178.4)], 0.6, vbus)
    track([(27.6, 179.5), (26.2, 178.4)], 1.2, vbus)
    diag = [(26.2, 178.4), (19.0, 172.6)]
    track(diag, 2.6, vbus)
    track([(19.0, 172.6), (17.2, 172.3)], 1.2, vbus)
    track([(32.4, 180.95), (32.4, 178.4)], 0.6, vbus)
    for at in ((32.4, 179.2), (32.4, 178.4)):
        via(at, vbus)
    # B4A9's B.Cu joint is 2.4 mm: at 1.6 mm it ran above the 20 C density with B4A9's contacts
    # carrying the whole current
    track([(32.4, 178.8), (26.2, 178.4)], 2.4, vbus, pcbnew.B_Cu)
    track(diag, 2.6, vbus, pcbnew.B_Cu)
    for k in range(4):
        f = k / 3
        via((26.2 + (19.6 - 26.2) * f, 178.4 + (173.4 - 178.4) * f), vbus)
    for at in ((18.4, 173.5), (20.2, 172.1)):
        via(at, vbus)

    # VBUS_F: F1:2 straight up to U2's IN bar (south end, its escape);
    # C1 (the only capacitance ahead of the eFuse) on a spur
    track([(18.23, 161.2), (18.23, 161.7)], 0.3, vbus_f)
    # the escape's joint to the bus: a tangent point has no copper width, so a 0.3 mm run and a 0.7 mm
    # taper from 0.45 mm past U2's bars (as close as the neighbouring bar ends and corner pads allow)
    track([(18.23, 161.7), (18.23, 162.6)], 0.3, vbus_f)
    track([(18.23, 161.65), (18.23, 162.6)], 0.7, vbus_f)
    track([(18.23, 163.0), (18.0, 166.9)], 2.6, vbus_f)
    track([(19.0, 165.0), c1], 0.8, vbus_f)

    # 5V_SYS: U2's OUT (north end) west to C3 and up to R4:1, 2.0 mm on F.Cu
    track([(17.74, 158.8), (17.74, 157.6)], 0.3, v5)
    track([(17.74, 157.6), (17.74, 156.7)], 0.3, v5)      # the same joint on the OUT bar's escape
    track([(17.74, 158.35), (17.74, 156.7)], 0.7, v5)
    track([(17.74, 156.6), (10.0, 156.6), (9.8, 153.0)], 2.0, v5)
    track([(c3[0], 156.6), c3], 1.0, v5)
    # ... and east on B.Cu to C5 and the buck's two VIN pads
    for at in ((15.6, 156.6), (16.6, 156.6), (14.6, 156.6)):
        via(at, v5)
    track([(14.6, 156.6), (40.8, 156.6), (40.8, 162.3)], 2.0, v5, pcbnew.B_Cu)
    via((c5[0], 157.4), v5)
    via((40.8, 162.3), v5)
    track([(c5[0], 157.4), c5], 0.6, v5)
    track([c5, (36.85, 159.05)], 0.5, v5)
    track([(40.8, 162.3), (40.0, 162.3), (40.0, 160.95), (39.15, 160.95)], 0.5, v5)
    return [vbus.GetNetname(), vbus_f.GetNetname(), v5.GetNetname()]


ISLAND = (92.4, 40.4, 109.6, 57.6)      # +1V2 on B.Cu inside U7's pin ring (U7 at (101, 49))


def lay_1v2(board):
    """MB-051: the chipset core's +1V2 as copper, not 0.2 mm tracks.

    The RT9013 (U4) and its 1 mOhm link (R8) sit just south-east of U7. A
    B.Cu +1V2 pour fills U7's inside (every core pin has its own via there,
    _plane_pads) and a 3 mm corridor to a via beside R8's +1V2 pad. Rule
    areas keep the router's tracks off both (a track there would cut the
    pour); vias may still pass, the pour clears them. Freerouting does not
    see the pour, so +1V2 is returned as a net to check on KiCad's
    connectivity after routing."""
    import math
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    r8 = board.FindFootprintByReference("R8")
    p2 = next(p for p in r8.Pads() if p.GetNetname() == "/+1V2")
    net = p2.GetNet()
    x, y = to(p2.GetPosition().x), to(p2.GetPosition().y)
    u7 = board.FindFootprintByReference("U7")
    if (round(to(u7.GetPosition().x), 3), round(to(u7.GetPosition().y), 3)) != (101.0, 49.0):
        raise SystemExit("lay_1v2: U7 moved; move the +1V2 island")
    if not (110.0 < x < 125.0 and 62.0 < y < 85.0):
        raise SystemExit("lay_1v2: R8 at (%.2f, %.2f), outside the corridor this was drawn for" % (x, y))
    at = (x, y + 1.6)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(p2.GetPosition())
    t.SetEnd(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
    t.SetWidth(mm(0.8))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)
    for dx in (0.0, 0.9):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(at[0] + dx), mm(at[1])))
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(net)
        v.SetLocked(True)
        board.Add(v)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
    track.SetEnd(pcbnew.VECTOR2I(mm(at[0] + 0.9), mm(at[1])))
    track.SetWidth(mm(0.8))
    track.SetLayer(pcbnew.F_Cu)
    track.SetNet(net)
    track.SetLocked(True)
    board.Add(track)

    x0, y0, x1, y1 = ISLAND
    corner = (x1 - 1.0, y1 - 1.0)
    dx, dy = at[0] - corner[0], at[1] - corner[1]
    n = math.hypot(dx, dy)
    ox, oy = -dy / n * 1.5, dx / n * 1.5
    corridor = [(corner[0] + ox, corner[1] + oy), (at[0] + ox, at[1] + oy),
                (at[0] - ox + dx / n * 1.2, at[1] - oy + dy / n * 1.2), (corner[0] - ox, corner[1] - oy)]
    island = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for pts, name, prio in ((island, "+1V2 island", 2), (corridor, "+1V2 corridor", 3)):
        z = pcbnew.ZONE(board)
        z.SetLayer(pcbnew.B_Cu)
        z.SetNet(net)
        z.SetZoneName(name)
        z.SetAssignedPriority(prio)
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        for px, py in pts:
            ol.Append(mm(px), mm(py))
        board.Add(z)
        k = pcbnew.ZONE(board)
        k.SetIsRuleArea(True)
        k.SetZoneName(name + " keep-out")
        k.SetDoNotAllowTracks(True)
        k.SetDoNotAllowVias(False)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowZoneFills(False)
        k.SetDoNotAllowFootprints(False)
        k.SetLayer(pcbnew.B_Cu)
        ol = k.Outline()
        ol.NewOutline()
        for px, py in pts:
            ol.Append(mm(px), mm(py))
        board.Add(k)
    return [net.GetNetname()]

