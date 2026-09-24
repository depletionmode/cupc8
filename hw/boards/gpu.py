#!/usr/bin/env python3
"""The graphics card (doc/hardware/gpu-protocol.md): an RP2040 running
PicoDVI, 640x480 DVI on an HDMI type-A receptacle at the card's top edge.

    python3 hw/boards/gpu.py [outdir]      (default build/hw/gpu)
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

# gpu_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's). TMDS
# pairs are GPIO n (N) and n+1 (P): the firmware inverts the pads, which
# puts the pairs round the chip in the receptacle's order.
TMDS = {"D0": 12, "D1": 14, "D2": 16, "CK": 10}
# GPIO25 (LED_ACT in pins.yaml) has no LED: the GPU card has only its power LED
GPIOS = {0: "UART_TX", 18: "HDMI_HPD", 19: "HDMI_SCL", 20: "HDMI_SDA"}
for lane, g in TMDS.items():
    GPIOS[g], GPIOS[g + 1] = "TMDS_%sN" % lane, "TMDS_%sP" % lane

# HDMI receptacle pins (type A)
HDMI_PINS = {1: "HD_D2P", 3: "HD_D2N", 4: "HD_D1P", 6: "HD_D1N", 7: "HD_D0P", 9: "HD_D0N",
             10: "HD_CKP", 12: "HD_CKN", 15: "DDC_SCL", 16: "DDC_SDA", 18: "HDMI_5V", 19: "HPD_5V"}
HDMI_GND = (2, 5, 8, 11, 17, 20)           # TMDS shields, DDC/CEC ground, shell
HDMI_NC = (13, 14)                          # CEC, utility


def schematic(path, footprint_libs):
    s = kg.Schematic("gpu", "CUPC/8 graphics card (DVI on HDMI)", paper="A2")
    rc.core(s, GPIOS)

    # ---- the receptacle
    j2 = s.add("jlc:HDMI19PIN043", "J2", "HDMI-A", "cupc8:HDMI_A_SHOUHAN_HDMI-19PIN-043",
               at=(214 * G, 40 * G), fields={"LCSC": "C2858275"})
    for pin, net in HDMI_PINS.items():
        s.connect(j2, pin, net)
    for pin in HDMI_GND:
        s.connect(j2, pin, "GND")
    for pin in HDMI_NC:
        s.nc(j2, pin)

    # ---- TMDS: 270 ohm in series with each GPIO, PicoDVI's DC-coupled
    # "DVI PHY" (Wren6991/PicoDVI hardware/mini_board, R12-R19): with the
    # sink's 50 ohm termination to its 3V3, a low GPIO sinks ~10 mA, as TMDS
    # asks. Two 4 x 0603 arrays (0402 arrays have pads 0.15 mm apart, under
    # the 0.2 mm clearance), in the connector's order.
    arrays = {"RN1": ("D2P", "D2N", "D1P", "D1N"), "RN2": ("D0P", "D0N", "CKP", "CKN")}
    for i, (ref, lines) in enumerate(arrays.items()):
        rn = s.add("Device:R_Pack04", ref, "270", "Resistor_SMD:R_Array_Convex_4x0603",
                   at=((188 + 16 * i) * G, 70 * G), fields={"LCSC": "C425067"})
        for k, line in enumerate(lines):
            s.connect(rn, k + 1, "TMDS_" + line)        # chip side
            s.connect(rn, 8 - k, "HD_" + line)          # connector side

    # ---- ESD: two TPD4E05U06 (0.5 pF) on the eight TMDS lines, by the receptacle
    for i, (ref, lines) in enumerate((("U5", ("D2P", "D2N", "D1P", "D1N")), ("U6", ("D0P", "D0N", "CKP", "CKN")))):
        u = s.add("Power_Protection:TPD4E05U06DQA", ref, "TPD4E05U06DQAR", "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
                  at=((188 + 22 * i) * G, 100 * G), fields={"LCSC": "C138714"})
        # flow-through: each line runs straight across its pin and the NC pad
        # opposite (1-10, 2-9, 4-7, 5-6), which is not connected inside, so
        # the NC pad is on the line's net
        for pins, line in zip((("1", "10"), ("2", "9"), ("4", "7"), ("5", "6")), lines):
            for pin in pins:
                s.connect(u, pin, "HD_" + line)
        s.connect(u, "3", "GND")
        s.connect(u, "8", "GND")

    # ---- +5V to the sink (its EDID ROM and hot-plug detect): a 100 mA PTC
    # against a shorted cable, and a Schottky so a monitor can't back-feed
    # the slot's +5V when the machine is off
    f1 = s.add("Device:Polyfuse", "F1", "100mA", "Fuse:Fuse_0805_2012Metric", at=(160 * G, 104 * G),
               fields={"LCSC": "C20975"})
    rc.two(s, f1, "+5V", "HDMI_5V_F")
    d3 = s.add("Device:D_Schottky", "D3", "B5819W", "Diode_SMD:D_SOD-123", at=(160 * G, 122 * G),
               fields={"LCSC": "C8598"})
    s.connect(d3, "A", "HDMI_5V_F")
    s.connect(d3, "K", "HDMI_5V")
    c20 = rc.passive(s, "C", "C20", "100n", (172 * G, 122 * G))
    rc.two(s, c20, "HDMI_5V", "GND")

    # ---- hot-plug detect: the sink pulls HPD to its +5V through 1k; the
    # divider gives 5 V x 33/56 = 2.9 V at the GPIO, and pulls it low unplugged
    r20 = rc.passive(s, "R", "R20", "22k", (180 * G, 112 * G))
    r21 = rc.passive(s, "R", "R21", "33k", (180 * G, 128 * G))
    rc.two(s, r20, "HPD_5V", "HDMI_HPD")
    rc.two(s, r21, "HDMI_HPD", "GND")

    # ---- DDC (EDID): I2C at 5 V on the cable side; a 2N7002 per line as a
    # bidirectional level shifter (gate at 3V3), 2k2 to the HDMI +5V on the
    # cable side as the HDMI source spec asks, 4k7 to 3V3 on the RP2040 side
    for i, (q, line) in enumerate((("Q1", "SCL"), ("Q2", "SDA"))):
        x = 196 + 22 * i
        fet = s.add("Transistor_FET:2N7002", q, "2N7002", "Package_TO_SOT_SMD:SOT-23", at=(x * G, 124 * G),
                    fields={"LCSC": "C8545"})
        s.connect(fet, "G", "3V3")
        s.connect(fet, "S", "HDMI_" + line)
        s.connect(fet, "D", "DDC_" + line)
        rlo = rc.passive(s, "R", "R%d" % (22 + 2 * i), "4k7", ((x - 6) * G, 110 * G))
        rhi = rc.passive(s, "R", "R%d" % (23 + 2 * i), "2k2", ((x + 8) * G, 138 * G))
        rc.two(s, rlo, "3V3", "HDMI_" + line)
        rc.two(s, rhi, "HDMI_5V", "DDC_" + line)

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


POWER_NETS = rc.POWER_NETS         # HDMI_5V (55 mA) stays a signal-width track: pin 18 is 0.3 mm wide
CX, CY = 26, -18               # the RP2040, turned round: its TMDS edge (GPIO10-17) faces the receptacle
HX = CX + 1.5                  # the receptacle's centre: pin n at HX - 4.5 + 0.5 (n - 1), so D2 runs straight up
# Up from the chip: the arrays, the ESD, the receptacle at the top edge. The
# edge's middle pins (RUN, SWD, DVDD, IOVDD, XIN/XOUT) sit between the D2
# and D1 pairs: DVDD's and IOVDD's caps stay in that pocket at their pins,
# the rest leave it through vias, and the crystal sits off to the left.
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    "C12": (CX - 0.7, CY - 5.3, 90),     # DVDD 23
    "C10": (CX - 1.5, CY + 6.2, 0),      # USB_VDD 48
    "C8": (CX - 1.5, CY + 8.2, 0),       # IOVDD 49
    "C5": (CX + 0.3, CY - 5.3, 90),      # IOVDD 22
    "Y1": (CX - 8.5, CY - 4.0, 0),
    "C16": (CX - 11.2, CY - 4.0, 90),
    "C17": (CX - 8.5, CY - 1.4, 0),
    "R2": (CX - 5.8, CY - 6.2, 90),      # XOUT
    "U3": (CX + 9, CY + 9, 0),       # flash, by the QSPI pins (now on the bottom edge)
    "C15": (CX + 10.5, CY + 4.6, 0),
    "R1": (CX + 14.5, CY + 9, 90),
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up: by its finger, clear of the SWD pins
    "U4": (14, -12.5, 0),
    "C18": (10.5, -12.5, 90),
    "J2": (HX, -44 + 6.90, 180),      # the drawing's board edge is 6.90 mm in front of the origin
    "U5": (HX - 3.5, -31.0, 90),     # pins 1-5 face the chip, 0.5 mm apart like the receptacle's
    "U6": (HX, -31.0, 90),
    "RN1": (HX - 4, -28.2, 90),
    "RN2": (HX, -28.2, 90),
    "F1": (39, -42.5, 0),
    "D3": (38.5, -39.5, 0),
    "C20": (36.8, -36.5, 90),
    "R20": (44.5, -42, 90),
    "R21": (44.5, -38.5, 90),
    "Q1": (44, -33, 0),
    "Q2": (44, -28, 0),
    "R22": (40.5, -30.5, 90),
    "R23": (47.5, -33, 90),
    "R24": (40.5, -25.5, 90),
    "R25": (47.5, -28, 90),
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LAYERS = 4
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 46, -16, 0)]
TITLE, REVISION = "CUPC/8 GPU", "A"


if __name__ == "__main__":
    rc.build("gpu", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR"}, GPIOS, TITLE, REVISION,
             layers=LAYERS, passes=100)
