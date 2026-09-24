#!/usr/bin/env python3
"""POW-006: the worst-case current budget, the input path and the slot feeds.

    python3 hw/power/budget.py

The loads are power.md's max column (design.LOADS_3V3 etc.), the 3V3 buck
input at design.BUCK_ETA_BUDGET, and the Wi-Fi card at Espressif's TX current
(rated at 100 % duty) through its own buck, so its +5V current rises as the
voltage reaching it falls. The voltage chain goes from the source to each card:

  source VBUS -> cable (VBUS and GND) -> receptacle -> 2 A PTC -> SY6280
    -> 5V_SYS -> slot PTC -> 0 ohm link -> sense -> contacts -> card

"worst" is every tolerance against us at once: vSafe5V min, the Type-C
cable's full IR drop, every resistance at its max (PTCs at R1max, the SY6280
hot) and the M1 worst-case load. "typical" is 5.0 V, half the cable limit,
resistances at their min. Current budgets need 10 % margin.
"""

import sys

import design as d
from spice import Checks

MARGIN = 0.10


def i_3v3():
    return sum(d.LOADS_3V3.values())


def i_buck_in(v5, i3=None):
    return (i3 if i3 is not None else i_3v3()) * 3.3 / (d.BUCK_ETA_BUDGET * v5)


def chain(corner, keyboard=d.I_KEYBOARD, wifi_3v3=d.WIFI_I_3V3, extra_3v3=0.0, extra_5v=0.0):
    """Node voltages (V) and the total VBUS current (A) at one corner.
    wifi_3v3 is the Wi-Fi card's 3V3 load; its +5V draw is solved here."""
    worst = corner == "worst"
    vbus = d.VBUS_MIN if worst else d.VBUS_NOM
    k = 1.0 if worst else 0.5
    r_in = (k * (d.CABLE_R_VBUS + d.CABLE_R_GND) + d.R_RECEPTACLE
            + (d.FUSE_IN_R_MAX if worst else d.FUSE_IN_R_MIN)
            + (d.SY6280_RON_MAX if worst else d.SY6280_RON_TYP) + d.R_5VSYS)
    r_slot = ((d.SLOT_PTC_R_MAX if worst else d.SLOT_PTC_R_MIN) + d.R_SLOT_LINK
              + d.R_SLOT_SENSE + d.R_SLOT_CONTACTS)
    v5 = v_card = vbus
    for _ in range(50):                     # both bucks' input currents depend on their input
        wifi = d.wifi_i_5v(v_card, wifi_3v3)
        itot = i_buck_in(v5, i_3v3() + extra_3v3) + keyboard + d.I_HDMI_5V + wifi + extra_5v
        v5 = vbus - itot * r_in
        v_card = v5 - wifi * r_slot
    return {"vbus": vbus, "itot": itot, "v5": v5, "r_slot": r_slot, "iwifi": wifi,
            "wifi_in": v_card,
            "kbd_port": v5 - keyboard * (r_slot + d.SY6280_RON_MAX if worst else r_slot + d.SY6280_RON_TYP)}


def proposed_rset(i_need):
    """Smallest E96 RSET whose minimum limit still covers i_need with margin."""
    e96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40,
           1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00,
           2.05, 2.10, 2.15, 2.21, 2.26, 2.32, 2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87,
           2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
           4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49, 5.62, 5.76, 5.90,
           6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45,
           8.66, 8.87, 9.09, 9.31, 9.53, 9.76]
    for r in sorted((x * 1e3 for x in e96), reverse=True):
        if d.sy6280_ilim(r)[0] >= i_need * (1 + MARGIN):
            return r
    return None


def main():
    c = Checks("POW-006 worst-case budget (hw/power/budget.py)")
    i3 = i_3v3()
    w, t = chain("worst"), chain("typical")
    c.info("3V3 load (max)", "%.0f mA; buck input at %.0f%%: %.0f mA at 5V_SYS %.2f V" % (
        1e3 * i3, 100 * d.BUCK_ETA_BUDGET, 1e3 * i_buck_in(w["v5"]), w["v5"]))
    c.info("Wi-Fi card from +5V", "%.0f mA worst, %.0f mA typical (ESP32 TX %.0f mA at 100%% duty + LEDs, "
           "through its buck at %.0f%%)" % (1e3 * w["iwifi"], 1e3 * t["iwifi"], 1e3 * d.ESP32_I_TX,
                                          100 * d.BUCK_ETA_BUDGET))
    c.info("chain, worst", "VBUS %.2f V -> 5V_SYS %.3f V -> Wi-Fi card +5V %.3f V, keyboard port %.3f V "
           "(total %.0f mA)" % (w["vbus"], w["v5"], w["wifi_in"], w["kbd_port"], 1e3 * w["itot"]))
    c.info("chain, typical", "VBUS %.2f V -> 5V_SYS %.3f V -> Wi-Fi card +5V %.3f V, keyboard port %.3f V "
           "(total %.0f mA)" % (t["vbus"], t["v5"], t["wifi_in"], t["kbd_port"], 1e3 * t["itot"]))

    m1 = w["itot"]
    lo, nom, hi = d.sy6280_ilim()
    c.check("B1", "M1 worst case vs %s source (the radio's minimum)" % d.WIFI_MIN_CLASS, m1,
            d.SOURCE_CLASSES[d.WIFI_MIN_CLASS], "<=", "A", need=MARGIN)
    c.check("B2", "M1 worst case vs SY6280 minimum limit (RSET %.2fk: %.2f..%.2f A)" % (
        d.SY6280_MAIN_RSET / 1e3, lo, hi), m1, lo, "<=", "A", need=MARGIN)
    rset = proposed_rset(m1)
    plo, pnom, phi = d.sy6280_ilim(rset)
    c.info("SY6280 RSET for B2", "%.2fk -> %.2f / %.2f / %.2f A (min/nom/max)" % (rset / 1e3, plo, pnom, phi))
    c.check("B3", "that RSET's nominal limit vs the SY6280's programmable max", pnom,
            d.SY6280_ILIM_PROG_MAX, "<=", "A")
    c.check("B4", "M1 worst case vs input PTC hold at %.0f C" % d.AMBIENT_C, m1, d.FUSE_IN_IHOLD_40C,
            "<=", "A", need=MARGIN)

    # default USB: the policy turns the radio off; an ordinary keyboard
    idle = chain("worst", keyboard=0.100, wifi_3v3=0.030 + d.WIFI_I_LEDS)
    c.check("B5", "default USB 2.0 port, radio off, 100 mA keyboard", idle["itot"],
            d.SOURCE_CLASSES["default USB 2.0"], "<=", "A")
    c.check("B6", "default USB 3.x port, radio off, 500 mA keyboard", chain(
        "worst", wifi_3v3=0.030 + d.WIFI_I_LEDS)["itot"],
        d.SOURCE_CLASSES["default USB 3.x"], "<=", "A")

    # slots
    hold = d.SLOT_PTC_IHOLD_40C
    c.check("B7", "Wi-Fi card +5V (worst) vs slot PTC hold at 40 C", w["iwifi"], hold, "<=", "A", need=MARGIN)
    c.check("B8", "IO card +5V (keyboard) vs slot PTC hold at 40 C", d.I_KEYBOARD, hold, "<=", "A",
            need=MARGIN)
    c.check("B9", "slot.md per-card budget (1 A, may all be +5V) vs slot PTC hold at 40 C",
            d.SLOT_CARD_MAX, hold, "<=", "A")
    gpu3 = d.LOADS_3V3["GPU card RP2040 + flash"] + d.LOADS_3V3["GPU card TMDS"]
    c.check("B10", "GPU card +3V3 vs slot +3V3 limit", gpu3, d.SLOT_3V3_MAX, "<=", "A", need=MARGIN)
    c.check("B11", "Wi-Fi card: slot feed vs Espressif's >= 0.5 A supply", hold, d.ESP32_SUPPLY_MIN,
            ">=", "A")
    c.check("B12", "keyboard VBUS at the IO card port, worst (USB 2.0 low-power port >= 4.40 V)",
            w["kbd_port"], 4.40, ">=")
    c.check("B13", "keyboard VBUS at the IO card port, typical", t["kbd_port"], 4.40, ">=")

    # slots 4-6: what is left for them to declare, with a 3.0 A source
    cap = min(d.SOURCE_CLASSES["Type-C 3.0 A"], plo, d.FUSE_IN_IHOLD_40C) / (1 + MARGIN)
    c.info("slots 4-6 at a 3.0 A source", "input path allows %.2f A (min of 3.0 A, SY6280 min %.2f A at "
           "RSET %.2fk, PTC hold %.2f A, less 10%%): %.0f mA left for slots 4-6 together" % (
               cap, plo, rset / 1e3, d.FUSE_IN_IHOLD_40C, 1e3 * (cap - m1)))
    c.check("B14", "M1 worst case vs the input path at a 3.0 A source (proposed RSET)", m1, cap, "<=", "A")

    # input protection
    c.check("B15", "TVS breakdown (min) vs vSafe5V max + 10%", d.TVS_VBR_MIN, d.VBUS_MAX * 1.1, ">=")
    c.info("TVS", "SMF5.0A standoff %.1f V is below vSafe5V max %.1f V (leakage rises, still below "
           "VBR); its %.1f V clamp exceeds the SY6280's 6 V abs max, so a surge is limited only "
           "by the switch's own rating" % (d.TVS_VRWM, d.VBUS_MAX, d.TVS_VCLAMP))
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
