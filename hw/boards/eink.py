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
import fillfeature as ff  # noqa: E402
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
        # 0603 (C23140, basic), so its designator fits over it in the row
        r = rc.passive(s, "R", "R%d" % (10 + i), "33R", ((186 + 5 * i) * G, 70 * G), fp=rc.R0603, lcsc="C23140")
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
CX, CY = 26, -16
HX, HY = 36.5, -39.6             # the header: its 2.5 mm insulator flush with the top edge, the pins out over it
PIN_X = {n: HX + 10.16 - 2.54 * (n - 1) for n in HEADER}    # turned 180: pin 1 at the right
TVS_Y, R_Y = -32.6, -24.8
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    # the core as on the storage card: the middle pins of the chip's top
    # edge (SWD, DVDD, IOVDD, XIN/XOUT) escape by vias (rc.pocket_escapes),
    # the crystal to the left, the flash by the QSPI pins (now at the bottom)
    "C12": (CX + 5.2, CY - 1.2, 0),      # DVDD 23
    "C3": (CX + 5.8, CY - 0.2, 0),       # IOVDD 1, clear of the flash
    "C5": (CX - 4.4, CY - 5.2, 0),       # IOVDD 22
    "C10": (CX - 1.5, CY + 6.2, 0),      # USB_VDD 48
    "C8": (CX - 1.5, CY + 8.2, 0),       # IOVDD 49
    "Y1": (CX - 8.5, CY - 4.0, 0),
    "C16": (CX - 11.2, CY - 4.0, 90),
    "C17": (CX - 8.5, CY - 1.4, 0),
    "R2": (CX - 5.8, CY - 6.2, 90),      # XOUT
    "U3": (CX + 8.2, CY + 5.6, 90),
    "C15": (CX + 12.0, CY + 3.4, 90),
    "R1": (CX + 12.0, CY + 7.4, 90),
    "J1": (0, 0, 0),
    "C2": (3, -11.5, 90),                # the slot's +3V3 comes in at B4/A4
    "R3": (8.5, -12.5, 90),              # RUN (CARD_RST_n, B9) pull-up, by its finger
    "U4": (14, -12.5, 270),
    "R60": (16.5, -13.6, 0),
    "R61": (18, -14.11, 90),
    "C18": (10.5, -12.5, 90),
    # REFRESH in the top-edge row with the power LED, its resistor under it
    "D2": (17, -41, 0), "R5": (17, -38.5, 0),
    "J2": (HX, HY, 180),
    # under the header: the pin names, then the TVS arrays, then a series
    # resistor under each signal pin
    "U5": (PIN_X[1] - 5.1, TVS_Y, 0),              # VCC, DIN, CLK, CS
    "U6": (PIN_X[9] + 3.8, TVS_Y, 0),              # DC, RST, BUSY, PWR
    "F1": (PIN_X[1] + 1.1, -32.4, 90),
    "C20": (PIN_X[1] + 3.9, -32.4, 90),
    "C21": (PIN_X[1] + 1.9, -30.0, 0),
    "TP1": (-4, -36), "TP2": (-4, -18.5), "TP3": (-4, -22), "TP4": (-4, -25.5), "TP5": (-4, -29), "TP6": (-4, -32.5),
})
# the series resistors in a row up and right of the chip's panel corner, in
# the order its pins come out (GPIO15..12 along the top, then 11..9 down the
# right side), so the fan-out doesn't cross; in two staggered rows, so each
# has its designator over it
CHIP_ORDER = ["EPD_PWR", "EPD_BUSY", "EPD_nRST", "EPD_DC", "EPD_DIN", "EPD_CLK", "EPD_nCS"]
PLACEMENT.update({"R%d" % (10 + SIGNALS.index(net)): (29.0 + 2.1 * k, R_Y - 3.6 * (k % 2), 0)
                  for k, net in enumerate(CHIP_ORDER)})
PLACEMENT.update({k: v + (0,) for k, v in PLACEMENT.items() if len(v) == 2})
# State the nominal coordinates directly: the arithmetic above otherwise
# truncates these placements one nanometre away from the saved routed board.
# Route guards remain exact; no tolerance is added.
PLACEMENT.update({"C13": (20.8, -6.2, 180), "C20": (50.56, -32.4, 90),
                  "C21": (48.56, -30.0, 0), "U5": (41.56, -32.6, 0),
                  "U6": (30.14, -32.6, 0)})
LAYERS = 4
LOGO_MM = 12
LEGEND = "EInk_Header_Legend"
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 9, -29, 0), ("cupc8:" + LEGEND, HX, HY, 0)]
TITLE, REVISION = "CUPC/8 e-ink", "A"


def preroute(board):
    """As the storage card: rp2040card.pocket_escapes, with SWDIO's via a
    row further out and towards the fingers, clear of the panel lines."""
    rc.pocket_escapes(board, swdio=(2.26, -0.6))
    _pin_spi_designators(board)


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



def _pin_spi_designators(board):
    import pcbnew
    for ref, (x, y, angle, size, stroke) in {'U3': (38945000, -10400000, 0.0, 1000000, 150000), 'R10': (37400000, -26475000, 0.0, 1000000, 150000), 'C17': (12700000, -21400000, 0.0, 1000000, 150000), 'C61': (26987500, -6650000, 0.0, 800000, 150000), 'C3': (34400000, -19800000, 0.0, 800000, 150000), 'C16': (12495000, -20000000, 0.0, 1000000, 150000), 'R3': (8500000, -10625000, 0.0, 1000000, 150000), 'C5': (24355000, -24200000, 0.0, 1000000, 150000), 'R60': (14300000, -16400000, 0.0, 1000000, 150000), 'C21': (48560000, -28595000, 0.0, 1000000, 150000), 'TP4': (-1055001, -25499999, 0.0, 1000000, 150000), 'Y1': (14500000, -22695000, 0.0, 1000000, 150000), 'J2': (22895000, -42415000, 0.0, 1000000, 150000), 'R61': (16800000, -15710000, 90.0, 800000, 150000), 'J1': (11500000, -6395000, 0.0, 1000000, 150000), 'R2': (21200000, -24075000, 0.0, 1000000, 150000), 'C63': (9795000, -16149999, 0.0, 800000, 150000), 'H1': (54001264, -35602474, 0.0, 1000000, 150000), 'C13': (22599999, -7400000, 90.0, 1000000, 150000), 'U4': (13200000, -8100000, 0.0, 1000000, 150000), 'R63': (29787500, -6250000, 0.0, 800000, 150000), 'C15': (40305000, -12600000, 0.0, 1000000, 150000), 'R13': (35300000, -30075000, 0.0, 1000000, 150000), 'R11': (39500000, -30075000, 0.0, 1000000, 150000), 'C8': (24500000, -6395000, 0.0, 1000000, 150000), 'C4': (31200000, -20605000, 0.0, 1000000, 150000), 'R15': (32100000, -30075000, 0.0, 1000000, 150000), 'F1': (44965000, -32400000, 0.0, 1000000, 150000), 'C20': (53385000, -32400000, 0.0, 1000000, 150000), 'R65': (10700000, -8350000, 0.0, 800000, 150000), 'C9': (18199999, -12000000, 90.0, 1000000, 150000), 'C6': (19400000, -16000000, 0.0, 800000, 150000), 'TP6': (-1055001, -32499999, 0.0, 1000000, 150000), 'TP5': (-1401240, -30599999, 0.0, 1000000, 150000), 'R16': (29000000, -23124999, 0.0, 1000000, 150000), 'TP1': (-55001, -35999999, 0.0, 1000000, 150000), 'R4': (324999, -38500000, 0.0, 1000000, 150000), 'C2': (175000, -11500000, 0.0, 1000000, 150000), 'R5': (13674999, -38500000, 0.0, 1000000, 150000), 'C18': (8500000, -14355000, 0.0, 1000000, 150000), 'U6': (27384999, -30600000, 0.0, 1000000, 150000), 'TP2': (-4001240, -16453762, 0.0, 1000000, 150000), 'C10': (27700000, -9400000, 0.0, 800000, 150000), 'C14': (17045000, -8000000, 0.0, 1000000, 150000), 'C7': (20799999, -14805000, 0.0, 1000000, 150000), 'TP3': (-1055001, -21999999, 0.0, 1000000, 150000), 'R14': (33200000, -26675000, 0.0, 1000000, 150000), 'R62': (36962500, -19100000, 0.0, 1000000, 150000), 'R1': (40315000, -8600000, 0.0, 1000000, 150000), 'U5': (42560000, -30154999, 0.0, 1000000, 150000), 'C60': (38942499, -17100000, 0.0, 1000000, 150000), 'C11': (24599999, -11000000, 0.0, 800000, 150000), 'U1': (26000000, -21975000, 0.0, 1000000, 150000), 'R12': (41600000, -26475000, 0.0, 1000000, 150000), 'C62': (30737500, -15950000, 90.0, 1000000, 150000), 'R64': (34252500, -13550000, 0.0, 1000000, 150000)}.items():
        word = board.FindFootprintByReference(ref).Reference()
        word.SetPosition(pcbnew.VECTOR2I(x, y))
        word.SetTextAngleDegrees(angle)
        word.SetTextSize(pcbnew.VECTOR2I(size, size))
        word.SetTextThickness(stroke)
        word.SetVisible(True)

# Exact qualified local filter locations; original component positions retained.
PLACEMENT.update({'R62': (34.1875, -17.1, 0.0), 'R63': (30.1875, -8.25, 180.0), 'R64': (31.9375, -14.55, 90.0, 'B'), 'C60': (36.1875, -17.1, 0.0), 'C61': (28.1875, -8.25, 180.0), 'C62': (31.9375, -16.55, 90.0, 'B'), 'C63': (11.85, -10.9, -90.0)})



# Actual independently routed local OE passives, existing placements retained.
PLACEMENT.update({'R62': (34.1875, -17.1, 0.0), 'R63': (30.1875, -8.25, 180.0), 'R64': (31.9375, -14.55, 90.0, 'B'), 'R65': (12.1, -13.15, -90.0), 'C60': (36.1875, -17.1, 0.0), 'C61': (28.1875, -8.25, 180.0), 'C62': (31.9375, -16.55, 90.0, 'B'), 'C63': (12.1, -15.15, 90.0)})


def _seeded_route(board, workdir):
    import route_seed
    result = route_seed.apply(
        board, os.path.join(HERE, "eink-full-route-seed.json"),
        board_name="eink", pour_nets=("/GND",),
        post_route_contract="eink-ahc-panel-preroute-v1")
    _pin_spi_designators(board)
    print("EInk full-route seed: %d copper items; origin %s; fresh full pipeline required" %
          (result['added'], result['origin_state']), end=" ", flush=True)
    return 0


if __name__ == "__main__":
    legend(os.path.join(kg.PROJECT_FOOTPRINTS["cupc8"], LEGEND + ".kicad_mod"))
    rc.build("eink", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR", "D2": "REFRESH"}, GPIOS,
             TITLE, REVISION, layers=LAYERS, passes=150, designator_reach=4, preroute=preroute, seeded_route=_seeded_route,
             post_fill=(lambda board: ff.round_board_fills(board, "eink")))
