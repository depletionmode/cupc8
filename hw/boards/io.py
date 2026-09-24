#!/usr/bin/env python3
"""The IO card (doc/hardware/io-card.md): an RP2040 as a USB host for a HID
keyboard, on a USB-A receptacle at the card's top edge.

    python3 hw/boards/io.py [outdir]      (default build/hw/io)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402
import rp2040card as rc  # noqa: E402

G = kg.GRID

# io_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's)
GPIOS = {7: "VBUS_EN", 8: "VBUS_nFAULT", 16: "UART_TX", 25: "LED_KBD"}


def schematic(path, footprint_libs):
    s = kg.Schematic("io", "CUPC/8 IO card (USB keyboard)", paper="A2")
    rc.core(s, GPIOS, "KBD", usb=True)

    # ---- VBUS: SY6280AAC switch from the slot's +5V. Ilim = 6800 / Rset:
    # 12k -> 0.57 A nominal (0.42-0.71 A over the +-25% spread), so a
    # keyboard gets its 500 mA and the card stays under the slot's 750 mA PTC
    u5 = s.add("jlc:SY6280AAC", "U5", "SY6280AAC", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL",
               at=(200 * G, 20 * G), fields={"LCSC": "C55136"})
    s.connect(u5, "IN", "+5V")
    s.connect(u5, "OUT", "VBUS")
    s.connect(u5, "GND", "GND")
    s.connect(u5, "ISET", "ISET")
    s.connect(u5, "EN", "VBUS_EN")
    r10 = rc.passive(s, "R", "R10", "12k", (186 * G, 30 * G))
    rc.two(s, r10, "ISET", "GND")
    r11 = rc.passive(s, "R", "R11", "100k", (186 * G, 46 * G))       # EN must not float (RP2040 in reset)
    rc.two(s, r11, "VBUS_EN", "GND")
    c20 = rc.passive(s, "C", "C20", "10u", (214 * G, 12 * G))        # datasheet: 10 uF at IN
    rc.two(s, c20, "+5V", "GND")
    c21 = rc.passive(s, "C", "C21", "100u", (222 * G, 12 * G))       # USB host port bulk (spec: >= 120 uF-ish, 100 uF ceramic)
    rc.two(s, c21, "VBUS", "GND")
    c22 = rc.passive(s, "C", "C22", "100n", (228 * G, 30 * G))
    rc.two(s, c22, "VBUS", "GND")
    # the SY6280AAC has no fault flag: VBUS_nFAULT reads VBUS through a
    # divider (5 V -> 2.97 V), so it goes low when the switch limits and VBUS
    # sags below ~3.4 V, or is shorted
    r12 = rc.passive(s, "R", "R12", "15k", (200 * G, 46 * G))
    r13 = rc.passive(s, "R", "R13", "22k", (200 * G, 64 * G))
    rc.two(s, r12, "VBUS", "VBUS_nFAULT")
    rc.two(s, r13, "VBUS_nFAULT", "GND")

    # ---- USB-A receptacle, ESD, 27 ohm series (design guide). The RP2040's
    # USB PHY switches its own 15k host pull-downs on in host mode.
    j2 = s.add("jlc:USB-302S", "J2", "USB-A", "cupc8:USB_A_SOFNG_USB-302S-T", at=(212 * G, 80 * G),
               fields={"LCSC": "C112455"})
    for pin, net in ((1, "VBUS"), (2, "USB_CONN_DM"), (3, "USB_CONN_DP"), (4, "GND"), (5, "GND"), (6, "GND")):
        s.connect(j2, pin, net)
    u6 = s.add("Power_Protection:USBLC6-2SC6", "U6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
               at=(212 * G, 110 * G), fields={"LCSC": "C7519"})
    s.connect(u6, "1", "USB_CONN_DM")
    s.connect(u6, "6", "USB_CONN_DM")
    s.connect(u6, "3", "USB_CONN_DP")
    s.connect(u6, "4", "USB_CONN_DP")
    s.connect(u6, "VBUS", "VBUS")
    s.connect(u6, "GND", "GND")
    r14 = rc.passive(s, "R", "R14", "27R", (190 * G, 96 * G))
    r15 = rc.passive(s, "R", "R15", "27R", (196 * G, 96 * G))
    rc.two(s, r14, "USB_DM", "USB_CONN_DM")
    rc.two(s, r15, "USB_DP", "USB_CONN_DP")

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


BODY, EDGE, POWER_NETS = rc.BODY, rc.EDGE, rc.POWER_NETS + ("/VBUS",)
# J2's opening is 12.04 mm in front of its footprint origin (the pegs are
# 2.54 mm in front, the shell face 9.5 mm beyond them: C112455 drawing), so
# turned to face up, the origin sits 12.04 mm below the top edge
PLACEMENT = dict(rc.core_placement(20, -24), **{
    "J1": (0, 0, 0),
    "U2": (1.5, -13.5, 0),
    "C1": (-4.5, -13.5, 90),
    "C2": (7.5, -13.5, 90),
    "U4": (17, -10, 0),
    "C18": (20.5, -10, 90),
    "R4": (-2.5, -38, 0),
    "D1": (-2.5, -40.5, 0),
    "R5": (1.5, -38, 0),
    "D2": (1.5, -40.5, 0),
    "J2": (40, -44 + 12.04, 180),
    "U6": (40, -25, 0),
    "R14": (33, -25.5, 90),
    "R15": (35.5, -25.5, 90),
    "U5": (50, -22, 0),
    "C20": (53, -27, 0),
    "C21": (46, -17.5, 0),
    "C22": (45.5, -25.5, 90),
    "R10": (43.5, -21, 90),
    "R11": (46.5, -21, 90),
    "R12": (37, -18, 90),
    "R13": (40, -18, 90),
    "TP1": (24, -8), "TP2": (27.5, -8), "TP3": (31, -8), "TP4": (34.5, -8), "TP5": (38, -8), "TP6": (41.5, -8),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 49.5, -10, 0)]


if __name__ == "__main__":
    rc.build("io", schematic, PLACEMENT, BODY, EDGE, POWER_NETS, GRAPHICS)
