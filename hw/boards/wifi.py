#!/usr/bin/env python3
"""The Wi-Fi card (doc/hardware/wifi-card.md): an ESP32-C3-MINI-1U on a slot
card, powered from the slot's +5V through its own TLV62569 buck, with MISO
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
    # a buck, not an LDO: hw/power (POW-003, THM-001) found the AMS1117 first
    # used here left the ESP32-C3 at 2.71 V in a TX burst at the worst corner
    # (3.0 V minimum) and at Tj 120 C; TI's model of this buck gives 3.22 V
    u2 = s.add("jlc:TLV62569DBVR", "U2", "TLV62569DBVR", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",
               at=(70 * G, 18 * G), fields={"LCSC": "C141836"})
    l1 = s.add("Device:L", "L1", "2.2u", "jlc:IND-SMD_L3.0-W3.0_FNR30XXS", at=(82 * G, 12 * G), rot=90,
               fields={"LCSC": "C167747"})
    u3 = s.add("jlc:74LVC1G125GW_C52140430", "U3", "74LVC1G125GW", "jlc:SOT-353-5_L2.0-W1.6-P0.65-LS2.1-BL",
               at=(70 * G, 80 * G), fields={"LCSC": "C52140430"})

    def passive(kind, ref, val, fp, lcsc, at, rot=90):
        return s.add("Device:" + kind, ref, val, fp, at=at, rot=rot, fields={"LCSC": lcsc})

    c1 = passive("C", "C1", "22u", C0805, "C45783", (60 * G, 26 * G))      # buck in
    c2 = passive("C", "C2", "22u", C0805, "C45783", (86 * G, 26 * G))      # buck out / module bulk
    c3 = passive("C", "C3", "100n", C0603, "C14663", (100 * G, 26 * G))    # at the module's 3V3 pin
    c4 = passive("C", "C4", "100n", C0603, "C14663", (80 * G, 90 * G))     # buffer VCC
    c5 = passive("C", "C5", "1u", C0603, "C15849", (90 * G, 70 * G))       # EN delay (Espressif: 10k/1u)
    r9 = passive("R", "R9", "453k", R0603, "C25818", (60 * G, 38 * G))     # feedback: 0.6 V x (1 + 453/100) = 3.32 V
    r10 = passive("R", "R10", "100k", R0603, "C25803", (60 * G, 46 * G))
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
    s.connect(u2, "EN", "+5V")
    s.connect(u2, "GND", "GND")
    s.connect(u2, "SW", "SW")
    s.connect(u2, "FB", "FB")
    s.connect(l1, 1, "SW")
    s.connect(l1, 2, "3V3")
    s.connect(r9, 1, "3V3")
    s.connect(r9, 2, "FB")
    s.connect(r10, 1, "FB")
    s.connect(r10, 2, "GND")
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
    "U3": (26, -15, 90),
    "C4": (26, -18.5, 0),
    "U2": (4, -15, 0),
    "L1": (4, -20, 0),
    "R9": (9, -16, 90),
    "R10": (11, -16, 90),
    "C1": (-2.5, -9, 90),
    "C2": (11, -12.5, 90),                 # clear of the fingers' GND ties (up to y = -9.45)
    "U1": (41, -29, 0),                    # the U.FL end towards the top edge, clear of H1
    "C3": (32.5, -31.4, 0),                # beside U1's 3V3 pin (pin 3)
    "R1": (30, -14, 90),
    "C5": (32, -14, 90),
    "R2": (52, -20, 90),
    "R3": (50, -20, 90),
    "R4": (48, -20, 90),
    # LINK, TX, RX along the top edge, in a row with the power LED
    # (milestone-1.md, Indicator LEDs), each resistor under its LED as R5
    "D2": (4, -41, 0),
    "R6": (4, -38.5, 0),
    "D3": (10, -41, 0),
    "R7": (10, -38.5, 0),
    "D4": (16, -41, 0),
    "R8": (16, -38.5, 0),
    "TP1": (34, -38, 0),
    "TP2": (28, -38, 0),
}
LOGO_MM = 12
# doc/milestone-1.md, Board revision: bump for every board sent to be made
TITLE, REVISION = "CUPC/8 Wi-Fi", "A"


def main():
    logo.footprint(LOGO_MM)
    lcsc = kg.pipeline("wifi", schematic, PLACEMENT, BODY, out=sys.argv[1] if len(sys.argv) > 1 else None,
                       io_card=True, power_nets=("/+5V", "/3V3", "/GND"),
                       graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 7, -29, 0)],
                       labels={"D1": "PWR", "D2": "LINK", "D3": "TX", "D4": "RX"},
                       title=TITLE, revision=REVISION, logo_keepout=True)    # bottom right
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
