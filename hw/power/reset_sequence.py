#!/usr/bin/env python3
"""MB-051 start-up, brown-out and fault sequences of the reset qualifier (ngspice).

The two comparators are TI's OPAx376 PSpice model (fetched and ported by
models/fetch.py). The REF3425, the MAX811 and the LVC07 have no vendor
models that run here, so they are behavioural blocks bounded by their
datasheet limits (hw/power/reset_supervisor.py):

  - REF3425: its output at the worst-case corner under test, following
    +3V3 less its 100 mV dropout, with a 1 ms first-order turn-on;
  - MAX811T: RESET low while +3V3 < VTH or ~MR < VCC/2, and for tRP after
    both clear; tRP is its 140 ms minimum (the early-release corner); an
    undefined output below VCC = 1 V is modelled open (only R_NPOR_PD holds);
  - SN74LVC07A: SLOTn_RST_n pulled to GND (25 ohm) while nPOR < 1.4 V
    (between its 0.8 V VIL and 2.0 V VIH), from 3V3_STBY.

A slot line is also pulled up by a card that is powered from slot +5V
(50 kOhm to its own 3.3 V), the cold-off case. Each scenario checks the
contract: nPOR and the slot reset are high only while +3V3 and +1V2 are
both inside their valid ranges and the RESET button is released, and
release comes only after both are good; and, where the rail falls, the
rail at the moment the qualifier's output switches.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reset_supervisor as rs  # noqa: E402
import spice  # noqa: E402

TRP = rs.MAX811_TRP[0]


def deck(v33, v12, button, card, ref, vth811, tstop, maxstep, trp=TRP):
    """One scenario: PWL waveforms for +3V3, +1V2, the button (1 = pressed)
    and the card's own supply; ref the REF3425 output corner."""
    pwl = lambda pts: "PWL(" + " ".join("%g %g" % p for p in pts) + ")"
    return f"""
V33 v33 0 {pwl(v33)}
V12 v12 0 {pwl(v12)}
VSTBY stby 0 3.3
VCARD vcard 0 {pwl(card)}
VBTN btn 0 {pwl(button)}
* REF3425 on +3V3, 1 ms turn-on
BREF ref0 0 V = min({ref}, max(V(v33) - 0.1, 0))
RREF ref0 refrc 1k
CREF refrc 0 1u
EREF vref 0 refrc 0 1
RL1 vref t33 {rs.R_L1}
RL2 t33 t12 {rs.R_L2}
RL3 t12 0 {rs.R_L3}
* +3V3 monitor (U18) and +1V2 monitor (U20)
RT v33 mon33p {rs.R_T}
RB mon33p 0 {rs.R_BT}
RF33 ok33 mon33p {rs.R_F33}
X18 mon33p t33 v33 0 ok33 OPAx376
RS v12 mon12p {rs.R_S}
RF12 ok12 mon12p {rs.R_F12}
X20 mon12p t12 v33 0 ok12 OPAx376
CD1 v33 0 1n
* the comparator outputs' board capacitance
CO33 ok33 0 100p
CO12 ok12 0 100p
* D7 BAT54A: common anode on nMR
DA nmr ok33 BAT54
DB nmr ok12 BAT54
.model BAT54 D(IS=1e-7 N=1.35 RS=1 CJO=10p)
* MAX811T: 20k ~MR pull-up, the RESET button to GND
RMR v33 nmr 20k
SBTN nmr 0 btn 0 SWB
.model SWB SW(VT=0.5 VH=0.1 RON=10 ROFF=1e12)
BOK ok811 0 V = (V(v33) > {vth811} && V(nmr) > 0.5 * V(v33)) ? 1 : 0
STMR tmr 0 ok811 0 SWR
.model SWR SW(VT=0.5 VH=0.1 RON=1e12 ROFF=1)
GTMR 0 tmr ok811 0 1u
CTMR tmr 0 1u
BNPOR npord 0 V = (V(ok811) > 0.5 && V(tmr) > {trp}) ? V(v33) : 0
SDRV npord npor v33 0 SWD
.model SWD SW(VT=1.0 VH=0.05 RON=100 ROFF=1e12)
RPD npor 0 {rs.R_NPOR_PD}
* one SLOTn_RST_n: 10k to +3V3, the card's 50k to its own supply, LVC07 from 3V3_STBY
RPU v33 slot 10k
RCARD vcard slot 50k
SLVC slot 0 npor 0 SWL
.model SWL SW(VT=1.4 VH=0.01 RON=1e12 ROFF=25)
.options method=gear
.tran {maxstep} {tstop} 0 {maxstep}
.control
run
wrdata reset_seq.dat v(v33) v(v12) v(npor) v(slot) v(ok33) v(ok12) v(nmr) v(t12) v(t33)
.endc
"""


def run_case(name, v33, v12, button=((0, 0),), card=((0, 3.3),), ref=rs.VREF, vth811=3.0,
             tstop=0.45, maxstep=20e-6, trp=TRP):
    spice.run("mb051_" + name, deck(v33, v12, button, card, ref, vth811, tstop, maxstep, trp),
              libs=("OPAx376.LIB",), timeout=1800)
    os.replace(os.path.join(spice.OUT, "reset_seq.dat"), os.path.join(spice.OUT, "mb051_%s.dat" % name))
    t, v33w, v12w, npor, slot, ok33, ok12, nmr, t12, t33 = spice.wave("mb051_" + name)
    return dict(t=t, v33=v33w, v12=v12w, npor=npor, slot=slot, ok33=ok33, ok12=ok12, nmr=nmr)


def released(w, key, level=2.0):
    return [w[key][k] > level for k in range(len(w["t"]))]


def contract(w, pressed=lambda t: False, need33=rs.V33_MIN, need12=rs.V12_MIN):
    """(violations, first release time): nPOR or the slot line high while a
    rail is out of range or the button is held."""
    bad, first = [], None
    for k, t in enumerate(w["t"]):
        up = w["npor"][k] > 2.0 or w["slot"][k] > 2.0
        if up and first is None:
            first = t
        if up and (w["v33"][k] < need33 or w["v12"][k] < need12 or pressed(t)):
            bad.append(t)
    return bad, first


def rail_at_switch(w, key, rail):
    """The rail when `key` (a comparator output) first falls below 1 V after
    having been high."""
    was = False
    for k, t in enumerate(w["t"]):
        if w[key][k] > 2.0:
            was = True
        elif was and w[key][k] < 1.0:
            return t, w[rail][k]
    return None, None


def run(c):
    lo, hi = rs.VREF * (1 - rs.REF_ERR), rs.VREF * (1 + rs.REF_ERR)
    up33 = [(0, 0), (2e-3, 0), (2.7e-3, 3.24)]            # POW-001: 0.7 ms rise to the DC low corner
    up12 = [(0, 0), (2.3e-3, 0), (2.8e-3, 1.172)]          # the LDO after +3V3 passes ~1.5 V; its worst low

    # 1. normal start-up, reference at its high corner (latest release)
    w = run_case("startup", up33, up12, ref=hi)
    bad, first = contract(w)
    c.check("S1", "start-up (3V3 0.7 ms to 3.24 V, 1V2 to 1.172 V): nPOR/slot high while a rail is out of range",
            len(bad), 0, "<=", "samples", fmt="%d")
    good = next(t for k, t in enumerate(w["t"]) if w["v33"][k] >= rs.V33_MIN and w["v12"][k] >= rs.V12_MIN)
    c.check("S1b", "start-up: release after both rails are valid, vs U6's 140 ms timeout (less 0.5 % for "
            "the time step)", 1e3 * ((first or 1.0) - good), 0.995 * 1e3 * TRP, ">=", "ms")

    # 2. +1V2 never comes up (LDO failed): everything stays in reset; a
    #    card powered from its own supply is held too
    w = run_case("no1v2", up33, [(0, 0)], ref=lo)
    bad, first = contract(w)
    c.check("S2", "+3V3 good, +1V2 absent: nPOR and slot stay low (first release, s; none = 1e9)",
            first if first is not None else 1e9, 1e8, ">=", "s", fmt="%.3g")

    # 3. machine off (+3V3 absent, 3V3_STBY up), card on slot +5V pulling RUN up
    w = run_case("off", [(0, 0)], [(0, 0)], card=[(0, 3.3)], ref=lo, tstop=0.05, maxstep=50e-6)
    c.check("S3", "+3V3 absent, card self-powered: slot reset maximum", max(w["slot"]), 0.8, "<=", "V")

    # 4. slow +1V2 brown-out after release, reference at its low corner
    #    (latest assertion): +1V2 at the comparator's switch
    dn12 = up12 + [(0.30, 1.172), (0.40, 1.10)]
    w = run_case("brown1v2", up33, dn12, ref=lo)
    t, v = rail_at_switch(w, "ok12", "v12")
    c.check("S4", "slow +1V2 brown-out (0.7 mV/ms): +1V2 when the 1V2 comparator trips vs the 1.140 V floor",
            v if v is not None else 0, rs.V12_MIN, ">=", "V")
    bad, _ = contract(w)
    c.check("S4b", "slow +1V2 brown-out: nPOR/slot high below the floor", len(bad), 0, "<=", "samples", fmt="%d")

    # 5. slow +3V3 brown-out to 3.10 V
    dn33 = up33 + [(0.30, 3.24), (0.40, 3.10)]
    w = run_case("brown3v3", dn33, up12, ref=lo, vth811=3.0)
    t, v = rail_at_switch(w, "ok33", "v33")
    c.check("S5", "slow +3V3 brown-out (1.4 mV/ms): +3V3 when the 3V3 comparator trips vs the 3.135 V floor",
            v if v is not None else 0, rs.V33_MIN, ">=", "V")
    bad, _ = contract(w)
    c.check("S5b", "slow +3V3 brown-out: nPOR/slot high below the floor", len(bad), 0, "<=", "samples", fmt="%d")

    # 6. fast +3V3 collapse (buck input lost at 1.22 A into ~67 uF: 18 mV/us)
    t0 = 6e-3                  # U6's timeout shortened to 1 ms here: this case is about the fall
    # (to 2.90 V and held: below that U6's own threshold owns the reset, and
    # the op amps' 2.2 V minimum supply is not modelled)
    dnf = up33 + [(t0, 3.24), (t0 + 0.34 / 18e3, 2.90)]
    w = run_case("collapse3v3", dnf, up12, ref=lo, maxstep=0.5e-6, tstop=t0 + 0.3e-3, trp=1e-3)
    tn = next((t for k, t in enumerate(w["t"]) if t > t0 and w["npor"][k] < 0.8), None)
    vfloor = next((t for k, t in enumerate(w["t"]) if t > t0 and w["v33"][k] < rs.V33_MIN), None)
    c.info("S6 fast collapse", "+3V3 at 18 mV/us: below 3.135 V at +%.1f us, nPOR low at +%.1f us "
           "(the qualifier's own delay; U6's VCC path alone is 20 us)" %
           (1e6 * (vfloor - t0), 1e6 * ((tn or t0) - t0)))
    delay = (tn or 1.0) - (vfloor or t0)
    c.check("S6", "fast +3V3 collapse: nPOR low within 10 us of +3V3 leaving its range",
            1e6 * delay, 10.0, "<=", "us")

    # 7. RESET button: 50 ms press after release
    press = [(0, 0), (0.25, 0), (0.2501, 1), (0.30, 1), (0.3001, 0)]
    w = run_case("button", up33, up12, button=press, ref=hi, tstop=0.60)
    bad, _ = contract(w, pressed=lambda t: 0.2502 <= t <= 0.30)
    c.check("S7", "RESET button held 50 ms: nPOR/slot high while held", len(bad), 0, "<=", "samples", fmt="%d")
    back = next((t for k, t in enumerate(w["t"]) if t > 0.30 and w["npor"][k] > 2.0), None)
    c.check("S7b", "RESET released: nPOR stays low for U6's timeout", 1e3 * ((back or 1.0) - 0.30), 140.0,
            ">=", "ms")

    # 8. no nuisance trip at the regulators' worst lows (with the source drops)
    lo33 = min(v[1] for k, v in rs.windows().items() if k.startswith("3V3"))
    lo12 = rs.windows()["1V2"][1]
    w = run_case("nuisance", [(0, 0), (2e-3, 0), (2.7e-3, lo33)], [(0, 0), (2.3e-3, 0), (2.8e-3, lo12)],
                 ref=hi, tstop=0.30)
    c.check("S8", "rails at their worst regulator lows (%.4f / %.4f V): nPOR released" % (lo33, lo12),
            w["npor"][-1], 2.0, ">=", "V")
