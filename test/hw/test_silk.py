#!/usr/bin/env python3
"""SILK-001: kicadgen's designator rules on a small board, in seconds.

    python3 test/hw/test_silk.py

- check_designators flags a designator over a via, over another part's
  courtyard, over a part's body, and the board's name over a via
- place_designators(reseat=True) moves a designator off a via that landed
  under it, and then the check is clean
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import pcbnew  # noqa: E402

mm = pcbnew.FromMM
OUTLINE = (0, 0, 30, 20)
fails = 0


def check(name, ok, detail=""):
    global fails
    print("%s %s%s" % ("pass" if ok else "FAIL", name, (": " + detail) if detail and not ok else ""))
    fails += not ok


def board():
    b = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(b, "/N")
    b.Add(net)
    for ref, x in (("R1", 8), ("R2", 20)):
        fp = pcbnew.FootprintLoad(kg.footprint_dir("Resistor_SMD"), "R_0603_1608Metric")
        fp.SetReference(ref)
        b.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(10)))
    kg.place_designators(b, OUTLINE)
    kg.mark_revision(b, "TEST", "A", (29, 19))
    return b, net


def via(b, net, at):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(mm(at[0]), mm(at[1])))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(net)
    b.Add(v)


b, net = board()
check("clean board", kg.check_designators(b) == [], str(kg.check_designators(b)))

# a via under R1's designator
t = b.FindFootprintByReference("R1").Reference()
at = t.GetPosition()
via(b, net, (pcbnew.ToMM(at.x), pcbnew.ToMM(at.y)))
bad = kg.check_designators(b)
check("designator over a via", "designator R1 over a via of /N" in bad, str(bad))
moved = kg.place_designators(b, OUTLINE, reseat=True)
check("reseat moves it", moved == ["R1"], str(moved))
check("clean after the reseat", kg.check_designators(b) == [], str(kg.check_designators(b)))

# R1's designator over R2's courtyard and body
b, net = board()
r2 = b.FindFootprintByReference("R2").GetPosition()
b.FindFootprintByReference("R1").Reference().SetPosition(r2)
bad = kg.check_designators(b)
check("designator over another courtyard", "designator R1 over the courtyard of R2" in bad, str(bad))
check("designator over a body", "designator R1 over the body of R2" in bad, str(bad))

# the board's name over a via
b, net = board()
via(b, net, (27, 18.5))
bad = kg.check_designators(b)
check("name over a via", "'TEST rev A' over a via of /N" in bad, str(bad))

print("SILK-001: %d failed" % fails)
sys.exit(1 if fails else 0)
