#!/usr/bin/env python3
"""The e-ink card (doc/proposals/eink-gpu.md, Decisions; card type $01, a
replacement for the HDMI graphics card): an RP2040 driving an e-paper panel
on its driver module (Good Display DESPI-C02 or a Waveshare e-Paper HAT),
which plugs into a 2.54 mm 9-pin header on the card's top edge by cable.

    python3 hw/boards/eink.py [outdir]      (default build/hw/eink)
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

# eink_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's)
GPIOS = {9: "EPD_nCS", 10: "EPD_CLK", 11: "EPD_DIN", 12: "EPD_DC", 13: "EPD_nRST", 14: "EPD_BUSY",
         15: "EPD_PWR", 16: "UART_TX", 24: "LED_REFRESH"}

# the header, in the module cable's order (Waveshare's 9-pin; pins.yaml):
# pin: (silkscreen name, net at the RP2040 or None for power)
HEADER = {1: ("VCC", None), 2: ("GND", None), 3: ("DIN", "EPD_DIN"), 4: ("CLK", "EPD_CLK"),
          5: ("CS", "EPD_nCS"), 6: ("DC", "EPD_DC"), 7: ("RST", "EPD_nRST"), 8: ("BUSY", "EPD_BUSY"),
          9: ("PWR", "EPD_PWR")}
SIGNALS = [net for _, net in HEADER.values() if net]       # header order, DIN .. PWR


def schematic(path, footprint_libs):
    s = kg.Schematic("eink", "CUPC/8 e-ink card (e-paper module)", paper="A2")
    # REFRESH (GPIO24) in the top-edge row: lit while the panel refreshes, the
    # one sign of life while the panel still shows an old picture
    rc.core(s, GPIOS, leds=[("LED_REFRESH", "green")])

    # ---- the header: the module's cable. It is handled from outside the
    # case, so every line has a TVS channel at the header, and each signal a
    # 33 ohm series resistor at the RP2040 side (edge rate on the 20 cm cable,
    # and current into the pin when the TVS clamps)
    j2 = s.add("jlc:PZ254R-11-09P", "J2", "EPD", "jlc:HDR-TH_9P-P2.54-H-M-W10.4", at=(224 * G, 50 * G),
               fields={"LCSC": "C492417"})
    s.connect(j2, 1, "EPD_VCC")
    s.connect(j2, 2, "GND")
    for i, net in enumerate(SIGNALS):
        s.connect(j2, 3 + i, net + "_J")
        r = rc.passive(s, "R", "R%d" % (10 + i), "33R", ((186 + 5 * i) * G, 70 * G))
        rc.two(s, r, net, net + "_J")

    # ---- the module's 3.3 V: through a 100 mA PTC, so a shorted cable or
    # module can't pull down the slot's +3V3 (shared by every card, with no
    # fuse of its own), and the module's own capacitors charge through it
    # rather than straight off the card's rail. The module draws <= 40 mA
    # while refreshing (eink-gpu.md, Power).
    f1 = s.add("Device:Polyfuse", "F1", "100mA", "Fuse:Fuse_0805_2012Metric", at=(186 * G, 24 * G),
               fields={"LCSC": "C20975"})
    rc.two(s, f1, "3V3", "EPD_VCC")
    c20 = rc.passive(s, "C", "C20", "10u", (198 * G, 20 * G))
    c21 = rc.passive(s, "C", "C21", "100n", (206 * G, 20 * G))
    rc.two(s, c20, "EPD_VCC", "GND")
    rc.two(s, c21, "EPD_VCC", "GND")

    # ---- ESD: two TPD4E05U06 (as the storage card), the seven signals and VCC
    for i, (ref, lines) in enumerate((("U5", ("EPD_VCC", "EPD_DIN_J", "EPD_CLK_J", "EPD_nCS_J")),
                                      ("U6", ("EPD_DC_J", "EPD_nRST_J", "EPD_BUSY_J", "EPD_PWR_J")))):
        u = s.add("Power_Protection:TPD4E05U06DQA", ref, "TPD4E05U06DQAR", "Package_SON:USON-10_2.5x1.0mm_P0.5mm",
                  at=((186 + 30 * i) * G, 100 * G), fields={"LCSC": "C138714"})
        for pin, net in zip(("1", "2", "4", "5"), lines):
            s.connect(u, pin, net)
        s.connect(u, "3", "GND")
        s.connect(u, "8", "GND")
        for pin in ("6", "7", "9", "10"):
            s.nc(u, pin)

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


# ---- the board: the storage card's core (the RP2040 turned round, so the
# panel pins GPIO9-15 are at its top-right corner, facing the header)
POWER_NETS = rc.POWER_NETS           # EPD_VCC stays a default track: it reaches a TVS pad 0.25 mm wide
CX, CY = 26, -19
HX, HY = 36.5, -39.6             # the header: its 2.5 mm insulator flush with the top edge, the pins out over it
PIN_X = {n: HX + 10.16 - 2.54 * (n - 1) for n in HEADER}    # turned 180: pin 1 at the right
TVS_Y, R_Y = -32.6, -26.6
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    # the core as on the storage card
    "C12": (CX - 0.7, CY - 5.3, 90),     # DVDD 23
    "C10": (CX - 1.5, CY + 6.2, 0),      # USB_VDD 48
    "C8": (CX - 3.2, CY + 7.2, 90),      # IOVDD 49
    "C5": (CX + 5.6, CY + 4.4, 0),       # IOVDD 22: out of the pocket, so XIN/XOUT can leave it (as storage)
    # the crystal turned round from the storage card's: XIN, the outermost of
    # the pins that leave the chip's top edge to the left, reaches its pad at
    # the crystal's top right, and XOUT (through R2) the bottom left, so the
    # two don't cross (with the panel lines also leaving that edge, XIN
    # would not route the storage card's way)
    "Y1": (CX - 10.0, CY - 4.5, 180),
    "C16": (CX - 8.9, CY - 7.3, 180),
    "C17": (CX - 11.0, CY - 1.0, 0),
    "R2": (CX - 8.2, CY - 1.0, 180),     # XOUT, under the crystal
    "U3": (CX + 7, CY + 9.5, 0),
    "C15": (CX + 7, CY + 5.6, 0),
    "R1": (CX + 12.5, CY + 9.5, 90),
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up, by its finger
    "U4": (14, -12.5, 0),
    "C18": (10.5, -12.5, 90),
    # REFRESH in the top-edge row with the power LED, its resistor under it
    "D2": (17, -41, 0), "R5": (17, -38.5, 0),
    "J2": (HX, HY, 180),
    # under the header: the pin names, then the TVS arrays, then a series
    # resistor under each signal pin
    "U5": (PIN_X[1] - 5.1, TVS_Y, 0),              # VCC, DIN, CLK, CS
    "U6": (PIN_X[9] + 3.8, TVS_Y, 0),              # DC, RST, BUSY, PWR
    "F1": (PIN_X[1] + 0.8, -30.5, 90),
    "C20": (PIN_X[1] + 3.8, -30.5, 90),
    "C21": (PIN_X[1] + 1.8, -35.2, 90),
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
# the series resistors in a row up and right of the chip's panel corner, in
# the order its pins come out (GPIO15..12 along the top, then 11..9 down the
# right side), so the fan-out doesn't cross and keeps clear of XIN/XOUT in
# the middle of the top edge; staggered, so each designator has room
CHIP_ORDER = ["EPD_PWR", "EPD_BUSY", "EPD_nRST", "EPD_DC", "EPD_DIN", "EPD_CLK", "EPD_nCS"]
PLACEMENT.update({"R%d" % (10 + SIGNALS.index(net)): (31.0 + 2.1 * k, R_Y - 2.4 * (k % 2), 90)
                  for k, net in enumerate(CHIP_ORDER)})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
LAYERS = 4
LOGO_MM = 12
LEGEND = "EInk_Header_Legend"
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 46, -16, 0), ("cupc8:" + LEGEND, HX, HY, 0)]
TITLE, REVISION = "CUPC/8 e-ink", "A"


XIN_Y = -26.2                  # XIN's run to the crystal, above C12 and the chip's fan-out
XOUT_Y, XOUT_X = -25.5, 19.3   # XOUT's, under XIN's and down the crystal's right to R2


def preroute(board):
    """XIN and XOUT, laid by hand: Freerouting left one or the other
    unrouted on every try, with the pins beside them and the panel lines all
    leaving the chip's top edge. Each goes from its pad straight up, left
    above everything else that fans out of that edge (those drop to the inner
    layers under them), XIN to C16 and down to the crystal's XIN pad (its
    top right), XOUT inside it and down the crystal's right side to R2. And
    TESTEN, as on every RP2040 card."""
    rc.tie_testen(board)
    x0, y0 = rc.pad_at(board, "U1", 20)                 # XIN
    xc, yc = rc.pad_at(board, "C16", 1)
    xy, yy = rc.pad_at(board, "Y1", 1)
    for net_pad in (("C16", 1), ("Y1", 1)):
        assert board.FindFootprintByReference(net_pad[0]).FindPadByNumber(str(net_pad[1])).GetNetname() == "/XIN"
    rc.track(board, "/XIN", (x0, y0), (x0, XIN_Y), width=0.15)
    rc.track(board, "/XIN", (x0, XIN_Y), (xc, XIN_Y), width=0.15)
    rc.track(board, "/XIN", (xc, XIN_Y), (xc, yc), width=0.15)
    rc.track(board, "/XIN", (xc, yc), (xy, yy), width=0.15)
    x1, y1 = rc.pad_at(board, "U1", 21)                 # XOUT
    xr, yr = rc.pad_at(board, "R2", 1)
    assert board.FindFootprintByReference("R2").FindPadByNumber("1").GetNetname() == "/XOUT"
    for a, b in (((x1, y1), (x1, XOUT_Y)), ((x1, XOUT_Y), (XOUT_X, XOUT_Y)), ((XOUT_X, XOUT_Y), (XOUT_X, yr - 0.8)),
                 ((XOUT_X, yr - 0.8), (xr, yr))):
        rc.track(board, "/XOUT", a, b, width=0.15)


def legend(path):
    """The header's pin names on the silkscreen, one under each pin, reading
    up to it: a board-only footprint (placed at the header's origin), so the
    designators keep clear of it. The DESPI-C02 has its pins in another
    order and is wired pin by pin with jumpers, by these names."""
    texts = []
    for n, (word, _) in sorted(HEADER.items()):
        x = PIN_X[n] - HX
        texts.append('\t(fp_text user "%s" (at %.2f 1.2 90) (layer "F.SilkS")\n'
                     '\t\t(effects (font (size 1 1) (thickness 0.15)) (justify right)))\n' % (word, x))
    # a courtyard round the names, so the designators keep off them
    x0, x1 = PIN_X[9] - HX - 0.8, PIN_X[1] - HX + 0.8
    texts.append('\t(fp_rect (start %.2f 1.05) (end %.2f 5.05) (stroke (width 0.05) (type solid)) (fill none) '
                 '(layer "F.CrtYd"))\n' % (x0, x1))
    with open(path, "w") as f:
        f.write('(footprint "%s"\n\t(version 20240108)\n\t(generator "cupc8-eink")\n\t(layer "F.Cu")\n'
                '\t(descr "the e-ink card\'s header pin names (hw/boards/eink.py writes it)")\n'
                '\t(attr board_only exclude_from_pos_files exclude_from_bom)\n'
                '\t(property "Reference" "LEGEND" (at 0 0 0) (layer "F.SilkS") (hide yes) '
                '(effects (font (size 1 1) (thickness 0.15))))\n'
                '\t(property "Value" "%s" (at 0 0 0) (layer "F.Fab") (hide yes) '
                '(effects (font (size 1 1) (thickness 0.15))))\n%s)\n' % (LEGEND, LEGEND, "".join(texts)))


if __name__ == "__main__":
    legend(os.path.join(kg.PROJECT_FOOTPRINTS["cupc8"], LEGEND + ".kicad_mod"))
    rc.build("eink", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR", "D2": "REFRESH"}, GPIOS,
             TITLE, REVISION, layers=LAYERS, passes=100, preroute=preroute)
