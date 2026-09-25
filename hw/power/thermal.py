#!/usr/bin/env python3
"""THM-001: regulator junction temperatures at 40 C ambient (Tj <= 100 C).

    python3 hw/power/thermal.py

Tj = 40 C + P x theta_JA, with the datasheet theta_JA (JEDEC boards; our
copper will usually do better, but nothing checks that yet). Each regulator
at the corner that heats it most:

  TLV62569 (3V3)  loss from the datasheet RDS(on) (hot, see design.py),
                  a switching-loss estimate and the control current, at both
                  5V_SYS corners; two loads: the M1 maximum (four cards),
                  and that plus slots 5-6 each drawing their 300 mA of +3V3
  TLV62569 (Wi-Fi card)  the same loss model at Espressif's TX current,
                  rated at 100 % duty (a long transfer or an RF test), from
                  the slot's +5V at both of its corners
  RT9013 (1V2)    (3V3 max - 1V2 min) x 40 mA, main board and CPU card
  TPS61023 (IO card keyboard boost)  the same kind of loss model, at 500 mA
                  and the highest set point, from the worst-case card input
  TPS63802 (GPU card HDMI buck-boost)  all it loses at its budget
                  efficiency (design.GPUB_ETA), at 55 mA and its highest output
  input eFuse     I^2 x RON max at the most current it passes without
                  limiting (its minimum limit)
  SY6280          the IO card's keyboard port at 500 mA, RDS(on) hot
"""

import sys

import budget
import design as d
from spice import Checks


def buck_loss(vin, iout, vout=3.3):
    dcy = vout / vin
    cond = iout ** 2 * d.BUCK_RDS_HOT * (dcy * d.BUCK_RHS + (1 - dcy) * d.BUCK_RLS)
    sw = vin * iout * 2 * d.BUCK_T_EDGE * d.BUCK_FSW
    return cond + sw + d.BUCK_IQ_LOSS


def boost_loss(vin, iout):
    """A TPS61023's IC loss at its highest set point: RDS(on) hot
    (x BUCK_RDS_HOT, as the buck), switching edges at 1 MHz, the control. The
    low side carries the inductor current for D, the high side for 1 - D."""
    vout = d.iob_vout_range()[2]
    dcy = 1 - vin / vout
    il = vout * iout / (d.IOB_ETA * vin)
    cond = il ** 2 * d.BUCK_RDS_HOT * (dcy * d.IOB_RLS + (1 - dcy) * d.IOB_RHS)
    sw = vout * il * 2 * d.BUCK_T_EDGE * 1.0e6
    return cond + sw + d.BUCK_IQ_LOSS


def tj(p, theta):
    return d.AMBIENT_C + p * theta


def main():
    c = Checks("THM-001 regulator junction temperatures at %.0f C ambient (hw/power/thermal.py)" % d.AMBIENT_C)
    lim = d.TJ_LIMIT_C
    theta_buck = d.BUCK_THETA_JA[d.BUCK_PACKAGE]
    v5s = (budget.chain("worst")["v5"], d.VBUS_MAX)
    m1 = budget.i_3v3()
    full = m1 + d.FUTURE_SLOTS * d.SLOT_3V3_MAX
    for ident, what, i in (("T1", "M1 maximum (4 cards)", m1),
                           ("T2", "M1 + slots 5-6 at 300 mA +3V3 each", full)):
        p = max(buck_loss(v, i) for v in v5s)
        c.check(ident, "TLV62569%s 3V3 buck, %s (%.0f mA): %.0f mW x %.0f C/W" % (
            d.BUCK_PACKAGE, what, 1e3 * i, 1e3 * p, theta_buck), tj(p, theta_buck), lim, "<=", "C", fmt="%.1f",
            fix="TLV62569PDDCR (design.BUCK_PACKAGE = 'DDC'), or cap slots 5-6's +3V3")
    # what the 3V3 can carry on this package, and on the others
    for pkg, th in sorted(d.BUCK_THETA_JA.items()):
        imax = 0.0
        while tj(max(buck_loss(v, imax + 0.01) for v in v5s), th) <= lim and imax < 2.0:
            imax += 0.01
        c.info("TLV62569%s" % pkg, "theta_JA %.0f C/W: Tj <= %.0f C up to %.2f A of 3V3" % (th, lim, imax))

    v3_hi = d.buck_vout_range()[1]
    p = (v3_hi - 1.2 * (1 - d.RT9013_TOL)) * d.I_1V2_MAX + v3_hi * d.RT9013["IQ"]
    c.check("T3", "RT9013 1V2 LDO (main board; the CPU card's is the same): %.0f mW x %.0f C/W" % (
        1e3 * p, d.RT9013_THETA_JA), tj(p, d.RT9013_THETA_JA), lim, "<=", "C", fmt="%.1f")

    bad = d.wifi_board_mismatches()
    for ref, want, got in bad:
        c.info(ref, "hw/boards/wifi.py has %s, these checks model %s (design.WIFI_BOARD)" % (got, want))
    c.check("T0", "Wi-Fi card regulator parts in hw/boards/wifi.py that differ from the model", len(bad), 0, "<=",
            "", fmt="%d")
    v_card = (budget.chain("worst")["wifi_in"], d.VBUS_MAX)
    p = max(buck_loss(v, d.WIFI_I_3V3) for v in v_card)
    theta_wifi = d.BUCK_THETA_JA[d.WIFI_BUCK_PACKAGE]
    c.check("T4", "TLV62569%s Wi-Fi card buck (hw/boards/wifi.py), %.0f mA: %.0f mW x %.0f C/W" % (
        d.WIFI_BUCK_PACKAGE, 1e3 * d.WIFI_I_3V3, 1e3 * p, theta_wifi), tj(p, theta_wifi), lim, "<=", "C",
        fmt="%.1f")

    v_io = budget.chain("worst")["io_in"]
    p = boost_loss(v_io, d.I_KEYBOARD)
    c.check("T5", "TPS61023 IO card keyboard boost, 500 mA at %.2f V from %.2f V in: %.0f mW x %.0f C/W" % (
        d.iob_vout_range()[2], v_io, 1e3 * p, d.IOB_THETA_JA), tj(p, d.IOB_THETA_JA), lim, "<=", "C",
        fmt="%.1f")

    # the GPU card's buck-boost: everything its efficiency loses, all in the IC
    vout = d.gpub_vout_range()[2]
    p = vout * d.I_HDMI_PIN * (1 / d.GPUB_ETA - 1)
    c.check("T6", "TPS63802 GPU card HDMI buck-boost, 55 mA at %.2f V, %.0f %% efficient: %.0f mW x %.0f C/W" % (
        vout, 100 * d.GPUB_ETA, 1e3 * p, d.GPUB_THETA_JA), tj(p, d.GPUB_THETA_JA), lim, "<=", "C", fmt="%.1f")

    lo, _, _ = d.insw_ilim()
    p = lo ** 2 * d.INSW_RON_MAX
    c.check("T8", "%s input eFuse at its minimum limit %.2f A (the most it passes without limiting): "
            "%.0f mW x %.1f C/W" % (d.INSW_PART, lo, 1e3 * p, d.INSW_THETA_JA), tj(p, d.INSW_THETA_JA), lim,
            "<=", "C", fmt="%.1f")
    p = d.I_KEYBOARD ** 2 * d.SY6280_RON_MAX
    c.check("T9", "SY6280 IO card keyboard port, 500 mA: %.0f mW x %.0f C/W" % (1e3 * p, d.SY6280_THETA_JA),
            tj(p, d.SY6280_THETA_JA), lim, "<=", "C", fmt="%.1f")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
