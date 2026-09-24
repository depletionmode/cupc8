#!/usr/bin/env python3
"""POW-006: the worst-case current budget, the input path and the slot feeds.

    python3 hw/power/budget.py

The loads are power.md's max column (design.LOADS_3V3 etc.: the four M1
cards, with the HDMI card in the graphics slot, the heavier of the two), the
3V3 buck input at design.BUCK_ETA_BUDGET, and the Wi-Fi card at Espressif's
TX current (rated at 100 % duty) through its own buck, so its +5V current
rises as the voltage reaching it falls. The voltage chain:

  source VBUS -> cable (VBUS and GND) -> receptacle -> PTC -> eFuse
    -> 5V_SYS -> slot PTC -> 0 ohm link -> sense -> contacts -> card

"worst" is every tolerance against us at once: vSafe5V min, the Type-C
cable's full IR drop, every resistance at its max and the M1 worst-case load.
"typical" is 5.0 V, half the cable limit, resistances at their min.
Current budgets need 10 % margin.

The policy (power.md): the full machine needs a Type-C 3.0 A source. On a
1.5 A source the radio stays off and SD writes are refused; B3 checks that
what is left fits.
"""

import sys

import design as d
from spice import Checks

MARGIN = 0.10
WIFI_IDLE_3V3 = 0.030 + d.WIFI_I_LEDS       # radio off: the ESP32-C3 idle, plus the card's LEDs


def i_3v3(sd_write=True):
    return sum(d.LOADS_3V3.values()) - (0 if sd_write else d.I_SD_WRITE)


def i_buck_in(v5, i3=None):
    return (i3 if i3 is not None else i_3v3()) * 3.3 / (d.BUCK_ETA_BUDGET * v5)


def chain(corner, keyboard=d.I_KEYBOARD, wifi_3v3=d.WIFI_I_3V3, extra_3v3=0.0, extra_5v=0.0, sd_write=True):
    """Node voltages (V) and the total VBUS current (A) at one corner.
    wifi_3v3 is the Wi-Fi card's 3V3 load; its +5V draw is solved here."""
    worst = corner == "worst"
    vbus = d.VBUS_MIN if worst else d.VBUS_NOM
    r_in = d.r_in(worst)
    r_slot = ((d.SLOT_PTC_R_MAX if worst else d.SLOT_PTC_R_MIN) + d.R_SLOT_LINK
              + d.R_SLOT_SENSE + d.R_SLOT_CONTACTS)
    r_kbd = r_slot + (d.SY6280_RON_MAX if worst else d.SY6280_RON_TYP)     # the IO card's port switch
    v5 = v_card = vbus
    for _ in range(50):                     # both bucks' input currents depend on their input
        wifi = d.wifi_i_5v(v_card, wifi_3v3)
        itot = i_buck_in(v5, i_3v3(sd_write) + extra_3v3) + keyboard + d.I_HDMI_5V + wifi + extra_5v
        v5 = vbus - itot * r_in
        v_card = v5 - wifi * r_slot
    return {"vbus": vbus, "itot": itot, "v5": v5, "r_slot": r_slot, "iwifi": wifi,
            "wifi_in": v_card, "kbd_port": v5 - keyboard * r_kbd}


def main():
    c = Checks("POW-006 worst-case budget (hw/power/budget.py)")
    i3 = i_3v3()
    w, t = chain("worst"), chain("typical")
    c.info("3V3 load (max)", "%.0f mA (storage card %.0f mA, graphics = HDMI card %.0f mA; the e-ink card "
           "takes %.0f mA and no +5V); buck input at %.0f%%: %.0f mA at 5V_SYS %.2f V" % (
               1e3 * i3, 1e3 * d.STORAGE_CARD_3V3, 1e3 * d.GPU_CARD_3V3, 1e3 * d.EINK_CARD_3V3,
               100 * d.BUCK_ETA_BUDGET, 1e3 * i_buck_in(w["v5"]), w["v5"]))
    c.info("Wi-Fi card from +5V", "%.0f mA worst, %.0f mA typical (ESP32 TX %.0f mA at 100%% duty + LEDs, "
           "through its buck at %.0f%%)" % (1e3 * w["iwifi"], 1e3 * t["iwifi"], 1e3 * d.ESP32_I_TX,
                                          100 * d.BUCK_ETA_BUDGET))
    c.info("chain, worst", "VBUS %.2f V -> 5V_SYS %.3f V -> Wi-Fi card +5V %.3f V, keyboard port %.3f V "
           "(total %.0f mA)" % (w["vbus"], w["v5"], w["wifi_in"], w["kbd_port"], 1e3 * w["itot"]))
    c.info("chain, typical", "VBUS %.2f V -> 5V_SYS %.3f V -> Wi-Fi card +5V %.3f V, keyboard port %.3f V "
           "(total %.0f mA)" % (t["vbus"], t["v5"], t["wifi_in"], t["kbd_port"], 1e3 * t["itot"]))

    m1 = w["itot"]
    lo, nom, hi = d.insw_ilim()
    c.check("B1", "M1 worst case vs a %s source (the full machine)" % d.FULL_CLASS, m1,
            d.SOURCE_CLASSES[d.FULL_CLASS], "<=", "A", need=MARGIN)
    c.check("B2", "M1 worst case vs the eFuse's minimum limit (RILM %.2fk: %.2f / %.2f / %.2f A)" % (
        d.INSW_RILM / 1e3, lo, nom, hi), m1, lo, "<=", "A", need=MARGIN,
        fix="lower RILM (design.INSW_RILM)")
    c.check("B3", "the eFuse's maximum limit vs a 3.0 A source + 10% (a fault trips the eFuse, not the "
            "source)", hi, d.SOURCE_CLASSES[d.FULL_CLASS] * 1.1, "<=", "A", fix="raise RILM")
    c.check("B4", "M1 worst case vs input PTC (%s) hold at %.0f C" % (d.FUSE_IN, d.AMBIENT_C), m1,
            d.FUSE_IN_IHOLD_40C, "<=", "A", need=MARGIN)

    # a 1.5 A source: PWR_HI low, so the radio is off and SD writes are refused
    # (reads are allowed: a microSD reading can draw as much as one writing,
    # so the SD stays in this budget at its full 100 mA)
    red = chain("worst", wifi_3v3=WIFI_IDLE_3V3)
    c.check("B5", "1.5 A source: radio off, SD reading (100 mA), 500 mA keyboard", red["itot"],
            d.SOURCE_CLASSES[d.REDUCED_CLASS], "<=", "A", need=MARGIN)
    # default USB: the same policy; what it can run is stated, not promised
    for ident, name, kbd in (("B6", "default USB 2.0", 0.100), ("B7", "default USB 3.x", d.I_KEYBOARD)):
        dflt = chain("worst", keyboard=kbd, wifi_3v3=WIFI_IDLE_3V3, sd_write=False)
        typ = chain("typical", keyboard=kbd, wifi_3v3=WIFI_IDLE_3V3, sd_write=False)
        c.info(name, "radio off, SD idle, %.0f mA keyboard: %.0f mA at the max budget, %.0f mA typical corner"
               % (1e3 * kbd, 1e3 * dflt["itot"], 1e3 * typ["itot"]))
        c.check(ident, "%s, radio off, SD idle, %.0f mA keyboard (max budget)" % (name, 1e3 * kbd),
                dflt["itot"], d.SOURCE_CLASSES[name], "<=", "A",
                fix="a decision: power.md says default USB runs the machine only at typical loads "
                    "(not guaranteed at the max budget), or the policy also turns the keyboard port off")

    # slots
    hold = d.SLOT_PTC_IHOLD_40C
    c.check("B8", "slot.md per-card +5V budget (%.2f A) vs slot PTC hold at 40 C" % d.SLOT_5V_MAX,
            d.SLOT_5V_MAX, hold, "<=", "A", need=MARGIN)
    c.check("B9", "Wi-Fi card +5V (worst) vs slot.md's %.2f A" % d.SLOT_5V_MAX, w["iwifi"], d.SLOT_5V_MAX,
            "<=", "A", need=MARGIN)
    # 500 mA is USB 2.0's hard limit for a device, not an estimate: no extra margin
    c.check("B10", "IO card +5V (keyboard, USB 2.0's 500 mA device maximum) vs slot.md's %.2f A" %
            d.SLOT_5V_MAX, d.I_KEYBOARD, d.SLOT_5V_MAX, "<=", "A")
    for ident, name, i in (("B11", "HDMI card", d.GPU_CARD_3V3), ("B12", "e-ink card", d.EINK_CARD_3V3),
                           ("B13", "storage card", d.STORAGE_CARD_3V3),
                           ("B14", "IO card", d.LOADS_3V3["IO card RP2040 + flash"])):
        c.check(ident, "%s +3V3 vs slot +3V3 limit" % name, i, d.SLOT_3V3_MAX, "<=", "A", need=MARGIN)
    c.check("B15", "Wi-Fi card: slot feed (PTC hold at 40 C) vs Espressif's >= 0.5 A supply", hold,
            d.ESP32_SUPPLY_MIN, ">=", "A")
    c.check("B16", "keyboard VBUS at the IO card port, worst (USB 2.0 low-power port >= 4.40 V)",
            w["kbd_port"], 4.40, ">=",
            fix="a decision: accept (keyboards run their logic at 3.3 V; typical passes, B17) - no board "
                "change reaches 4.40 V at vSafe5V min with a full-drop cable")
    c.check("B17", "keyboard VBUS at the IO card port, typical", t["kbd_port"], 4.40, ">=")

    # slots 5-6: what is left for them to declare with a 3.0 A source
    cap = min(d.SOURCE_CLASSES[d.FULL_CLASS], lo, d.FUSE_IN_IHOLD_40C) / (1 + MARGIN)
    left = cap - m1
    c.info("slots 5-6 at a 3.0 A source", "input path allows %.2f A (min of 3.0 A, eFuse min %.2f A, PTC "
           "hold %.2f A, less 10%%): %.0f mA of +5V-equivalent left for slots 5-6 together" % (
               cap, lo, d.FUSE_IN_IHOLD_40C, 1e3 * left))
    c.check("B18", "slots 5-6: headroom at a 3.0 A source", left, 0.0, ">=", "A")

    # input protection
    ov_lo, ov_hi = d.insw_ovlo()
    c.check("B19", "eFuse OVLO lowest trip vs vSafe5V max", ov_lo, d.VBUS_MAX, ">=", fix="raise the OVLO divider")
    c.check("B20", "eFuse OVLO highest trip vs 5V_SYS loads' 6 V absolute max", ov_hi, d.DOWNSTREAM_ABS_MAX, "<=",
            fix="lower the OVLO divider, or 0.1 % resistors")
    c.check("B21", "TVS breakdown (min) vs vSafe5V max + 10%", d.TVS_VBR_MIN, d.VBUS_MAX * 1.1, ">=")
    c.check("B22", "TVS clamp vs the eFuse's 23 V rating", d.TVS_VCLAMP, 23.0, "<=")
    return c.done()


if __name__ == "__main__":
    sys.exit(main())
