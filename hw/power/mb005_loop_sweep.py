#!/usr/bin/env python3
"""MB-005: how much USB-C input-loop resistance the downstream checks allow.

    python3 hw/power/mb005_loop_sweep.py                  budget + analytic checks (seconds)
    python3 hw/power/mb005_loop_sweep.py --spice 20,100   also the ngspice decks at those mOhm (minutes)

design.R_RECEPTACLE (the "USB-C receptacle + VBUS/GND copper to the fuse
<= 20 mOhm loop" assumption) is the only term swept. Everything else in
design.r_in() stays as it is: the Type-C cable at its full IR-drop limit,
the input PTC at its maximum, the eFuse at its maximum RON, 5V_SYS copper at
its 20 mOhm. Each existing check keeps its own limit and its own `need`
margin; the sweep only reports the largest loop resistance at which it still
passes. It changes no requirement: that is a decision for David
(doc/hardware/mb005-loop-requirement-derivation.md).

Analytic rows (not in any existing check, prefixed X):
  X1  PWR_HI (POW-005 C4) with the ground offset a pull-up Rp sees: the
      cable's GND drop plus the GND half of the loop, at the M1 worst load
  X2  eFuse IN at a 3.0 A draw (the source's rating) vs its UVLO + 20 %
      (the margin POW-004 I4 uses)
  X3  3V3_STBY (HT7533-2) stays in regulation at the M1 worst load, so the
      POWER button's MAX16054 cannot reset
"""

import argparse
import concurrent.futures
import contextlib
import io
import os
import subprocess
import sys
import tempfile

import budget
import cc
import design as d
import spice
from spice import Checks

HERE = os.path.dirname(os.path.abspath(__file__))
R_HI = 0.35             # ohm: the search's upper end (budget.chain has no solution past ~0.4)
GND_SHARE = 0.5         # the fraction of the loop in the GND return (symmetric split)


def collect(fn, r_loop, argv=None):
    """Run a check module's main() with R_RECEPTACLE = r_loop and return
    {ident: (ok, value, limit, kind, need)}; its printout is swallowed."""
    got = {}
    orig_check, orig_r, orig_argv = Checks.check, d.R_RECEPTACLE, sys.argv

    def check(self, ident, what, value, limit, kind, unit="V", fmt="%.3f", need=0.0, fix=None):
        ok = orig_check(self, ident, what, value, limit, kind, unit, fmt, need, fix)
        got[ident] = (ok, value, limit, kind, need, what)
        return ok

    Checks.check, d.R_RECEPTACLE = check, r_loop
    sys.argv = argv or [fn.__module__ + ".py"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fn()
    finally:
        Checks.check, d.R_RECEPTACLE, sys.argv = orig_check, orig_r, orig_argv
    return got


def analytic(r_loop):
    """The X rows at one loop resistance: {ident: (ok, value, limit, kind, need, what)}."""
    old, d.R_RECEPTACLE = d.R_RECEPTACLE, r_loop
    try:
        worst = budget.chain("worst")
    finally:
        d.R_RECEPTACLE = old
    i = worst["itot"]
    v_off = i * (d.CABLE_R_GND + GND_SHARE * r_loop)
    rise_max = cc.pwr_hi_trips()[0]
    v3a = float("inf")
    for kind, val, tol in d.RP_SOURCES["3.0A"]:
        r = cc.rd_eff(d.RD * (1 - d.RD_TOL))
        if kind == "I":         # a current source: I x Rd, whatever the ground offset
            v = (val * (1 - tol) - d.ADC_LEAK) * r
        else:                   # a pull-up to the source's rail, seen from our ground
            v = (d.RP_PULLUP[kind][0] - v_off) * r / (val * (1 + tol) + r) - d.ADC_LEAK * r
        v3a = min(v3a, v)
    i_src = d.SOURCE_CLASSES[d.FULL_CLASS]
    v_in = d.VBUS_MIN - i_src * (d.CABLE_R_VBUS + d.CABLE_R_GND + r_loop + d.FUSE_IN_R_MAX)
    v_f = d.VBUS_MIN - i * (d.CABLE_R_VBUS + d.CABLE_R_GND + r_loop + d.FUSE_IN_R_MAX)
    rows = {
        "X1": (rise_max, v3a, "<=", 0.0, "PWR_HI highest trip vs 3.0 A class minimum with %.0f mV GND offset"
               % (1e3 * v_off)),
        "X2": (v_in, d.INSW_UVLO * 1.2, ">=", 0.0, "eFuse IN at a 3.0 A draw vs UVLO + 20 %"),
        "X3": (v_f - d.STBY_LDO_DROPOUT, d.STBY_LDO_VOUT[1], ">=", 0.0,
               "HT7533 input minus dropout at the M1 worst load vs 3V3_STBY max"),
    }
    out = {}
    for ident, (value, limit, kind, need, what) in rows.items():
        margin = value - limit if kind == ">=" else limit - value
        out[ident] = (margin >= need * abs(limit), value, limit, kind, need, what)
    return out


def fast(r_loop):
    """POW-006 and the X rows at one loop resistance."""
    got = {"POW-006 " + k: v for k, v in collect(budget.main, r_loop).items()}
    got.update({"analytic " + k: v for k, v in analytic(r_loop).items()})
    return got


def limits(evaluate, r_hi=R_HI, tol=1e-5):
    """{name: largest loop resistance (ohm) at which it passes}, by bisection.
    None: fails even at 0; inf: passes up to r_hi. Checks whose value does not
    move with the loop are dropped. Assumes each check is monotonic in R,
    which a grid pre-scan confirms."""
    base, top = evaluate(0.0), evaluate(r_hi)
    grid = [evaluate(r_hi * k / 16) for k in range(17)]
    found = {}
    for name, (ok0, v0, lim0, *_rest) in base.items():
        if abs(top[name][1] - v0) < 1e-9 and abs(top[name][2] - lim0) < 1e-9:
            continue
        passes = [g[name][0] for g in grid]
        if any(b and not a for a, b in zip(passes, passes[1:])):
            raise ValueError("%s is not monotonic in the loop resistance" % name)
        if not ok0:
            found[name] = None
            continue
        if top[name][0]:
            found[name] = float("inf")
            continue
        lo, hi = 0.0, r_hi
        while hi - lo > tol:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if evaluate(mid)[name][0] else (lo, mid)
        found[name] = lo
    return found, base


def ipc2221_rise(current, width_mm, thickness_um, internal=False):
    """Steady temperature rise (C) of a lone trace, IPC-2221B's fit
    I = k dT^0.44 A^0.725 (A in mil^2; k 0.048 outer, 0.024 inner). IPC-2152
    finds inner layers run about as cool as outer ones, and an adjacent plane
    cooler still, so the outer k is the IPC-2152-style estimate for both and
    the inner k an upper bound. Past ~100 C rise it is off the charts."""
    area = (width_mm / 0.0254) * (thickness_um / 25.4)
    return (current / ((0.024 if internal else 0.048) * area ** 0.725)) ** (1 / 0.44)


# (label, drawn width mm, finished thickness um): the MB-005 route's segments
# at main_input_heat.py's sensitivity copper (80 % width, 24.9 / 11.4 um) and
# nominal, and wider outer-layer alternatives
HEAT_ROWS = (
    ("J1-F1 F.Cu 0.5 mm, nominal 1 oz", 0.5, 34.8),
    ("J1-F1 F.Cu 0.5 mm, sensitivity (0.4 mm x 24.9 um)", 0.4, 24.9),
    ("F1-U2 In2 0.5 mm alone, sens. (0.4 mm x 11.4 um)", 0.4, 11.4),
    ("F1-U2 In3 1.0 mm alone, sens. (0.8 mm x 11.4 um)", 0.8, 11.4),
    ("outer 2.0 mm, sensitivity (1.6 mm x 24.9 um)", 1.6, 24.9),
    ("outer 3.0 mm, sensitivity (2.4 mm x 24.9 um)", 2.4, 24.9),
    ("outer 4.0 mm, sensitivity (3.2 mm x 24.9 um)", 3.2, 24.9),
)


SPICE = {
    "POW-001": ("buck", None), "POW-003": ("buck", ["buck.py", "wifi-card"]), "POW-004": ("inrush", None),
    "POW-007": ("boost", None), "POW-008": ("hdmi", None),
}


def spice_one(test, r_mohm):
    """Run one ngspice check at one loop resistance in its own process and
    scratch directory (build/power stays untouched). Returns its records."""
    with tempfile.TemporaryDirectory(prefix="mb005_") as scratch:
        code = ("import sys, json, importlib; sys.path.insert(0, %r)\n"
                "import spice, mb005_loop_sweep as s\n"
                "spice.OUT = %r\n"
                "m = importlib.import_module(%r)\n"
                "got = s.collect(m.main, %r, %r)\n"
                "print('JSON' + json.dumps(got))\n") % (HERE, scratch, SPICE[test][0], r_mohm / 1e3,
                                                        SPICE[test][1])
        proc = subprocess.run([sys.executable, "-c", code], cwd=HERE, capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("JSON")]
    if not lines:
        return {"error": proc.stderr.strip().splitlines()[-1:] or ["no output"]}
    import json
    return json.loads(lines[-1][4:])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spice", help="comma-separated loop resistances in mOhm for the ngspice checks")
    args = parser.parse_args()

    found, base = limits(fast)
    print("Largest USB-C input loop (design.R_RECEPTACLE) each check allows, everything else unchanged")
    print("(current assumption %.0f mOhm)" % (1e3 * d.R_RECEPTACLE))
    for name, r in sorted(found.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)):
        what = base[name][5]
        shown = "fails at 0" if r is None else ("> %.0f" % (1e3 * R_HI) if r == float("inf") else "%.1f" % (1e3 * r))
        print("  %-16s %10s mOhm  %s" % (name, shown, what))

    amps = d.insw_ilim()[2]
    print("Trace self-heating at the eFuse's %.3f A maximum limit (IPC-2221B fit; outer k = "
          "IPC-2152-style estimate, inner k = upper bound):" % amps)
    for label, width, um in HEAT_ROWS:
        print("  %-52s %6.1f C  (inner-k bound %6.1f C)" % (
            label, ipc2221_rise(amps, width, um), ipc2221_rise(amps, width, um, internal=True)))

    if args.spice:
        values = [float(x) for x in args.spice.split(",")]
        jobs = [(t, r) for r in values for t in SPICE]
        with concurrent.futures.ThreadPoolExecutor(max(1, (os.cpu_count() or 2) // 3)) as pool:
            res = dict(zip(jobs, pool.map(lambda j: spice_one(*j), jobs)))
        print("ngspice checks at each loop resistance (pass/FAIL, value, limit, margin):")
        for test in SPICE:
            for r in values:
                got = res[(test, r)]
                if "error" in got:
                    print("  %s @ %5.0f mOhm: error %s" % (test, r, got["error"]))
                    continue
                for ident, (ok, value, limit, kind, need, what) in sorted(got.items()):
                    margin = value - limit if kind == ">=" else limit - value
                    print("  %s @ %5.0f mOhm %-4s %-5s %.4f %s %.4f margin %+.4f  %s" % (
                        test, r, "pass" if ok else "FAIL", ident, value, kind, limit, margin, what))
    return 0


if __name__ == "__main__":
    sys.exit(main())
