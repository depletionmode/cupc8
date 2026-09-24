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

# 0603 throughout: KiCad's 0402 silkscreen sits closer to its pads than
# kicadgen.check_silk allows
R0603 = "Resistor_SMD:R_0603_1608Metric"
# JLC's footprint for C1521989: pin 1 at the bottom left, running right
TQFP144 = "jlc:TQFP-144_L20.0-W20.0-P0.50-LS22.0-BL"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
LCSC = {
    "100n": "C14663", "1u": "C15849", "4.7u": "C19666",         # caps (basic)
    "10k": "C25804", "100": "C22775", "1k": "C21190",           # resistors (basic)
    "33x4": "C25508",                                           # 4D03WGJ0330T5E, 33 ohm x4 convex
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
    ["CPU_nSTB", "CPU_RW", "CPU_SYNC", None],
    ["CPU_D0", "CPU_D1", "CPU_D2", "CPU_D3"],
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
        c = s.add("Device:C", ref, value, C0603, at=at, fields={"LCSC": LCSC[value]})
        s.connect(c, 1, a)
        s.connect(c, 2, b)
        return c

    def res(ref, value, a, b, at):
        r = s.add("Device:R", ref, value, R0603, at=at, fields={"LCSC": LCSC[value]})
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
        rn = s.add("Device:R_Pack04", "RN%d" % (i + 1), "33", "jlc:RES-ARRAY-SMD_0603-8P-L3.2-W1.6-BL",
                   at=((16 + 16 * i) * G, 108 * G), fields={"LCSC": LCSC["33x4"]})
        for k, net in enumerate(nets):
            if net:
                s.connect(rn, "R%d.1" % (k + 1), net)                      # finger side
                s.connect(rn, "R%d.2" % (k + 1), "FPGA_" + net[4:])        # FPGA side
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
    d1 = s.add("Device:LED", "D1", "red", "LED_SMD:LED_0603_1608Metric", at=(160 * G, (row - 4) * G),
               fields={"LCSC": "C2286"})
    s.connect(d1, "K", "LED_K")
    s.connect(d1, "A", "LED_A")
    res("R9", "1k", "3V3", "LED_A", at=(170 * G, row * G))

    # power LED (milestone-1.md, Indicator LEDs): 3V3, the same spot on every board
    d2 = s.add("Device:LED", "D2", "red", "LED_SMD:LED_0603_1608Metric", at=(176 * G, (row - 4) * G),
               fields={"LCSC": "C2286"})
    s.connect(d2, "K", "GND")
    s.connect(d2, "A", "PWR_LED_A")
    res("R10", "1k", "3V3", "PWR_LED_A", at=(186 * G, row * G))
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
# Card body 72 x 60 mm above the PCIe x8 finger tab (the footprint draws the
# tab's Edge.Cuts; its ends meet the body at y = 60). The FPGA's bank-3
# side (A[15:0], IRQ) faces the fingers and its bank-2 side (control, D,
# timers, config, in the fingers' order from the bottom up) faces right; the 33 ohm arrays sit between each
# side and the fingers, the flash beside the config pins.

W, H = 72.0, 60.0
EDGE_X = 11.0                        # finger A1/B1 centre
FPGA = (38.0, 22.0, 0)
OUTLINE = (0, 0, W, H)
TAB = (EDGE_X - 0.65, EDGE_X + 50.65)          # where the footprint's tab meets the body
EDGE = [(TAB[1], H), (W, H), (W, 0), (0, 0), (0, H), (TAB[0], H)]
ZONES = ("/GND", ("/GND", ("In1.Cu",)), ("/3V3", ("In2.Cu",)))
LOGO_MM = 12
POWER_LED = kg.power_led_at(OUTLINE)


def fpga_pad(pin):
    """Board position of an FPGA pad and its outward direction."""
    import math
    x0, y0, rot = FPGA
    side, k = divmod(int(pin) - 1, 36)   # 0 bottom, 1 right, 2 top, 3 left (unrotated), k along it
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
    p = {"J1": (EDGE_X, H + 4.95, 0), "U1": FPGA}
    for ref, (_, _, pin) in DECOUPLING.items():
        if pin:
            p[ref] = beside(pin)
    # the PLL filter caps sit between these and their pins' neighbours
    p["C11"] = beside(123, along=-0.75)
    p["C8"] = beside(57, along=-0.5)
    p.update({
        "C15": (16, 44, 90), "C16": (66, 44, 90),              # 3V3 bulk: finger entry, right side
        # PLL0 filter (pins 53/54, right side) and PLL1 (126/127, left side)
        "C18": (52.2, 22.5, 270), "C17": (54.9, 22.5, 270), "R6": (54.9, 26.8, 90),
        "C20": (24.1, 22.0, 90), "C19": (16.5, 22.0, 90), "R7": (16.5, 26.0, 90),
        # 33 ohm arrays: A below the FPGA, D and control to its right
        "RN1": (29.0, 40.5, 0), "RN2": (33.6, 40.5, 0), "RN3": (38.2, 40.5, 0), "RN4": (42.8, 40.5, 0),
        "RN5": (58.0, 30.5, 90), "RN6": (58.0, 27.0, 90), "RN7": (58.0, 23.5, 90), "RN8": (58.0, 20.0, 90),
        # config flash and its pull-ups, top right by the config pins, clear
        # of the mounting hole's keep-out
        "U2": (60.0, 9.0, 0), "C23": (60.5, 3.0, 0),
        "R1": (40.0, 4.0, 90), "R2": (44.0, 4.0, 90), "R3": (48.0, 4.0, 90), "R4": (52.0, 4.0, 90),
        "R5": (56.0, 4.0, 90),
        # 1V2 LDO and its rail LED, top left
        "U3": (15.0, 5.0, 0), "C21": (11.0, 5.0, 90), "C22": (19.0, 5.0, 90),
        "D1": (9.5, 12.0, 90), "R9": (12.5, 12.0, 90), "Q1": (9.5, 17.0, 0), "R8": (9.5, 21.5, 0),
        "D2": POWER_LED + (0,), "R10": (POWER_LED[0] + 3.5, POWER_LED[1], 0),
        "H1": (W - 4.0, 4.0, 0),
        "TP1": (2.5, 8.0, 0), "TP2": (2.5, 13.0, 0), "TP3": (2.5, 18.0, 0),
    })
    return p


def main():
    import pcbnew  # noqa: F401 - first, so its start-up noise comes before the step lines
    import logo
    logo.footprint(LOGO_MM)
    out = sys.argv[1] if len(sys.argv) > 1 else None
    # GND poured on both outer layers (zones[0], which the pipeline ties the
    # fingers to and stitches) and as the In1 plane; 3V3 is the In2 plane
    lcsc = kg.pipeline(
        "cpu", schematic, placement(), OUTLINE, out=out, edge=EDGE, card_edge=True, layers=4,
        zones=ZONES, zone_outline=kg.card_zone(OUTLINE, TAB, H + 4.95 - 1.5),
        labels={"D1": "1V2", "D2": "PWR"},
        graphics=[("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, 7.5, 46.0, 0)])
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
