"""Post-route VBUS bypass experiment for the saved main-board route.

The B.Cu path winds around the J1 GND fanout vias and plated hold-down.
No GND via is removed. Input-loop resistance and heating remain open.
"""


def reinforce_input_vbus(board):
    import pcbnew

    mm, to = pcbnew.FromMM, pcbnew.ToMM
    anchors = {(19.2242, 173.3617), (27.6, 179.6788)}
    found = set()
    tracks = board.Tracks()
    for i in range(len(tracks)):
        item = tracks[i]
        if item.GetClass() != "PCB_VIA" or item.GetNetname() != "/VBUS":
            continue
        p = item.GetPosition()
        xy = (round(to(p.x), 6), round(to(p.y), 6))
        if xy in anchors:
            found.add(xy)
    if found != anchors:
        raise RuntimeError("reinforce_input_vbus: F1/J1 via anchors changed")
    net = board.FindNet("/VBUS")
    if net is None:
        raise RuntimeError("reinforce_input_vbus: missing VBUS net")

    def point(x, y):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    # The narrow final segment clears J1's nearby GND fanout via. The
    # centre segment skirts the GND via at (23.825, 177) on its north side.
    for a, z, width in (((19.2242, 173.3617), (22.0, 174.0), 3.0),
                        ((22.0, 174.0), (26.7, 177.2), 1.8),
                        ((26.7, 177.2), (27.6, 179.6788), 0.7)):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(point(*a))
        item.SetEnd(point(*z))
        item.SetWidth(mm(width))
        item.SetLayer(pcbnew.B_Cu)
        item.SetNet(net)
        board.Add(item)
