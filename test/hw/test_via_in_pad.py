#!/usr/bin/env python3
"""VIP-001: no open via hole in a pad (JLC via-in-pad; audit I3, I5, I6, io J2).

    python3 test/hw/test_via_in_pad.py [built card dir ...]

- kicadgen.ground_fanout(pad_clear=0.1) on a synthetic module (a row of 0.5 mm
  GND pads at 0.8 mm pitch, 1.45 mm GND pads 0.5 mm apart, a big shell-like
  GND pad, an exposed pad): every via's drill ends up 0.1 mm or more outside
  every pad's solder-mask opening, each via keeps its neck to its pad, and
  the exempt exposed pad keeps its via in the pad. Without `pad_clear` the
  same board has open holes (the old fan-out).
- vias_in_pad_openings flags a hole in a pad, one 0.05 mm short of the rule,
  passes one exactly on it, and honours `allowed`.
- the built cards, when given as arguments or when build/hw/<card> has current
  evidence: no open via hole in any pad but U1.57 (the RP2040 exposed pad,
  audit I3: accepted, not plugged).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import pcbnew  # noqa: E402

mm, to = pcbnew.FromMM, pcbnew.ToMM
fails = 0
# cards whose pipeline sets pad_via_clear (cpu keeps its own: its one via touching a pad has its hole under mask)
CARDS = ("gpu", "io", "storage", "eink", "system", "wifi")


def check(name, ok, detail=""):
    global fails
    print("%s %s%s" % ("pass" if ok else "FAIL", name, (": " + detail) if detail and not ok else ""))
    fails += not ok


def add_pad(fp, number, x, y, w, h, net):
    p = pcbnew.PAD(fp)
    p.SetNumber(number)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I(mm(w), mm(h)))
    layers = pcbnew.LSET()
    for layer in (pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste):
        layers.AddLayer(layer)
    p.SetLayerSet(layers)
    p.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    p.SetNet(net)
    fp.Add(p)


def module():
    """A 40 x 30 board with U1 at (20, 15): nine GND pads 0.5 x 1.0 at 0.8 mm
    pitch (y 8), nine signal pads (y 22), 1.45 mm GND pads 1.98 mm apart
    (y 13), a 5 x 2.5 mm GND pad (y 17, like a connector shell) and a GND
    exposed pad (y 12, U1.EP)."""
    b = pcbnew.BOARD()
    gnd, sig = pcbnew.NETINFO_ITEM(b, "/GND"), pcbnew.NETINFO_ITEM(b, "/S")
    b.Add(gnd)
    b.Add(sig)
    for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
        b.Add(s)
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference("U1")
    b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(20), mm(15)))
    for i in range(9):
        add_pad(fp, str(i + 1), 16.8 + 0.8 * i, 8, 0.5, 1.0, gnd)
        add_pad(fp, str(10 + i), 16.8 + 0.8 * i, 22, 0.5, 1.0, sig)
    for i, x in enumerate((18.02, 20.0, 21.98)):
        add_pad(fp, str(20 + i), x, 13, 1.45, 1.45, gnd)
    add_pad(fp, "SH", 20, 17.5, 5.0, 2.5, gnd)
    add_pad(fp, "EP", 26, 14, 3.0, 3.0, gnd)
    return b, fp


def items(b, kind):
    tracks = b.Tracks()          # indexed: iterating it breaks on Python 3.14
    return [tracks[i].Cast() for i in range(len(tracks)) if tracks[i].Type() == kind]


def vias(b):
    return items(b, pcbnew.PCB_VIA_T)


def put_via(b, x, y):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(b.FindNet("/GND"))
    b.Add(v)


# ground_fanout with the rule
b, fp = module()
gnd_pads = [p for p in fp.Pads() if p.GetNetname() == "/GND"]
n = kg.ground_fanout(b, "/GND", pad_clear=0.1, in_pad_ok=("U1.EP",))
check("a via for each GND pad", n == len(gnd_pads), "%d vias for %d pads" % (n, len(gnd_pads)))
bad = kg.vias_in_pad_openings(b, 0.1, allowed=("U1.EP",))
check("no drill within 0.1 mm of a mask opening", bad == [], str(bad))
ep = next(p for p in fp.Pads() if p.GetNumber() == "EP")
check("the exempt exposed pad keeps one via in the pad",
      sum(1 for v in vias(b) if ep.HitTest(v.GetPosition())) == 1)
necks = items(b, pcbnew.PCB_TRACE_T)
ends = {(t.GetEnd().x, t.GetEnd().y) for t in necks}
check("each via has its neck", len(necks) == n and ends == {(v.GetPosition().x, v.GetPosition().y) for v in vias(b)})
# the via's copper stays off every other pad's mask opening by more than the drill needs (no clipped corner)
check("vias stay 0.32 mm (their copper ring plus 0.02) off every opening but the exempt pad's", not [
    v for v in vias(b) for name, box in kg._mask_openings(b)
    if name != "U1.EP" and kg._pad_gap(to(v.GetPosition().x), to(v.GetPosition().y), box) < 0.32 - 1e-4])

old, _ = module()
kg.ground_fanout(old, "/GND")
check("without pad_clear the same board has open holes",
      len(kg.vias_in_pad_openings(old, 0.1, allowed=("U1.EP",))) > 0)

# the checker on single vias
b, fp = module()
pad1 = next(p for p in fp.Pads() if p.GetNumber() == "1")
px, py = to(pad1.GetPosition().x), to(pad1.GetPosition().y)
put_via(b, px, py)
found = kg.vias_in_pad_openings(b, 0.1)
check("a via in a pad is flagged", any(s.startswith("U1.1 ") for s in found), str(found))
check("... unless the pad is allowed", not any(s.startswith("U1.1 ") for s in kg.vias_in_pad_openings(b, 0.1, allowed=("U1.1",))))
for name, gap, expect in (("exactly on the rule", 0.25 + 0.01 + 0.0, False), ("0.05 mm short of it", 0.25 + 0.01 - 0.05, True)):
    b, fp = module()
    # pad 1's outer end faces -y: the opening ends at py - 0.5 - the mask expansion
    put_via(b, px, py - 0.5 - kg.SOLDER_MASK_EXPANSION - 0.15 - 0.1 + (0.05 if expect else 0.0) - 0.0)
    flagged = any(s.startswith("U1.1 ") for s in kg.vias_in_pad_openings(b, 0.1))
    check("a drill %s is %s" % (name, "flagged" if expect else "accepted"), flagged == expect, str(kg.vias_in_pad_openings(b, 0.1)))

# built cards
dirs = sys.argv[1:]
if not dirs:
    import boardevidence
    for card in CARDS:
        d = os.path.join(ROOT, "build", "hw", card)
        try:
            boardevidence.validate(card, d)
            dirs.append(d)
        except (ValueError, OSError, KeyError):
            print("skip %s: build/hw/%s is absent or stale" % (card, card))
for d in dirs:
    card = os.path.basename(os.path.normpath(d))
    board = pcbnew.LoadBoard(os.path.join(d, card + ".kicad_pcb"))
    bad = kg.vias_in_pad_openings(board, 0.1, allowed=("U1.57",) if card != "wifi" else ())
    check("%s: no open via hole in a pad" % card, bad == [], "; ".join(bad[:6]))
    ok_ep = kg.vias_in_pad_openings(board, 0.1)
    print("     %s: %s" % (card, "accepted open holes: " + ", ".join(ok_ep) if ok_ep else "none at all"))
sys.exit(1 if fails else 0)
