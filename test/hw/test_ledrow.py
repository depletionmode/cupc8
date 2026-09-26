#!/usr/bin/env python3
"""LED-001: every board's LEDs in one row with its power LED, along the top
edge (milestone-1.md, Indicator LEDs).

    python3 test/hw/test_ledrow.py

- the main board's placement as main.py computes it (wanted(), the source,
  in seconds): every LED on the power LED's line, near the top edge
- every board built under build/hw/<board>/: the same on the laid-out board
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, os.path.join(ROOT, "hw", "boards"))
import pcbnew  # noqa: E402

TOL = 0.25            # mm off the power LED's line
TOP = 6.0             # mm: the row's line from the body's top edge
fails = 0


def check(name, leds, pwr, top):
    """leds: {ref: (x, y)}; pwr: the power LED's ref; top: the top edge's y"""
    global fails
    y0 = leds[pwr][1]
    off = sorted(r for r, (x, y) in leds.items() if abs(y - y0) > TOL)
    ok = not off and y0 - top <= TOP
    print("%s %s: %d LEDs%s" % ("pass" if ok else "FAIL", name, len(leds),
                                "" if ok else ", LEDs off the power LED's row: %s (the row %.1f mm below the "
                                "top edge)" % (" ".join(off) or "none", y0 - top)))
    fails += not ok


# the main board, from its script
import main  # noqa: E402

parts = main.build_parts()
at = main.wanted(parts)
leds = {p.ref: at[p.ref][:2] for p in parts if p.lib == "Device:LED"}
check("main (source)", leds, "D6", main.OUTLINE[1])

# every board built
for pcb in sorted(glob.glob(os.path.join(ROOT, "build", "hw", "*", "*.kicad_pcb"))):
    name = os.path.basename(os.path.dirname(pcb))
    if os.path.basename(pcb) != name + ".kicad_pcb":
        continue
    b = pcbnew.LoadBoard(pcb)
    leds = {fp.GetReference(): (pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y))
            for fp in b.GetFootprints() if fp.GetFPIDAsString().startswith("LED_SMD:")}
    if not leds:
        continue
    # the power LED: the one nearest the top-left corner (power_led_at)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    pwr = min(leds, key=lambda r: (leds[r][0] - x0) ** 2 + (leds[r][1] - y0) ** 2)
    check(name, leds, pwr, y0)

print("LED-001: %d failed" % fails)
sys.exit(1 if fails else 0)
