#!/usr/bin/env python3
"""The graphics card (doc/hardware/gpu-protocol.md): an RP2040 running
PicoDVI, 640x480 DVI on an HDMI type-A receptacle at the card's top edge.

    python3 hw/boards/gpu.py [outdir]      (default build/hw/gpu)
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402
import fillfeature as ff  # noqa: E402
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
# TMDS series resistors (RN1/RN2): UNI-ROYAL 4D03WGJ0361T5E, 4 x 360 ohm +-5 %,
# the same 4D03 convex 0603 x 4 array as PicoDVI's 270 ohm C425067. Checked
# by test/hw/test_rp2040_thermal.py (IIOVSS_MAX and the DVI swing).
TMDS_R, TMDS_R_LCSC = "360", "C182716"


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

    # ---- TMDS: a series resistor on each GPIO, PicoDVI's DC-coupled
    # "DVI PHY" (Wren6991/PicoDVI hardware/mini_board, R12-R19, 270 ohm):
    # with the sink's 50 ohm termination to its 3V3, a low GPIO sinks the
    # line current. 360 ohm, not PicoDVI's 270: at 270 the four sinking lines
    # alone take 46.0 mA of the RP2040's 50 mA IIOVSS_MAX
    # (hw/power/rp2040_thermal.py R3); at 360 ohm 35.8 mA, and the swing at
    # the sink stays inside DVI 1.0's 150-1200 mV (TMDS_R below). Two
    # 4 x 0603 arrays (0402 arrays have pads 0.15 mm apart, under the 0.2 mm
    # clearance), in the connector's order.
    arrays = {"RN1": ("D2P", "D2N", "D1P", "D1N"), "RN2": ("D0P", "D0N", "CKP", "CKN")}
    for i, (ref, lines) in enumerate(arrays.items()):
        rn = s.add("Device:R_Pack04", ref, TMDS_R, "Resistor_SMD:R_Array_Convex_4x0603",
                   at=((188 + 16 * i) * G, 70 * G), fields={"LCSC": TMDS_R_LCSC})
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

    # ---- +5V to the sink (its EDID ROM and hot-plug detect; HDMI: 4.8-5.3 V,
    # >= 55 mA). The slot's +5V is 4.1 V at the card at the worst corner and
    # up to 5.4 V at vSafe5V max, so a TPS63802 buck-boost holds the pin at
    # 5.045 V either way (power.md, GPU card HDMI +5V; POW-008). The 200 mA
    # PTC is ahead of it, so its drop doesn't come off the pin, and it still
    # trips on a shorted cable (the converter's current limit pulls far more
    # through it). No Schottky: the TPS63802 disconnects its output from its
    # input when it is off, so a monitor can't back-feed the card.
    f1 = s.add("Device:Polyfuse", "F1", "200mA", "Fuse:Fuse_0805_2012Metric", at=(160 * G, 104 * G),
               fields={"LCSC": "C20976"})
    rc.two(s, f1, "+5V", "HDMI_5V_F")
    u7 = s.add("jlc:TPS63802DLAR", "U7", "TPS63802DLAR", "jlc:VSON-10_L3.0-W2.0-P0.50-TL",
               at=(152 * G, 132 * G), fields={"LCSC": "C2845237"})
    s.connect(u7, "VIN", "HDMI_5V_F")
    s.connect(u7, "EN", "HDMI_5V_F")          # on whenever the card has power
    s.connect(u7, "MODE", "GND")              # power save: it never sinks current from the pin
    s.connect(u7, "AGND", "GND")
    s.connect(u7, "GND", "GND")
    s.nc(u7, "PG")
    s.connect(u7, "L1", "BB_L1")
    s.connect(u7, "L2", "BB_L2")
    s.connect(u7, "VOUT", "HDMI_5V")
    s.connect(u7, "FB", "BB_FB")
    l1 = s.add("Device:L", "L1", "470n", "jlc:IND-SMD_L4.4-W4.2", at=(136 * G, 132 * G), fields={"LCSC": "C167200"})
    rc.two(s, l1, "BB_L1", "BB_L2")
    c21 = rc.passive(s, "C", "C21", "10u", (150 * G, 104 * G))
    rc.two(s, c21, "HDMI_5V_F", "GND")
    # 300k / 33k 1 % (basic parts): 0.5 V x (1 + 300/33) = 5.045 V; R2 <= 100k (datasheet)
    r26 = rc.passive(s, "R", "R26", "300k", (172 * G, 126 * G), fp=rc.R0603, lcsc="C23024")
    r27 = rc.passive(s, "R", "R27", "33k", (172 * G, 142 * G), fp=rc.R0603, lcsc="C4216")
    rc.two(s, r26, "HDMI_5V", "BB_FB")
    rc.two(s, r27, "BB_FB", "GND")
    c22 = rc.passive(s, "C", "C22", "22u", (180 * G, 142 * G))
    c23 = rc.passive(s, "C", "C23", "22u", (186 * G, 142 * G))
    rc.two(s, c22, "HDMI_5V", "GND")
    rc.two(s, c23, "HDMI_5V", "GND")
    c20 = rc.passive(s, "C", "C20", "100n", (172 * G, 108 * G))
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
CX, CY = 26, -16               # the RP2040, turned round: its TMDS edge (GPIO10-17) faces the receptacle
HX = CX + 1.5                  # the receptacle's centre: pin n at HX - 4.5 + 0.5 (n - 1), so D2 runs straight up
# Up from the chip: the arrays, the ESD, the receptacle at the top edge. The
# edge's middle pins (RUN, SWD, DVDD, IOVDD, XIN/XOUT) sit between the D2
# and D1 pairs: DVDD's and IOVDD's caps stay in that pocket at their pins,
# the rest leave it through vias, and the crystal sits off to the left.
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    "C4": (CX + 5.9, CY - 3.2, 0),       # IOVDD 10: GND pad to the right, so its fan-out via stays out of the CK pair's corridor
    "C12": (CX + 5.2, CY - 1.2, 0),      # DVDD 23 (its pin escapes by a via: pocket_escapes)
    "C10": (CX - 1.5, CY + 6.2, 0),      # USB_VDD 48
    "C8": (CX - 1.5, CY + 8.2, 0),       # IOVDD 49
    "C5": (CX + 8.5, CY + 2.4, 0),       # IOVDD 22: out of the pocket, so XIN/XOUT can leave it
    "Y1": (CX - 8.5, CY - 4.0, 0),
    "C16": (CX - 11.2, CY - 4.0, 90),
    "C17": (CX - 8.5, CY - 1.4, 0),
    "R2": (CX - 5.8, CY - 6.2, 90),      # XOUT
    "U3": (CX + 9.5, CY + 6.0, 0),     # flash, by the QSPI pins (now on the bottom edge)
    "C15": (CX + 15.2, CY + 2.8, 90),
    "R1": (CX + 15.0, CY + 6.0, 90),
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up: by its finger, clear of the SWD pins
    "U4": (14, -12.5, 270),
    "R60": (16.5, -13.6, 0),
    "R61": (18, -14.11, 90),
    "C18": (10.5, -12.5, 90),
    "J2": (HX, -44 + 6.90, 180),      # the drawing's board edge is 6.90 mm in front of the origin
    "U5": (HX - 3.25, -31.0, 90),     # pins 1-5 face the chip, 0.5 mm apart like the receptacle's
    "U6": (HX - 0.25, -31.0, 90),
    "RN1": (HX - 3.5, -27.0, 90),       # 1.4 mm below the ESD GND vias (preroute)
    "RN2": (HX + 0.3, -27.0, 90),
    # the HDMI +5V buck-boost in the open area left of the receptacle; its
    # 5.045 V runs over to pin 18 (55 mA). TI's layout (SLVSEU9D, 12): U7
    # turned so its power pins (VIN, L1, GND, L2, VOUT) face up in a row, the
    # inductor across them above, the input cap left and the output caps
    # right, each at its pin; the FB divider below, by FB, away from L1/L2
    "U7": (9.0, -35.0, 90),
    "L1": (9.0, -38.8, 180),          # pad 1 (L1) over pin 9, pad 2 (L2) over pin 7
    "C21": (6.35, -34.95, 270),       # VIN: pad 1 level with pin 10
    "F1": (4.1, -34.95, 90),          # ahead of it
    "C22": (11.65, -34.95, 270),      # VOUT: pad 1 level with pin 6
    "C23": (13.7, -34.95, 270),
    "R27": (8.0, -30.85, 180),        # FB (pad 1) to GND
    "R26": (11.2, -30.85, 180),       # VOUT (pad 1) to FB; U7's designator between them and U7
    "C20": (33.4, -28.4, 90),         # HDMI_5V at the receptacle's pin 18
    "R20": (37.2, -31.4, 0),          # HPD divider
    "R21": (37.2, -29.8, 0),
    "Q1": (44, -29.0, 0),
    "Q2": (44, -24.5, 0),
    "R22": (40.6, -26.9, 90),
    "R23": (47.5, -29.0, 90),
    "R24": (40.6, -23.1, 90),
    "R25": (47.5, -24.5, 90),
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LAYERS = 4
LOGO_MM = 12
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 48.5, -16.5, 0)]
TITLE, REVISION = "CUPC/8 GPU", "A"


def buck_boost(board):
    """The TPS63802's copper, per TI's layout (SLVSEU9D, 12): its pads are
    0.3 mm at 0.5 mm pitch, too tight for the router to lay the loops short.
    The power row (VIN, L1, GND, L2, VOUT) faces up: VIN and VOUT straight
    out to their caps, L1 and L2 up to the inductor. EN goes up under the
    package to VIN; MODE (GND) joins AGND, which joins GND pin 8 through
    the package's middle, and takes them down by a via that also ties in the
    input cap's ground. FB runs down to its divider, away from L1/L2. The
    GND pad fan-out's vias for the block's parts are taken off first: they
    would sit where this copper goes (the caps' and R27's GND pads are on
    the top pour, which the block's own via ties down)."""
    import pcbnew
    pads = {(p.GetPosition().x, p.GetPosition().y) for ref in ("U7", "C21", "C22", "C23", "R27")
            for p in board.FindFootprintByReference(ref).Pads()}
    tr = board.Tracks()                       # indexed: iterating it breaks on Python 3.14
    items = [tr[i].Cast() for i in range(len(tr))]
    ends = {(t.GetEnd().x, t.GetEnd().y) for t in items
            if t.Type() == pcbnew.PCB_TRACE_T and (t.GetStart().x, t.GetStart().y) in pads}
    for t in items:
        if (t.Type() == pcbnew.PCB_TRACE_T and (t.GetStart().x, t.GetStart().y) in pads) or \
           (t.Type() == pcbnew.PCB_VIA_T and (t.GetPosition().x, t.GetPosition().y) in ends):
            board.Remove(t)

    at = lambda ref, n: rc.pad_at(board, ref, n)          # noqa: E731
    en, mode, agnd, fb = at("U7", 1), at("U7", 2), at("U7", 3), at("U7", 4)
    vout, l2, gnd, l1, vin = at("U7", 6), at("U7", 7), at("U7", 8), at("U7", 9), at("U7", 10)
    cin, cout = at("C21", 1), at("C22", 1)
    rc.track(board, "/HDMI_5V_F", at("F1", 2), cin, width=0.4)
    rc.track(board, "/HDMI_5V_F", vin, (cin[0], vin[1]), width=0.3)
    rc.track(board, "/HDMI_5V_F", en, vin, width=0.2)
    rc.track(board, "/HDMI_5V", vout, (cout[0], vout[1]), width=0.3)
    rc.track(board, "/HDMI_5V", cout, at("C23", 1), width=0.4)
    # L1 and L2: straight up off the pin, then out at 45 degrees into the
    # inductor's pad, at its inner bottom corner
    for pin, pad, net in ((l1, at("L1", 1), "/BB_L1"), (l2, at("L1", 2), "/BB_L2")):
        side = math.copysign(1, pad[0] - pin[0])
        corner = (pad[0] - side * 0.33, pad[1] + 1.0)
        rise = (pin[0], corner[1] + abs(corner[0] - pin[0]))
        rc.track(board, net, pin, rise, width=0.25)
        rc.track(board, net, rise, corner, width=0.4)
    # GND: pin 8 through the middle to AGND, MODE beside it, down and out
    # to a via below EN, and on to the input cap's GND pad (the designator
    # sits under the package, clear of this copper)
    down = (mode[0], mode[1] + 0.57)
    gvia = (mode[0] - 1.05, mode[1] + 1.17)
    rc.track(board, "/GND", gnd, agnd, width=0.2)
    rc.track(board, "/GND", mode, agnd, width=0.25)
    rc.track(board, "/GND", mode, down, width=0.25)
    rc.track(board, "/GND", down, gvia, width=0.25)
    rc.via(board, "/GND", gvia)
    rc.track(board, "/GND", gvia, at("C21", 2), width=0.3)
    # FB: under PG and down to R26's FB pad, then across to R27's; the
    # divider's VOUT end (R26 pad 1) the router takes to the output caps
    r27, r26 = at("R27", 1), at("R26", 2)
    turn = fb[1] + 0.62
    rc.track(board, "/BB_FB", fb, (fb[0], turn), width=0.2)
    rc.track(board, "/BB_FB", (fb[0], turn), (r26[0], turn), width=0.2)
    rc.track(board, "/BB_FB", (r26[0], turn), r26, width=0.2)
    rc.track(board, "/BB_FB", r26, r27, width=0.2)


# TMDS pairs laid by hand (GC-007, hw/si/tmds_si.py). Freerouting cannot hold a
# pair's gap, and its 0.15 mm tracks laid apart are 115-140 ohm; on F.Cu over the
# In1 GND plane (JLC04161H-7628, prepreg 0.2104 mm) the xsection.py lower bounds
# are 99.5-101 ohm for 0.2 mm tracks 0.21 mm apart (the RP2040 side, where the pads
# are 0.4 mm apart) and 95-98 ohm for 0.25 mm tracks 0.25 mm apart (the resistor
# arrays to the receptacle, where the ESD pads are 0.5 mm apart). The arrays and
# ESD parts are shifted in x (PLACEMENT) so that each pair meets the receptacle
# with its centre line on the receptacle's pair centre: the two lines then part
# 0.25 mm each, symmetrically, at the receptacle's pads.
CHIP_W, CHIP_HALF = 0.2, 0.2            # 0.2 mm gap: the RP2040's pads are 0.4 mm apart
HD_W, HD_HALF = 0.25, 0.25              # 0.25 mm gap
# chip side: pair centre lines, RP2040 pads to the resistor arrays' chip-side pads
# (the arrays' pads are 0.5 mm wide, the pair's tracks land inside them)
CHIP_SIDE = {
    "D2": [(23.6, -19.5), (23.6, -21.6), (23.2, -22.0), (23.2, -25.85)],
    "D1": [(27.6, -19.5), (27.6, -20.1), (27.8, -21.1), (27.8, -21.9), (24.8, -24.9), (24.8, -25.85)],
    "D0": [(28.4, -19.5), (28.4, -19.95), (28.7, -21.25), (28.7, -23.0), (27.0, -24.7), (27.0, -25.85)],
    "CK": [(29.5, -18.4), (29.95, -18.4), (30.3, -18.75), (30.3, -23.2), (28.6, -24.9), (28.6, -25.85)],
}
# connector side: from the arrays' connector-side pads up between the ESD GND vias
# (bulging around them: the via is 0.6 mm and the ESD pads 0.5 mm apart), through
# the ESD pads, to y = PARTING where the two lines part to the receptacle's pads.
# The vertices at y = -30.615 and -31.385 are the ESD pads' centres (Freerouting
# joins a pad only at a track end).
PARTING = -32.05
HD_SIDE = {
    "D2": [(23.2, -28.1), (23.2, -28.6), (23.35, -28.9), (23.35, -29.9), (23.5, -30.35), (23.5, -30.615),
           (23.5, -31.385), (23.5, PARTING)],
    "D1": [(24.8, -28.1), (24.8, -28.8), (25.15, -29.15), (25.15, -29.9), (25.0, -30.35), (25.0, -30.615),
           (25.0, -31.385), (25.0, PARTING)],
    "D0": [(27.0, -28.1), (27.0, -28.8), (26.375, -29.425), (26.375, -29.9), (26.5, -30.3), (26.5, -30.615),
           (26.5, -31.385), (26.5, PARTING)],
    "CK": [(28.6, -28.1), (28.6, -28.8), (28.125, -29.275), (28.125, -29.9), (28.0, -30.3), (28.0, -30.615),
           (28.0, -31.385), (28.0, PARTING)],
}
# pad numbers: RP2040 (P, N); resistor array and its chip-side and connector-side pads (P, N)
U1_PADS = {"D2": (28, 27), "D1": (18, 17), "D0": (16, 15), "CK": (14, 13)}
RN_PADS = {"D2": ("RN1", (1, 2), (8, 7)), "D1": ("RN1", (3, 4), (6, 5)),
           "D0": ("RN2", (1, 2), (8, 7)), "CK": ("RN2", (3, 4), (6, 5))}
# receptacle pad x (P, N) of each pair; the lines part at 45 degrees, then run up
# into the pad (its bottom edge is at y = -32.44)
J2_PADS = {"D2": (23.0, 24.0), "D1": (24.5, 25.5), "D0": (26.0, 27.0), "CK": (27.5, 28.5)}
PAIRS = {"D2": ("D2P", "D2N"), "D1": ("D1P", "D1N"), "D0": ("D0P", "D0N"), "CK": ("CKP", "CKN")}


def _offset(points, d):
    """The polyline `points` moved `d` mm to the left of its heading (y is down
    on the board, so left of 'up' is -x), mitred at the corners."""
    dirs = []
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        dirs.append(((b[0] - a[0]) / length, (b[1] - a[1]) / length))
    normals = [(dy, -dx) for dx, dy in dirs]
    out = [(points[0][0] + normals[0][0] * d, points[0][1] + normals[0][1] * d)]
    for (nx1, ny1), (nx2, ny2) in zip(normals, normals[1:]):
        bx, by = nx1 + nx2, ny1 + ny2
        scale = d * 2 / (bx * bx + by * by)      # d / cos(half turn) on the unit bisector
        out.append((points[len(out)][0] + bx * scale, points[len(out)][1] + by * scale))
    out.append((points[-1][0] + normals[-1][0] * d, points[-1][1] + normals[-1][1] * d))
    return out


def _lay(board, net, points, width):
    for a, b in zip(points, points[1:]):
        rc.track(board, net, a, b, width=width)


def tmds_route(board):
    """The four TMDS pairs, RP2040 pin to receptacle pad, laid coupled on F.Cu
    (CHIP_SIDE, HD_SIDE, J2_PADS). A rigid pair keeps P and N the same length
    (a bend costs the outer line d x angle, and the bends of a pair cancel; the
    one net bend, CK's, is 0.63 mm)."""
    at = lambda ref, pad: rc.pad_at(board, ref, pad)           # noqa: E731
    for lane, (p, n) in PAIRS.items():
        rn, chip_pads, hd_pads = RN_PADS[lane]
        for k, (net, sign) in enumerate((("/TMDS_" + p, 1), ("/TMDS_" + n, -1))):
            line = [at("U1", U1_PADS[lane][k])] + _offset(CHIP_SIDE[lane], sign * CHIP_HALF) + [at(rn, chip_pads[k])]
            _lay(board, net, line, CHIP_W)
        left, right = _offset(HD_SIDE[lane], HD_HALF), _offset(HD_SIDE[lane], -HD_HALF)
        for k, (net, line, pad) in enumerate((("/HD_" + p, left, J2_PADS[lane][0]), ("/HD_" + n, right, J2_PADS[lane][1]))):
            # Open the corridor around U6's unchanged 0.6 mm GND via.
            # The two inner launch corners need 50 um more clearance.
            if (lane, k) in (("D0", 1), ("CK", 0)):
                expected = (26.625, -29.861847) if lane == "D0" else (27.875, -29.861847)
                if math.dist(line[3], expected) > 1e-5:
                    raise ValueError("TMDS ESD launch corner geometry changed")
                line[3] = (line[3][0] + (-0.05 if lane == "D0" else 0.05), line[3][1])
            x, y = line[-1]
            path = [at(rn, hd_pads[k])] + line + [(pad, y - abs(pad - x)), (pad, -32.65)]
            for i, (a, b) in enumerate(zip(path, path[1:])):
                # Adjacent array-pad copper adds capacitance at the first
                # departure diagonal. Narrow its first 0.25 mm on both
                # polarities; keep the remainder at the normal pair width.
                if lane != "D2" and i == 2:
                    length = math.dist(a, b)
                    if length < 0.25 or abs(abs(a[0] - b[0]) - abs(a[1] - b[1])) > 1e-5:
                        raise ValueError("TMDS array departure geometry changed")
                    fraction = 0.25 / length
                    split = (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))
                    rc.track(board, net, a, split, width=0.175)
                    rc.track(board, net, split, b, width=HD_W)
                else:
                    rc.track(board, net, a, b, width=HD_W)


def esd_silk(board):
    """U5 and U6 sit 3.0 mm apart (their pair centres line up with the
    receptacle's): U5's right end line and U6's pin 1 mark would touch each other
    and U5's last pad. Drop the end line, shrink the mark to a dot."""
    import pcbnew
    for ref, right in (("U5", True), ("U6", False)):
        fp = board.FindFootprintByReference(ref)
        for item in [fp.GraphicalItems()[i] for i in range(fp.GraphicalItems().size())]:
            g = pcbnew.Cast_to_PCB_SHAPE(item)
            if not g or g.GetLayer() != pcbnew.F_SilkS:
                continue
            x0 = pcbnew.ToMM(g.GetBoundingBox().GetX())
            if right and g.GetShape() == pcbnew.SHAPE_T_SEGMENT and x0 > pcbnew.ToMM(fp.GetPosition().x) + 1.2:
                fp.Remove(item)
            elif not right and g.GetShape() == pcbnew.SHAPE_T_POLY:      # a dot instead of the triangle
                g.GetPolyShape().Inflate(pcbnew.FromMM(-0.07), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,
                                         pcbnew.FromMM(0.005))


def tmds_ground_escape(board):
    """Move U6.3's existing fan-out via 0.21 mm towards the ESD package.

    Keep its diameter/drill and ground connection; the array departure
    bends need this space. Fail if the expected fan-out changes.
    """
    import pcbnew
    x, y = rc.pad_at(board, "U6", 3)
    old, new = (x, y + 1.0), (x, y + 0.79)
    moved_vias = moved_ends = 0
    tracks = board.Tracks()
    for i in range(len(tracks)):
        track = tracks[i]
        if track.GetNetname() != "/GND":
            continue
        if track.Type() == pcbnew.PCB_VIA_T:
            pos = track.GetPosition()
            if math.dist((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)), old) < 1e-5:
                track.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(new[0]), pcbnew.FromMM(new[1])))
                moved_vias += 1
        else:
            for getter, setter in ((track.GetStart, track.SetStart), (track.GetEnd, track.SetEnd)):
                pos = getter()
                if math.dist((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)), old) < 1e-5:
                    setter(pcbnew.VECTOR2I(pcbnew.FromMM(new[0]), pcbnew.FromMM(new[1])))
                    moved_ends += 1
    if (moved_vias, moved_ends) != (1, 1):
        raise ValueError("U6.3 ground fan-out geometry changed")


def preroute(board):
    import route_seed
    route_seed.normalize_placement(board, "C13", (20800000, -6199999), (20800000, -6200000))
    route_seed.normalize_placement(board, "F1", (4099999, -34950000), (4100000, -34950000))
    """GND the router can't give room to, between the TMDS lines:
    - the receptacle's shield and DDC-ground pins (2, 5, 8, 11, 17) sit
      between signal pins: each gets a via 2 mm behind its pad, under the
      receptacle's body, on a track along the pad
    - each ESD's GND pins (3 and 8) are in the middle of its rows, between
      two pairs: a track joins them through the package, and pin 3's
      fan-out via (or one of ours, 1.4 mm towards the chip) takes them down
    - the pins in the middle of the chip's top edge (rp2040card.pocket_escapes)
    - the HDMI +5V buck-boost (buck_boost)"""
    # The clipped L1 outline includes the 0.01 mm mask expansion beyond
    # the 0.15 mm silk clearance from pad copper.
    # Shorten its four upright ends to give the plotted Gerber real margin.
    import pcbnew
    fp = next(f for f in board.GetFootprints() if f.GetReference() == "L1")
    changed = 0
    for i in range(fp.GraphicalItems().size()):
        g = pcbnew.Cast_to_PCB_SHAPE(fp.GraphicalItems()[i])
        if not g or g.GetLayer() != pcbnew.F_SilkS or g.GetShape() != pcbnew.SHAPE_T_SEGMENT:
            continue
        a, b = g.GetStart(), g.GetEnd()
        ax, ay, bx, by = map(pcbnew.ToMM, (a.x, a.y, b.x, b.y))
        if abs(ax - bx) > .001 or not any(abs(ax - x) < .001 for x in (6.72, 11.28)):
            continue
        def shortened(y):
            for old, new in ((-36.645, -36.68), (-37.495, -37.47), (-40.105, -40.13)):
                if abs(y - old) < .001:
                    return new
            return y
        new_ay, new_by = shortened(ay), shortened(by)
        if new_ay == ay and new_by == by:
            continue
        g.SetStart(pcbnew.VECTOR2I(a.x, pcbnew.FromMM(new_ay)))
        g.SetEnd(pcbnew.VECTOR2I(b.x, pcbnew.FromMM(new_by)))
        changed += 1
    if changed != 4:
        raise ValueError("L1 clipped silk outline changed")
    rc.pocket_escapes(board)
    buck_boost(board)
    tmds_ground_escape(board)
    tmds_route(board)
    esd_silk(board)
    import pcbnew

    # B13 (SCK) is between two top-side GND fingers, while A13 is GND on
    # the reverse. A via in the tab would cut into A13's ground tie. Carry
    # SCK straight up between the GND ties and change layers beyond their
    # ends, where the reverse-side copper has stopped.
    sck = rc.pad_at(board, "J1", "B13")
    escape = (sck[0], -10.3)
    rc.track(board, "/SCK", sck, escape)
    rc.via(board, "/SCK", escape)

    def gnd_via_near(x, y, dx, dy):
        tracks = board.Tracks()
        return any(tracks[i].Type() == pcbnew.PCB_VIA_T and tracks[i].GetNetname() == "/GND" and
                   abs(pcbnew.ToMM(tracks[i].GetPosition().x) - x) < dx and
                   abs(pcbnew.ToMM(tracks[i].GetPosition().y) - y) < dy for i in range(len(tracks)))
    for pin in (2, 5, 8, 11, 17):
        x, y = rc.pad_at(board, "J2", pin)
        if not gnd_via_near(x, y - 2.0, 0.3, 0.3):       # unless the fan-out put one there
            rc.via(board, "/GND", (x, y - 2.0))
            rc.track(board, "/GND", (x, y), (x, y - 2.0), width=0.25)
    for ref in ("U5", "U6"):
        (x8, y8), (x3, y3) = rc.pad_at(board, ref, 8), rc.pad_at(board, ref, 3)
        rc.track(board, "/GND", (x8, y8), (x3, y3), width=0.2)
        # a via 1.4 mm towards the chip, unless the fan-out gave pin 3 one
        if not gnd_via_near(x3, y3, 1.0, 2.0):
            rc.via(board, "/GND", (x3, y3 + 1.4))
            rc.track(board, "/GND", (x3, y3), (x3, y3 + 1.4), width=0.2)


    # Exact nanometre placement from the isolated DRC-qualified filter candidate.
    for ref, (x, y) in {'R62': (31187500, -20850000), 'R63': (34437500, -19500000), 'R64': (32437500, -21800000), 'C60': (31187500, -22850000), 'C61': (34437500, -17500000), 'C62': (31957500, -24320000), 'C63': (11850000, -10650000)}.items():
        board.FindFootprintByReference(ref).SetPosition(pcbnew.VECTOR2I(x, y))
    # 45 degree relief avoids the actual starved C60 ground spoke.
    board.FindFootprintByReference("C60").FindPadByNumber("2").SetThermalSpokeAngle(pcbnew.EDA_ANGLE(45.0, pcbnew.DEGREES_T))
    board.FindFootprintByReference("R65").SetPosition(pcbnew.VECTOR2I(12100000, -13150000))
    _pin_spi_designators(board)


def _pin_spi_designators(board):
    import pcbnew
    for ref, (x, y, angle, size, stroke) in {'R61': (16800000, -15710000, 90.0, 800000, 150000), 'R64': (35437500, -24199999, 0.0, 800000, 150000), 'R22': (38600000, -25025000, 0.0, 1000000, 150000), 'R27': (8000000, -29174999, 0.0, 1000000, 150000), 'C14': (17045000, -8000000, 0.0, 1000000, 150000), 'Q2': (44000000, -21854999, 0.0, 1000000, 150000), 'C15': (40700000, -15955000, 0.0, 1000000, 150000), 'R60': (19700000, -16000000, 0.0, 800000, 150000), 'R3': (8500000, -10625000, 0.0, 1000000, 150000), 'R20': (37200000, -32814999, 0.0, 1000000, 150000), 'Y1': (14500000, -22695000, 0.0, 1000000, 150000), 'C17': (14745000, -17400000, 0.0, 1000000, 150000), 'R1': (43315000, -10000000, 0.0, 1000000, 150000), 'R26': (11200000, -29174999, 0.0, 1000000, 150000), 'R62': (28872500, -20850000, 0.0, 800000, 150000), 'TP3': (-1055001, -21999999, 0.0, 1000000, 150000), 'U6': (30595000, -30000000, 0.0, 1000000, 150000), 'U4': (11000000, -15100000, 0.0, 800000, 150000), 'C21': (5350000, -32305000, 0.0, 1000000, 150000), 'TP5': (-1055001, -28999999, 0.0, 1000000, 150000), 'F1': (2099999, -32325000, 0.0, 1000000, 150000), 'H1': (52001264, -35602474, 0.0, 1000000, 150000), 'U7': (9000000, -32670000, 0.0, 800000, 150000), 'C20': (33400000, -26545000, 0.0, 1000000, 150000), 'C18': (8194999, -15500000, 0.0, 1000000, 150000), 'C4': (33699999, -21600000, 90.0, 800000, 150000), 'R63': (36752500, -22500000, 0.0, 1000000, 150000), 'C12': (36200000, -19600000, 0.0, 800000, 150000), 'C9': (18199999, -12000000, 90.0, 1000000, 150000), 'C63': (10050000, -8250000, 0.0, 1000000, 150000), 'C8': (24500000, -6395000, 0.0, 1000000, 150000), 'C3': (35000000, -14799999, 0.0, 800000, 150000), 'R24': (40600000, -21224999, 0.0, 1000000, 150000), 'C62': (30557500, -26920000, 90.0, 1000000, 150000), 'TP2': (-4001240, -16453762, 0.0, 1000000, 150000), 'R21': (37200000, -28384999, 0.0, 1000000, 150000), 'C2': (175000, -11500000, 0.0, 1000000, 150000), 'C23': (13700000, -37595000, 0.0, 1000000, 150000), 'J2': (17404999, -38705000, 0.0, 1000000, 150000), 'C60': (27382500, -22850000, 0.0, 1000000, 150000), 'J1': (11500000, -6395000, 0.0, 1000000, 150000), 'TP6': (-1055001, -32499999, 0.0, 1000000, 150000), 'RN1': (24000000, -24505000, 0.0, 1000000, 150000), 'C6': (20400000, -19400000, 90.0, 800000, 150000), 'C10': (27900000, -7800000, 0.0, 1000000, 150000), 'C7': (20799999, -14805000, 0.0, 1000000, 150000), 'R23': (47500000, -30875000, 0.0, 1000000, 150000), 'TP1': (-1055001, -35999999, 0.0, 1000000, 150000), 'L1': (9000000, -41845000, 0.0, 1000000, 150000), 'TP4': (-1055001, -25499999, 0.0, 1000000, 150000), 'C13': (22599999, -7600000, 90.0, 1000000, 150000), 'U3': (35500000, -6155000, 0.0, 1000000, 150000), 'R2': (19200000, -24075000, 0.0, 1000000, 150000), 'C16': (12495000, -20000000, 0.0, 1000000, 150000), 'C5': (37500000, -15005000, 0.0, 1000000, 150000), 'R4': (324999, -38500000, 0.0, 1000000, 150000), 'C61': (37037500, -16700000, 0.0, 1000000, 150000), 'C22': (11650000, -32305000, 0.0, 1000000, 150000), 'C11': (22400000, -10600000, 90.0, 800000, 150000), 'U5': (20904999, -31000000, 0.0, 1000000, 150000), 'RN2': (27800000, -24505000, 0.0, 1000000, 150000), 'R25': (47500000, -26375000, 0.0, 1000000, 150000), 'U1': (29000000, -10924999, 0.0, 1000000, 150000), 'Q1': (44000000, -31645000, 0.0, 1000000, 150000), 'R65': (14900000, -15550000, 90.0, 800000, 150000)}.items():
        word = board.FindFootprintByReference(ref).Reference()
        word.SetPosition(pcbnew.VECTOR2I(x, y))
        word.SetTextAngleDegrees(angle)
        word.SetTextSize(pcbnew.VECTOR2I(size, size))
        word.SetTextThickness(stroke)
        word.SetVisible(True)

# Exact local filters; original component positions retained.
PLACEMENT.update({'R62': (31.1875, -20.85, 90.0), 'R63': (34.4375, -19.5, -90.0), 'R64': (32.4375, -21.8, 90.0), 'C60': (31.1875, -22.85, 90.0), 'C61': (34.4375, -17.5, -90.0), 'C62': (31.9575, -24.32, 180.0), 'C63': (11.85, -10.65, -90.0)})

# Exact qualified additional local OE resistor placement.
PLACEMENT.update({"R65": (12.1, -13.15, -90.0)})


def _seeded_route(board, workdir):
    import route_seed
    result = route_seed.apply(
        board, os.path.join(HERE, "gpu-full-route-seed.json"),
        board_name="gpu", pour_nets=("/GND",),
        post_route_contract="gpu-ahc-tmds-preroute-v1")
    _pin_spi_designators(board)
    print("GPU full-route seed: %d copper items; origin %s; fresh full pipeline required" %
          (result['added'], result['origin_state']), end=" ", flush=True)
    return 0


if __name__ == "__main__":
    rc.build("gpu", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR"}, GPIOS, TITLE, REVISION,
             layers=LAYERS, passes=90, designator_reach=4, preroute=preroute, seeded_route=_seeded_route,
             post_fill=(lambda board: ff.round_board_fills(board, "gpu")))
