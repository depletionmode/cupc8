"""What the RP2040 slot cards (GPU and IO) share: the slot, the card's own
3V3, and the RP2040 minimal system from Raspberry Pi's "Hardware design with
RP2040", laid out on the schematic sheet around a fixed origin.

    core(s, gpios)   adds the parts and wires them; `gpios` maps the card's
                     own GPIO numbers to nets (hw/pins.yaml)

Every placed part carries its JLC LCSC number. Passives are JLC basic parts.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
import kicadgen as kg  # noqa: E402

G = kg.GRID
R0402 = "Resistor_SMD:R_0402_1005Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
TESTPAD = "cupc8:TestPad_D1.0mm"

# JLC basic parts, except where noted
LCSC = {
    "100n": "C1525", "1u": "C52923", "33p": "C1562",                 # 0402
    "10u": "C15850", "22u": "C45783",                                  # 0805
    "100u": "C15008",                                                  # 1206, 6.3 V
    "33R": "C25105", "1k": "C11702", "470R": "C25117", "2k2": "C25879", "4k7": "C25900",
    "10k": "C25744", "12k": "C25752", "15k": "C25756", "22k": "C25768", "33k": "C25779",
    "100k": "C25741",
    "27R": "C25100",       # extended: the design guide's 27 ohm (22 ohm is basic, 27 is not)
    "270R": "C25099",      # extended: PicoDVI's TMDS series resistor
}

# The slot (doc/hardware/slot.md)
SLOT_GND = ("B3", "A3", "B5", "A5", "B8", "A8", "B11", "A11", "B12", "A12", "A13", "B14", "A15", "B17", "A17")
SLOT_RSVD = ("A6", "A7", "A9", "A10", "A16")

# RP2040 power pins (QFN-56 numbers)
IOVDD = ("1", "10", "22", "33", "42", "49")
DVDD = ("23", "50")


def passive(s, kind, ref, value, at, rot=0, fp=None, lcsc=None):
    """A resistor or capacitor by value; the LCSC number follows the value
    (0402, and the bulk caps), or is given with another footprint."""
    if fp is None:
        fp = {"R": R0402, "C": C0805 if value in ("10u", "22u") else C1206 if value == "100u" else C0402}[kind]
    return s.add("Device:" + kind, ref, value, fp, at=at, rot=rot, fields={"LCSC": lcsc or LCSC[value]})


def hide_pin_numbers(s, lib_id):
    """Pin numbers off for a symbol whose 2.54 mm pins are too short to show
    them clear of the body or a no-connect cross (the RP2040's GPIO names
    carry the numbers that matter; the crystal is symmetric)."""
    sym = s._symbol(lib_id)
    if not kg.find1(sym, "pin_numbers"):
        sym.insert(2, ["pin_numbers", "hide"])


def two(s, part, a, b):
    s.connect(part, 1, a)
    s.connect(part, 2, b)



# Board coordinates (mm): every I/O card's outline (slot.md, Mechanical),
# the finger tab at the bottom, the connector on the top edge. The power LED
# sits at kg.IO_CARD_PWR_LED with its resistor below it, as on the Wi-Fi
# card; the M3 hole at kg.IO_CARD_HOLE.
BODY, EDGE = kg.IO_CARD_BODY, kg.IO_CARD_EDGE
OUTLINE_PLACEMENT = {"D1": kg.IO_CARD_PWR_LED + (0,),
                     "R4": (kg.IO_CARD_PWR_LED[0], kg.IO_CARD_PWR_LED[1] + 2.5, 0),
                     "H1": kg.IO_CARD_HOLE + (0,)}
POWER_NETS = ("/+5V", "/GND")         # 3V3 and 1V1 reach the RP2040's fine pads: u1_nets()


def core_placement(cx, cy, turn=0):
    """Board positions of the RP2040 and its own parts around it, the chip
    at (cx, cy), turned 0 or 180 degrees: decoupling next to its pins, the
    flash by the QSPI pins, the crystal by XIN/XOUT (unturned: the flash
    above-left, the crystal below)."""
    # The top edge is the crowded one: QSPI (x -2.6..-0.6) fans out up-left,
    # USB_DM/DP (x 1.4, 1.0) straight up, and VREG/ADC (x 1.8..2.6) up-right
    # to a column of caps on the right. DVDD 50's cap sits in that column on
    # the 1V1 net with VREG_VOUT, as on the Pico, since nothing fits above it.
    rel = {
        "U1": (0, 0, 0),
        "C3": (-5.8, -1.6, 0),        # IOVDD 1
        "C4": (-5.2, 3.2, 0),         # IOVDD 10, below the slot pins' fan-out
        "C12": (0.6, 5.4, 270),       # DVDD 23: pad 1 (1V1) to the pin
        "C5": (0.4, 7.6, 270),        # IOVDD 22
        "C6": (5.2, 1.2, 0),          # IOVDD 33
        "C7": (5.2, -2.6, 0),         # IOVDD 42
        "C9": (5.2, -4.4, 0),         # ADC_AVDD 43
        "C11": (5.2, -6.2, 0),        # VREG_VIN 44
        "C14": (5.2, -8.0, 0),        # VREG_VOUT 45
        "C13": (5.2, -9.8, 0),        # DVDD 50
        "C10": (0.3, -5.3, 90),       # USB_VDD 48
        "C8": (0.3, -7.2, 90),        # IOVDD 49
        "U3": (-7.0, -10.0, 90),      # flash
        "C15": (-2.4, -10.0, 90),
        "R1": (-11.5, -10.0, 90),     # BOOTSEL
        "Y1": (-5.0, 8.6, 0),
        "R2": (-1.6, 5.4, 90),        # XOUT
        "C16": (-7.8, 8.6, 90),
        "C17": (-5.0, 11.4, 0),
        "R3": (3.6, 6.0, 90),         # RUN pull-up (boards may move it by the slot)
    }
    if turn == 180:                      # the same arrangement, the chip turned round
        return {r: (cx - x, cy - y, (rot + 180) % 360) for r, (x, y, rot) in rel.items()}
    return {r: (cx + x, cy + y, rot) for r, (x, y, rot) in rel.items()}


# the slot's pins on every RP2040 card (hw/pins.yaml)
SLOT_GPIOS = {2: "SCK_MCU", 3: "MOSI_MCU", 4: "MISO_OUT", 5: "CS_n_MCU", 6: "IRQ_n"}


def u1_nets(gpios, usb):
    """Every net on the RP2040's pins but GND: they leave 0.4 mm pitch pads,
    so they take the "Fine" net class (0.15 mm tracks)."""
    nets = {"3V3", "1V1", "RUN", "SWCLK", "SWDIO", "XIN", "XOUT", "QSPI_SS", "QSPI_SCLK",
            "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3"} | set(SLOT_GPIOS.values()) | {"SCK", "MOSI", "CS_n", "CS_OE"} | set(gpios.values())
    if usb:
        nets |= {"USB_DP", "USB_DM"}
    return tuple(sorted("/" + n for n in nets))


def core(s, gpios, leds=(), usb=False):
    """The shared circuit. Sheet origin: the slot at the left, the RP2040 in
    the middle of an A2 sheet. `gpios` {gpio: net} are the card's own pins
    (the slot pins GPIO2-6 are wired here); every other GPIO is left
    unconnected. `leds`: the card's own LEDs [(net, "red"/"green")]. `usb`: the native
    USB port is used (nets USB_DP, USB_DM). Returns the parts."""
    p = {}
    # ---- the slot
    j1 = p["J1"] = s.add("cupc8:CUPC8_Slot", "J1", "slot", "Connector_PCBEdge:BUS_PCIexpress_x1",
                         at=(30 * G, 40 * G))
    for pin in ("B1", "B2", "A2"):
        s.connect(j1, pin, "+5V")
    for pin in SLOT_GND:
        s.connect(j1, pin, "GND")
    s.connect(j1, "A1", "PRSNT")               # PRSNT1_n joined to PRSNT2_n: a seated card
    s.connect(j1, "B18", "PRSNT")
    for pin in ("B4", "A4"):
        s.connect(j1, pin, "3V3")
    for pin in SLOT_RSVD + ("A18",):           # RSVD, and PROG_n (UART-bootloader cards only)
        s.nc(j1, pin)
    s.connect(j1, "B6", "SWCLK")
    s.connect(j1, "B7", "SWDIO")
    s.connect(j1, "B9", "RUN")                 # CARD_RST_n, open drain on the main board
    s.connect(j1, "B10", "IRQ_n")
    s.connect(j1, "B13", "SCK")
    s.connect(j1, "A14", "CS_n")
    s.connect(j1, "B15", "MOSI")
    s.connect(j1, "B16", "MISO")

    # ---- 3V3 from the slot's +3V3 (power.md: the GPU and IO cards draw well
    # under the slot's 300 mA); 22 uF where it comes onto the card
    p["C2"] = passive(s, "C", "C2", "22u", (44 * G, 14 * G))
    two(s, p["C2"], "3V3", "GND")
    flg = [s.add("power:PWR_FLAG", "#FLG0%d" % (i + 1), "PWR_FLAG", at=((6 + 6 * i) * G, 6 * G)) for i in range(3)]
    for f, net in zip(flg, ("+5V", "GND", "3V3")):   # the regulator's pins are passive; VREG_VOUT drives 1V1
        s.connect(f, 1, net)

    # ---- the RP2040
    hide_pin_numbers(s, "MCU_RaspberryPi:RP2040")
    hide_pin_numbers(s, "Device:Crystal_GND24")
    u1 = p["U1"] = s.add("MCU_RaspberryPi:RP2040", "U1", "RP2040",
                         "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", at=(110 * G, 50 * G),
                         fields={"LCSC": "C2040"})
    for pin in IOVDD + ("43", "44", "48"):     # IOVDD, ADC_AVDD, VREG_VIN, USB_VDD
        s.connect(u1, pin, "3V3")
    for pin in DVDD + ("45",):                 # the core regulator's 1V1 out feeds DVDD
        s.connect(u1, pin, "1V1")
    s.connect(u1, "57", "GND")
    s.connect(u1, "TESTEN", "GND")
    s.connect(u1, "RUN", "RUN")
    s.connect(u1, "SWCLK", "SWCLK")
    s.connect(u1, "SWDIO", "SWDIO")
    s.connect(u1, "XIN", "XIN")
    s.connect(u1, "XOUT", "XOUT")
    for pin, net in (("QSPI_SD0", "QSPI_SD0"), ("QSPI_SD1", "QSPI_SD1"), ("QSPI_SD2", "QSPI_SD2"),
                     ("QSPI_SD3", "QSPI_SD3"), ("QSPI_SCLK", "QSPI_SCLK"), ("~{QSPI_SS}", "QSPI_SS")):
        s.connect(u1, pin, net)
    pins = {**SLOT_GPIOS, **gpios}
    for g in range(30):
        name = "GPIO%d" % g + ({26: "/ADC0", 27: "/ADC1", 28: "/ADC2", 29: "/ADC3"}.get(g, ""))
        if g in pins:
            s.connect(u1, name, pins[g])
        else:
            s.nc(u1, name)
    for pin in ("USB_DP", "USB_DM"):
        if usb:
            s.connect(u1, pin, pin)
        else:
            s.nc(u1, pin)

    # decoupling, per the design guide: 100 nF on each IOVDD, DVDD,
    # ADC_AVDD and USB_VDD pin; 1 uF on VREG_VIN and VREG_VOUT
    x = 70
    for i, (val, net) in enumerate([("100n", "3V3")] * 6 + [("100n", "3V3")] * 2 + [("1u", "3V3")] +
                                   [("100n", "1V1")] * 2 + [("1u", "1V1")]):
        c = p["C%d" % (3 + i)] = passive(s, "C", "C%d" % (3 + i), val, ((x + 5 * i) * G, 14 * G))
        two(s, c, net, "GND")

    # ---- QSPI flash
    u3 = p["U3"] = s.add("Memory_Flash:W25Q16JVSS", "U3", "W25Q16JVSSIQ", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
                         at=(160 * G, 40 * G), fields={"LCSC": "C131025"})
    s.connect(u3, "~{CS}", "QSPI_SS")
    s.connect(u3, "DO/IO_{1}", "QSPI_SD1")
    s.connect(u3, "~{WP}/IO_{2}", "QSPI_SD2")
    s.connect(u3, "DI/IO_{0}", "QSPI_SD0")
    s.connect(u3, "CLK", "QSPI_SCLK")
    s.connect(u3, "~{HOLD}/~{RESET}/IO_{3}", "QSPI_SD3")
    s.connect(u3, "VCC", "3V3")
    s.connect(u3, "GND", "GND")
    p["C15"] = passive(s, "C", "C15", "100n", (176 * G, 40 * G))
    two(s, p["C15"], "3V3", "GND")
    # BOOTSEL: a pad, shorted to GND at power-up for the USB boot ROM (debug only)
    p["R1"] = passive(s, "R", "R1", "1k", (150 * G, 58 * G))
    two(s, p["R1"], "QSPI_SS", "BOOTSEL")

    # ---- 12 MHz crystal X322512MSB4SI: CL = 20 pF, so 2 x (20 - ~3 pF stray)
    # = 34 pF -> 33 pF each side; 1k in XOUT as the design guide (drive level)
    y1 = p["Y1"] = s.add("Device:Crystal_GND24", "Y1", "12MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
                         at=(160 * G, 80 * G), fields={"LCSC": "C9002"})
    s.connect(y1, 1, "XIN")
    s.connect(y1, 3, "XTAL_OUT")
    s.connect(y1, 2, "GND")
    s.connect(y1, 4, "GND")
    p["R2"] = passive(s, "R", "R2", "1k", (150 * G, 72 * G))
    two(s, p["R2"], "XOUT", "XTAL_OUT")
    p["C16"] = passive(s, "C", "C16", "33p", (172 * G, 76 * G))
    p["C17"] = passive(s, "C", "C17", "33p", (180 * G, 76 * G))
    two(s, p["C16"], "XIN", "GND")
    two(s, p["C17"], "XTAL_OUT", "GND")

    # ---- RUN: pulled up here; CARD_RST_n from the main board pulls it low
    p["R3"] = passive(s, "R", "R3", "10k", (150 * G, 90 * G))
    two(s, p["R3"], "3V3", "RUN")

    # Generic KiCad logic graphics leave signal names blank. Annotate the
    # actual TI DCK numeric pins for independent BOM/datasheet checks;
    # numbers, locations, pin electrical types and circuit nets stay exact.
    logic = s._symbol("74xGxx:74LVC1G125")
    names = {"1": "~{OE}", "2": "A", "3": "GND", "4": "Y", "5": "VCC"}
    seen = set()
    for unit in kg.find(logic, "symbol"):
        for pin in kg.find(unit, "pin"):
            number = str(kg.find1(pin, "number")[1])
            if number not in names:
                raise ValueError("unexpected TI125 generic symbol pin " + number)
            kg.find1(pin, "name")[1] = kg.Q(names[number])
            seen.add(number)
    if seen != set(names):
        raise ValueError("TI125 generic symbol numeric pin set changed")
    if not kg.find1(logic, "pin_names"):
        logic.insert(2, ["pin_names", "hide"])
    else:
        kg.find1(logic, "pin_names").append("hide")
    hide_pin_numbers(s, "74xGxx:74LVC1G125")

    # ---- MISO: CS_n isolates the MCU pad while deselected, including reset.
    # The LVC output has220ohm source damping; each card contributes47k bias.
    # The native DCK footprint is retained; exact C7833 supplier CAD/CPL is
    # a separate release requirement, not proven by schematic generation.
    u4 = p["U4"] = s.add("74xGxx:74LVC1G125", "U4", "SN74LVC1G125DCKR", "jlc:SC-70-5_L2.1-W1.3-P0.65-LS2.1-BR",
                         at=(30 * G, 80 * G), fields={"LCSC": "C7833"})
    s.connect(u4, 1, "CS_OE")
    s.connect(u4, 2, "MISO_OUT")
    s.connect(u4, 4, "MISO_SRC")
    p["R60"] = passive(s, "R", "R60", "220", (60 * G, 80 * G), lcsc="C25091")
    two(s, p["R60"], "MISO_SRC", "MISO")
    p["R61"] = passive(s, "R", "R61", "47k", (80 * G, 80 * G), lcsc="C25792")
    two(s, p["R61"], "MISO", "GND")
    s.connect(u4, 5, "3V3")
    s.connect(u4, 3, "GND")
    p["C18"] = passive(s, "C", "C18", "100n", (48 * G, 80 * G))
    two(s, p["C18"], "3V3", "GND")

    # Slot input filters. MISO OE has its own local RC, independent of MCU CS.
    for i, (signal, rref, cref) in enumerate((("SCK", "R62", "C60"),
                                             ("MOSI", "R63", "C61"),
                                             ("CS_n", "R64", "C62"))):
        p[rref] = passive(s, "R", rref, "220", (64 * G, (20 + 18 * i) * G), lcsc="C25091")
        two(s, p[rref], signal, signal + "_MCU")
        p[cref] = passive(s, "C", cref, "10p", (84 * G, (20 + 18 * i) * G), lcsc="C32949")
        two(s, p[cref], signal + "_MCU", "GND")
    p["R65"] = passive(s, "R", "R65", "220", (14 * G, 64 * G), lcsc="C25091")
    two(s, p["R65"], "CS_n", "CS_OE")
    p["C63"] = passive(s, "C", "C63", "10p", (30 * G, 96 * G), lcsc="C32949")
    two(s, p["C63"], "CS_OE", "GND")

    # ---- LEDs (milestone-1.md, Indicator LEDs): the power LED, lit from the
    # card's own 3V3, in the same place on every card; then the card's own
    # (`leds`: [(net, colour)])
    p["R4"] = passive(s, "R", "R4", "1k", (8 * G, 96 * G), fp=R0603, lcsc="C21190")
    p["D1"] = s.add("Device:LED", "D1", "red", LED0603, at=(8 * G, 112 * G), rot=90, fields={"LCSC": "C2286"})
    two(s, p["R4"], "3V3", "LED_PWR")
    s.connect(p["D1"], "A", "LED_PWR")
    s.connect(p["D1"], "K", "GND")
    for i, (net, colour) in enumerate(leds):
        r, d = "R%d" % (5 + i), "D%d" % (2 + i)
        # red KT-0603R (Vf ~2 V) takes 1k from 3V3; green KT-0603G (Vf ~2.9 V) 100R
        red = colour == "red"
        p[r] = passive(s, "R", r, "1k" if red else "100R", ((22 + 14 * i) * G, 96 * G), fp=R0603,
                       lcsc="C21190" if red else "C22775")
        p[d] = s.add("Device:LED", d, colour, LED0603, at=((22 + 14 * i) * G, 118 * G), rot=90,
                     fields={"LCSC": "C2286" if red else "C12624"})
        two(s, p[r], net, net + "_A")
        s.connect(p[d], "A", net + "_A")
        s.connect(p[d], "K", "GND")

    # ---- the M3 mounting hole every I/O card has (slot.md, Mechanical)
    p["H1"] = s.add("Mechanical:MountingHole", "H1", "M3", kg.MOUNTING_HOLE, at=(60 * G, 112 * G))

    # ---- bring-up pads (slot.md: "a BOOTSEL pad and SWD test pads")
    for i, net in enumerate(("BOOTSEL", "SWCLK", "SWDIO", "RUN", "UART_TX", "GND")):
        ref = "TP%d" % (i + 1)
        p[ref] = s.add("Connector:TestPoint", ref, net, TESTPAD, at=((40 + 6 * i) * G, 104 * G))
        s.connect(p[ref], 1, net)
    return p


# JLC: keep every via's drill this far (mm) outside a pad's mask opening (kicadgen.pipeline);
# the RP2040's exposed pad U1.57 is exempt: its thermal via stays in the pad (audit I3, accepted)
PAD_VIA_CLEAR = 0.1


def build(name, schematic, placement, power_nets, graphics, labels, gpios, title, revision, usb=False,
          layers=2, passes=40, preroute=None, seeded_route=None, post_fill=None, designator_reach=None, extra_fine_nets=()):
    """The whole pipeline for an RP2040 card (as hw/boards/wifi.py)."""
    import logo
    for fpid, *_ in graphics:
        if fpid.startswith("cupc8:KaplanLabs_Logo_"):
            logo.footprint(float(fpid.rsplit("_", 1)[1][:-2]))
    def prepare(board):
        miso_launch(board)
        return (preroute or tie_testen)(board)
    lcsc = kg.pipeline(name, schematic, dict(placement, **OUTLINE_PLACEMENT), BODY,
                       out=sys.argv[1] if len(sys.argv) > 1 else None, io_card=True,
                       title=title, revision=revision,
                       power_nets=power_nets, graphics=graphics, layers=layers, labels=labels, passes=passes,
                       fine_nets=tuple(sorted(set(u1_nets(gpios, usb)) | set(extra_fine_nets))), prepare=prepare, route_tries=6, designator_reach=designator_reach,
                       seeded_route=seeded_route,
                       post_fill=post_fill,
                       logo_keepout=True, pad_via_clear=PAD_VIA_CLEAR, pad_via_ok=("U1.57",),
                       # four layers: GND poured on both outer layers, In1 a
                       # solid GND plane; In2 routes signals
                       zones=("/GND", ("/GND", ("In1.Cu",))) if layers == 4 else ("/GND",))
    print("LCSC:", " ".join(sorted(lcsc)))


# ---- hand-laid copper, before Freerouting (kicadgen.pipeline's `preroute`)

def track(board, net, a, b, width=0.2, layer=None):
    """A locked track from a to b (mm) on `net`, top layer unless given."""
    import pcbnew
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
    t.SetWidth(pcbnew.FromMM(width))
    t.SetLayer(pcbnew.F_Cu if layer is None else layer)
    t.SetNet(board.FindNet(net))
    t.SetLocked(True)
    board.Add(t)


def via(board, net, at, size=0.6, drill=0.3):
    import pcbnew
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(at[0]), pcbnew.FromMM(at[1])))
    v.SetWidth(pcbnew.FromMM(size))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetNet(board.FindNet(net))
    v.SetLocked(True)
    board.Add(v)


def pad_at(board, ref, num):
    """(x, y) mm of a pad."""
    import pcbnew
    fp = board.FindFootprintByReference(ref)
    p = [q for q in fp.Pads() if q.GetNumber() == str(num)][0].GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def miso_launch(board, ref="U4", *, oe_net=None):
    """Guard the TI pin map and lock its short source/bias output legs."""
    fp = board.FindFootprintByReference(ref)
    if fp.GetValue() != "SN74LVC1G125DCKR":
        raise ValueError("MISO launch requires the qualified TI LVC pin map")
    if oe_net is not None:
        if ref != "U3" or oe_net != "/CS_OE":
            raise ValueError("explicit OE topology is only the WiFi local filtered branch")
        for part, value, code, nets in (("R68", "220", "C25091", {"1": "/CS_n", "2": "/CS_OE"}),
                                        ("C69", "10p", "C32949", {"1": "/CS_OE", "2": "/GND"})):
            fitted = board.FindFootprintByReference(part)
            if fitted is None or fitted.GetValue() != value or fitted.GetField("LCSC").GetText() != code or {q.GetNumber(): q.GetNetname() for q in fitted.Pads()} != nets:
                raise ValueError("WiFi filtered OE branch part/pin/source identity changed: " + part)
    expected = {"1": (oe_net or "/CS_n") if ref == "U3" else "/CS_OE", "2": "/MISO_INT" if ref == "U3" else "/MISO_OUT",
                "3": "/GND", "4": "/MISO_SRC", "5": "/3V3"}
    actual = {p.GetNumber(): p.GetNetname() for p in fp.Pads()}
    if actual != expected:
        raise ValueError("MISO launch buffer pin map changed")
    for net, first, last in (("/MISO_SRC", (ref, 4), ("R60", 1)),
                             ("/MISO", ("R60", 2), ("R61", 1))):
        a, b = pad_at(board, *first), pad_at(board, *last)
        if abs(a[1] - b[1]) > 1e-5:
            # IO places the new resistors below its nearby IOVDD capacitor.
            if first != ("U4", 4) or math.dist(a, (17.15, -19.1)) > 1e-5 or math.dist(b, (18.49, -20.5)) > 1e-5:
                raise ValueError("MISO launch pad alignment or rotation changed")
            bend = (b[0], a[1])
            track(board, net, a, bend, width=0.2)
            track(board, net, bend, b, width=0.2)
        else:
            track(board, net, a, b, width=0.2)


def tie_testen(board):
    """TESTEN (pin 19) is a test input tied to GND between two signal pins: a track straight
    in from its pad to the exposed GND pad, which the fan-out vias join to
    the pours (nothing else reaches it: the pour can't get between pins)."""
    tx, ty = pad_at(board, "U1", 19)
    cx, cy = pad_at(board, "U1", 57)
    # straight in, across the pad's own axis, to 1.2 mm from the centre
    if abs(tx - cx) > abs(ty - cy):
        end = (cx + math.copysign(1.2, tx - cx), ty)
    else:
        end = (tx, cy + math.copysign(1.2, ty - cy))
    track(board, "/GND", (tx, ty), end)


def escape(board, pin, out, side=0.0, net=None):
    """A Fine-class escape for an RP2040 pin: a track from its pad to a via
    `out` mm from the pad's centre, outwards (negative: inwards, into the
    ring between the pads and the exposed pad, under the chip), `side` mm
    along the chip's edge. The via drops the net to the inner layers."""
    import math
    px, py = pad_at(board, "U1", pin)
    cx, cy = pad_at(board, "U1", 57)
    ux, uy = px - cx, py - cy
    if abs(ux) > abs(uy):                     # the pin's edge: outward unit vector
        ux, uy = math.copysign(1, ux), 0.0
    else:
        ux, uy = 0.0, math.copysign(1, uy)
    vx, vy = px + ux * out - uy * side, py + uy * out + ux * side
    netname = net or board.FindFootprintByReference("U1").FindPadByNumber(str(pin)).GetNetname()
    if side:                                 # out past the pad's end, over by `side` at 45 degrees, on to the via
        pts = [(px, py), (px + ux * 0.75, py + uy * 0.75),
               (px + ux * (0.75 + abs(side)) - uy * side, py + uy * (0.75 + abs(side)) + ux * side), (vx, vy)]
    else:
        pts = [(px, py), (vx, vy)]
    for a, b in zip(pts, pts[1:]):
        track(board, netname, a, b, width=0.15)
    via(board, netname, (vx, vy), size=0.65)


def pocket_escapes(board, swdio=(1.16, 0.0)):
    """The turned cards (GPU, storage): the middle of the chip's top edge,
    between the pins that fan out to the edge connector, has seven pins to
    get out: RUN, SWCLK and IOVDD 22 through vias in the ring under the chip,
    SWDIO, DVDD 23 and XOUT through vias in a row just outside, XIN through
    one a row further out. Freerouting can't find these in a 0.4 mm pitch
    row with the pocket walled in by signal pairs."""
    tie_testen(board)
    for pin in (26, 24, 22):                  # RUN, SWCLK, IOVDD: in
        escape(board, pin, -1.14)
    escape(board, 25, *swdio)                 # SWDIO: out, one row (or where the board says)
    for pin in (23, 21):                      # DVDD, XOUT: out, one row
        escape(board, pin, 1.16)
    escape(board, 20, 2.26, side=0.3)         # XIN: the next row out, clear of XOUT's via


def io_preroute(board):
    """The unturned card (IO): TESTEN in, and DVDD 23 straight down to its
    cap, which Freerouting kept walling in with the SWD fan-out."""
    tie_testen(board)
    (ax, ay), (bx, by) = pad_at(board, "U1", 23), pad_at(board, "C12", 1)
    track(board, "/1V1", (ax, ay), (bx, by), width=0.15)
