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
import fillfeature as ff  # noqa: E402
import rp2040card as rc  # noqa: E402

G = kg.GRID

# storage_mcu in hw/pins.yaml (the slot pins, GPIO2-6, are rp2040card's)
GPIOS = {12: "SD_MISO", 13: "SD_nCS_SRC", 14: "SD_SCK_SRC", 15: "SD_MOSI_SRC", 16: "UART_TX", 17: "SD_nDETECT",
         18: "SD_DAT1", 19: "SD_DAT2", 24: "LED_ACT", 25: "LED_CARD"}

# TF-01A pins (jlc:TF-01A, the SD pin names in SPI mode in brackets)
SOCKET = {1: "SD_DAT2", 2: "SD_nCS", 3: "SD_MOSI", 4: "3V3", 5: "SD_SCK", 6: "GND", 7: "SD_MISO_SRC", 8: "SD_DAT1",
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

    # Source damping: RP outputs and the socket's MISO driver, before the
    # remaining routed fanout. GPIO/pin functions and socket pin order stay fixed.
    for idx, net in enumerate(("SD_SCK", "SD_MOSI", "SD_nCS", "SD_MISO")):
        rr = rc.passive(s, "R", "R%d" % (31 + idx), "68" if idx == 0 else "47", ((180 + 10 * idx) * G, 125 * G), lcsc="C25131" if idx == 0 else "C25118")
        rc.two(s, rr, net + "_SRC", net)

    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


POWER_NETS = rc.POWER_NETS
CX, CY = 26, -16               # the RP2040, turned round: its SD pins (GPIO12-19) face the socket
SX = 40                        # the socket: its opening on the top edge
PLACEMENT = dict(rc.core_placement(CX, CY, turn=180), **{
    # the chip's top edge after the turn: SD pins at its right end and on the
    # top of its left side, and the left group crosses over the middle to the
    # socket; so the middle pins (SWD, DVDD, IOVDD, XIN/XOUT) escape by vias
    # (pocket_escapes) and the crystal sits to the left, the flash by the
    # QSPI pins (now at the bottom)
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
GRAPHICS = [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 9, -29, 0)]
TITLE, REVISION = "CUPC/8 storage", "A"


def prepare(board):
    import route_seed
    route_seed.normalize_placement(board, "C13", (20800000, -6199999), (20800000, -6200000))
    """rp2040card.pocket_escapes, with SWDIO's via a row further out and
    towards the fingers: from the first row Freerouting found no way past the
    SD lines to finger B7."""
    import pcbnew
    # The card-side J2 outline finishes exactly 0.15 mm from pad 11's
    # plotted mask opening; shorten this one endpoint by 0.03 mm.
    fp = next(f for f in board.GetFootprints() if f.GetReference() == "J2")
    edits = 0
    for i in range(fp.GraphicalItems().size()):
        g = pcbnew.Cast_to_PCB_SHAPE(fp.GraphicalItems()[i])
        if not g or g.GetLayer() != pcbnew.F_SilkS or g.GetShape() != pcbnew.SHAPE_T_SEGMENT:
            continue
        a = g.GetStart()
        if abs(pcbnew.ToMM(a.x) - 47.37) < .001 and abs(pcbnew.ToMM(a.y) + 41.075 + TOP_EDGE_SHIFT_MM) < .001:
            g.SetStart(pcbnew.VECTOR2I(a.x, pcbnew.FromMM(-41.105 - TOP_EDGE_SHIFT_MM)))
            edits += 1
    if edits != 1:
        raise ValueError("J2 card-side silk outline changed")
    rc.pocket_escapes(board, swdio=(2.26, -0.6))
    _pin_spi_designators(board)



def _pin_spi_designators(board):
    import pcbnew
    for ref, (x, y, angle, size, stroke) in {'R65': (16900000, -15300000, 90.0, 800000, 150000), 'C16': (12495000, -20000000, 0.0, 1000000, 150000), 'C63': (12700000, -8300000, 0.0, 800000, 150000), 'C2': (175000, -11500000, 0.0, 1000000, 150000), 'C61': (38737500, -15200000, 0.0, 800000, 150000), 'R6': (22000000, -36825000, 0.0, 1000000, 150000), 'U4': (9600000, -16100000, 0.0, 1000000, 150000), 'TP4': (-1055001, -25499999, 0.0, 1000000, 150000), 'TP5': (-1055001, -28999999, 0.0, 1000000, 150000), 'R64': (38187500, -19230000, 0.0, 1000000, 150000), 'R60': (13900000, -14800000, 0.0, 800000, 150000), 'TP1': (-1055001, -35999999, 0.0, 1000000, 150000), 'R5': (13674999, -38500000, 0.0, 1000000, 150000), 'C11': (23199999, -11000000, 0.0, 1000000, 150000), 'R2': (20200000, -24075000, 0.0, 1000000, 150000), 'U5': (33055000, -26500000, 0.0, 1000000, 150000), 'TP6': (-1055001, -32499999, 0.0, 1000000, 150000), 'Y1': (13555000, -23000000, 0.0, 1000000, 150000), 'J1': (11500000, -6395000, 0.0, 1000000, 150000), 'C18': (8500000, -14355000, 0.0, 1000000, 150000), 'C10': (27900000, -8400000, 0.0, 1000000, 150000), 'C17': (14745000, -17400000, 0.0, 1000000, 150000), 'U3': (38945000, -10400000, 0.0, 1000000, 150000), 'C5': (24355000, -23200000, 0.0, 1000000, 150000), 'C8': (24500000, -6395000, 0.0, 1000000, 150000), 'C6': (20400000, -19400000, 90.0, 800000, 150000), 'C20': (39900000, -22154999, 0.0, 1000000, 150000), 'C62': (36787500, -21849999, 90.0, 1000000, 150000), 'R63': (34437500, -21775000, 0.0, 800000, 150000), 'U6': (47500000, -27355000, 0.0, 1000000, 150000), 'R61': (12399999, -16110000, 0.0, 1000000, 150000), 'H1': (52001264, -35602474, 0.0, 1000000, 150000), 'R62': (27412499, -24100000, 0.0, 1000000, 150000), 'R3': (8500000, -10625000, 0.0, 1000000, 150000), 'C15': (40305000, -12600000, 0.0, 1000000, 150000), 'RN1': (50500000, -27495000, 0.0, 1000000, 150000), 'C14': (17999999, -7600000, 90.0, 800000, 150000), 'C60': (30787500, -23900000, 90.0, 1000000, 150000), 'C7': (19799999, -14805000, 0.0, 1000000, 150000), 'C3': (37200000, -16800000, 0.0, 800000, 150000), 'C4': (28600000, -21800000, 90.0, 800000, 150000), 'C13': (22599999, -8000000, 90.0, 1000000, 150000), 'TP2': (-4001240, -16453762, 0.0, 1000000, 150000), 'R4': (324999, -38500000, 0.0, 1000000, 150000), 'R21': (49800000, -32375000, 0.0, 1000000, 150000), 'R20': (30600000, -26200000, 0.0, 800000, 150000), 'TP3': (-1055001, -22999999, 0.0, 1000000, 150000), 'C9': (19250000, -12000000, 90.0, 1000000, 150000), 'J2': (30775000, -36820000, 0.0, 1000000, 150000), 'R1': (40315000, -8600000, 0.0, 1000000, 150000), 'U1': (27000000, -21975000, 0.0, 1000000, 150000), 'C21': (43099999, -21900000, 0.0, 1000000, 150000)}.items():
        word = board.FindFootprintByReference(ref).Reference()
        word.SetPosition(pcbnew.VECTOR2I(x, y))
        word.SetTextAngleDegrees(angle)
        word.SetTextSize(pcbnew.VECTOR2I(size, size))
        word.SetTextThickness(stroke)
        word.SetVisible(True)

# Exact qualified local filter locations; original component positions retained.
PLACEMENT.update({'R62': (30.1875, -21.1, 0.0), 'R63': (33.9375, -19.0, -90.0), 'R64': (35.1875, -17.05, 90.0), 'C60': (32.1875, -21.1, 0.0), 'C61': (33.9375, -17.0, -90.0), 'C62': (35.1875, -19.05, 90.0), 'C63': (12.1, -13.15, 90.0)})



# Actual independently routed local OE passives, existing placements retained.
PLACEMENT.update({'R62': (30.1875, -21.1, 0.0), 'R63': (33.9375, -19.0, -90.0), 'R64': (35.1875, -17.05, 90.0), 'R65': (17.75, -11.0, 90.0), 'C60': (32.1875, -21.1, 0.0), 'C61': (33.9375, -17.0, -90.0), 'C62': (35.1875, -19.05, 90.0), 'C63': (16.1, -11.9, 90.0)})


def _seeded_route(board, workdir):
    import route_seed
    result = route_seed.apply(
        board, os.path.join(HERE, "storage-full-route-seed.json"),
        board_name="storage", pour_nets=("/GND",),
        post_route_contract="storage-ahc-preroute-v1")
    _pin_spi_designators(board)
    print("storage full-route seed: %d copper items; origin %s; fresh full pipeline required" %
          (result['added'], result['origin_state']), end=" ", flush=True)
    return 0


# The 51 mm finished card keeps its finger datum and central circuitry fixed.
# Move only perimeter fittings to the new top edge; the local routed seed
# and fresh full fabrication pipeline qualify their changed connections.
PLACEMENT.update({"R31": (36.5, -21.5, 0), "R32": (32.8, -26.1573, 45), "R33": (30.7, -23.1467, 45), "R34": (44.3167, -29.9, -90)})

TOP_EDGE_SHIFT_MM = 3.55
TOP_EDGE_MOVED_REFS = ('J2', 'D2', 'R5', 'D3', 'R6', 'R21')
for _ref in TOP_EDGE_MOVED_REFS:
    _at = PLACEMENT[_ref]
    PLACEMENT[_ref] = (_at[0], _at[1] - TOP_EDGE_SHIFT_MM, *_at[2:])


if __name__ == "__main__":
    rc.build("storage", schematic, PLACEMENT, POWER_NETS, GRAPHICS, {"D1": "PWR", "D2": "ACT", "D3": "CARD"}, GPIOS,
             TITLE, REVISION, layers=LAYERS, passes=150, designator_reach=4, preroute=prepare, seeded_route=_seeded_route,
             post_fill=(lambda board: ff.round_board_fills(board, "storage")),
             extra_fine_nets=("/SD_SCK", "/SD_MOSI", "/SD_nCS", "/SD_MISO_SRC"))
