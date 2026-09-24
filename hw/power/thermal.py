#!/usr/bin/env python3
"""THM-001: regulator junction temperatures at 40 C ambient (Tj <= 100 C).

    python3 hw/power/thermal.py

Tj = 40 C + P x theta_JA, with the datasheet theta_JA (JEDEC boards; our
copper will usually do better, but nothing checks that yet). Each regulator
at the corner that heats it most:

  TLV62569 (3V3)  loss from the datasheet RDS(on) (hot, see design.py),
                  a switching-loss estimate and the control current, at both
                  5V_SYS corners; two loads: the M1 maximum, and the M1
                  maximum plus slots 4-6 each drawing their 300 mA of +3V3
  TLV62569 (Wi-Fi card)  the same loss model at Espressif's TX current,
                  rated at 100 % duty (a long transfer or an RF test), from
                  the slot's +5V at both of its corners
  RT9013 (1V2)    (3V3 max - 1V2 min) x 40 mA, main board and CPU card
  AMS1117 (card)  (+5V max - VOUT min) x Iout + VIN x IQ. The +5V max is
                  vSafe5V max with no drop (the lightest load elsewhere).
                  No M1 card has one: the system, GPU and IO cards run from
                  the slot's +3V3 (power.md), so these only say what one
                  would take if they ever regulated from +5V.
  SY6280          I^2 x RDS(on) hot at the most current the input can pass
                  (its minimum limit) and on the IO card at 500 mA
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


def tj(p, theta):
    return d.AMBIENT_C + p * theta


def main():
    c = Checks("THM-001 regulator junction temperatures at %.0f C ambient (hw/power/thermal.py)" % d.AMBIENT_C)
    lim = d.TJ_LIMIT_C
    theta_buck = d.BUCK_THETA_JA[d.BUCK_PACKAGE]
    v5s = (budget.chain("worst")["v5"], d.VBUS_MAX)
    m1 = budget.i_3v3()
    full = m1 + d.FUTURE_SLOTS * d.SLOT_3V3_MAX
    for ident, what, i in (("T1", "M1 maximum", m1), ("T2", "M1 + slots 4-6 at 300 mA +3V3 each", full)):
        p = max(buck_loss(v, i) for v in v5s)
        c.check(ident, "TLV62569%s 3V3 buck, %s (%.0f mA): %.0f mW x %.0f C/W" % (
            d.BUCK_PACKAGE, what, 1e3 * i, 1e3 * p, theta_buck), tj(p, theta_buck), lim, "<=", "C", fmt="%.1f")
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
    c.check("T4", "TLV62569%s Wi-Fi card buck (hw/boards/wifi.py), %.0f mA: %.0f mW x %.0f C/W" % (
        d.BUCK_PACKAGE, 1e3 * d.WIFI_I_3V3, 1e3 * p, theta_buck), tj(p, theta_buck), lim, "<=", "C", fmt="%.1f")

    ams = d.AMS1117
    cards = (("T5", "GPU card, if from +5V", d.LOADS_3V3["GPU card RP2040 + flash"] + d.LOADS_3V3["GPU card TMDS"]),
             ("T6", "IO card, if from +5V", d.LOADS_3V3["IO card RP2040 + flash"]),
             ("T7", "system card, if from +5V", d.LOADS_3V3["sysctl RP2040 + flash"]))
    for ident, what, i in cards:
        p = (d.VBUS_MAX - d.AMS1117_VOUT_MIN) * i + d.VBUS_MAX * ams["IQ"]
        c.check(ident, "AMS1117 %s, %.0f mA from %.2f V: %.0f mW x %.0f C/W" % (
            what, 1e3 * i, d.VBUS_MAX, 1e3 * p, d.AMS1117_THETA_JA), tj(p, d.AMS1117_THETA_JA), lim, "<=",
            "C", fmt="%.1f")

    lo, _, _ = d.sy6280_ilim(budget.proposed_rset(budget.chain("worst")["itot"]))
    for ident, what, i in (("T8", "main input, at its minimum limit %.2f A (proposed RSET)" % lo, lo),
                           ("T9", "IO card keyboard port, 500 mA", d.I_KEYBOARD)):
        p = i ** 2 * d.SY6280_RON_MAX
        c.check(ident, "SY6280 %s: %.0f mW x %.0f C/W" % (what, 1e3 * p, d.SY6280_THETA_JA),
                tj(p, d.SY6280_THETA_JA), lim, "<=", "C", fmt="%.1f")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
