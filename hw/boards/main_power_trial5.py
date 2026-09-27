"""Post-route copper experiment for the main board's +5 V slot feed.

This runs after the saved SES is imported, so the router input and its
structural identity guard remain unchanged. It is an isolated trial until
finished-copper and conductor-temperature minima are qualified.
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
    if len(diagonal) != 1 or bus_end_vias != {(4.2, 40.52), (3.4, 149.0)}:
        raise RuntimeError("reinforce_slot_5v: eFuse or slot-bus route changed")
    diagonal[0].SetWidth(mm(1.5))

    net = board.FindNet("/+5V")
    if net is None:
        raise RuntimeError("reinforce_slot_5v: missing +5V net")

    def track(a, z, width, layer):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(point(*a))
        item.SetEnd(point(*z))
        item.SetWidth(mm(width))
        item.SetLayer(layer)
        item.SetNet(net)
        board.Add(item)

    # In4 contributes a fourth long inner/outer path. Its 7.5 mm width is
    # the verified maximum: 8 mm shorts slot IRQ pull-ups and breaches the
    # board's copper-edge clearance. The F.Cu path fits at 4.5 mm.
    track((4.5, 40.52), (4.5, 149.0), 7.5, pcbnew.In4_Cu)
    track((2.75, 40.52), (2.75, 149.0), 4.5, pcbnew.F_Cu)
    track((2.75, 40.52), (4.5, 40.52), 1.0, pcbnew.F_Cu)
    track((2.75, 149.0), (4.5, 149.0), 1.0, pcbnew.F_Cu)
