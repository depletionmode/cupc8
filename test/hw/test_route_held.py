#!/usr/bin/env python3
"""ROUTE-001: kicadgen.autoroute keeps the router's copper on a net that is
pre-routed partly on an inner layer.

    python3 test/hw/test_route_held.py

A 4-layer 30 x 20 mm board: net /N joins R1 pad 1 and R2 pad 1, and is
pre-routed as two locked vias joined by a locked In2 track; Freerouting
must join each pad to its via. After the session import the net must be
one piece (KiCad's connectivity), and the pre-routed In2 track still there.
autoroute used to drop every track of such a net and put back only the
pre-routing, which left the router's pad-to-via tracks out: the main
board's VBUS_F, pre-routed on In3, came back open.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import pcbnew  # noqa: E402

mm = pcbnew.FromMM
fails = 0


def check(name, ok, detail=""):
    global fails
    print("%s %s%s" % ("pass" if ok else "FAIL", name, (": " + detail) if detail and not ok else ""))
    fails += not ok


b = pcbnew.BOARD()
b.SetCopperLayerCount(4)
b.SetEnabledLayers(b.GetEnabledLayers())
for (x0, y0, x1, y1) in ((0, 0, 30, 0), (30, 0, 30, 20), (30, 20, 0, 20), (0, 20, 0, 0)):
    e = pcbnew.PCB_SHAPE(b)
    e.SetShape(pcbnew.SHAPE_T_SEGMENT)
    e.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
    e.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    e.SetLayer(pcbnew.Edge_Cuts)
    b.Add(e)
net = pcbnew.NETINFO_ITEM(b, "/N")
b.Add(net)
for ref, x in (("R1", 6), ("R2", 24)):
    fp = pcbnew.FootprintLoad(kg.footprint_dir("Resistor_SMD"), "R_0603_1608Metric")
    fp.SetReference(ref)
    b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(10)))
    for p in fp.Pads():
        if p.GetNumber() == "1":
            p.SetNet(net)
vias = [(10, 14), (20, 14)]
for x, y in vias:
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(net)
    v.SetLocked(True)
    b.Add(v)
t = pcbnew.PCB_TRACK(b)
t.SetStart(pcbnew.VECTOR2I(mm(10), mm(14)))
t.SetEnd(pcbnew.VECTOR2I(mm(20), mm(14)))
t.SetWidth(mm(0.3))
t.SetLayer(pcbnew.In2_Cu)
t.SetNet(net)
t.SetLocked(True)
b.Add(t)

with tempfile.TemporaryDirectory() as work:
    pcb = os.path.join(work, "held.kicad_pcb")
    pcbnew.SaveBoard(pcb, b)
    b = pcbnew.LoadBoard(pcb)
    kg.autoroute(b, work, passes=5, tries=1)
    b.BuildConnectivity()
    open_n = b.GetConnectivity().GetUnconnectedCount(False)
    ts = b.Tracks()
    inner = [ts[i] for i in range(len(ts)) if ts[i].Type() == pcbnew.PCB_TRACE_T and ts[i].GetLayer() == pcbnew.In2_Cu]
check("the held net is one piece after routing", open_n == 0, "%d connections open" % open_n)
check("the pre-routed In2 track is still there", len(inner) == 1, "%d In2 tracks" % len(inner))
print("ROUTE-001: %d failed" % fails)
sys.exit(1 if fails else 0)
