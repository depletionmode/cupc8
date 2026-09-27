"""Post-route copper experiment for the main board's 5 V distribution.

This runs after the saved SES is imported, so the router input and its
structural identity guard remain unchanged. It is an isolated trial: input
VBUS copper, finished-copper minima and conductor temperature remain open.
"""


def reinforce_slot_5v(board):
    import pcbnew

    mm, to = pcbnew.FromMM, pcbnew.ToMM

    def point(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    # Require the exact eFuse output route and slot-bus landing geometry.
    # A later placement or routing revision must redraw and recheck this
    # reinforcement instead of silently applying it to new coordinates.
    tracks = board.Tracks()
    diagonal = []
    bus_end_vias = set()
    sys_vias = set()
    for i in range(len(tracks)):
        item = tracks[i]
        if item.GetClass() == "PCB_TRACK" and item.GetNetname() == "/5V_SYS" and item.GetLayer() == pcbnew.F_Cu:
            a, z = item.GetStart(), item.GetEnd()
            ends = {(round(to(a.x), 4), round(to(a.y), 4)),
                    (round(to(z.x), 4), round(to(z.y), 4))}
            if ends == {(11.26, 153.8), (9.5375, 152.0)} and item.GetWidth() == mm(1.0):
                diagonal.append(item)
        if item.GetClass() == "PCB_VIA" and item.GetNetname() == "/+5V":
            p = item.GetPosition()
            xy = (round(to(p.x), 4), round(to(p.y), 4))
            if xy in {(4.2, 40.52), (3.4, 149.0)}:
                bus_end_vias.add(xy)
            if xy == (14.8, 152.0):
                bus_end_vias.add(xy)
        if item.GetClass() == "PCB_VIA" and item.GetNetname() == "/5V_SYS":
            p = item.GetPosition()
            xy = (round(to(p.x), 4), round(to(p.y), 4))
            if xy in {(12.5, 162.0), (34.0, 162.0)}:
                sys_vias.add(xy)
    if (len(diagonal) != 1 or
            bus_end_vias != {(4.2, 40.52), (3.4, 149.0), (14.8, 152.0)} or
            sys_vias != {(12.5, 162.0), (34.0, 162.0)}):
        raise RuntimeError("reinforce_slot_5v: eFuse or slot-bus route changed")
    diagonal[0].SetWidth(mm(1.5))

    net = board.FindNet("/+5V")
    if net is None:
        raise RuntimeError("reinforce_slot_5v: missing +5V net")

    def track(a, z, width, layer, signal=net):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(point(*a))
        item.SetEnd(point(*z))
        item.SetWidth(mm(width))
        item.SetLayer(layer)
        item.SetNet(signal)
        board.Add(item)

    # In4 contributes a fourth long inner/outer path. Its 7.5 mm width is
    # the verified maximum: 8 mm shorts slot IRQ pull-ups and breaches the
    # board's copper-edge clearance. The F.Cu path fits at 4.5 mm.
    track((4.5, 40.52), (4.5, 149.0), 7.5, pcbnew.In4_Cu)
    track((2.75, 40.52), (2.75, 149.0), 4.5, pcbnew.F_Cu)
    track((2.75, 40.52), (4.5, 40.52), 1.0, pcbnew.F_Cu)
    track((2.75, 149.0), (4.5, 149.0), 1.0, pcbnew.F_Cu)

    # The original buck VIN feed takes a long detour around its feedback via.
    # The In4 path passes below that via and joins the existing F.Cu feed at
    # (40, 160.95). The through via at that point is clear of U3's pads.
    sys = board.FindNet("/5V_SYS")
    if sys is None:
        raise RuntimeError("reinforce_slot_5v: missing 5V_SYS net")
    track((12.5, 162.0), (34.0, 162.0), 2.4, pcbnew.In4_Cu, sys)
    for a, z in (((34.0, 162.0), (34.0, 163.0)),
                 ((34.0, 163.0), (40.0, 163.0)),
                 ((40.0, 163.0), (40.0, 160.95))):
        track(a, z, 2.5, pcbnew.In4_Cu, sys)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(point(40.0, 160.95))
    via.SetWidth(mm(0.6))
    via.SetDrill(mm(0.3))
    via.SetNet(sys)
    board.Add(via)
    track((34.0, 162.0), (35.5, 159.05), 1.5, pcbnew.In4_Cu, sys)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(point(35.5, 159.05))
    via.SetWidth(mm(0.6))
    via.SetDrill(mm(0.3))
    via.SetNet(sys)
    board.Add(via)

    # Parallel the R4-to-bus bend on In4 and enlarge the narrow R4 pad feed.
    for a, z in (((4.5, 149.0), (4.5, 149.5)),
                 ((4.5, 149.5), (14.8, 149.5)),
                 ((14.8, 149.5), (14.8, 152.0))):
        track(a, z, 4.0, pcbnew.In4_Cu)
    feed = []
    for i in range(len(tracks)):
        item = tracks[i]
        if item.GetClass() != "PCB_TRACK" or item.GetNetname() != "/+5V" or item.GetLayer() != pcbnew.F_Cu:
            continue
        a, z = item.GetStart(), item.GetEnd()
        ends = {(round(to(a.x), 4), round(to(a.y), 4)),
                (round(to(z.x), 4), round(to(z.y), 4))}
        if ends == {(12.4625, 152.0), (15.6, 152.0)} and item.GetWidth() == mm(0.7):
            feed.append(item)
    if len(feed) != 1:
        raise RuntimeError("reinforce_slot_5v: R4 output feed changed")
    feed[0].SetWidth(mm(1.5))
