#!/usr/bin/env python3
"""The system card: sysctl, an RP2040 with its own USB-C port to the host PC,
in the main board's keyed PCIe x4 system slot (doc/hardware/system-slot.md).

    python3 hw/boards/system.py [outdir]      (default build/hw/system)

Power: the card runs from the slot's +3V3 (three contacts), the main board's
3V3 buck, as power.md's tree and current budget have it. The slot's +5V and
the USB-C VBUS are not used at all: VBUS reaches no copper beyond the
receptacle, so the card cannot back-feed the host or the slot rails. The
USB controller's VBUS detect is forced on in firmware (the pico-sdk and
TinyUSB default); every GPIO is taken, so there is none left to sense VBUS.

The RP2040 follows Raspberry Pi's "Hardware design with RP2040" minimal
design: W25Q16 on QSPI, 12 MHz crystal with a 1 kOhm series resistor on
XOUT, the internal 1V1 regulator, 100 nF per supply pin, 27 Ohm on D+/D-.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import logo  # noqa: E402

G = kg.GRID

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
TP = "cupc8:TestPad_D1.0mm"

# sysctl GPIO -> net, from hw/pins.yaml (fw/rp2040/sysctl depends on them).
# Outputs that drive a slot SPI bus go through 33 Ohm source termination
# (the "_MCU" nets), as every card driver on the CPU bus has (cpu-bus.md).
GPIO = {
    0: "LED_USB_TX", 1: "LED_USB_RX",
    2: "BR_SCK_MCU", 3: "BR_MOSI_MCU", 4: "BR_MISO", 5: "BR_nCS_MCU",
    6: "CHIPSET_nCRESET", 7: "CHIPSET_CDONE",
    8: "FL1_MISO", 9: "FL1_nCS_MCU",
    10: "FL0_SCK_MCU", 11: "FL0_MOSI_MCU", 12: "FL0_MISO", 13: "FL0_nCS_MCU",
    14: "FL1_SCK_MCU", 15: "FL1_MOSI_MCU",
    16: "CPUCARD_nCRESET", 17: "CPUCARD_CDONE",
    18: "PROG_CLK", 19: "PROG_IO",
    20: "MUX_SEL0", 21: "MUX_SEL1", 22: "MUX_SEL2",
    23: "SYS_nRST", 24: "I2C_SDA", 25: "I2C_SCL",
    26: "CC1", 27: "CC2", 28: "V1V2_SENSE", 29: "LED_STATUS",
}
TERMINATED = ["BR_SCK", "BR_MOSI", "BR_nCS", "FL0_SCK", "FL0_MOSI", "FL0_nCS",
              "FL1_SCK", "FL1_MOSI", "FL1_nCS"]

# two-pin parts: ref, symbol, value, footprint, LCSC, net on pin 1 (top), pin 2
PASSIVES = (
    # RP2040 supply pins, one 100 nF each (IOVDD x6, USB_VDD, ADC_AVDD, DVDD x2)
    [("C%d" % i, "Device:C", "100n", C0603, "C14663", "+3V3", "GND") for i in range(1, 9)] +
    [("C9", "Device:C", "100n", C0603, "C14663", "1V1", "GND"),
     ("C10", "Device:C", "100n", C0603, "C14663", "1V1", "GND"),
     ("C11", "Device:C", "100n", C0603, "C14663", "+3V3", "GND"),       # flash
     ("C12", "Device:C", "1u", C0603, "C15849", "+3V3", "GND"),        # VREG_VIN
     ("C13", "Device:C", "1u", C0603, "C15849", "1V1", "GND"),         # VREG_VOUT
     ("C14", "Device:C", "10u", C0805, "C15850", "+3V3", "GND"),       # slot bulk
     # X322512MSB4SI: CL = 20 pF; 2 x (20 - ~4 pF stray) = 32 pF -> 33 pF
     ("C15", "Device:C", "33p", C0603, "C1663", "XIN", "GND"),
     ("C16", "Device:C", "33p", C0603, "C1663", "XOUT_X", "GND"),
     ("R1", "Device:R", "1k", R0603, "C21190", "XOUT", "XOUT_X"),
     ("R2", "Device:R", "27", R0603, "C25190", "USB_DP_MCU", "USB_DP"),
     ("R3", "Device:R", "27", R0603, "C25190", "USB_DM_MCU", "USB_DM"),
     ("R4", "Device:R", "5.1k", R0603, "C23186", "USB_CC1", "GND"),     # UFP Rd
     ("R5", "Device:R", "5.1k", R0603, "C23186", "USB_CC2", "GND"),
     ("R6", "Device:R", "1k", R0603, "C21190", "QSPI_nSS", "BOOTSEL"),  # short TP to GND
     ("R7", "Device:R", "10k", R0603, "C25804", "+3V3", "I2C_SDA"),
     ("R8", "Device:R", "10k", R0603, "C25804", "+3V3", "I2C_SCL"),
     # power LED (milestone-1.md, Indicator LEDs): red, 1 kOhm from 3V3
     ("R9", "Device:R", "1k", R0603, "C21190", "+3V3", "LED_PWR"),
     # green drops ~3 V, so 100 Ohm for a few mA from 3.3 V (as the Wi-Fi card)
     ("R10", "Device:R", "100", R0603, "C22775", "LED_STATUS", "LED_ST"),
     ("D1", "Device:LED", "red", LED0603, "C2286", "LED_PWR", "GND"),        # power
     ("D2", "Device:LED", "green", LED0603, "C12624", "LED_ST", "GND"),      # status, GPIO29
     # USB activity to (TX) and from (RX) the host, lit ~30 ms by the firmware
     ("R20", "Device:R", "100", R0603, "C22775", "LED_USB_TX", "LED_TX"),
     ("D3", "Device:LED", "green", LED0603, "C12624", "LED_TX", "GND"),
     ("R21", "Device:R", "100", R0603, "C22775", "LED_USB_RX", "LED_RX"),
     ("D4", "Device:LED", "green", LED0603, "C12624", "LED_RX", "GND")] +
    [("R%d" % (11 + i), "Device:R", "33", R0603, "C23140", n + "_MCU", n) for i, n in enumerate(TERMINATED)]
)

# test pads: SWD and RUN for bring-up of the card itself, BOOTSEL (short to
# GND at power-up for the USB boot ROM), and the rails
TEST_PADS = [("TP1", "SWCLK"), ("TP2", "SWDIO"), ("TP3", "RUN"), ("TP4", "BOOTSEL"),
             ("TP5", "+3V3"), ("TP6", "GND"), ("TP7", "1V1"), ("TP8", "RSVD_B1"), ("TP9", "RSVD_B2")]


def schematic(path, footprint_libs):
    s = kg.Schematic("system", "CUPC/8 system card (sysctl RP2040)")

    u1 = s.add("MCU_RaspberryPi:RP2040", "U1", "RP2040",
               "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
               at=(24 * G, 30 * G), fields={"LCSC": "C2040"})
    for name in ("IOVDD", "USB_VDD", "ADC_AVDD", "VREG_VIN"):
        for n, pin in u1.pins.items():
            if pin[3] == name:
                s.connect(u1, n, "+3V3")
    for n, pin in u1.pins.items():
        if pin[3] == "DVDD":
            s.connect(u1, n, "1V1")
    s.connect(u1, "VREG_VOUT", "1V1")
    s.connect(u1, "GND", "GND")
    s.connect(u1, "TESTEN", "GND")
    s.connect(u1, "RUN", "RUN")               # internal pull-up; TP3 to reset
    s.connect(u1, "SWCLK", "SWCLK")
    s.connect(u1, "SWDIO", "SWDIO")
    s.connect(u1, "XIN", "XIN")
    s.connect(u1, "XOUT", "XOUT")
    s.connect(u1, "USB_DP", "USB_DP_MCU")
    s.connect(u1, "USB_DM", "USB_DM_MCU")
    for q, net in (("QSPI_SCLK", "QSPI_SCLK"), ("~{QSPI_SS}", "QSPI_nSS"), ("QSPI_SD0", "QSPI_SD0"),
                   ("QSPI_SD1", "QSPI_SD1"), ("QSPI_SD2", "QSPI_SD2"), ("QSPI_SD3", "QSPI_SD3")):
        s.connect(u1, q, net)
    for g, net in GPIO.items():
        pin = [n for n, p in u1.pins.items() if p[3].split("/")[0] == "GPIO%d" % g]
        s.connect(u1, pin[0], net)

    u2 = s.add("Memory_Flash:W25Q16JVSS", "U2", "W25Q16JVSSIQ", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
               at=(96 * G, 44 * G), fields={"LCSC": "C131025"})
    for pin, net in (("1", "QSPI_nSS"), ("6", "QSPI_SCLK"), ("5", "QSPI_SD0"), ("2", "QSPI_SD1"),
                     ("3", "QSPI_SD2"), ("7", "QSPI_SD3"), ("8", "+3V3"), ("4", "GND")):
        s.connect(u2, pin, net)

    y1 = s.add("jlc:X322512MSB4SI", "Y1", "12MHz", "jlc:CRYSTAL-SMD_4P-L3.2-W2.5-BL",
               at=(120 * G, 44 * G), fields={"LCSC": "C9002"})
    s.connect(y1, "1", "XIN")
    s.connect(y1, "3", "XOUT_X")
    s.connect(y1, "2", "GND")
    s.connect(y1, "4", "GND")

    # USB-C to the host: data only. VBUS goes nowhere (see the module doc).
    # JLC's own footprint (its pads are the ones JLC places: bomcheck, BRD-001)
    j1 = s.add("jlc:TYPE-C-31-M-12", "J1", "TYPE-C-31-M-12", "jlc:USB-C_SMD-TYPE-C-31-M-12_1",
               at=(96 * G, 18 * G), fields={"LCSC": "C165948"})
    for pin, net in (("A1B12", "GND"), ("B1A12", "GND"), ("1", "GND"), ("2", "GND"), ("3", "GND"),
                     ("4", "GND"), ("A5", "USB_CC1"), ("B5", "USB_CC2"), ("A6", "USB_DP"),
                     ("B6", "USB_DP"), ("A7", "USB_DM"), ("B7", "USB_DM")):
        s.connect(j1, pin, net)
    for pin in ("A4B9", "B4A9", "A8", "B8"):    # VBUS goes nowhere; SBU unused
        s.nc(j1, pin)

    # ESD clamps to +3V3, the rail of the pins they protect, not to VBUS:
    # tied to VBUS its steering diodes would lift VBUS to ~2.7 V from the
    # D+ pull-up whenever the card is on and the host is not
    u3 = s.add("Power_Protection:USBLC6-2SC6", "U3", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
               at=(120 * G, 18 * G), fields={"LCSC": "C7519"})
    s.connect(u3, "1", "USB_DP")
    s.connect(u3, "6", "USB_DP")
    s.connect(u3, "3", "USB_DM")
    s.connect(u3, "4", "USB_DM")
    s.connect(u3, "5", "+3V3")
    s.connect(u3, "2", "GND")

    j2 = s.add("cupc8:CUPC8_SystemSlot", "J2", "system slot", "Connector_PCBEdge:BUS_PCIexpress_x4",
               at=(66 * G, 30 * G))
    for n, pin in j2.pins.items():
        name = pin[3]
        if name in ("+3V3", "GND"):
            s.connect(j2, n, name)
        elif name == "+5V" or name.startswith("RSVD_A"):
            s.nc(j2, n)
        elif name.startswith("RSVD_B"):
            # to test pads TP10/TP11 rather than no-connect crosses: on this
            # symbol's left side a cross collides with the next pin's number
            s.connect(j2, n, name)
        elif name in ("PRSNT1_n", "PRSNT2_n"):
            s.connect(j2, n, "PRSNT")        # joined on the card, as on PCIe
        else:
            s.connect(j2, n, name)

    # passives in rows along the bottom of the sheet
    x, y = 8 * G, 64 * G
    for ref, lib, val, fp, lcsc, n1, n2 in PASSIVES:
        led = lib == "Device:LED"
        p = s.add(lib, ref, val, fp, at=(x, y), rot=90 if led else 0, fields={"LCSC": lcsc})
        s.connect(p, "A" if led else 1, n1)
        s.connect(p, "K" if led else 2, n2)
        x += 5 * G
        if x > 156 * G:
            x, y = 8 * G, y + 19 * G
    x, y = x + 4 * G, y
    for ref, net in TEST_PADS:
        p = s.add("Connector:TestPoint", ref, net, TP, at=(x, y))
        s.connect(p, 1, net)
        x += 5 * G

    for i, net in enumerate(("+3V3", "GND")):
        f = s.add("power:PWR_FLAG", "#FLG0%d" % (i + 1), "PWR_FLAG", at=((140 + 6 * i) * G, 60 * G))
        s.connect(f, 1, net)

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


# Board: a 56 x 38 mm body above the x4 card-edge tab (mm, y down). The
# edge footprint draws the tab's own Edge.Cuts; it meets the body at its
# (-0.65, -4.95) and (33.65, -4.95), so at y = 38 with the tab centred.
W, H = 56, 38
EDGE_AT = (W / 2 - 16.5, H + 4.95)
OUTLINE = (0, 0, W, H)
EDGE = [(EDGE_AT[0] - 0.65, H), (0, H), (0, 0), (W, 0), (W, H), (EDGE_AT[0] + 33.65, H)]
LOGO_MM = 12
LABELS = {"D1": "PWR", "D2": "STAT", "D3": "TX", "D4": "RX"}   # silkscreen says what each LED shows
LOGO_AT = (48.8, 28.6)

PLACEMENT = {
    "J2": (EDGE_AT[0], EDGE_AT[1], 0),
    "U1": (28, 17, 0),
    # the HRO drawing puts the board edge 5.79 mm from the locating pegs,
    # which this footprint has at y = -1.21: the edge is at y = 4.58, and the
    # shell overhangs it by 0.51 mm. A half turn faces the opening up.
    "J1": (42, 4.58, 180),
    "U3": (42, 11.5, 0),
    "R2": (41, 15.5, 0), "R3": (41, 17.5, 0),
    "R4": (49.5, 6, 0), "R5": (49.5, 8, 0),
    "U2": (13, 13, 0),
    "C11": (18.5, 7.5, 0),
    "R6": (12, 18.5, 0),
    "Y1": (19, 25, 0),
    "C15": (13.3, 23, 90), "C16": (13.3, 27, 90), "R1": (23, 26.5, 90),
    # decoupling around U1 (28, 17)
    "C1": (21.8, 14.5, 90), "C2": (21.8, 19, 90),
    "C3": (24.5, 23.8, 0), "C9": (31.5, 23.8, 0),
    "C4": (34.2, 19, 90), "C5": (34.2, 14.5, 90), "C13": (36.5, 16.8, 90),
    "C6": (22.4, 10.3, 90), "C10": (25.2, 10.3, 90), "C7": (28, 10.3, 90), "C8": (30.8, 10.3, 90),
    "C12": (33.6, 10.3, 90),
    "C14": (9, 27, 90),
    "R7": (38, 22, 90), "R8": (40, 22, 90),
    "D1": kg.power_led_at(OUTLINE) + (0,), "R9": (6.5, 3, 0),
    "D3": (51, 12, 0), "R20": (51, 14.5, 0),
    "D4": (51, 17, 0), "R21": (51, 19.5, 0),
    "D2": (45, 19, 0), "R10": (45, 21.5, 0),
}
for _i, _n in enumerate(TERMINATED):
    PLACEMENT["R%d" % (11 + _i)] = (14 + 3.4 * _i, 31, 90)
for _i, (_ref, _) in enumerate(TEST_PADS):
    PLACEMENT[_ref] = (2.5, 7.5 + 3 * _i, 0)


# every net on the RP2040's 0.4 mm-pitch pads routes in 0.15 mm track (kicadgen "Fine")
FINE_NETS = sorted({"/" + n for n in list(GPIO.values()) + [
    "+3V3", "1V1", "GND", "RUN", "SWCLK", "SWDIO", "XIN", "XOUT", "USB_DP_MCU", "USB_DM_MCU",
    "QSPI_SCLK", "QSPI_nSS", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3"]})


def main():
    import pcbnew  # noqa: F401 - first, so its start-up noise comes before the step lines
    logo.footprint(LOGO_MM)
    lcsc = kg.pipeline(
        "system", schematic, PLACEMENT, OUTLINE, out=sys.argv[1] if len(sys.argv) > 1 else None,
        # no Power class (0.5 mm tracks): the RP2040's supply pins are 0.2 mm
        # wide at a 0.4 mm pitch, and the whole card draws under 100 mA
        power_nets=(), edge=EDGE, card_edge=True, layers=4, fine_nets=FINE_NETS,
        # the pour reaches over the finger tops, so GND fingers join it
        zone_outline=kg.card_zone(OUTLINE, (EDGE_AT[0] - 0.65, EDGE_AT[0] + 33.65), EDGE_AT[1] - 1.5),
        graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, LOGO_AT[0], LOGO_AT[1], 0)], labels=LABELS)
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
