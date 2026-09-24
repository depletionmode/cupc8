#!/usr/bin/env python3
"""POW-005: the USB-C CC divider, the PWR_HI comparator and the sysctl ADC
thresholds against the Type-C spec.

    python3 hw/power/cc.py

1. The CC voltage every compliant source can produce on our sink: each Rp
   option (current source, or pull-up to 5 V or 3.3 V) at its tolerance
   extremes, into our Rd at its tolerance, loaded by the comparator network
   and the ADC pin leakage. These "realised" ranges are what the thresholds
   must separate. (The spec's vRd ranges are wider because they allow Rd
   +-10 %; they are printed too, for reference.)
2. PWR_HI: one TLV7011 for both CC lines, so CC1 and CC2 are averaged
   through two equal resistors (only one CC line is ever driven; the other
   sits on its Rd), and compared with half of 0.66 V taken from 3V3. The
   trip points, referred back to CC, include the 3V3 tolerance, the divider
   resistors, the comparator's offset and its hysteresis.
   These are worst-case stack-ups (every tolerance at its extreme at once),
   so they pass on any positive margin; the margin is printed.
3. The sysctl ADC thresholds (0.20, 0.66, 1.23 V) with the ADC's reference
   and conversion errors.
4. TI's TLV7011 model in ngspice: PWR_HI with CC at the worst-case default
   USB maximum and at the worst-case 1.5 A minimum, so the vendor model
   agrees with the arithmetic.
"""

import sys

import design as d
import spice
from spice import Checks



def rd_eff(rd):
    """Rd in parallel with the averaging network (2 R to the other CC's Rd)."""
    load = 2 * d.CC_AVG_R + d.RD
    return rd * load / (rd + load)


def cc_range(adv):
    """(min, max) CC voltage for one advertisement over every Rp option."""
    lo, hi = float("inf"), 0.0
    for kind, val, tol in d.RP_SOURCES[adv]:
        for rd in (d.RD * (1 - d.RD_TOL), d.RD * (1 + d.RD_TOL)):
            r = rd_eff(rd)
            if kind == "I":
                vs = [(val * (1 - tol) - d.ADC_LEAK) * r, (val * (1 + tol) + d.ADC_LEAK) * r]
            else:
                vmin, vmax = d.RP_PULLUP[kind]
                vs = [vmin * r / (val * (1 + tol) + r) - d.ADC_LEAK * r,
                      vmax * r / (val * (1 - tol) + r) + d.ADC_LEAK * r]
            lo, hi = min(lo, *vs), max(hi, *vs)
    return lo, hi


def pwr_hi_trips():
    """(rising trip max, falling trip min) referred to the driven CC line."""
    lo3, hi3 = d.buck_vout_range()
    rt, rb = d.CC_REF_R
    t = d.CC_REF_TOL_R
    ref_lo = lo3 * rb * (1 - t) / (rb * (1 - t) + rt * (1 + t))
    ref_hi = hi3 * rb * (1 + t) / (rb * (1 + t) + rt * (1 - t))
    # the averaging node: CC * k, with the undriven CC's Rd pulling it down
    # slightly and the two averaging resistors mismatched by their tolerance
    r1, r2 = d.CC_AVG_R, d.CC_AVG_R
    k_lo = (d.RD + r2 * (1 - t)) / (r1 * (1 + t) + r2 * (1 - t) + d.RD)
    k_hi = (d.RD + r2 * (1 + t)) / (r1 * (1 - t) + r2 * (1 + t) + d.RD)
    hys_hi = d.TLV7011_VHYS[1]
    rise_max = (ref_hi + d.TLV7011_VIO + hys_hi / 2) / k_lo
    fall_min = (ref_lo - d.TLV7011_VIO - hys_hi / 2) / k_hi
    return rise_max, fall_min, (ref_lo, ref_hi), (k_lo, k_hi)


def spice_check(c, v_default_max, v_15_min):
    """TI's TLV7011 model: PWR_HI for CC held at each value (averaged network)."""
    rt, rb = d.CC_REF_R
    deck = """
V3 v3 0 {v3}
Vcc1 cc1 0 PWL(0 0 1u 0 101u {vlo} 400u {vlo} 500u {vhi} 900u {vhi})
Rd1 cc1 0 {rd}
Rd2 cc2 0 {rd}
Ra cc1 avg {ra}
Rb cc2 avg {ra}
Rt v3 ref {rt}
Rb2 ref 0 {rb}
X1 avg ref out v3 0 TLV7011
Rl out 0 100k
.tran 1u 900u
.control
run
meas tran pwr_lo find v(out) at=390u
meas tran pwr_hi find v(out) at=890u
.endc
""".format(v3=d.buck_vout(), vlo=v_default_max, vhi=v_15_min, rd=d.RD, ra=d.CC_AVG_R, rt=rt, rb=rb)
    m = spice.run("pow005_tlv7011", deck, libs=("tlv7011.lib",))
    v3 = d.buck_vout()
    c.check("C8", "TLV7011 model: PWR_HI with CC at the worst default-USB max (%.3f V)" % v_default_max,
            m["pwr_lo"], 0.1 * v3, "<=")
    c.check("C9", "TLV7011 model: PWR_HI with CC at the worst 1.5 A min (%.3f V)" % v_15_min,
            m["pwr_hi"], 0.9 * v3, ">=")


def main():
    c = Checks("POW-005 USB-C CC divider and thresholds (hw/power/cc.py)")
    ranges = {adv: cc_range(adv) for adv in d.RP_SOURCES}
    for adv, (lo, hi) in ranges.items():
        s_lo, s_hi = d.VRD_RANGES[adv]
        c.info("CC %-7s" % adv, "realised %.3f .. %.3f V (spec vRd %.2f .. %.2f V)" % (lo, hi, s_lo, s_hi))
    c.check("C1", "realised ranges inside the spec's vRd windows: default max", ranges["default"][1],
            d.VRD_RANGES["default"][1], "<=")
    c.check("C2", "realised ranges inside the spec's vRd windows: 1.5 A min", ranges["1.5A"][0],
            d.VRD_RANGES["1.5A"][0], ">=")

    rise, fall, ref, k = pwr_hi_trips()
    c.info("PWR_HI", "reference %.4f..%.4f V, averaging factor %.4f..%.4f; trips referred to CC: "
           "falls no lower than %.3f V, rises no higher than %.3f V" % (ref[0], ref[1], k[0], k[1], fall, rise))
    c.check("C3", "PWR_HI stays low for any default source (lowest trip vs default max)", fall,
            ranges["default"][1], ">=")
    c.check("C4", "PWR_HI goes high for any 1.5 A source (highest trip vs 1.5 A min)", rise,
            ranges["1.5A"][0], "<=")

    # sysctl ADC classes (sysctl.md): errors from its reference and conversion
    for ident, name, th, below, above in (
            ("C5", "0.20 V: no CC vs default", d.VRD_THRESH["connect"], 0.0, ranges["default"][0]),
            ("C6", "0.66 V: default vs 1.5 A", d.VRD_THRESH["1.5A"], ranges["default"][1], ranges["1.5A"][0]),
            ("C7", "1.23 V: 1.5 A vs 3.0 A", d.VRD_THRESH["3.0A"], ranges["1.5A"][1], ranges["3.0A"][0])):
        err = th * d.ADC_VREF_TOL + d.ADC_ERR_V
        gap = min(th - err - below, above - (th + err))
        c.check(ident, "ADC threshold %s: +-%.0f mV error, worst gap to a class" % (name, 1e3 * err),
                gap, 0.0, ">=")
    spice_check(c, ranges["default"][1], ranges["1.5A"][0])
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
