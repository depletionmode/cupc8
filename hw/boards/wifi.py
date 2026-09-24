#!/usr/bin/env python3
"""The Wi-Fi card (doc/hardware/wifi-card.md): an ESP32-C3-MINI-1U on a slot
card, powered from the slot's +5V through its own AMS1117-3.3, with MISO
released through a 74LVC1G125 whenever the card is not selected.

    python3 hw/boards/wifi.py [outdir]      (default build/hw/wifi)
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

# ESP32-C3 GPIOs (hw/pins.yaml, wifi_mcu); the symbol names them IOn
SLOT_GPIO = {"SCK": "IO6", "MOSI": "IO7", "MISO_OUT": "IO5", "CS_n": "IO10", "IRQ_n": "IO3"}


def schematic(path, footprint_libs):
    s = kg.Schematic("wifi", "CUPC/8 Wi-Fi card")
    j1 = s.add("cupc8:CUPC8_Slot", "J1", "slot", "Connector_PCBEdge:BUS_PCIexpress_x1", at=(30 * G, 50 * G))
    u1 = s.add("jlc:ESP32-C3-MINI-1U-N4", "U1", "ESP32-C3-MINI-1U-N4",
               "jlc:WIFIM-SMD_61P-L13.2-W12.5-P0.80", at=(110 * G, 50 * G), fields={"LCSC": "C2911374"})
    u2 = s.add("jlc:AMS1117-3.3", "U2", "AMS1117-3.3", "jlc:SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR",
               at=(70 * G, 18 * G), fields={"LCSC": "C6186"})
    u3 = s.add("jlc:74LVC1G125GW_C52140430", "U3", "74LVC1G125GW", "jlc:SOT-353-5_L2.0-W1.6-P0.65-LS2.1-BL",
               at=(70 * G, 80 * G), fields={"LCSC": "C52140430"})

    def passive(kind, ref, val, fp, lcsc, at, rot=90):
        return s.add("Device:" + kind, ref, val, fp, at=at, rot=rot, fields={"LCSC": lcsc})

    c1 = passive("C", "C1", "22u", C0805, "C45783", (60 * G, 26 * G))      # regulator in
    c2 = passive("C", "C2", "22u", C0805, "C45783", (82 * G, 26 * G))      # regulator out / module bulk
    c3 = passive("C", "C3", "100n", C0603, "C14663", (96 * G, 26 * G))     # at the module's 3V3 pin
    c4 = passive("C", "C4", "100n", C0603, "C14663", (80 * G, 90 * G))     # buffer VCC
    c5 = passive("C", "C5", "1u", C0603, "C15849", (90 * G, 70 * G))       # EN delay (Espressif: 10k/1u)
    r1 = passive("R", "R1", "10k", R0603, "C25804", (90 * G, 60 * G))      # EN pull-up
    r2 = passive("R", "R2", "10k", R0603, "C25804", (136 * G, 14 * G), rot=0)     # GPIO9 boot strap: normal boot
    r3 = passive("R", "R3", "10k", R0603, "C25804", (136 * G, 30 * G), rot=0)     # GPIO8 strap high
    r4 = passive("R", "R4", "10k", R0603, "C25804", (136 * G, 46 * G), rot=0)     # GPIO2 strap high
    r5 = passive("R", "R5", "1k", R0603, "C21190", (108 * G, 18 * G))      # power LED
    # red: a green LED drops ~3 V, too close to the 3.3 V rail for 1 kOhm (~1.3 mA here)
    d1 = s.add("Device:LED", "D1", "red", "LED_SMD:LED_0603_1608Metric", at=(108 * G, 28 * G), rot=90,
               fields={"LCSC": "C2286"})
    # green, so 100 Ohm: 2-6 mA over its 2.7-3.1 V spread, well inside GPIO4's drive
    r6 = passive("R", "R6", "100", R0603, "C22775", (146 * G, 70 * G))     # link LED
    d2 = s.add("Device:LED", "D2", "green", "LED_SMD:LED_0603_1608Metric", at=(146 * G, 80 * G), rot=90,
               fields={"LCSC": "C12624"})
    # TX/RX: socket data sent and received (milestone-1.md, Indicator LEDs), green like LINK
    r7 = passive("R", "R7", "100", R0603, "C22775", (40 * G, 82 * G))       # TX LED
    d3 = s.add("Device:LED", "D3", "green", "LED_SMD:LED_0603_1608Metric", at=(40 * G, 92 * G), rot=90,
               fields={"LCSC": "C12624"})
    r8 = passive("R", "R8", "100", R0603, "C22775", (56 * G, 82 * G))       # RX LED
    d4 = s.add("Device:LED", "D4", "green", "LED_SMD:LED_0603_1608Metric", at=(56 * G, 92 * G), rot=90,
               fields={"LCSC": "C12624"})
    h1 = s.add("Mechanical:MountingHole", "H1", "M3", kg.MOUNTING_HOLE, at=(20 * G, 100 * G))
    tp1 = s.add("Connector:TestPoint", "TP1", "USB_D-", "cupc8:TestPad_D1.0mm", at=(152 * G, 50 * G),
                rot=90)
    tp2 = s.add("Connector:TestPoint", "TP2", "USB_D+", "cupc8:TestPad_D1.0mm", at=(152 * G, 56 * G),
                rot=90)
    f1 = s.add("power:PWR_FLAG", "#FLG01", "PWR_FLAG", at=(50 * G, 12 * G))
    f2 = s.add("power:PWR_FLAG", "#FLG02", "PWR_FLAG", at=(56 * G, 12 * G))

    # the slot (doc/hardware/slot.md)
    for p in ("B1", "B2", "A2"):
        s.connect(j1, p, "+5V")
    for p in ("B3", "A3", "B5", "A5", "B8", "A8", "B11", "A11", "B12", "A12", "A13", "B14", "A15", "B17", "A17"):
        s.connect(j1, p, "GND")
    s.connect(j1, "A1", "PRSNT")               # PRSNT1_n joined to PRSNT2_n: seated card
    s.connect(j1, "B18", "PRSNT")
    for p in ("B4", "A4"):                     # the card regulates its own 3V3 from +5V
        s.nc(j1, p)
    for p in ("A6", "A7", "A9", "A10", "A16"):  # RSVD
        s.nc(j1, p)
    s.connect(j1, "B6", "U0RXD")               # SWCLK: sysctl -> card UART
    s.connect(j1, "B7", "U0TXD")               # SWDIO: card -> sysctl UART
    s.connect(j1, "B9", "EN")                  # CARD_RST_n, open drain on the main board
    s.connect(j1, "B10", "IRQ_n")
    s.connect(j1, "B13", "SCK")
    s.connect(j1, "A14", "CS_n")
    s.connect(j1, "B15", "MOSI")
    s.connect(j1, "B16", "MISO")
    s.connect(j1, "A18", "BOOT")               # PROG_n -> GPIO9

    # power
    s.connect(u2, "VIN", "+5V")
    s.connect(u2, "GND", "GND")
    s.connect(u2, "2", "3V3")                  # the tab (4) is stacked on VOUT
    s.connect(u2, "4", "3V3")
    for c, net in ((c1, "+5V"), (c2, "3V3"), (c3, "3V3"), (c4, "3V3")):
        s.connect(c, 1, net)
        s.connect(c, 2, "GND")
    s.connect(f1, 1, "+5V")
    s.connect(f2, 1, "GND")

    # the module
    for num, (_, _, _, name, *_) in sorted(u1.pins.items(), key=lambda kv: int(kv[0])):
        if name == "GND":
            s.connect(u1, num, "GND")
        elif name == "NC":
            s.nc(u1, num)
    s.connect(u1, "3V3", "3V3")
    s.connect(u1, "EN", "EN")
    s.connect(u1, SLOT_GPIO["SCK"], "SCK")
    s.connect(u1, SLOT_GPIO["MOSI"], "MOSI")
    s.connect(u1, SLOT_GPIO["MISO_OUT"], "MISO_INT")
    s.connect(u1, SLOT_GPIO["CS_n"], "CS_n")
    s.connect(u1, SLOT_GPIO["IRQ_n"], "IRQ_n")
    s.connect(u1, "RXD0", "U0RXD")
    s.connect(u1, "TXD0", "U0TXD")
    s.connect(u1, "IO9", "BOOT")
    s.connect(u1, "IO8", "STRAP8")
    s.connect(u1, "IO2", "STRAP2")
    s.connect(u1, "IO4", "LED_LINK")
    s.connect(u1, "IO18", "USB_DN")
    s.connect(u1, "IO19", "USB_DP")

    # EN: RC per Espressif; CARD_RST_n pulls it low
    s.connect(r1, 1, "3V3")
    s.connect(r1, 2, "EN")
    s.connect(c5, 1, "EN")
    s.connect(c5, 2, "GND")
    # straps
    for r, net in ((r2, "BOOT"), (r3, "STRAP8"), (r4, "STRAP2")):
        s.connect(r, 1, "3V3")
        s.connect(r, 2, net)

    # MISO released unless this card is selected
    s.connect(u3, "~{OE}", "CS_n")
    s.connect(u3, "A", "MISO_INT")
    s.connect(u3, "Y", "MISO")
    s.connect(u3, "VCC", "3V3")
    s.connect(u3, "GND", "GND")

    # LEDs
    s.connect(r5, 1, "3V3")
    s.connect(r5, 2, "LED_PWR")
    s.connect(d1, "A", "LED_PWR")
    s.connect(d1, "K", "GND")
    s.connect(r6, 1, "LED_LINK")
    s.connect(r6, 2, "LED_LINK_A")
    s.connect(d2, "A", "LED_LINK_A")
    s.connect(d2, "K", "GND")

    s.connect(u1, "IO0", "LED_TX")
    s.connect(u1, "IO1", "LED_RX")
    for r, d, net in ((r7, d3, "LED_TX"), (r8, d4, "LED_RX")):
        s.connect(r, 1, net)
        s.connect(r, 2, net + "_A")
        s.connect(d, "A", net + "_A")
        s.connect(d, "K", "GND")
    del h1                                     # a hole: no pins

    # native USB-Serial/JTAG, for debugging only
    s.connect(tp1, 1, "USB_DN")
    s.connect(tp2, 1, "USB_DP")

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


# Board coordinates (mm). The finger tab is the footprint's: x -0.65..19.65,
# meeting the body at y = -4.95; the body extends up (negative y).
BODY = kg.IO_CARD_BODY                      # every I/O card's outline (slot.md, Mechanical)
EDGE = kg.IO_CARD_EDGE
PLACEMENT = {
    "H1": kg.IO_CARD_HOLE + (0,),
    "D1": kg.IO_CARD_PWR_LED + (0,),           # the power LED: the same place on every board
    "R5": (-3, -38.5, 0),
    "J1": (0, 0, 0),
    "U3": (26, -15, 0),
    "C4": (26, -18.5, 0),
    "U2": (4, -14, 0),
    "C1": (-2.5, -9, 90),
    "C2": (11, -12.5, 90),                 # clear of the fingers' GND ties (up to y = -9.45)
    "U1": (41, -29, 0),                    # the U.FL end towards the top edge, clear of H1
    "C3": (32.5, -31.4, 0),                # beside U1's 3V3 pin (pin 3)
    "R1": (30, -14, 90),
    "C5": (32, -14, 90),
    "R2": (52, -20, 90),
    "R3": (50, -20, 90),
    "R4": (48, -20, 90),
    "R6": (19, -24, 0),
    "D2": (19, -26.5, 0),                  # LINK, TX, RX in a row
    "R7": (25, -24, 0),
    "D3": (25, -26.5, 0),
    "R8": (31, -24, 0),
    "D4": (31, -26.5, 0),
    "TP1": (34, -38, 0),
    "TP2": (28, -38, 0),
}
LOGO_MM = 12


def main():
    logo.footprint(LOGO_MM)
    lcsc = kg.pipeline("wifi", schematic, PLACEMENT, BODY, out=sys.argv[1] if len(sys.argv) > 1 else None,
                       edge=EDGE, card_edge=True, zone_outline=kg.card_zone(BODY, kg.IO_CARD_TAB, -1.5), power_nets=("/+5V", "/3V3", "/GND"),
                       graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 10, -35, 0)],
                       labels={"D1": "PWR", "D2": "LINK", "D3": "TX", "D4": "RX"})
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
