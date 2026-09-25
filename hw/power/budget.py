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


def chain(corner, keyboard=d.I_KEYBOARD, wifi_3v3=d.WIFI_I_3V3, extra_3v3=0.0, extra_5v=0.0, sd_write=True,
          typ_loads=False, vbus=None):
    """Node voltages (V) and the total VBUS current (A) at one corner.
    wifi_3v3 is the Wi-Fi card's 3V3 load and keyboard the IO card's port load;
    their +5V draws, through each card's converter, are solved here.
    typ_loads: power.md's Typ column instead of Max (B6/B7)."""
    worst = corner == "worst"
    vbus = vbus if vbus is not None else (d.VBUS_MIN if worst else d.VBUS_NOM)
    r_in = d.r_in(worst)
    r_slot = ((d.SLOT_PTC_R_MAX if worst else d.SLOT_PTC_R_MIN) + d.R_SLOT_LINK
              + d.R_SLOT_SENSE + d.R_SLOT_CONTACTS)
    i3 = (sum(d.LOADS_3V3_TYP.values()) if typ_loads else i_3v3(sd_write)) + extra_3v3
    hdmi = d.I_HDMI_5V_TYP if typ_loads else d.I_HDMI_5V
    v5 = v_card = v_io = vbus
    for _ in range(80):                     # the converters' input currents depend on their input
        wifi = d.wifi_i_5v(v_card, wifi_3v3)
        io = d.iob_i_in(v_io, keyboard)     # the IO card's keyboard boost
        itot = i_buck_in(v5, i3) + io + hdmi + wifi + extra_5v
        v5 = vbus - itot * r_in
        v_card = v5 - wifi * r_slot
        v_io = v5 - io * r_slot
    ron = d.SY6280_RON_MAX if worst else d.SY6280_RON_TYP        # the port switch after the boost
    return {"vbus": vbus, "itot": itot, "v5": v5, "r_slot": r_slot, "iwifi": wifi, "iio": io,
            "wifi_in": v_card, "io_in": v_io,
            "kbd_port": d.iob_vout(v_io, keyboard, "lo" if worst else "nom") - keyboard * ron}


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
    # default USB: power.md promises typical loads only (the same policy: radio
    # off, no SD writes). The typical loads at the worst-case voltage corner
    for ident, name in (("B6", "default USB 2.0"), ("B7", "default USB 3.x")):
        mx = chain("worst", keyboard=0.100, wifi_3v3=WIFI_IDLE_3V3, sd_write=False)
        typ = chain("worst", keyboard=d.I_KEYBOARD_TYP, wifi_3v3=WIFI_IDLE_3V3, typ_loads=True)
        c.info(name, "radio off: %.0f mA at typical loads (power.md Typ, %.0f mA keyboard); at the max "
               "budget with the SD idle and a 100 mA keyboard %.0f mA, which is not promised" % (
                   1e3 * typ["itot"], 1e3 * d.I_KEYBOARD_TYP, 1e3 * mx["itot"]))
        c.check(ident, "%s, radio off, typical loads (power.md: default USB runs typical loads only)" % name,
                typ["itot"], d.SOURCE_CLASSES[name], "<=", "A", need=MARGIN)

    # slots
    hold = d.SLOT_PTC_IHOLD_40C
    c.check("B8", "slot.md per-card +5V budget (%.2f A) vs slot PTC hold at 40 C" % d.SLOT_5V_MAX,
            d.SLOT_5V_MAX, hold, "<=", "A", need=MARGIN)
    c.check("B9", "Wi-Fi card +5V (worst) vs slot.md's %.2f A" % d.SLOT_5V_MAX, w["iwifi"], d.SLOT_5V_MAX,
            "<=", "A", need=MARGIN)
    # the keyboard's 500 mA (USB 2.0's device maximum) through the boost, at its
    # highest set point, from the worst-case card input
    c.check("B10", "IO card +5V (500 mA keyboard through its boost, card input %.2f V) vs slot.md's %.2f A"
            % (w["io_in"], d.SLOT_5V_MAX), w["iio"], d.SLOT_5V_MAX, "<=", "A",
            fix="a decision: slot.md's +5V per card 0.55 A -> 0.80 A (the SMD1206P110TFT slot PTC holds "
                "%.2f A at 40 C, B10b) - no boost can hold the port at USB's 4.40 V for 500 mA from a 4 V "
                "card input on 0.55 A" % hold)
    c.check("B10b", "IO card +5V (worst, through its boost) vs slot PTC hold at 40 C", w["iio"], hold, "<=",
            "A", need=MARGIN)
    for ident, name, i in (("B11", "HDMI card", d.GPU_CARD_3V3), ("B12", "e-ink card", d.EINK_CARD_3V3),
                           ("B13", "storage card", d.STORAGE_CARD_3V3),
                           ("B14", "IO card", d.LOADS_3V3["IO card RP2040 + flash"])):
        c.check(ident, "%s +3V3 vs slot +3V3 limit" % name, i, d.SLOT_3V3_MAX, "<=", "A", need=MARGIN)
    c.check("B15", "Wi-Fi card: slot feed (PTC hold at 40 C) vs Espressif's >= 0.5 A supply", hold,
            d.ESP32_SUPPLY_MIN, ">=", "A")
    lo_b, nom_b, hi_b = d.iob_vout_range()
    c.info("keyboard boost", "TPS61023 set %.3f / %.3f / %.3f V (VREF +-2.5 %%, 1 %% divider); the "
           "port = that less the SY6280's drop at 500 mA (the droop in a step is POW-007)" % (lo_b, nom_b, hi_b))
    c.check("B16", "keyboard VBUS at the IO card port, worst: boost at its low set point (USB 2.0 "
            "low-power port >= 4.40 V)", w["kbd_port"], d.USB_PORT_MIN, ">=")
    c.check("B17", "keyboard VBUS at the IO card port, typical", t["kbd_port"], d.USB_PORT_MIN, ">=")
    hi_c = chain("typical", keyboard=0.0, wifi_3v3=WIFI_IDLE_3V3, vbus=d.VBUS_MAX)
    port_hi = max(hi_b, d.iob_vout(hi_c["io_in"], 0.0, "hi"))
    c.check("B17b", "keyboard VBUS highest: VBUS %.1f V, light loads (boost set point %.3f V, or "
            "pass-through at %.3f V)" % (d.VBUS_MAX, hi_b, hi_c["io_in"]), port_hi, d.USB_PORT_MAX, "<=")
    c.check("B17c", "IO card +5V highest (the eFuse's OVLO trip, max) vs the boost's %.1f V absolute max"
            % d.IOB_VIN_ABS, d.insw_ovlo()[1], d.IOB_VIN_ABS, "<=")

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
