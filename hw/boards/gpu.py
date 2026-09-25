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

    # ---- +5V to the sink (its EDID ROM and hot-plug detect; HDMI: 4.8-5.3 V,
    # >= 55 mA). The slot's +5V is 4.1 V at the card at the worst corner and
    # up to 5.4 V at vSafe5V max, so a TPS63802 buck-boost holds the pin at
    # 5.03 V either way (power.md, GPU card HDMI +5V; POW-008). The 200 mA
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
    # 825k / 91k 1 %: 0.5 V x (1 + 825/91) = 5.03 V
    r26 = rc.passive(s, "R", "R26", "825k", (172 * G, 126 * G), fp=rc.R0603, lcsc="C25823")
    r27 = rc.passive(s, "R", "R27", "91k", (172 * G, 142 * G), fp=rc.R0603, lcsc="C23265")
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
    "U4": (14, -12.5, 0),
    "C18": (10.5, -12.5, 90),
    "J2": (HX, -44 + 6.90, 180),      # the drawing's board edge is 6.90 mm in front of the origin
    "U5": (HX - 3.8, -31.0, 90),     # pins 1-5 face the chip, 0.5 mm apart like the receptacle's
    "U6": (HX, -31.0, 90),
    "RN1": (HX - 3.8, -27.0, 90),       # 1.4 mm below the ESD GND vias (preroute)
    "RN2": (HX, -27.0, 90),
    # the HDMI +5V buck-boost in the open area left of the receptacle; its
    # 5.03 V runs over to pin 18 (55 mA). TI's layout (SLVSEU9D, 12): U7
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
    GND pad fan-out's vias for U7 are taken off first: they would sit where
    this copper goes."""
    import pcbnew
    fp = board.FindFootprintByReference("U7")
    pads = {(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()}
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


def preroute(board):
    """GND the router can't give room to, between the TMDS lines:
    - the receptacle's shield and DDC-ground pins (2, 5, 8, 11, 17) sit
      between signal pins: each gets a via 2 mm behind its pad, under the
      receptacle's body, on a track along the pad
    - each ESD's GND pins (3 and 8) are in the middle of its rows, between
      two pairs: a track joins them through the package, and pin 3's
      fan-out via (or one of ours, 1.4 mm towards the chip) takes them down
    - the pins in the middle of the chip's top edge (rp2040card.pocket_escapes)
    - the HDMI +5V buck-boost (buck_boost)"""
    rc.pocket_escapes(board)
    buck_boost(board)
    import pcbnew

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


if __name__ == "__main__":
    rc.build("gpu", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR"}, GPIOS, TITLE, REVISION,
             layers=LAYERS, passes=90, preroute=preroute)
