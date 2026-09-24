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
GPIOS = {0: "UART_TX", 18: "HDMI_HPD", 19: "HDMI_SCL", 20: "HDMI_SDA", 25: "LED_ACT"}
for lane, g in TMDS.items():
    GPIOS[g], GPIOS[g + 1] = "TMDS_%sN" % lane, "TMDS_%sP" % lane

# HDMI receptacle pins (type A)
HDMI_PINS = {1: "HD_D2P", 3: "HD_D2N", 4: "HD_D1P", 6: "HD_D1N", 7: "HD_D0P", 9: "HD_D0N",
             10: "HD_CKP", 12: "HD_CKN", 15: "DDC_SCL", 16: "DDC_SDA", 18: "HDMI_5V", 19: "HPD_5V"}
HDMI_GND = (2, 5, 8, 11, 17, 20)           # TMDS shields, DDC/CEC ground, shell
HDMI_NC = (13, 14)                          # CEC, utility


def schematic(path, footprint_libs):
    s = kg.Schematic("gpu", "CUPC/8 graphics card (DVI on HDMI)", paper="A2")
    rc.core(s, GPIOS, "ACT")

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
    # asks. Two 4 x 0402 arrays, in the connector's order.
    arrays = {"RN1": ("D2P", "D2N", "D1P", "D1N"), "RN2": ("D0P", "D0N", "CKP", "CKN")}
    for i, (ref, lines) in enumerate(arrays.items()):
        rn = s.add("Device:R_Pack04", ref, "270", "Resistor_SMD:R_Array_Convex_4x0402",
                   at=((188 + 16 * i) * G, 70 * G), fields={"LCSC": "C728722"})
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


# Taller than the other cards (60 mm is the slot's limit): the receptacle,
# the ESD, the arrays and the crystal stack up between the chip and the top
# edge, in that order, so the TMDS lines run straight up.
BODY = (-6, -52, 56, -4.95)
EDGE = [(-0.65, -4.95), (-6, -4.95), (-6, -52), (56, -52), (56, -4.95), (19.65, -4.95)]
POWER_NETS = rc.POWER_NETS + ("/HDMI_5V",)
HX = 26                        # the receptacle's centre: pin n at HX - 4.5 + 0.5 (n - 1)
# the chip turned round, so its TMDS edge (GPIO10-17) faces the receptacle;
# the crystal moves from under it (turned: over it) to the gap the TMDS
# lines leave in the middle of that edge, by XIN/XOUT
PLACEMENT = dict(rc.core_placement(24, -20, turn=180), **{
    # the pocket between the D2 and D1 routes: XIN/XOUT, DVDD 23 and IOVDD 22
    # sit on this edge between the pairs, so their parts do too
    "R2": (24.25, -25.3, 90),
    "C12": (23.3, -25.3, 90),
    "C5": (23.3, -27.2, 90),
    "Y1": (24.0, -29.6, 0),
    "C16": (21.4, -29.6, 90),
    "C17": (26.6, -29.6, 90),
    "J1": (0, 0, 0),
    "U2": (1.5, -13.5, 0),
    "C1": (-4.5, -13.5, 90),
    "C2": (7.5, -13.5, 90),
    "U4": (17, -10, 0),
    "C18": (20.5, -10, 90),
    "R4": (-2.5, -46, 0),
    "D1": (-2.5, -48.5, 0),
    "R5": (1.5, -46, 0),
    "D2": (1.5, -48.5, 0),
    "J2": (HX, -52 + 6.90, 180),      # the drawing's board edge is 6.90 mm in front of the origin
    "U5": (HX - 3.25, -38.3, 90),     # pins 1-5 face the chip, 0.5 mm apart like the receptacle's
    "U6": (HX - 0.25, -38.3, 90),
    "RN1": (HX - 3.25, -33.5, 90),
    "RN2": (HX - 0.25, -33.5, 90),
    "F1": (35, -40.5, 90),
    "D3": (35, -36.5, 90),
    "C20": (32.5, -38.5, 90),
    "R20": (38, -44, 90),
    "R21": (38, -40.5, 90),
    "Q1": (41.5, -36, 0),
    "Q2": (46.5, -36, 0),
    "R22": (41.5, -32, 90),
    "R23": (41.5, -40, 90),
    "R24": (46.5, -32, 90),
    "R25": (46.5, -40, 90),
    "TP1": (-2, -24), "TP2": (1.5, -24), "TP3": (5, -24), "TP4": (-2, -29), "TP5": (1.5, -29), "TP6": (5, -29),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LAYERS = 2
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 48, -22, 0)]


if __name__ == "__main__":
    rc.build("gpu", schematic, PLACEMENT, BODY, EDGE, POWER_NETS, GRAPHICS, layers=LAYERS)
