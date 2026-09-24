#!/usr/bin/env python3
"""The storage card (doc/hardware/storage-card.md, card type $04): an
RP2040 with a push-push microSD socket on the card's top edge, SD in SPI
mode on SPI1.

    python3 hw/boards/storage.py [outdir]      (default build/hw/storage)
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

# storage_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's)
GPIOS = {12: "SD_MISO", 13: "SD_nCS", 14: "SD_SCK", 15: "SD_MOSI", 16: "UART_TX", 17: "SD_nDETECT",
         18: "SD_DAT1", 19: "SD_DAT2", 24: "LED_ACT", 25: "LED_CARD"}

# TF-01A pins (jlc:TF-01A, the SD pin names in SPI mode in brackets)
SOCKET = {1: "SD_DAT2", 2: "SD_nCS", 3: "SD_MOSI", 4: "3V3", 5: "SD_SCK", 6: "GND", 7: "SD_MISO", 8: "SD_DAT1",
          9: "SD_nDETECT", 10: "GND", 11: "GND", 12: "GND", 13: "GND"}


def schematic(path, footprint_libs):
    s = kg.Schematic("storage", "CUPC/8 storage card (microSD)", paper="A2")
    # LEDs along the top edge: ACT (media access, GPIO24) and CARD (a card in
    # and mounted, GPIO25)
    rc.core(s, GPIOS, leds=[("LED_ACT", "green"), ("LED_CARD", "green")])

    # ---- the socket: push-push with a card-detect switch that closes to the
    # shell (GND) when a card is in, so SD_nDETECT reads low
    j2 = s.add("jlc:TF-01A", "J2", "microSD", "jlc:TF-SMD_TF-01A", at=(214 * G, 50 * G), fields={"LCSC": "C91145"})
    for pin, net in SOCKET.items():
        s.connect(j2, pin, net)
    c20 = rc.passive(s, "C", "C20", "10u", (186 * G, 20 * G))           # the card's write current, up to ~100 mA
    c21 = rc.passive(s, "C", "C21", "100n", (194 * G, 20 * G))
    rc.two(s, c20, "3V3", "GND")
    rc.two(s, c21, "3V3", "GND")

    # ---- 10k pull-ups on CMD and DAT0-3 (SD spec: the lines float until the
    # card drives them), and on card detect
    rn = s.add("Device:R_Pack04", "RN1", "10k", "Resistor_SMD:R_Array_Convex_4x0603", at=(190 * G, 40 * G),
               fields={"LCSC": "C29718"})
    for k, net in enumerate(("SD_MOSI", "SD_MISO", "SD_DAT1", "SD_DAT2")):
        s.connect(rn, 8 - k, "3V3")
        s.connect(rn, k + 1, net)
    r20 = rc.passive(s, "R", "R20", "10k", (206 * G, 30 * G))
    r21 = rc.passive(s, "R", "R21", "10k", (212 * G, 30 * G))
    rc.two(s, r20, "3V3", "SD_nCS")
    rc.two(s, r21, "3V3", "SD_nDETECT")

    # ---- ESD: two TPD4E05U06 (0.5 pF) on the socket's seven signal lines
    for i, (ref, lines) in enumerate((("U5", ("SD_SCK", "SD_MOSI", "SD_MISO", "SD_nCS")),
                                      ("U6", ("SD_DAT1", "SD_DAT2", "SD_nDETECT", None)))):
        u = s.add("Power_Protection:TPD4E05U06DQA", ref, "TPD4E05U06DQAR", "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
                  at=((188 + 22 * i) * G, 100 * G), fields={"LCSC": "C138714"})
        for pin, net in zip(("1", "2", "4", "5"), lines):
            if net:
                s.connect(u, pin, net)
            else:
                s.nc(u, pin)
        s.connect(u, "3", "GND")
        s.connect(u, "8", "GND")
        for pin in ("6", "7", "9", "10"):
            s.nc(u, pin)

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


POWER_NETS = rc.POWER_NETS
CX, CY = 26, -19               # the RP2040, turned round: its SD pins (GPIO12-19) face the socket
SX = 40                        # the socket: its opening on the top edge
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    # the chip's top edge after the turn: SD pins at its right end and on its
    # left side, so the middle (DVDD, IOVDD, XIN/XOUT, SWD) is open: the
    # crystal goes straight above XIN/XOUT, the flash by the QSPI pins (now
    # at the bottom)
    "C12": (CX + 5.2, CY - 1.2, 0),      # DVDD 23 (its pin escapes by a via: pocket_escapes)
    "C5": (CX - 3.2, CY - 4.6, 0),       # IOVDD 22
    "C10": (CX - 1.5, CY + 6.2, 0),      # USB_VDD 48
    "C8": (CX - 3.2, CY + 7.2, 90),      # IOVDD 49
    "R2": (CX + 3.7, CY - 7.2, 90),      # XOUT
    "Y1": (CX + 0.4, CY - 9.6, 0),
    "C16": (CX - 2.9, CY - 9.6, 90),
    "C17": (CX + 3.7, CY - 9.6, 90),
    "U3": (CX + 7, CY + 9.5, 0),
    "C15": (CX + 7, CY + 5.6, 0),
    "R1": (CX + 12.5, CY + 9.5, 90),
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up, by its finger
    "U4": (14, -12.5, 0),
    "C18": (10.5, -12.5, 90),
    # ACT and CARD in the top-edge row with the power LED, resistors under them
    "D2": (17, -41, 0), "R5": (17, -38.5, 0),
    "D3": (22, -41, 0), "R6": (22, -38.5, 0),
    # the socket turned so its opening faces up, flush with the top edge (its
    # front is 9.5 mm from the footprint origin): the card's push-push travel
    # takes it past the edge
    "J2": (SX, -44 + 9.5, 180),
    "C20": (SX - 0.1, -24.8, 90),
    "C21": (SX + 2.3, -25.3, 90),
    "U5": (SX - 3.6, -25.5, 90),
    "U6": (SX + 5.5, -25.5, 90),
    "RN1": (SX + 10.5, -25.0, 90),
    "R20": (SX - 6.0, -24.0, 90),
    "R21": (SX + 9.8, -30.5, 90),
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LAYERS = 4
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 46, -16, 0)]
TITLE, REVISION = "CUPC/8 storage", "A"


if __name__ == "__main__":
    rc.build("storage", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR", "D2": "ACT", "D3": "CARD"}, GPIOS,
             TITLE, REVISION, layers=LAYERS, passes=100, preroute=rc.pocket_escapes)
