#!/usr/bin/env python3
"""The Wi-Fi card (doc/hardware/wifi-card.md): an ESP32-C3-MINI-1U on a slot
card, powered from the slot's +5V through its own TLV62569 buck, with MISO
released through a TI LVC buffer whenever the card is not selected; a 220 ohm
source resistor and 47k ground bias damp the shared return. Three permanently
enabled local TI stages isolate the ESP clock/data/select input pads.

    python3 hw/boards/wifi.py [outdir]      (default build/hw/wifi)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402
import fillfeature as ff  # noqa: E402
import logo  # noqa: E402
import rp2040card as rc  # noqa: E402

G = kg.GRID
R0402 = "Resistor_SMD:R_0402_1005Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# ESP32-C3 GPIOs (hw/pins.yaml, wifi_mcu); the symbol names them IOn
SLOT_GPIO = {"SCK": "IO6", "MOSI": "IO7", "MISO_OUT": "IO5", "CS_n": "IO10", "IRQ_n": "IO3"}


def schematic(path, footprint_libs):
    s = kg.Schematic("wifi", "CUPC/8 Wi-Fi card", paper="A1")
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
    # Generic KiCad logic graphics leave signal names blank. Annotate the
    # actual TI DCK numeric pins for independent BOM/datasheet checks;
    # numbers, locations, pin electrical types and circuit nets stay exact.
    logic = s._symbol("74xGxx:74LVC1G125")
    names = {"1": "~{OE}", "2": "A", "3": "GND", "4": "Y", "5": "VCC"}
    seen = set()
    for unit in kg.find(logic, "symbol"):
        for pin in kg.find(unit, "pin"):
            number = str(kg.find1(pin, "number")[1])
            if number not in names:
                raise ValueError("unexpected TI125 generic symbol pin " + number)
            kg.find1(pin, "name")[1] = kg.Q(names[number])
            seen.add(number)
    if seen != set(names):
        raise ValueError("TI125 generic symbol numeric pin set changed")
    if not kg.find1(logic, "pin_names"):
        logic.insert(2, ["pin_names", "hide"])
    else:
        kg.find1(logic, "pin_names").append("hide")
    rc.hide_pin_numbers(s, "74xGxx:74LVC1G125")

    u3 = s.add("74xGxx:74LVC1G125", "U3", "SN74LVC1G125DCKR", "jlc:SC-70-5_L2.1-W1.3-P0.65-LS2.1-BR",
               at=(70 * G, 80 * G), fields={"LCSC": "C7833"})

    def passive(kind, ref, val, fp, lcsc, at, rot=90):
        return s.add("Device:" + kind, ref, val, fp, at=at, rot=rot, fields={"LCSC": lcsc})

    c1 = passive("C", "C1", "22u", C0805, "C602037", (60 * G, 26 * G))     # buck in (CL21A226MAYNNNE; MAQ C45783 is NRND)
    c2 = passive("C", "C2", "22u", C0805, "C602037", (86 * G, 26 * G))     # buck out / module bulk
    c3 = passive("C", "C3", "100n", C0603, "C14663", (100 * G, 26 * G))    # at the module's 3V3 pin
    c4 = passive("C", "C4", "100n", C0603, "C14663", (80 * G, 90 * G))     # buffer VCC
    c5 = passive("C", "C5", "1u", C0603, "C15849", (90 * G, 70 * G))       # EN delay (Espressif: 10k/1u)
    r9 = passive("R", "R9", "453k", R0603, "C861412", (60 * G, 38 * G))     # feedback: 0.6 V x (1 + 453/100) = 3.32 V
    r10 = passive("R", "R10", "100k", R0603, "C122538", (60 * G, 46 * G))
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
    # Regulated power crosses the passive inductor before the LVC VCC pin.
    f3 = s.add("power:PWR_FLAG", "#FLG03", "PWR_FLAG", at=(120 * G, 12 * G))
    s.connect(f3, 1, "3V3")

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
    s.connect(u1, SLOT_GPIO["SCK"], "WIFI_SCK_PAD")
    s.connect(u1, SLOT_GPIO["MOSI"], "WIFI_MOSI_PAD")
    s.connect(u1, SLOT_GPIO["MISO_OUT"], "MISO_INT")
    s.connect(u1, SLOT_GPIO["CS_n"], "WIFI_CS_n_PAD")
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
    s.connect(u3, "~{OE}", "CS_OE")
    s.connect(u3, "A", "MISO_INT")
    s.connect(u3, "Y", "MISO_SRC")
    r60 = passive("R", "R60", "220", R0402, "C25091", (70 * G, 100 * G))
    r61 = passive("R", "R61", "47k", R0402, "C25792", (90 * G, 100 * G))
    s.connect(r60, 1, "MISO_SRC")
    s.connect(r60, 2, "MISO")
    s.connect(r61, 1, "MISO")
    s.connect(r61, 2, "GND")
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

    # Permanent local TI stages isolate all three ESP input pads from the slot rail.
    # Exact physical routes are a separate extracted SI qualification.
    for i, (signal, uref, rin, rout, cin, cout, bypass, capval, capcode) in enumerate((
            ("CS_n", "U4", "R62", "R63", "C60", "C61", "C62", "10p", "C32949"),
            ("SCK", "U5", "R64", "R65", "C63", "C64", "C65", "5.6p", "C161329"),
            ("MOSI", "U6", "R66", "R67", "C66", "C67", "C68", "4.7p", "C161327"))):
        row = (30 + 50 * i) * G
        a, y, pad = ("WIFI_" + signal + suffix for suffix in ("_A", "_Y", "_PAD"))
        u = s.add("74xGxx:74LVC1G125", uref, "SN74LVC1G125DCKR",
                  "jlc:SC-70-5_L2.1-W1.3-P0.65-LS2.1-BR", at=(230 * G, row), fields={"LCSC": "C7833"})
        for pin, name in ((1, "GND"), (2, a), (3, "GND"), (4, y), (5, "3V3")):
            s.connect(u, pin, name)
        for ref, first, second, at in ((rin, signal, a, (200 * G, row)), (rout, y, pad, (260 * G, row))):
            r = passive("R", ref, "270" if ref in ("R63", "R65") else "220", R0402,
                        "C25099" if ref in ("R63", "R65") else "C25091", at, rot=0)
            s.connect(r, 1, first); s.connect(r, 2, second)
        for ref, value, code, name, at in ((cin, capval, capcode, a, (200 * G, row + 18 * G)),
                (cout, "10p", "C32949", (pad + "_CAP" if cout in ("C61", "C64") else pad), (260 * G, row + 18 * G)),
                (bypass, "100n", "C1525", "3V3", (230 * G, row + 18 * G))):
            c = passive("C", ref, value, "Capacitor_SMD:C_0402_1005Metric", code, at)
            s.connect(c, 1, name); s.connect(c, 2, "GND")
    # Series damping in the capacitor shunt branches only; no change to
    # the ESP endpoints or physical routes; R63/R65 have separate output damping.
    for ref, net, at in (("R69", "WIFI_CS_n_PAD", (270 * G, 58 * G)),
                         ("R70", "WIFI_SCK_PAD", (270 * G, 108 * G))):
        r = passive("R", ref, "15", R0402, "C25083", at, rot=0)
        s.connect(r, 1, net); s.connect(r, 2, net + "_CAP")
    r68 = passive("R", "R68", "220", R0402, "C25091", (75 * G, 122 * G), rot=0)
    s.connect(r68, 1, "CS_n"); s.connect(r68, 2, "CS_OE")
    c69 = passive("C", "C69", "10p", "Capacitor_SMD:C_0402_1005Metric", "C32949", (90 * G, 122 * G))
    s.connect(c69, 1, "CS_OE"); s.connect(c69, 2, "GND")

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
    "R60": (22.5, -15.65, 180),
    "R61": (21, -16.16, 90),
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
PLACEMENT.update({'R5': (-3.0, -38.5, 0.0), 'R4': (48.0, -20.0, 90.0), 'R9': (9.0, -16.0, 90.0), 'R62': (35.5, -20.8811, -90.0), 'U1': (41.0, -29.0, 0.0), 'H1': (52.0, -40.0, 0.0), 'R8': (16.0, -38.5, 0.0), 'L1': (4.0, -20.0, 0.0), 'D3': (10.0, -41.0, 0.0), 'C2': (11.0, -12.5, 90.0), 'R61': (21.0, -16.16, 90.0), 'C1': (-2.5, -9.0, 90.0), 'R6': (4.0, -38.5, 0.0), 'U3': (26.0, -15.0, 0.0), 'R67': (50.0, -23.0, 0.0), 'TP2': (28.0, -38.0, 0.0), 'C3': (32.5, -31.4, 0.0), 'R3': (50.0, -20.0, 90.0), 'D4': (16.0, -41.0, 0.0), 'C4': (26.0, -18.5, 0.0), 'R2': (52.0, -20.0, 90.0), 'R60': (22.5, -15.65, 180.0), 'C69': (25.5, -13.0, 0.0), 'C5': (32.0, -14.0, 90.0), 'J1': (0.0, 0.0, 0.0), 'D2': (4.0, -41.0, 0.0), 'U2': (4.0, -15.0, 0.0), 'D1': (-3.0, -41.0, 0.0), 'R10': (11.0, -16.0, 90.0), 'TP1': (34.0, -38.0, 0.0), 'R7': (10.0, -38.5, 0.0), 'R1': (30.0, -14.0, 90.0), 'C62': (36.25, -19.75, -90.0, 'B'), 'C66': (47.5, -19.25, 180.0, 'B'), 'U5': (47.75, -25.5, 0.0, 'B'), 'C63': (48.0, -28.75, 90.0, 'B'), 'C67': (43.75, -30.25, 90.0, 'B'), 'R65': (45.5, -25.0, 90.0, 'B'), 'R64': (41.5, -22.25, 180.0, 'B'), 'C60': (33.5, -23.0, 90.0, 'B'), 'R63': (34.0, -20.5, 180.0, 'B'), 'C64': (42.5, -25.5, 90.0, 'B'), 'U4': (36.5, -22.0, 90.0, 'B'), 'R66': (49.5, -20.25, -90.0, 'B'), 'C61': (39.5, -24.25, 0.0, 'B'), 'U6': (48.05, -22.1, -90.0, 'B'), 'C68': (49.0, -29.5, 90.0, 'B'), 'C65': (45.75, -29.5, 90.0, 'B')})
PLACEMENT.update({'C63': (48.0, -28.0, 270.0, 'B'), 'C69': (25.5, -11.4, 0.0), 'R68': (27.8, -11.8, 90.0)})
LOGO_MM = 12
# doc/milestone-1.md, Board revision: bump for every board sent to be made
TITLE, REVISION = "CUPC/8 Wi-Fi", "A"



# Visible references are pinned to the independently checked two-sided layout.
_SPI_REF_POSITIONS = {'R5': (-3.0, -36.825, 0.0, 1.0, 0.15, True), 'R4': (45.425, -19.0, 0.0, 1.0, 0.15, True), 'R9': (9.0, -13.575, 0.0, 1.0, 0.15, True), 'R62': (38.500001, -18.106099, 90.0, 0.8, 0.15, True), 'U1': (41.0, -36.845, 0.0, 1.0, 0.15, True), 'H1': (52.001264, -35.602474, 0.0, 1.0, 0.15, True), 'R8': (16.0, -36.825, 0.0, 1.0, 0.15, True), 'L1': (4.0, -22.445, 0.0, 1.0, 0.15, True), 'D3': (10.0, -42.43, 0.0, 1.0, 0.15, False), 'C2': (13.825, -12.5, 0.0, 1.0, 0.15, True), 'R61': (18.685, -16.16, 0.0, 1.0, 0.15, True), 'C1': (-2.5, -6.355, 0.0, 1.0, 0.15, True), 'R6': (4.0, -36.825, 0.0, 1.0, 0.15, True), 'U3': (29.85, -18.0, 0.0, 1.0, 0.15, True), 'R67': (52.775, -25.0, 0.0, 0.8, 0.15, True), 'TP2': (27.998759, -40.046236, 0.0, 1.0, 0.15, True), 'C3': (29.175, -31.4, 0.0, 1.0, 0.15, True), 'R3': (50.0, -17.575, 0.0, 1.0, 0.15, True), 'D4': (16.0, -42.43, 0.0, 1.0, 0.15, False), 'C4': (22.675, -18.5, 0.0, 1.0, 0.15, True), 'R2': (54.574999, -20.0, 0.0, 1.0, 0.15, True), 'R60': (19.724999, -12.649999, 0.0, 1.0, 0.15, True), 'R68': (27.8, -9.1, 0.0, 0.8, 0.15, True), 'C69': (22.745, -8.4, 0.0, 0.8, 0.15, True), 'C5': (34.574999, -13.0, 0.0, 1.0, 0.15, True), 'J1': (8.5, -6.395, 0.0, 1.0, 0.15, True), 'D2': (4.0, -42.43, 0.0, 1.0, 0.15, False), 'U2': (4.0, -17.395, 0.0, 1.0, 0.15, True), 'D1': (-3.0, -42.43, 0.0, 1.0, 0.15, False), 'R63': (35.75, -18.75, 0.0, 0.8, 0.15, True), 'R10': (13.575, -16.0, 0.0, 1.0, 0.15, True), 'G1': (7.0, -29.0, 0.0, 1.0, 0.15, False), 'TP1': (33.998759, -40.046236, 0.0, 1.0, 0.15, True), 'R7': (10.0, -36.825, 0.0, 1.0, 0.15, True), 'R1': (29.0, -11.575, 0.0, 1.0, 0.15, True), 'C62': (38.555, -18.75, 0.0, 0.8, 0.15, True), 'R69': (40.5, -25.25, 0.0, 0.8, 0.15, True), 'C66': (50.254999, -18.25, 0.0, 0.8, 0.15, True), 'U5': (43.0, -28.0, 0.0, 0.8, 0.15, True), 'C63': (45.695, -31.0, 0.0, 0.8, 0.15, True), 'C67': (41.445, -30.25, 0.0, 0.8, 0.15, True), 'R65': (44.9, -19.8, 0.0, 0.8, 0.15, True), 'R64': (40.7, -20.45, 0.0, 0.8, 0.15, True), 'C60': (31.195, -22.0, 0.0, 0.8, 0.15, True), 'C64': (42.5, -23.645, 0.0, 0.8, 0.15, True), 'U4': (36.5, -24.95, 0.0, 0.8, 0.15, True), 'R66': (51.815, -21.25, 0.0, 0.8, 0.15, True), 'C61': (39.5, -27.055, 0.0, 0.8, 0.15, True), 'U6': (51.199999, -25.1, 0.0, 0.8, 0.15, True), 'C68': (51.305, -28.5, 0.0, 0.8, 0.15, True), 'R70': (46.0, -27.5, 0.0, 0.8, 0.15, True), 'C65': (47.25, -32.754999, 0.0, 0.8, 0.15, True)}

_SPI_REF_POSITIONS['R68'] = (27.8, -9.1, 0.0, 0.8, 0.15, True)

def _pin_spi_designators(board):
    import pcbnew
    for ref, (x, y, angle, size, stroke, visible) in _SPI_REF_POSITIONS.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            raise ValueError("SPI physical reference missing: " + ref)
        text = fp.Reference()
        text.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        text.SetTextAngleDegrees(angle)
        text.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        text.SetTextThickness(pcbnew.FromMM(stroke))
        text.SetVisible(visible)
        text.SetLayer(pcbnew.B_SilkS if fp.IsFlipped() else pcbnew.F_SilkS)
        text.SetMirrored(fp.IsFlipped())

def _finish_spi(board):
    import pcbnew, route_seed
    route_seed.verify_installed(board, os.path.join(HERE, "wifi-full-route-seed.json"))
    # Remove only the new U6 marker clipped by its necessary local GND return.
    fp = board.FindFootprintByReference("U6")
    graphics = fp.GraphicalItems()
    for item in [graphics[i].Cast() for i in range(len(graphics))]:
        if item.GetLayer() == pcbnew.B_SilkS and item.GetShape() == pcbnew.SHAPE_T_CIRCLE:
            fp.Remove(item)
            item.thisown = False
    kg.clip_silk_to_pads(board)
    _pin_spi_designators(board)

PLACEMENT.update({'R63': (37.25, -22.0, 90.0), 'R69': (40.5, -23.25, 180.0, 'B'), 'R70': (43.5, -25.25, 90.0, 'B')})

def _seeded_route(board, workdir):
    import route_seed
    result = route_seed.apply(
        board, os.path.join(HERE, "wifi-full-route-seed.json"),
        board_name="wifi", pour_nets=("/GND",),
        post_route_contract="wifi-lvc-permanent-local-spi-oe-v2")
    print("Wi-Fi full-route seed: %d copper items; origin %s; fresh full pipeline required" %
          (result['added'], result['origin_state']), end=" ", flush=True)
    return 0


def main():
    logo.footprint(LOGO_MM)
    lcsc = kg.pipeline("wifi", schematic, PLACEMENT, BODY, out=sys.argv[1] if len(sys.argv) > 1 else None,
                       io_card=True, power_nets=("/+5V", "/3V3", "/GND"),
                       graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 7, -29, 0)],
                       labels={"D1": "PWR", "D2": "LINK", "D3": "TX", "D4": "RX"},
                       title=TITLE, revision=REVISION, logo_keepout=True,    # bottom right
                       prepare=lambda board: rc.miso_launch(board, "U3", oe_net="/CS_OE"),
                       seeded_route=_seeded_route,
                       post_route=_finish_spi,
                       post_fill=(lambda board: ff.round_board_fills(board, "wifi")),
                       designator_reach=4,
                       pad_via_clear=0.1)      # no open via hole in the module's GND pads (audit I6)
    print("LCSC:", " ".join(sorted(lcsc)))


# The 51 mm finished card keeps its finger datum and central circuitry fixed.
# Move only perimeter fittings to the new top edge; the local routed seed
# and fresh full fabrication pipeline qualify their changed connections.
TOP_EDGE_SHIFT_MM = 3.55
TOP_EDGE_MOVED_REFS = ('H1', 'D1', 'R5', 'D2', 'R6', 'D3', 'R7', 'D4', 'R8')
for _ref in TOP_EDGE_MOVED_REFS:
    _at = PLACEMENT[_ref]
    PLACEMENT[_ref] = (_at[0], _at[1] - TOP_EDGE_SHIFT_MM, *_at[2:])


if __name__ == "__main__":
    main()
