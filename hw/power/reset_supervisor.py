#!/usr/bin/env python3
"""MB-051: the main board's dual-rail reset qualifier (David, 2026-09-28).

    +3V3 ─ U17 REF3425 ─ VREF25 ─ R_L1 ─ T33 ─ R_L2 ─ T12 ─ R_L3 ─ GND   (0.1 % ladder)
    +3V3 ─ R_T ─ MON33_P ─ R_BT ─ GND ; MON33_OK ─ R_F33 ─ MON33_P
           U18 OPA376: IN+ MON33_P, IN- T33, out MON33_OK   (high: +3V3 good)
    +1V2 ─ R_S ─ MON12_P ;              MON12_OK ─ R_F12 ─ MON12_P
           U20 OPA376: IN+ MON12_P, IN- T12, out MON12_OK   (high: +1V2 good)
    MON33_OK, MON12_OK ─ D7 BAT54A cathodes; its common anode on nMR (U6 MAX811T
           ~MR, SW1 RESET, SYS_nRST)                  nPOR ─ R_NPOR_PD ─ GND
    U19 SN74LVC07A on 3V3_STBY: six open-drain buffers, A = nPOR, Y = SLOTn_RST_n

The comparators are precision op amps run open loop with resistor
hysteresis: a comparator's own offset (TLV7011/TLV1811/TLV3012: 4-15 mV max)
is wider than the whole 1V2 window, and the zero-drift OPA333 first tried
recovers from saturation in ~440 us (its TI model), where the OPA376 (25 uV,
2 uV/C, 0.33 us overload recovery) switches in a few us. U17, U18 and U20 run
from +3V3: below 3.00-3.15 V U6 holds nPOR low by itself, and U6's 140-560 ms
timeout after ~MR goes high outlasts the reference's 2.5 ms turn-on, so the
qualifier is only needed, and only relied on, while +3V3 is inside U6's
threshold. Either comparator low pulls ~MR low through its diode; U6 then
holds nPOR low until both rails, the RESET button and SYS_nRST have let go
for its timeout. U19 holds all six SLOTn_RST_n low whenever nPOR is low, in
parallel with the TCA9555 (which only ever drives low: fw/sysctl/core/power.c
expander_apply) and the 10k pull-ups; it runs from 3V3_STBY, so a card on
slot +5V is held while +3V3 is absent, when U6 is unpowered and R_NPOR_PD
keeps nPOR low.

The links R7 (3V3_BUCK -> +3V3) and R8 (1V2_LDO -> +1V2) become 1 mOhm alloy
shunts: a 0 ohm jumper (<= 50 mOhm) drops 31-61 mV at 0.62-1.22 A of 3V3,
more than the whole 3V3 window.

This file holds the fitted values and datasheet limits, and computes modeled
threshold windows by enumerating the tolerance and input-bias corners. The
1 nA input-bias bound is an engineering allowance: TI specifies a 25 C
maximum, with typical curves at higher temperatures. Qualification therefore
includes the first-article reset measurements at the specified ambient.
The routed-board binding is hw/power/rail_reset_window.py (MB-051).

    python3 hw/power/reset_supervisor.py            # threshold windows (fast)
    python3 hw/power/reset_supervisor.py --spice    # + ngspice sequences
"""

from itertools import product
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design as d  # noqa: E402

# ---------------------------------------------------------------- parts (LCSC)
PARTS = {
    "U17": ("REF3425IDBVR", "C187836"),     # TI REF34 SBAS804G: 2.5 V, +-0.05 %, 6 ppm/C (box), 95 uA
    "U18": ("OPA376AIDBVR", "C42134"),      # TI SBOS406G: Vos 25 uV, 2 uV/C, 2 V/us, 0.33 us overload
    "U20": ("OPA376AIDBVR", "C42134"),      #   recovery; the 3V3 (U18) and 1V2 (U20) comparators
    "U19": ("SN74LVC07APWR", "C7809"),      # TI SCAS595: hex open-drain buffer, 1.65-5.5 V, Ioff
    "D7": ("BAT54ALT1G", "C92068"),         # onsemi BAT54ALT1: common anode, VF <= 0.32 V at 1 mA
    "R7": ("RLM12FTCMR001", "C393098"),     # 1 mOhm +-1 % 1206 alloy shunts as the 3V3 and
    "R8": ("RLM12FTCMR001", "C393098"),     #   1V2 links (a 0 ohm jumper is only <= 50 mOhm)
}
# 0.1 %, +-10 ppm/C thin film, 0603 (values and LCSC with >= 1000 in stock, 2026-09-28)
R_PREC = {4.12e3: "C861436", 9.53e3: "C705800",   # these two are 25 ppm/C: see R_TOL_25
          7.5e3: "C408767", 1e3: "C394536", 2e3: "C394539", 4.7e3: "C860425", 10e3: "C860067", 12e3: "C860098",
          13e3: "C705706", 16e3: "C860148", 18e3: "C860169", 20e3: "C408766", 22e3: "C860236",
          24e3: "C860256", 27e3: "C860277", 30e3: "C860320", 33e3: "C705707", 39e3: "C860362",
          43e3: "C860392", 47e3: "C860407", 100e3: "C394537", 120e3: "C860087", 150e3: "C860126",
          180e3: "C860161", 200e3: "C394540", 220e3: "C860227", 270e3: "C860272", 300e3: "C860312",
          330e3: "C860332"}

# ---------------------------------------------------------------- circuit values
R_L1, R_L2, R_L3 = 7.5e3, 4.12e3, 10e3  # VREF25 -> T33 (1.633 V) -> T12 (1.156 V) -> GND, 0.1 %
R_T, R_BT, R_F33 = 9.53e3, 10e3, 6.8e6   # +3V3 -> MON33_P -> GND (0.1 %) ; MON33_OK -> MON33_P (1 %)
R_S, R_F12 = 1.0e3, 2.7e6              # +1V2 -> MON12_P ; MON12_OK -> MON12_P (1 %)
R_1PCT = {1e3: "C21190", 2.7e6: "C26095", 6.8e6: "C23213", 100e3: "C25803"}   # 1 % 0603
R_NPOR_PD = 100e3                      # nPOR -> GND (U6 unpowered)

# ---------------------------------------------------------------- datasheet limits
VREF = 2.5
V33_OP = (3.135, 3.465)         # +3V3 over which the 1V2 comparator must be right (below: U6 holds)
REF_ERR = (500 +                # initial accuracy, 25 C (max)
           6 * 165 +            # temperature coefficient, box method over -40..125 C (max)
           100 +                # long-term drift allowance (typ 25 + 10 ppm over 2000 h)
           60 +                 # thermal hysteresis allowance (typ 30 ppm, cycle 1)
           200 +                # solder-heat shift allowance (DS fig 7-2: all units < 100 ppm)
           15 * (V33_OP[1] - 2.6)) * 1e-6   # line regulation 15 ppm/V (max) from VOUT + VDO
R_TOL = 0.001 + 10e-6 * 60      # 0.1 % plus 10 ppm/C over 25 +- 60 C
R_TOL_25 = 0.001 + 25e-6 * 60   # R_L2 (4.12k) and R_T (9.53k) are stocked only at 25 ppm/C
R_TOL_1PCT = 0.01 + 100e-6 * 60 # an ordinary 1 % part
VOS = (25e-6 + 2e-6 * 100 +     # OPA376 Vos (max) + drift (max, -40..125 C) over 100 C
       0.5 * 10 ** (-76 / 20) + # CMRR 76 dB (min) over the <= 0.5 V from its VS/2 test point
       20e-6 * 0.35)            # PSRR 20 uV/V (max) over the +3V3 range
IB = 1e-9                       # OPA376 input bias allowance (10 pA max at 25 C; hot typ curves)
VO_SWING = 0.050                # OPA376 output swing from either rail (40 mV max, 10k, -40..125 C)

MAX811_TRP = (0.140, 0.560)     # s, reset active timeout (ADI MAX811 DS, -40..85 C)
MAX811_MR_PULLUP = (10e3, 30e3)
MAX811_MR_VIL = 0.25            # x VCC, VCC > VTH(max)
MAX811_TMD = 0.5e-6             # MR to reset propagation (typ; DS gives no max)
MAX811_VTH = (3.00, 3.15)       # its own +3V3 threshold, -40..85 C
BAT54_VF_1MA = 0.32             # 25 C max at 1 mA
BAT54_VF_COLD = 0.10            # allowance for the rise at -40..0 C

# ---------------------------------------------------------------- rails and loads
V33_MIN, V12_MIN = d.V3V3_MIN, d.V1V2_MIN            # 3.135 V, 1.140 V: the valid floors
POW001_3V3_LOW = 3.238          # POW-001 P4h: 0->500 mA step minimum at the DC low corner
POW002_1V2_LOW = 1.1715         # POW-002 same model/corner at conservative 46 mA: L6 1.171569 V,
                               # rounded down; includes core + auxiliary + loose sense bound
I_3V3 = {"M1": 0.617, "slots 5-6 full": 1.22}       # power.md: M1 max; with 2 x 300 mA future cards
I_1V2 = d.I_1V2_MAX + 0.001     # the chipset core + the 1V2 LED base and sense branches
R_LINK33 = 0.001 * 1.01 * (1 + 200e-6 * 95)          # R7 at 115 C: 1 % and 200 ppm/C
R_LINK12 = R_LINK33             # R8, the same 1 mOhm shunt
# copper allowances the routed board must meet (rail_reset_window.py extracts them)
CU33_MAX = 0.010                # R7:2 to the 3V3 sense point and to every U7 +3V3 pin
CU12_MAX = 0.030                # R8:2 to the 1V2 sense point and to every U7 +1V2 pin
MARGIN_MIN = 0.005              # required clearance on each side of each window
M1_WINDOWS = ('3V3 M1', '1V2')   # slots 5-6 are future cards, outside the M1 release load


def _signs(n):
    return product((-1, 1), repeat=n)


def taps(l1=None, l2=None, l3=None):
    """[(T33, T12)] at every reference and ladder tolerance corner."""
    l1, l2, l3 = l1 or R_L1, l2 or R_L2, l3 or R_L3
    out = []
    for sv, s1, s2, s3, si33, si12 in _signs(6):
        vr = VREF * (1 + sv * REF_ERR)
        a, b, c = l1 * (1 + s1 * R_TOL), l2 * (1 + s2 * R_TOL_25), l3 * (1 + s3 * R_TOL)
        g1, g2 = 1 / a + 1 / b, 1 / b + 1 / c
        det = g1 * g2 - 1 / b**2
        # Exact two-node KCL, including both independent IN- bias currents.
        rhs33, rhs12 = vr / a - si33 * IB, -si12 * IB
        out.append(((g2 * rhs33 + rhs12 / b) / det,
                    (rhs33 / b + g1 * rhs12) / det))
    return out


def thresholds_3v3(r_t=None, r_bt=None, r_f=None, tap=None):
    """(fall_min, fall_max, rise_min, rise_max) of +3V3 at R_T's rail end.
    The comparator runs from +3V3 itself: its high output is the rail less
    up to VO_SWING, its low output 0..VO_SWING."""
    r_t, r_bt, r_f = r_t or R_T, r_bt or R_BT, r_f or R_F33
    falls, rises = [], []
    for (t33, _), et, eb, ef, sv, sw, sib in product(tap or taps(), (-1, 1), (-1, 1), (-1, 1), (-1, 1), (0, 1), (-1, 1)):
        rt, rb, rf = r_t * (1 + et * R_TOL_25), r_bt * (1 + eb * R_TOL), r_f * (1 + ef * R_TOL_1PCT)
        vp = t33 + sv * VOS
        g = 1 / rt + 1 / rb + 1 / rf
        sw_v = sw * VO_SWING
        rises.append((vp * g - sw_v / rf + sib * IB) / (1 / rt))          # output low: VOL = sw_v
        falls.append((vp * g + sw_v / rf + sib * IB) / (1 / rt + 1 / rf)) # output high: V33 - sw_v
    return min(falls), max(falls), min(rises), max(rises)


def thresholds_1v2(r_s=None, r_f=None, tap=None):
    """(fall_min, fall_max, rise_min, rise_max) of +1V2 at R_S's rail end."""
    r_s, r_f = r_s or R_S, r_f or R_F12
    falls, rises = [], []
    for (_, t12), es, ef, sv, sw, v33, sib in product(tap or taps(), (-1, 1), (-1, 1), (-1, 1), (0, 1), V33_OP, (-1, 1)):
        rs, rf = r_s * (1 + es * R_TOL_1PCT), r_f * (1 + ef * R_TOL_1PCT)
        vp = t12 + sv * VOS
        for vout, out in ((sw * VO_SWING, rises), (v33 - sw * VO_SWING, falls)):
            out.append(vp + (vp - vout) * rs / rf + sib * IB * rs)
    return min(falls), max(falls), min(rises), max(rises)


def windows(cu33=CU33_MAX, cu12=CU12_MAX):
    """Per rail: (floor + load drop, regulator low - source drop) at the sense
    point, for each 3V3 load case. The drop from the regulator to any point,
    and between the sense point and any load, is at most the total current
    times the driving-point resistance from the link to the farther point
    (a transfer resistance never exceeds the driving-point one)."""
    out = {}
    for case, i in I_3V3.items():
        out["3V3 " + case] = (V33_MIN + i * cu33, POW001_3V3_LOW - i * (R_LINK33 + cu33))
    out["1V2"] = (V12_MIN + I_1V2 * cu12, POW002_1V2_LOW - I_1V2 * (R_LINK12 + cu12))
    return out


def margins(cu33=CU33_MAX, cu12=CU12_MAX):
    """[(name, window low, window high, fall_min, rise_max, fall_max, low margin, high margin)].
    Low margin: the rail at every load stays valid until the reset asserts.
    High margin: the reset releases, and never trips in operation, at the
    regulator's worst low."""
    rows = []
    th = {"3V3": thresholds_3v3(), "1V2": thresholds_1v2()}
    for name, (lo, hi) in windows(cu33, cu12).items():
        fmin, fmax, rmin, rmax = th[name.split()[0]]
        rows.append((name, lo, hi, fmin, rmax, fmax, fmin - lo, hi - max(rmax, fmax)))
    return rows


def m1_margins(cu33=CU33_MAX, cu12=CU12_MAX):
    """Required release windows; margins() also keeps the future-load diagnostic."""
    return [row for row in margins(cu33, cu12) if row[0] in M1_WINDOWS]


def copper_limit_3v3(case='M1'):
    """Largest routed resistance preserving both unchanged 5 mV margins.

    Derive the bound from the actual tolerance-corner thresholds and load,
    rather than treating the original 10 mOhm planning estimate as a limit.
    """
    current = I_3V3[case]
    fmin, fmax, _, rmax = thresholds_3v3()
    return min((fmin - V33_MIN - MARGIN_MIN) / current,
               (POW001_3V3_LOW - max(fmax, rmax) - MARGIN_MIN) / current - R_LINK33)


def copper_limit_1v2():
    """Core-rail copper bound from the same two 5 mV inequalities."""
    fmin, fmax, _, rmax = thresholds_1v2()
    return min((fmin - V12_MIN - MARGIN_MIN) / I_1V2,
               (POW002_1V2_LOW - max(fmax, rmax) - MARGIN_MIN) / I_1V2 - R_LINK12)


def sense_current_bounds():
    """Absolute rail current at the two high-impedance monitor inputs.

    Both comparator inputs must lie in their specified common-mode interval
    (-0.1 V to supply +0.1 V), already required for the threshold proof.
    Bound the entire voltage interval across each input resistor, including
    tolerance and temperature drift. This intentionally loose copper bound
    does not depend on the input bias typical-temperature curves. Reversal
    is conservatively charged as a drop in either direction.
    """
    span = V33_OP[1] + 0.1
    return {'/+3V3': span / (R_T * (1 - R_TOL_25)),
            '/+1V2': max(span, d.V1V2_MAX + .1) / (R_S * (1 - R_TOL_1PCT))}


def effective_copper(net, load_ohms, tap_ohms, case='M1'):
    """Conservative equivalent drop with pin load and sense current separated.

    For unit current into a load pad the passive-network maximum principle
    puts every tap voltage between source and that pad. Its transfer drop
    is thus <= that pad's driving-point resistance. Reciprocity gives the
    same bound for the effect of sense current at a load. Superposition then
    bounds distributed load by its total current times the worst *load-pad*
    resistance, plus absolute sense current times the tap resistance. Include
    the extra sense current through the fitted link as well.
    """
    current = I_3V3[case] if net == '/+3V3' else I_1V2
    link = R_LINK33 if net == '/+3V3' else R_LINK12
    # 3V3 also supplies non-chip loads. Reciprocity bounds their effect on
    # each measured terminal by that terminal's self resistance. For 1V2,
    # only the chipset's 40 mA is restricted to the measured U7 pins; keep
    # the original additional 1 mA allowance at arbitrary unmeasured loads.
    if net == '/+3V3':
        load_drop = current * max(load_ohms, tap_ohms)
    else:
        # R11 LED transistor base and R100 ADC branch can each draw at most
        # the full core rail over the minimum resistor. Their total is a
        # conservative DC/sampling bound, without requiring ADC leakage data.
        aux = d.V1V2_MAX * (1 / 10e3 + 1 / 1e3) / (1 - (.01 + 100e-6 * 95))
        aux = max(aux, current - d.I_1V2_MAX)
        load_drop = d.I_1V2_MAX * load_ohms + aux * max(load_ohms, tap_ohms)
        load_drop += max(0, aux - (current - d.I_1V2_MAX)) * link
    return (load_drop + sense_current_bounds()[net] * (tap_ohms + link)) / current


def mr_low_level():
    """Worst ~MR voltage while a monitor output is low: diode VF (cold) +
    op-amp output swing, against the MAX811's VIL = 0.25 VCC at VCC = V33_MIN."""
    i = d.V3V3_MAX / MAX811_MR_PULLUP[0]
    return BAT54_VF_1MA + BAT54_VF_COLD + VO_SWING, MAX811_MR_VIL * V33_MIN, i


def main():
    from spice import Checks
    c = Checks("MB-051 dual-rail reset qualifier: guaranteed threshold windows (hw/power/reset_supervisor.py)")
    c.info("reference", "REF3425 2.500 V, worst total error +-%.3f %% (initial, box drift, LTD, "
           "hysteresis, solder shift, line)" % (100 * REF_ERR))
    f3 = thresholds_3v3()
    f1 = thresholds_1v2()
    c.info("3V3 monitor", "falls %.4f..%.4f V, rises %.4f..%.4f V (nominal hysteresis %.1f mV)" %
           (f3[0], f3[1], f3[2], f3[3], 1000 * (sum(f3[2:]) - sum(f3[:2])) / 2))
    c.info("1V2 monitor", "falls %.4f..%.4f V, rises %.4f..%.4f V (nominal hysteresis %.1f mV)" %
           (f1[0], f1[1], f1[2], f1[3], 1000 * (sum(f1[2:]) - sum(f1[:2])) / 2))
    future = next(row for row in margins() if row[0] == '3V3 slots 5-6 full')
    c.info('future slots 5-6 (advisory)', 'low/high margins %.2f/%.2f mV; outside M1 load' %
           (1000 * future[6], 1000 * future[7]))
    for k, (name, lo, hi, fmin, rmax, fmax, mlo, mhi) in enumerate(m1_margins()):
        c.info("window " + name, "valid-floor side %.4f V, regulator side %.4f V "
               "(copper allowances %.0f / %.0f mOhm)" % (lo, hi, 1e3 * CU33_MAX, 1e3 * CU12_MAX))
        c.check("W%da" % (k + 1), "%s: reset asserts (fall min) before any load leaves its valid range"
                % name, 1000 * mlo, 1000 * MARGIN_MIN, ">=", "mV")
        c.check("W%db" % (k + 1), "%s: releases (rise max) and never trips (fall max) at the regulator's "
                "worst low" % name, 1000 * mhi, 1000 * MARGIN_MIN, ">=", "mV")
    vmr, vil, i = mr_low_level()
    c.check("W4", "~MR low level with a monitor low (VF cold + swing) vs MAX811 VIL at 3.135 V",
            vmr, vil, "<=", "V")
    # the OPA376 specifies CMRR/Vos for VCM <= (V+) - 1.3 V; V+ is +3V3 itself, so
    # the worst case is the lowest +3V3 U6 lets the qualifier matter at (3.00 V)
    vcm = max(MAX811_VTH[0] * R_BT / (R_T + R_BT), max(t for t, _ in taps()))
    c.check("W5", "comparator inputs inside the OPA376's specified input range (<= V+ - 1.3 V) at +3V3 = 3.00 V",
            vcm, MAX811_VTH[0] - 1.3, "<=", "V")
    c.check("W6", "REF3425 input headroom from +3V3 at U6's lowest threshold (3.00 V) vs VOUT + 100 mV dropout",
            MAX811_VTH[0], VREF + 0.1, ">=", "V")
    if "--spice" in sys.argv:
        import reset_sequence
        reset_sequence.run(c)
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
