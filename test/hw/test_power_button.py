#!/usr/bin/env python3
"""MB-053: the main board's POWER button (power.md, On/off), from main.py.

    python3 test/hw/test_power_button.py

- the eFuse's EN/UVLO is the MAX16054's OUT, not tied to IN (tied to IN,
  the machine starts on when USB is plugged in)
- the MAX16054 runs from the standby LDO, whose input is VBUS_F (ahead of
  the eFuse: always powered), CLEAR held low, IN on the POWER switch
- EN has a pull-down to GND
- POWER and RESET: side by side on the front (south) edge, labelled
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hw", "boards"))
import main  # noqa: E402

fails = 0


def check(name, ok, detail=""):
    global fails
    print("%s %s%s" % ("pass" if ok else "FAIL", name, (": " + detail) if detail and not ok else ""))
    fails += not ok


specs = main.build_parts()
parts = {p.ref: p for p in specs}          # one unit per part is enough here


def one(lcsc):
    hits = [p for p in parts.values() if p.lcsc == lcsc]
    return hits[0] if len(hits) == 1 else None


efuse, toggle, ldo = one(main.POWER["EFUSE"][1]), one(main.POWER["ONOFF"][1]), one(main.POWER["STBY_LDO"][1])
check("one eFuse, one MAX16054, one standby LDO", efuse and toggle and ldo)
if efuse and toggle and ldo:
    en = efuse.conns["EN/UVLO"]
    check("eFuse EN/UVLO on the MAX16054's OUT", en == toggle.conns["OUT"], "EN on %s" % en)
    check("eFuse EN/UVLO not tied to IN", en != efuse.conns["IN"], "EN on %s: the machine starts on" % en)
    check("standby LDO from the eFuse's IN (always powered)", ldo.conns["VIN"] == efuse.conns["IN"])
    check("MAX16054 from the standby LDO", toggle.conns["VCC"] == ldo.conns["VOUT"])
    check("MAX16054 CLEAR on GND", toggle.conns["CLEAR"] == "GND")
    check("EN pulled down", any(p.lib == "Device:R" and set(p.conns.values()) == {en, "GND"} for p in parts.values()))
    sw = {p.value: p for p in parts.values() if p.lcsc == "C318884"}
    check("POWER and RESET switches", set(sw) == {"POWER", "RESET"}, str(sorted(sw)))
    if set(sw) == {"POWER", "RESET"}:
        check("POWER switch on the MAX16054's IN and GND",
              set(sw["POWER"].conns.values()) - {None} == {toggle.conns["IN"], "GND"})
        at = main.wanted(specs)
        (px, py), (rx, ry) = at[sw["POWER"].ref][:2], at[sw["RESET"].ref][:2]
        check("both on the front (south) edge", min(py, ry) >= main.H - 5.0, "y %.1f, %.1f" % (py, ry))
        check("side by side", abs(py - ry) < 0.1 and abs(px - rx) < 20.0)
        check("labelled", main.LABELS.get(sw["POWER"].ref) == "POWER" and main.LABELS.get(sw["RESET"].ref) == "RESET")
print("MB-053: %d failed" % fails)
sys.exit(1 if fails else 0)
