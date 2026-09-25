#!/usr/bin/env python3
"""The M1 CPU card: cpu.vhd in an iCE40HX4K-TQ144 on a PCIe-x8-style card edge
(doc/hardware/cpu-bus.md), booting itself from its own W25Q32 config flash,
which the system card reprograms through the socket (FL1 bus, CRESET_n, CDONE).

    python3 hw/boards/cpu.py [outdir]      (default build/hw/cpu)

The FPGA pins come from hw/pins.yaml (cpu_fpga), the same source as
build/hw/cpucard.pcf, so the schematic cannot disagree with the bitstream.

Power, per Lattice's iCE40 hardware checklist (FPGA-TN-02006):
  - VCC 1V2 from an RT9013-12GB off the socket's +3V3; every VCCIO bank,
    SPI_VCC and VPP_2V5 on 3V3 (VPP_2V5 may be 2.5-3.3 V for SPI-master boot)
  - VCCPLL0/1 through 100 ohm with 4.7 uF + 100 nF to their own GNDPLL, which
    is NOT joined to board ground; the checklist asks for this filter even
    when, as here, the PLLs are unused
  - VPP_FAST unconnected; 100 nF on every supply pin, 4.7 uF per rail group
Configuration: SPI_SS_B and SPI_SCK pulled up (controller mode), CRESET_B
and CDONE pulled up here as well as on the main board. /WP and /HOLD of the
flash are pulled high: the FPGA reads it with plain 0x0B fast reads.
Bus: every card output has 33 ohm at the driver (cpu-bus.md, Electrical),
four to a resistor array. CARD_ID = 10: CARD_ID0 strapped to GND, CARD_ID1
left to the main board's pull-up. PRSNT1_n is joined to PRSNT2_n.
"""

import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402

G = kg.GRID

# ------------------------------------------------------------------- parts

# 0402 passives and 0402x4 arrays: the card has the I/O cards' 62 x 39 mm outline
R0402 = "Resistor_SMD:R_0402_1005Metric"
# JLC's footprint for C1521989: pin 1 at the bottom left, running right
TQFP144 = "jlc:TQFP-144_L20.0-W20.0-P0.50-LS22.0-BL"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
ARRAY = "jlc:RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL"
LCSC = {
    "100n": "C1525", "1u": "C52923", "4.7u": "C23733",          # 0402 caps (basic)
    "10k": "C25744", "100": "C25076", "1k": "C11702",           # 0402 resistors (basic)
    "33x4": "C25501",                                           # 4D02WGJ0330TCE, 33 ohm x4, 0402x4
}


def fpga_pins():
    """{package pin: signal} for the CPU card FPGA, from hw/pins.yaml."""
    with open(os.path.join(ROOT, "hw", "pins.yaml")) as f:
        dev = yaml.safe_load(f)["devices"]["cpu_fpga"]
    out = {}
    for group in dev["groups"].values():
        for sig in group["signals"]:
            pins = sig["pin"] if isinstance(sig["pin"], list) else [sig["pin"]]
            for i, p in enumerate(pins):
                name = sig["name"] + (str(i) if sig.get("width", 1) > 1 else "")
                out[p] = (name, sig["dir"])
    return out


PINS = fpga_pins()
# card outputs get 33 ohm at the driver: FPGA pin on FPGA_x, finger on x
DRIVEN = [n for n, d in sorted(PINS.values(), key=lambda v: v[0]) if d in ("out", "inout")]
SERIES = [
    ["CPU_A0", "CPU_A1", "CPU_A2", "CPU_A3"],
    ["CPU_A4", "CPU_A5", "CPU_A6", "CPU_A7"],
    ["CPU_A8", "CPU_A9", "CPU_A10", "CPU_A11"],
    ["CPU_A12", "CPU_A13", "CPU_A14", "CPU_A15"],
    ["CPU_nSTB", "CPU_RW", "CPU_SYNC", None],               # bottom side, after CLK and /RST
    ["CPU_D0", "CPU_D1", "CPU_D2", "CPU_D3"],               # right side, bottom up
    ["CPU_D4", "CPU_D5", "CPU_D6", "CPU_D7"],
    ["CPU_TMR_EXP0", "CPU_TMR_EXP1", "CPU_HALTED", "CPU_WAITING"],
]
assert sorted(n for a in SERIES for n in a if n) == sorted(DRIVEN), "series arrays miss a card output"

# socket pin name (doc) -> net
SOCKET = {"/STB": "CPU_nSTB", "/RDY": "CPU_nRDY", "/CPU_RST": "CPU_nRST", "RW": "CPU_RW",
          "SYNC": "CPU_SYNC", "HALTED": "CPU_HALTED", "WAITING": "CPU_WAITING", "CPU_CLK": "CPU_CLK",
          "+3V3": "3V3", "GND": "GND", "CARD_ID0": "GND", "CRESET_n": "CRESET_n", "CDONE": "CDONE",
          "FL1_SCK": "FL1_SCK", "FL1_MOSI": "FL1_MOSI", "FL1_MISO": "FL1_MISO", "FL1_nCS": "FL1_nCS",
          "PRSNT1_n": "PRSNT", "PRSNT2_n": "PRSNT"}
for i in range(16):
    SOCKET["A%d" % i] = "CPU_A%d" % i
for i in range(8):
    SOCKET["D%d" % i] = "CPU_D%d" % i
for i in range(4):
    SOCKET["IRQ%d" % i] = "CPU_IRQ%d" % i
for i in range(2):
    SOCKET["TMR_EXP%d" % i] = "CPU_TMR_EXP%d" % i
# +5V (the card runs from +3V3), CARD_ID1 (a 1: the main board's pull-up)
# and the RSVD pins are left unconnected

# configuration and power pins of the FPGA (unit 5)
FPGA_POWER = {"GND": "GND", "VCC": "1V2", "VCC_SPI": "3V3", "VPP_2V5": "3V3",
              "VCCPLL0": "VCCPLL0", "GNDPLL0": "GNDPLL0", "VCCPLL1": "VCCPLL1", "GNDPLL1": "GNDPLL1",
              "CDONE": "CDONE", "~{CRESET}": "CRESET_n", "IOB_105_SDO": "FL1_MOSI",
              "IOB_106_SDI": "FL1_MISO", "IOB_107_SCK": "FL1_SCK", "IOB_108_SS": "FL1_nCS"}

# decoupling: ref -> (net, value, FPGA pin it sits beside, or None). One
# 100 nF per supply pin, 4.7 uF per rail group (TN-02006 table 2.2)
DECOUPLING = {
    "C1": ("1V2", "100n", 27), "C2": ("1V2", "100n", 40), "C3": ("1V2", "100n", 92), "C4": ("1V2", "100n", 111),
    "C5": ("3V3", "100n", 6), "C6": ("3V3", "100n", 30), "C7": ("3V3", "100n", 46), "C8": ("3V3", "100n", 57),
    "C9": ("3V3", "100n", 89), "C10": ("3V3", "100n", 100), "C11": ("3V3", "100n", 123),
    "C12": ("3V3", "100n", 131), "C13": ("3V3", "100n", 72), "C14": ("3V3", "100n", 108),
    "C15": ("3V3", "4.7u", None), "C16": ("3V3", "4.7u", None),
}


def net_of(pin_num, pin_name):
    """The net on an FPGA package pin (None: unused I/O)."""
    if pin_num in PINS:
        name, d = PINS[pin_num]
        return ("FPGA_" + name[4:]) if name in DRIVEN else name
    if pin_name.startswith("VCCIO"):
        return "3V3"
    return FPGA_POWER.get(pin_name)


# --------------------------------------------------------------- schematic

def schematic(path, footprint_libs):
    s = kg.Schematic("cpu", "CUPC/8 CPU card: iCE40HX4K-TQ144, W25Q32 config flash", paper="A2")

    def cap(ref, value, a, b, at):
        c = s.add("Device:C", ref, value, C0402, at=at, fields={"LCSC": LCSC[value]})
        s.connect(c, 1, a)
        s.connect(c, 2, b)
        return c

    def res(ref, value, a, b, at):
        r = s.add("Device:R", ref, value, R0402, at=at, fields={"LCSC": LCSC[value]})
        s.connect(r, 1, a)
        s.connect(r, 2, b)
        return r

    # the card edge
    j1 = s.add("cupc8:CUPC8_CPUSocket", "J1", "CPU card edge", "Connector_PCBEdge:BUS_PCIexpress_x8",
               at=(32 * G, 48 * G))
    for num, (x, y, a, name, *_rest) in j1.pins.items():
        if name in SOCKET:
            s.connect(j1, num, SOCKET[name])
        else:
            s.nc(j1, num, stub=G)

    # the FPGA, five units: banks 0-3 and config/power
    unit_at = {4: (68, 32), 3: (68, 76), 1: (100, 32), 2: (100, 76), 5: (134, 32)}
    u1 = {}
    for unit, (gx, gy) in unit_at.items():
        u = s.add("FPGA_Lattice:ICE40HX4K-TQ144", "U1", "ICE40HX4K-TQ144",
                  TQFP144, at=(gx * G, gy * G), unit=unit,
                  fields={"LCSC": "C1521989"})
        u1[unit] = u
        for num, (x, y, a, name, ptype, ln, hidden) in u.pins.items():
            if num in u.used or ptype == "no_connect":
                continue
            net = net_of(int(num), name)
            if net:
                s.connect(u, num, net)
            elif not hidden:
                s.nc(u, num, stub=G)

    # config flash
    u2 = s.add("Memory_Flash:W25Q32JVSS", "U2", "W25Q32JVSSIQ", "jlc:SOIC-8_L5.3-W5.3-P1.27-LS8.0-BL",
               at=(172 * G, 28 * G), fields={"LCSC": "C179173"})
    for pin, net in (("~{CS}", "FL1_nCS"), ("CLK", "FL1_SCK"), ("DI/IO_{0}", "FL1_MOSI"),
                     ("DO/IO_{1}", "FL1_MISO"), ("~{WP}/IO_{2}", "FL1_WPHOLD"), ("~{HOLD}/~{RESET}/IO_{3}", "FL1_WPHOLD"),
                     ("VCC", "3V3"), ("GND", "GND")):
        s.connect(u2, pin, net)

    # 1V2 LDO
    u3 = s.add("jlc:RT9013-12GB", "U3", "RT9013-12GB", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",
               at=(172 * G, 52 * G), fields={"LCSC": "C58464"})
    for pin, net in (("VIN", "3V3"), ("EN", "3V3"), ("GND", "GND"), ("VOUT", "1V2")):
        s.connect(u3, pin, net)
    s.nc(u3, "NC")

    # 33 ohm series arrays
    for i, nets in enumerate(SERIES):
        rn = s.add("Device:R_Pack04", "RN%d" % (i + 1), "33", ARRAY,
                   at=((16 + 16 * i) * G, 108 * G), fields={"LCSC": LCSC["33x4"]})
        for k, net in enumerate(nets):
            if net:
                s.connect(rn, "R%d.1" % (k + 1), "FPGA_" + net[4:])        # FPGA side: pads 1-4
                s.connect(rn, "R%d.2" % (k + 1), net)                      # finger side: pads 8-5
            else:
                s.nc(rn, "R%d.1" % (k + 1), stub=G)
                s.nc(rn, "R%d.2" % (k + 1), stub=G)

    # pull-ups (TN-02006 table 3.1)
    row = 124
    for i, net in enumerate(("CRESET_n", "CDONE", "FL1_nCS", "FL1_SCK", "FL1_WPHOLD")):
        res("R%d" % (i + 1), "10k", "3V3", net, at=((14 + 8 * i) * G, row * G))
    # PLL supply filters: R6/C17/C18 for PLL0, R7/C19/C20 for PLL1
    for i, k in enumerate(("0", "1")):
        res("R%d" % (6 + i), "100", "1V2", "VCCPLL" + k, at=((54 + 20 * i) * G, row * G))
        cap("C%d" % (17 + 2 * i), "4.7u", "VCCPLL" + k, "GNDPLL" + k, at=((60 + 20 * i) * G, row * G))
        cap("C%d" % (18 + 2 * i), "100n", "VCCPLL" + k, "GNDPLL" + k, at=((66 + 20 * i) * G, row * G))
    # LDO in/out, flash
    cap("C21", "1u", "3V3", "GND", at=(96 * G, row * G))
    cap("C22", "4.7u", "1V2", "GND", at=(102 * G, row * G))
    cap("C23", "100n", "3V3", "GND", at=(114 * G, row * G))
    for i, (ref, (net, val, _)) in enumerate(DECOUPLING.items()):
        cap(ref, val, net, "GND", at=((14 + 6 * i) * G, (row + 14) * G))

    # 1V2 rail LED (power.md): 1.2 V cannot light an LED, so an NPN switches it
    q1 = s.add("Transistor_BJT:MMBT3904", "Q1", "MMBT3904", "Package_TO_SOT_SMD:SOT-23",
               at=(150 * G, row * G), fields={"LCSC": "C20526"})
    res("R8", "10k", "1V2", "LED_B", at=(142 * G, row * G))
    s.connect(q1, "B", "LED_B")
    s.connect(q1, "E", "GND")
    s.connect(q1, "C", "LED_K")
    d1 = s.add("Device:LED", "D2", "red", "LED_SMD:LED_0603_1608Metric", at=(160 * G, (row - 4) * G),
               fields={"LCSC": "C2286"})
    s.connect(d1, "K", "LED_K")
    s.connect(d1, "A", "LED_A")
    res("R10", "1k", "3V3", "LED_A", at=(170 * G, row * G))

    # power LED (milestone-1.md, Indicator LEDs): 3V3, the same spot on every board
    d2 = s.add("Device:LED", "D1", "red", "LED_SMD:LED_0603_1608Metric", at=(176 * G, (row - 4) * G),
               fields={"LCSC": "C2286"})
    s.connect(d2, "K", "GND")
    s.connect(d2, "A", "PWR_LED_A")
    res("R9", "1k", "3V3", "PWR_LED_A", at=(186 * G, row * G))
    # M3 mounting hole (as the I/O cards, slot.md Mechanical)
    s.add("Mechanical:MountingHole", "H1", "M3", kg.MOUNTING_HOLE, at=(196 * G, (row - 4) * G))

    # test pads
    for i, net in enumerate(("1V2", "3V3", "GND")):
        tp = s.add("Connector:TestPoint", "TP%d" % (i + 1), net, "cupc8:TestPad_D1.0mm",
                   at=((204 + 8 * i) * G, row * G))
        s.connect(tp, 1, net)

    # power flags: the socket and the LDO have passive pins
    for i, net in enumerate(("3V3", "GND", "1V2", "VCCPLL0", "VCCPLL1", "GNDPLL0", "GNDPLL1")):
        f = s.add("power:PWR_FLAG", "#FLG%02d" % (i + 1), "PWR_FLAG", at=((120 + 8 * i) * G, (row + 14) * G))
        s.connect(f, 1, net)

    # the FPGA's NC pins are typed no_connect (and hidden): nothing to mark
    left = [(p.ref, n) for p in s.parts for n, pin in p.pins.items()
            if n not in p.used and pin[4] != "no_connect"]
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)




# ------------------------------------------------------------------- board
#
# The I/O cards' outline (cpu-bus.md, CPU card outline; slot.md, Mechanical)
# in the frame of the x8 finger footprint (finger B1 at the origin): the body
# is kg.IO_CARD_BODY, the M3 hole and the power LED where every card has them,
# and the x8 tab (x -0.65 .. 50.65) under it with 5.35 mm shoulders. Nothing
# is placed in the 4.5 mm strip above the fingers (their GND ties and vias).
# The FPGA sits against the top edge, which leaves a 10 mm band between its
# bottom pins and the fingers for the arrays and the bus's fan-out (5.7 mm
# with the decaps above it did not route); the top side's four supply pins
# are decoupled from the package's top corners instead, all on planes.
# The FPGA's bank-3 side (A[15:0], then CLK and the control lines) faces the
# fingers and its bank-2 side (D, IRQ, timers, then config) faces right, each
# in the fingers' left-to-right order, so the front-side bus lines reach
# their fingers without crossing.

BODY = kg.IO_CARD_BODY
TAB_TOP = BODY[3]                      # where the tab meets the body
DY = BODY[1] + 44.0                  # the layout is drawn for a 39.05 mm body; a taller one adds at the top
FPGA = (24.5, -31.3 + DY, 0)         # its top pad row 0.85 mm from the top edge
ZONES = ("/GND", ("/GND", ("In1.Cu",)), ("/3V3", ("In2.Cu",)))
LOGO_MM = 12
LOGO_AT = (49.4, -14.6 + DY)              # the empty lower right: D and timer lines pass under it
TITLE, REVISION = "CUPC/8 CPU", "A"
SILK_TEXT = (0.8, 0.15)              # designators at JLC's minimum height: this card is 0402s
POWER_LED = kg.IO_CARD_PWR_LED


def fpga_pad(pin):
    """Board position of an FPGA pad and its outward direction."""
    import math
    x0, y0, rot = FPGA
    n = float(pin)                       # a half pin is the spot between two
    side = int((n - 1) // 36)            # 0 bottom, 1 right, 2 top, 3 left (unrotated)
    k = n - 1 - 36 * side                # along it
    t = -8.75 + 0.5 * k
    ux, uy, ox, oy = [(t, 10.95, 0, 1), (10.95, -t, 1, 0), (-t, -10.95, 0, -1), (-10.95, t, -1, 0)][side]
    a = math.radians(rot)                # KiCad turns counter-clockwise on screen (y down)
    rx, ry = ux * math.cos(a) + uy * math.sin(a), -ux * math.sin(a) + uy * math.cos(a)
    dx, dy = round(ox * math.cos(a) + oy * math.sin(a)), round(-ox * math.sin(a) + oy * math.cos(a))
    return x0 + rx, y0 + ry, dx, dy


def beside(pin, dist=3.2, along=0.0):
    """A chip capacitor just outside an FPGA pin, radial, pad 1 towards the pin;
    `along` slides it along the package side (room for designators)."""
    x, y, dx, dy = fpga_pad(pin)
    rot = {(1, 0): 0, (-1, 0): 180, (0, 1): 270, (0, -1): 90}[(dx, dy)]
    return (round(x + dx * dist + abs(dy) * along, 3), round(y + dy * dist + abs(dx) * along, 3), rot)


def placement():
    p = {"J1": (0, 0, 0), "U1": FPGA, "H1": kg.IO_CARD_HOLE + (0,)}
    for ref, (_, _, pin) in DECOUPLING.items():
        if pin:
            p[ref] = beside(pin)
    # the PLL filter caps sit between these and their pins' neighbours
    p["C11"] = beside(123, along=-3.0)
    p["C12"] = beside(131, along=1.5)
    p["C8"] = beside(57, along=-0.5)
    # the bottom side's decaps step aside from the arrays under the bus pins
    p["C5"] = beside(6, along=-4.0)
    p["C1"] = beside(27, along=4.5)
    p["C6"] = beside(30, along=6.0)
    fx, fy = FPGA[:2]
    p.update({
        # the top side's supply pins (VPP 108, VCC 92, VCCIO1 100 and 89) are
        # decoupled from the package's top corners: the pad row is at the edge
        "C14": (fx - 12.5, fy - 11.2, 0), "C3": beside(37, along=2.0),
        "C10": (fx + 12.2, fy - 11.0, 90), "C9": (fx - 14.15, -26.2 + DY, 180),
        "C13": beside(72, along=2.5),                               # VCC_SPI
        "C15": (9.0, -21.0 + DY, 0), "C16": (54.8, -21.5 + DY, 90),          # 3V3 bulk
        # PLL0 filter (pins 53/54, right side) and PLL1 (126/127, left side)
        "C18": beside(53.5, dist=3.25)[:2] + (270,), "C17": (51.4, -20.9 + DY, 0), "R6": (48.2, -20.9 + DY, 0),
        "C20": beside(126.5, dist=3.25)[:2] + (90,), "C19": (3.2, -30.2 + DY, 0), "R7": (3.2, -26.6 + DY, 0),
        # 33 ohm arrays at their pins, FPGA side (pads 1-4) towards the
        # package and in the pins' order, finger side (pads 8-5) away from
        # it: A and control in a row under the bottom side, D and the timer
        # lines in a column right of the right side
        "RN1": (16.5, fy + 15.1, 0), "RN2": (19.5, fy + 15.1, 0), "RN3": (22.3, fy + 15.1, 0),
        "RN4": (25.1, fy + 15.1, 0), "RN5": (27.9, fy + 15.1, 0),
        "RN6": (45.8, fy + 7.8, 90), "RN7": (45.8, fy + 5.0, 90), "RN8": (45.8, fy - 0.2, 90),
        # config flash by the config pins, under the top edge beside the
        # hole, its decap, and the configuration pull-ups
        "U2": (45.3, -38.6 + DY, 0), "C23": (48.6, -35.6 + DY, 90),
        "R1": (49.8, -33.6 + DY, 0), "R2": (49.8, -31.2 + DY, 0), "R3": (49.8, -28.8 + DY, 0), "R4": (49.8, -26.4 + DY, 0),
        "R5": (49.8, -24.0 + DY, 0),
        # LEDs along the top edge from the common PWR spot, each resistor
        # under its LED; the 1V2 LED's switch below; the LDO beside them
        "D1": POWER_LED + (0,), "R9": (POWER_LED[0], POWER_LED[1] + 2.6, 0),
        "D2": (POWER_LED[0] + 4.5, POWER_LED[1], 0), "R10": (POWER_LED[0] + 4.5, POWER_LED[1] + 2.6, 0),
        "Q1": (POWER_LED[0] + 0.2, POWER_LED[1] + 8.8, 0), "R8": (POWER_LED[0] + 3.8, POWER_LED[1] + 12.6, 0),
        "U3": (5.4, -40.8 + DY, 0), "C21": (4.2, -36.4 + DY, 0), "C22": (4.2, -33.4 + DY, 0),
        "TP1": (-3.0, -19.0 + DY, 0), "TP2": (1.0, -19.0 + DY, 0), "TP3": (5.0, -19.0 + DY, 0),
    })
    return p


def a_vias(board, via=0.6, drill=0.3, track=0.2):
    """Locked pre-routing: each address line leaves its array (finger side,
    pads 8-5, 0.5 mm apart) on a short track to its own via, in two
    staggered rows just under the arrays. A goes to the back-side fingers;
    placing its layer changes here keeps the front below the arrays clear
    for the control and data lines, which Freerouting otherwise has to
    thread through vias it scattered itself."""
    import pcbnew
    mm = pcbnew.FromMM
    for fp in board.GetFootprints():
        if fp.GetReference() not in ("RN1", "RN2", "RN3", "RN4"):
            continue
        for pad in fp.Pads():
            k = int(pad.GetNumber())
            if k <= 4:
                continue
            px, py = pad.GetPosition().x, pad.GetPosition().y
            v = pcbnew.VECTOR2I(px, py + mm(1.2 if k % 2 else 2.4))
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pad.GetPosition())
            t.SetEnd(v)
            t.SetWidth(mm(track))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(pad.GetNet())
            t.SetLocked(True)
            board.Add(t)
            vi = pcbnew.PCB_VIA(board)
            vi.SetPosition(v)
            vi.SetWidth(mm(via))
            vi.SetDrill(mm(drill))
            vi.SetNet(pad.GetNet())
            vi.SetLocked(True)
            board.Add(vi)


def track(board, net, layer, a, b, width):
    import pcbnew
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
    t.SetWidth(pcbnew.FromMM(width))
    t.SetLayer(layer)
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)


def supply_fingers(board, width=0.5, via=0.6, drill=0.3, top=TAB_TOP - 6.0):
    """Locked tie from the three +3V3 fingers (B5-B7, front) into the In2
    plane: each rises on F.Cu, a bar joins them, and one via drops into the
    plane above the presence link's run (which cuts the plane's sliver over
    the fingers off). The pad fan-out skips edge fingers, and a plane net is
    not Freerouting's to join."""
    import pcbnew
    to = pcbnew.ToMM
    for fp in board.GetFootprints():
        if fp.GetReference() != "J1":
            continue
        pads = [p for p in fp.Pads() if p.GetNetname() == "/3V3"]
        xs = sorted(to(p.GetPosition().x) for p in pads)
        net = pads[0].GetNet()
        for p in pads:
            x = to(p.GetPosition().x)
            track(board, net, pcbnew.F_Cu, (x, to(p.GetBoundingBox().GetTop()) + width / 2), (x, top), width)
        track(board, net, pcbnew.F_Cu, (xs[0], top), (xs[-1], top), width)
        mid = (xs[0] + xs[-1]) / 2
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(mid), pcbnew.FromMM(top)))
        v.SetWidth(pcbnew.FromMM(via))
        v.SetDrill(pcbnew.FromMM(drill))
        v.SetNet(net)
        v.SetLocked(True)
        board.Add(v)


KNEE = 1.3                           # mm from an FPGA pad's centre to past the pad row's inner ends


def plane_pins(board, via=0.6, drill=0.3, width=0.25, gap=0.2):
    """Every FPGA pin on a plane net (GND, 3V3) needs its own via: Freerouting
    leaves plane nets to their planes. kicadgen.ground_fanout places them one
    pin at a time, and next to another supply pin 0.5 mm away it can leave
    none. So the FPGA's are redone here as one scheme: each pin's track runs
    straight in under the package past the pad row, then to a via that leans
    away from its supply-pin neighbours (whose vias lean the other way), clear
    of every via, track and pad already there."""
    import math
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        k = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
        return math.hypot(px - ax - k * dx, py - ay - k * dy)
    u1 = [fp for fp in board.GetFootprints() if fp.GetReference() == "U1"][0]
    at = {(p.GetPosition().x, p.GetPosition().y) for p in u1.Pads() if p.GetNetname() in ("/GND", "/3V3")}
    tracks = board.Tracks()
    items = [tracks[i].Cast() for i in range(len(tracks))]
    fanned = [s for s in items if s.Type() == pcbnew.PCB_TRACE_T and (s.GetStart().x, s.GetStart().y) in at]
    ends = {(s.GetEnd().x, s.GetEnd().y) for s in fanned}
    for item in fanned + [v for v in items if v.Type() == pcbnew.PCB_VIA_T
                          and (v.GetPosition().x, v.GetPosition().y) in ends]:
        board.Remove(item)
    tracks = board.Tracks()
    items = [tracks[i].Cast() for i in range(len(tracks))]
    segs = [(to(s.GetStart().x), to(s.GetStart().y), to(s.GetEnd().x), to(s.GetEnd().y), s.GetNetname(),
             to(s.GetWidth())) for s in items if s.Type() == pcbnew.PCB_TRACE_T]
    vias = [(to(v.GetPosition().x), to(v.GetPosition().y), v.GetNetname()) for v in items
            if v.Type() == pcbnew.PCB_VIA_T]
    pads = [(p, p.GetBoundingBox()) for fp in board.GetFootprints() for p in fp.Pads()]
    supply = {int(p.GetNumber()) for p in u1.Pads() if p.GetNetname() in ("/GND", "/3V3")}
    for pad in u1.Pads():
        net = pad.GetNetname()
        if net not in ("/GND", "/3V3"):
            continue
        cx, cy = to(pad.GetPosition().x), to(pad.GetPosition().y)
        num = int(pad.GetNumber())
        _, _, dx, dy = fpga_pad(num)
        # along the side, towards the next pin; lean away from supply-pin
        # neighbours, whose vias fan out the other way
        sx, sy = dy, -dx                              # the next pin's direction on every side
        lean = (num - 1 in supply) - (num + 1 in supply)
        sides = [s * (lean or 1) for s in (0.5, 1.0, 0.0, 1.5, -0.5, 2.0, -1.0)] if lean else \
            [0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0]
        placed = False
        for depth in (1.8, 2.6, 3.4, 4.2, 5.0, 5.8, 6.6):
            for side in sides:
                vx, vy = cx - dx * depth + sx * side, cy - dy * depth + sy * side
                if any(math.hypot(vx - x, vy - y) < via + gap for x, y, _ in vias):
                    continue
                if any(n != net and seg_dist(vx, vy, *s[:4]) < via / 2 + gap + s[5] / 2 for s in segs
                       for n in (s[4],)):
                    continue
                # straight in past the pad row's inner ends, then over to the via
                kx, ky = cx - dx * KNEE, cy - dy * KNEE
                path = [(cx + (kx - cx) * i / 8, cy + (ky - cy) * i / 8) for i in range(9)] + \
                       [(kx + (vx - kx) * i / 16, ky + (vy - ky) * i / 16) for i in range(1, 17)]
                if any(n != net and seg_dist(px, py, *s[:4]) < width / 2 + gap + s[5] / 2
                       for s in segs for n in (s[4],) for px, py in path):
                    continue
                if any(n != net and math.hypot(px - x, py - y) < width / 2 + gap + via / 2
                       for x, y, n in vias for px, py in path):
                    continue
                bad = False
                for p, bb in pads:
                    if p.GetNetname() == net:
                        continue
                    grow = gap + width / 2
                    x0, y0, x1, y1 = to(bb.GetLeft()) - grow, to(bb.GetTop()) - grow, to(bb.GetRight()) + grow, \
                        to(bb.GetBottom()) + grow
                    if any(x0 < px < x1 and y0 < py < y1 for px, py in path) or \
                            (x0 - via / 2 < vx < x1 + via / 2 and y0 - via / 2 < vy < y1 + via / 2):
                        bad = True
                        break
                if bad:
                    continue
                track(board, pad.GetNet(), pcbnew.F_Cu, (cx, cy), (kx, ky), width)
                track(board, pad.GetNet(), pcbnew.F_Cu, (kx, ky), (vx, vy), width)
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
                v.SetWidth(mm(via))
                v.SetDrill(mm(drill))
                v.SetNet(pad.GetNet())
                v.SetLocked(True)
                board.Add(v)
                segs += [(cx, cy, kx, ky, net, width), (kx, ky, vx, vy, net, width)]
                vias.append((vx, vy, net))
                placed = True
                break
            if placed:
                break
        if not placed:
            raise SystemExit("U1 pin %s (%s): no room for its plane via" % (pad.GetNumber(), net))


def key_ties(board, width=0.25):
    """The GND ties ground_fingers runs up the fingers either side of the key
    notch pass 0.3 mm from its edge at their 0.5 mm width: narrow those."""
    import pcbnew
    to = pcbnew.ToMM
    notch = (10.55, 12.45)                            # the footprint's key, x of its sides
    tracks = board.Tracks()
    for s in [tracks[i].Cast() for i in range(len(tracks))]:
        if s.Type() == pcbnew.PCB_TRACE_T and s.GetNetname() == "/GND" and s.IsLocked() and \
                to(s.GetStart().y) > TAB_TOP - 5 and min(abs(to(s.GetStart().x) - n) for n in notch) < 0.8:
            s.SetWidth(pcbnew.FromMM(width))


def ring_pads(board):
    """No pour joins the FPGA's supply pads: between pads 0.5 mm apart it
    could only reach one through a sliver under the 0.15 mm minimum. Each has
    its own via to its plane (plane_pins). (A rule area would do it too, but
    KiCad hands Freerouting a fill-only rule area as a keepout for tracks.)"""
    import pcbnew
    for fp in board.GetFootprints():
        if fp.GetReference() == "U1":
            for pad in fp.Pads():
                if pad.GetNetname() in ("/GND", "/3V3"):
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)


def prepare(board):
    """The card's own pre-routing, run after the pad fan-out. In1 carries
    signals as well as the GND pour: on the I/O-card outline the bus has a
    10 mm band to its fingers, and two signal layers are not enough there.
    The GND pour on In1 fills round them, and every piece of it is joined by
    GND vias to the stitched outer pours; In2 stays a solid 3V3 plane."""
    import pcbnew
    board.SetLayerType(board.GetLayerID("In1.Cu"), pcbnew.LT_SIGNAL)
    ring_pads(board)
    key_ties(board)
    a_vias(board)
    supply_fingers(board)
    plane_pins(board)


def main():
    import pcbnew  # noqa: F401 - first, so its start-up noise comes before the step lines
    import logo
    logo.footprint(LOGO_MM)
    out = sys.argv[1] if len(sys.argv) > 1 else None
    # GND poured on both outer layers (zones[0], which the pipeline ties the
    # fingers to and stitches) and as the In1 plane; 3V3 is the In2 plane
    lcsc = kg.pipeline(
        "cpu", schematic, placement(), None, out=out, io_card=True, tab=kg.X8_TAB, layers=4, zones=ZONES,
        labels={"D1": "PWR", "D2": "1V2"}, title=TITLE, revision=REVISION, prepare=prepare,
        presence={"layer": "In2.Cu"},   # a B.Cu run would wall the address lines off their fingers
        passes=80,                      # 60 left one bus net unrouted after its three tries
        silk_text=SILK_TEXT,
        graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM,) + LOGO_AT + (0,)])
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
