#!/usr/bin/env python3
"""HW-MB: the CUPC/8 main board.

The chipset iCE40HX4K with its W25Q32 configuration flash, 512 KB SRAM, the
SST39VF040 ROM, the 12 MHz oscillator, the reset supervisor, USB-C power in
(fuse, TVS, current-limited switch, 3V3 buck, 1V2 LDO) with the CC comparator
power policy, and the sockets: the PCIe x8 CPU socket, the PCIe x4 system
slot and six PCIe x1 I/O slots, with the slot expanders, the programming-port
mux, and the pulls that let the machine run with no system card.

Specs: doc/hardware/{cpu-bus,slot,system-slot,memory-map,power,sysctl,
debugging}.md. The chipset's pins come from hw/pins.yaml (the same file that
generates build/hw/chipset.pcf), so the schematic cannot drift from the FPGA
build. hw/tools/pincheck.py checks the netlist against the docs.

    python3 hw/boards/main.py [outdir]      (default build/hw/main)
"""

import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402
import edgesym  # noqa: E402
import sockets  # noqa: E402

G = kg.GRID

# ------------------------------------------------------------------ parts

# LCSC numbers of the passives (JLC basic parts unless noted)
R0603 = {"0": "C21189", "33": "C23140", "100": "C22775", "1k": "C21190", "2.2k": "C4190", "3k": "C4211",
         "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804", "22k": "C31850", "27k": "C22967",
         "47k": "C25819", "100k": "C25803", "1M": "C22935"}
C0603 = {"100n": "C14663", "1u": "C15849", "4.7u": "C19666", "10u": "C19702"}
FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"


class Spec:
    """One schematic symbol (one unit) and what each pin connects to."""

    def __init__(self, ref, lib, value, fp, lcsc, conns, unit=1, group="misc"):
        self.ref, self.lib, self.value, self.fp, self.lcsc = ref, lib, value, fp, lcsc
        self.conns, self.unit, self.group = conns, unit, group


PARTS = []
_group = ["misc"]


def group(name):
    _group[0] = name


def part(ref, lib, value, fp, lcsc, conns, unit=1):
    PARTS.append(Spec(ref, lib, value, fp, lcsc, conns, unit, _group[0]))


def R(ref, value, a, b, fp=FP_R, lcsc=None):
    part(ref, "Device:R", value, fp, lcsc or R0603[value], {1: a, 2: b})


def C(ref, value, a, b="GND"):
    if value == "22u":
        part(ref, "Device:C", value, "Capacitor_SMD:C_0805_2012Metric", "C45783", {1: a, 2: b})
    else:
        part(ref, "Device:C", value, FP_C, C0603[value], {1: a, 2: b})


def LED(ref, a, k):
    part(ref, "Device:LED", "red", "LED_SMD:LED_0603_1608Metric", "C2286", {"A": a, "K": k})


_tp = [0]


def TP(net):
    _tp[0] += 1
    part("TP%d" % _tp[0], "Connector:TestPoint", net, TP_FP, "", {1: net})


def flag(net):
    part("#FLG%02d" % (len([p for p in PARTS if p.ref.startswith("#FLG")]) + 1), "power:PWR_FLAG",
         "PWR_FLAG", "", "", {1: net})


def load_pins():
    with open(os.path.join(ROOT, "hw", "pins.yaml")) as f:
        return yaml.safe_load(f)


def flat_signals(dev):
    """(name without brackets, pin) for every bit of a device in pins.yaml."""
    for grp in dev["groups"].values():
        for s in grp["signals"]:
            w = s.get("width", 1)
            pins = s["pin"] if isinstance(s["pin"], list) else [s["pin"]]
            for i in range(w):
                yield (s["name"] if w == 1 else "%s%d" % (s["name"], i)), pins[i]


# chipset outputs with 33 ohm at the chipset (cpu-bus.md, slot.md): the FPGA
# pin is on <name>_SRC and the resistor's far side on the bus net
SERIES = ("CPU_nRDY", "CPU_IRQ", "CPU_D", "CPU_nRST", "SPI_SCK", "SPI_MOSI", "SPI_nCS", "BR_MISO")


def far_net(sig):
    """The bus-side net of a chipset signal that has a series resistor."""
    if sig.startswith("SPI_nCS"):
        k = int(sig[len("SPI_nCS"):])
        return "SLOT%d_CS_n" % (k + 1) if k < 6 else "AUX_CS_n"
    return sig


def has_series(sig):
    return any(sig.startswith(s) and (sig[len(s):].isdigit() or sig == s) for s in SERIES)


# iCE40HX4K-TQ144 pins that are not user I/O (KiCad's FPGA_Lattice symbol)
CHIPSET_FIXED = {
    65: "CHIPSET_CDONE", 66: "CHIPSET_nCRESET", 67: "FL0_MOSI", 68: "FL0_MISO", 70: "FL0_SCK",
    71: "FL0_nCS", 72: "+3V3", 108: "+3V3", 109: None, 54: "VCCPLL", 126: "VCCPLL",
    53: "GND", 127: "GND",
}


def slot_net(n, name):
    """Net of an I/O slot contact from its slot.md name (slot n = 1..6)."""
    name = name.split(" ")[0]                        # "PRSNT1_n (GND on main board)"
    return {"+5V": "SLOT%d_5V" % n, "+3V3": "+3V3", "GND": "GND", "PRSNT1_n": "GND",
            "SWCLK": "SLOT%d_SWCLK" % n, "SWDIO": "SLOT%d_SWDIO" % n, "CARD_RST_n": "SLOT%d_RST_n" % n,
            "IRQ_n": "SLOT_nIRQ%d" % (n - 1), "SCK": "SPI_SCK", "MOSI": "SPI_MOSI", "MISO": "SPI_MISO",
            "CS_n": "SLOT%d_CS_n" % n, "PRSNT2_n": "SLOT%d_PRSNT2_n" % n, "PROG_n": "SLOT%d_PROG_n" % n,
            }.get(name, "SLOT%d_%s" % (n, name))            # RSVD_Ax: a test pad


def cpu_net(name):
    """Net of a CPU socket contact from its cpu-bus.md name."""
    fixed = {"+5V": "+5V", "+3V3": "+3V3", "GND": "GND", "PRSNT1_n": "GND", "CRESET_n": "CPUCARD_nCRESET",
             "CDONE": "CPU_CDONE", "CARD_ID0": "CPU_CARD_ID0", "CARD_ID1": "CPU_CARD_ID1", "CPU_CLK": "CPU_CLK",
             "/CPU_RST": "CPU_nRST", "/STB": "CPU_nSTB", "/RDY": "CPU_nRDY", "RW": "CPU_RW", "SYNC": "CPU_SYNC",
             "HALTED": "CPU_HALTED", "WAITING": "CPU_WAITING", "PRSNT2_n": "CPU_PRSNT2_n"}
    if name in fixed:
        return fixed[name]
    if name.startswith("FL1_"):
        return name
    if name.startswith("RSVD"):
        return "CPU_" + name
    for p in ("A", "D", "IRQ", "TMR_EXP"):
        if name.startswith(p) and name[len(p):].isdigit():
            return "CPU_" + name
    raise KeyError(name)


def sys_net(name):
    """Net of a system slot contact from its system-slot.md name."""
    fixed = {"+5V": "+5V", "+3V3": "+3V3", "GND": "GND", "PRSNT1_n": "GND", "SYS_nRST": "nMR",
             "CPUCARD_CDONE": "CPU_CDONE", "PRSNT2_n": "SYS_PRSNT2_n"}
    if name in fixed:
        return fixed[name]
    if name.startswith("RSVD"):
        return "SYS_" + name
    return name


def build_parts():
    PARTS.clear()
    _tp[0] = 0
    pins = load_pins()

    # ---- power in: USB-C sink, fuse, TVS, current-limited switch (power.md)
    group("power")
    part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C power", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         "C165948", {"A4": "VBUS", "A1": "GND", "SH": "GND", "A5": "CC1", "B5": "CC2",
                     "A6": None, "A7": None, "B6": None, "B7": None, "A8": None, "B8": None})
    R("R1", "5.1k", "CC1", "GND")
    R("R2", "5.1k", "CC2", "GND")
    part("U1", "jlc:USBLC6-2SC6", "USBLC6-2SC6", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", "C7519",
         {1: "CC1", 6: "CC1", 3: "CC2", 4: "CC2", 2: "GND", 5: "VBUS_F"})
    part("F1", "Device:Polyfuse", "2A", "Fuse:Fuse_1812_4532Metric", "C20812", {1: "VBUS", 2: "VBUS_F"})
    part("D1", "Device:D_Zener", "SMF5.0A", "Diode_SMD:D_SOD-123F", "C193402", {"K": "VBUS_F", "A": "GND"})   # a unidirectional TVS
    C("C1", "4.7u", "VBUS_F")
    C("C2", "100n", "VBUS_F")
    part("U2", "jlc:SY6280AAC", "SY6280AAC", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BL", "C55136",
         {"IN": "VBUS_F", "EN": "VBUS_F", "GND": "GND", "ISET": "ISET", "OUT": "5V_SYS"})
    R("R3", "4.7k", "ISET", "GND")                  # 6800 / 4.7k = 1.45 A limit
    C("C3", "22u", "5V_SYS")
    C("C4", "22u", "5V_SYS")
    R("R4", "0", "5V_SYS", "+5V", "Resistor_SMD:R_1206_3216Metric", "C17888")     # 5V isolation link

    # ---- 3V3 buck, 1V2 LDO
    part("U3", "jlc:TLV62569DBVR", "TLV62569DBVR", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C141836",
         {"VIN": "5V_SYS", "EN": "5V_SYS", "GND": "GND", "SW": "BUCK_SW", "FB": "BUCK_FB"})
    part("L1", "Device:L", "2.2uH", "jlc:IND-SMD_L3.0-W3.0_FNR30XXS", "C167747", {1: "BUCK_SW", 2: "3V3_BUCK"})
    R("R5", "100k", "3V3_BUCK", "BUCK_FB")          # 0.6 V x (1 + 100k/22k) = 3.33 V
    R("R6", "22k", "BUCK_FB", "GND")
    C("C5", "10u", "5V_SYS")
    C("C6", "100n", "5V_SYS")
    C("C7", "22u", "3V3_BUCK")
    C("C8", "22u", "3V3_BUCK")
    R("R7", "0", "3V3_BUCK", "+3V3", "Resistor_SMD:R_1206_3216Metric", "C17888")  # 3V3 isolation link
    part("U4", "jlc:RT9013-12GB", "RT9013-12GB", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", "C58464",
         {"VIN": "+3V3", "EN": "+3V3", "GND": "GND", "NC": None, "VOUT": "1V2_LDO"})
    C("C9", "1u", "+3V3")
    C("C10", "1u", "1V2_LDO")
    R("R8", "0", "1V2_LDO", "+1V2")                 # 1V2 isolation link

    # ---- rail LEDs (the 1V2 one through a transistor: 1.2 V cannot light an LED)
    R("R9", "2.2k", "+5V", "LED_5V")
    LED("D2", "LED_5V", "GND")
    R("R10", "1k", "+3V3", "LED_3V3")
    LED("D3", "LED_3V3", "GND")
    R("R11", "10k", "+1V2", "Q1_B")
    part("Q1", "Transistor_BJT:MMBT3904", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", "C20526",
         {"B": "Q1_B", "E": "GND", "C": "LED_1V2_K"})
    R("R12", "1k", "+3V3", "LED_1V2_A")
    LED("D4", "LED_1V2_A", "LED_1V2_K")

    # ---- USB-C power policy (sysctl.md): PWR_HI when either CC >= 0.66 V.
    # Only one CC line carries the source's Rp; the other sits at 0 V on its
    # Rd, so the mean of the two is half the active one: compare it with 0.33 V.
    R("R13", "1M", "CC1", "CC_AVG")
    R("R14", "1M", "CC2", "CC_AVG")
    C("C11", "100n", "CC_AVG")
    R("R15", "27k", "+3V3", "CC_REF")               # 3.3 V x 3k / 30k = 0.33 V
    R("R16", "3k", "CC_REF", "GND")
    part("U5", "jlc:TLV7011DBVR", "TLV7011DBVR", "jlc:TSOT-23-5_L2.9-W1.6-P0.95-LS2.8-BL", "C702117",
         {"VCC": "+3V3", "VEE": "GND", "IN+": "CC_AVG", "IN": "CC_REF", "OUT": "PWR_HI"})
    C("C12", "100n", "+3V3")
    for net in ("VBUS_F", "5V_SYS", "+5V", "3V3_BUCK", "+3V3", "1V2_LDO", "+1V2", "CC1", "CC2", "PWR_HI"):
        TP(net)
    for net in ("GND", "+3V3", "+1V2", "VCCPLL"):
        flag(net)

    # ---- reset supervisor and clock
    group("clock")
    part("U6", "jlc:MAX811TEUS+T", "MAX811TEUS", "jlc:SOT-143_L2.9-W1.3-P1.92-LS2.3-BR", "C7272",
         {"VCC": "+3V3", "GND": "GND", "~{MR}": "nMR", "~{RESET}": "nPOR"})
    C("C13", "100n", "+3V3")
    # the switch's two terminals each join a pair of pads; diagonal pads are
    # always on different terminals, whichever way the pairs run
    part("SW1", "jlc:TS-1187A-B-A-B", "RESET", "jlc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5", "C318884",
         {1: "nMR", 4: "GND", 2: None, 3: None})
    part("Y1", "jlc:HSO321S12MHZ3.3V", "12MHz", "jlc:OSC-SMD_4P-L3.2-W2.5-BL_TG-5006CE", "C160457",
         {"~{OE}": "+3V3", "VDD": "+3V3", "GND": "GND", "OUT": "OSC_OUT"})
    C("C14", "100n", "+3V3")
    R("R17", "33", "OSC_OUT", "CLK12")
    R("R18", "33", "OSC_OUT", "CPU_CLK")
    for net in ("CLK12", "CPU_CLK", "nPOR", "nMR"):
        TP(net)

    # ---- chipset
    group("chipset")
    chip = {}
    for sig, pin in flat_signals(pins["devices"]["chipset"]):
        chip[pin] = sig + "_SRC" if has_series(sig) else sig
    for pin, net in CHIPSET_FIXED.items():
        chip[pin] = net
    base = kg.load_symbol("FPGA_Lattice:ICE40HX4K-TQ144")
    unused = {int(n) for u in range(1, 6) for n, p in kg.symbol_pins(base, u).items()
              if chip.get(int(n)) is None and p[3] not in ("VCC", "GND") and not p[3].startswith("VCCIO")}
    fpga_symbol({n for n in unused if n >= 100})
    sym = kg.load_symbol("cupc8_fpga:ICE40HX4K-TQ144")
    for unit in range(1, 6):
        conns = {}
        for num, p in kg.symbol_pins(sym, unit).items():
            name = p[3]
            n = int(num)
            if n in chip:
                conns[num] = chip[n]
            elif name.startswith("VCCIO"):
                conns[num] = "+3V3"
            elif name == "VCC":
                conns[num] = "+1V2"
            elif name == "GND":
                conns[num] = "GND"
            else:
                conns[num] = None                   # NC and unused I/O
        part("U7", "cupc8_fpga:ICE40HX4K-TQ144", "ICE40HX4K-TQ144", "Package_QFP:TQFP-144_20x20mm_P0.5mm",
             "C1521989", conns, unit=unit)
    for i, sig in enumerate(s for s in sorted(set(chip.values()), key=str) if s and s.endswith("_SRC")):
        base = sig[:-4]
        R("R%d" % (20 + i), "33", sig, far_net(base))
    # VCC 1V2: one 100 nF per pin, and bulk; VCCIO: one per pin; PLL filter
    for i, net in enumerate(["+1V2"] * 4 + ["+3V3"] * 10):
        C("C%d" % (20 + i), "100n", net)
    C("C34", "10u", "+1V2")
    C("C35", "10u", "+3V3")
    R("R50", "100", "+1V2", "VCCPLL")
    C("C36", "10u", "VCCPLL")
    C("C37", "100n", "VCCPLL")
    C("C38", "100n", "VCCPLL")
    # configuration: CRESET, CDONE and the flash chip select pulled up, so the
    # chipset boots from its flash with no system card (system-slot.md)
    for i, net in enumerate(("CHIPSET_nCRESET", "CHIPSET_CDONE", "FL0_nCS", "BR_nCS")):
        R("R%d" % (51 + i), "10k", "+3V3", net)
    part("U8", "jlc:W25Q32JVSSIQ_C179173", "W25Q32JVSSIQ", "jlc:SOIC-8_L5.3-W5.3-P1.27-LS8.0-BL", "C179173",
         {"~{CS}": "FL0_nCS", "DO(IO1)": "FL0_MISO", "WP#(IO2)": "+3V3", "GND": "GND", "DI(IO0)": "FL0_MOSI",
          "CLK": "FL0_SCK", "HOLD#orRESET#(IO3)": "+3V3", "VCC": "+3V3"})
    C("C39", "100n", "+3V3")
    # CDONE LED through a transistor, 100k base so CDONE still reads high
    R("R55", "100k", "CHIPSET_CDONE", "Q2_B")
    part("Q2", "Transistor_BJT:MMBT3904", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", "C20526",
         {"B": "Q2_B", "E": "GND", "C": "LED_CDONE_K"})
    R("R56", "1k", "+3V3", "LED_CDONE_A")
    LED("D5", "LED_CDONE_A", "LED_CDONE_K")
    # GPO LEDs D1-D8 of the docs are D11-D18 here
    for i in range(8):
        R("R%d" % (60 + i), "1k", "GPO%d" % i, "LED_GPO%d" % i)
        LED("D%d" % (11 + i), "LED_GPO%d" % i, "GND")
    for net in ("CHIPSET_nCRESET", "CHIPSET_CDONE", "FL0_SCK", "FL0_MOSI", "FL0_MISO", "FL0_nCS",
                "BR_SCK", "BR_MOSI", "BR_MISO", "BR_nCS"):
        TP(net)

    # ---- memory: SRAM (A16-A18 low: 64 KB used, parts.md) and ROM
    group("memory")
    sram = {"A%d" % i: "MEM_A%d" % i for i in range(16)}
    sram.update({"A16": "GND", "A17": "GND", "A18": "GND", "~{WE}": "MEM_nWE", "~{OE}": "MEM_nOE",
                 "~{CS}": "MEM_nCE_RAM", "VDD": "+3V3", "GND": "GND"})
    sram.update({"I/O%d" % i: "MEM_D%d" % i for i in range(8)})
    part("U9", "jlc:IS62WV5128EBLL-45HLI", "IS62WV5128EBLL-45HLI", "jlc:STSOP-32_L8.0-W11.8-P0.50-LS13.4-TL",
         "C1348955", sram)
    C("C40", "100n", "+3V3")
    rom = {"A%d" % i: "MEM_A%d" % i for i in range(19)}
    rom.update({"DQ%d" % i: "MEM_D%d" % i for i in range(8)})
    rom.update({"~{CE}": "MEM_nCE_ROM", "~{OE}": "MEM_nOE", "~{WE}": "MEM_nWE", "VDD": "+3V3", "VSS": "GND"})
    part("U10", "jlc:SST39VF040-70-4I-NHE", "SST39VF040", "jlc:PLCC-32_L14.0-W11.5-P1.27-T", "C645939", rom)
    C("C41", "100n", "+3V3")
    # both chips deselected, and no ROM write, while the chipset configures
    for i, net in enumerate(("MEM_nCE_RAM", "MEM_nCE_ROM", "MEM_nWE")):
        R("R%d" % (70 + i), "10k", "+3V3", net)
    TP("MEM_nCE_RAM")

    # ---- CPU socket (cpu-bus.md)
    group("cpu")
    names = edgesym.pinout("doc/hardware/cpu-bus.md")
    part("J2", "cupc8:CUPC8_CPUSocket", "CPU socket", sockets.SOCKETS["CUPC8_CPUSocket"][0], "C404111",
         {num: cpu_net(n) for num, n in names.items()})
    for i, net in enumerate(("CPU_nSTB", "CPU_nRST", "CPU_PRSNT2_n", "CPU_CARD_ID0", "CPU_CARD_ID1",
                             "CPUCARD_nCRESET", "CPU_CDONE", "FL1_nCS")):
        R("R%d" % (80 + i), "10k", "+3V3", net)
    for i in range(8):                               # weak keepers: a floating bus reads $FF
        R("R%d" % (90 + i), "47k", "+3V3", "CPU_D%d" % i)
    C("C42", "10u", "+5V")
    C("C43", "10u", "+3V3")
    C("C44", "100n", "+3V3")
    for net in ["CPU_nRST", "CPU_CDONE", "CPUCARD_nCRESET", "FL1_SCK", "FL1_MOSI", "FL1_MISO", "FL1_nCS"] + \
            sorted({cpu_net(n) for n in names.values() if n.startswith("RSVD")}):
        TP(net)

    # ---- system slot (system-slot.md)
    group("system")
    names = edgesym.pinout("doc/hardware/system-slot.md")
    part("J3", "cupc8:CUPC8_SystemSlot", "System slot", sockets.SOCKETS["CUPC8_SystemSlot"][0], "C19188869",
         {num: sys_net(n) for num, n in names.items()})
    R("R100", "1k", "+1V2", "V1V2_SENSE")          # sysctl's ADC on the 1V2 rail
    for i, net in enumerate(("MUX_SEL0", "MUX_SEL1", "MUX_SEL2", "SYS_PRSNT2_n")):
        R("R%d" % (101 + i), "10k", "+3V3", net)   # MUX_SEL high: channel 7, nothing
    R("R105", "4.7k", "+3V3", "I2C_SDA")
    R("R106", "4.7k", "+3V3", "I2C_SCL")
    C("C45", "10u", "+3V3")
    C("C46", "100n", "+3V3")
    for net in ["SYS_PRSNT2_n", "I2C_SDA", "I2C_SCL", "PROG_CLK", "PROG_IO", "MUX_SEL0", "MUX_SEL1",
                "MUX_SEL2"] + sorted({sys_net(n) for n in names.values() if n.startswith("RSVD")}):
        TP(net)

    # ---- programming-port mux: one 4051 for SWCLK, one for SWDIO; channel n-1 = slot n
    group("mux")
    for ref, com, pre, cap in (("U11", "PROG_CLK", "MUX_CLK", "C47"), ("U12", "PROG_IO", "MUX_IO", "C48")):
        conns = {"A": com, "S0": "MUX_SEL0", "S1": "MUX_SEL1", "S2": "MUX_SEL2", "~{E}": "GND", "VEE": "GND",
                 "GND": "GND", "VCC": "+3V3", "A6": None, "A7": None}
        conns.update({"A%d" % i: "%s%d" % (pre, i + 1) for i in range(6)})
        part(ref, "jlc:CD74HC4051PWR", "CD74HC4051PWR", "jlc:TSSOP-16_L5.0-W4.4-P0.65-LS6.4-BL", "C352826", conns)
        C(cap, "100n", "+3V3")
    # expanders (sysctl.md): U13 at $20 drives CARD_RST_n / PROG_n, U14 at $21 reads presence
    exp = {"VCC": "+3V3", "GND": "GND", "SCL": "I2C_SCL", "SDA": "I2C_SDA", "~{INT}": None}
    u13 = dict(exp, A0="GND", A1="GND", A2="GND", P06=None, P07=None, P16=None, P17=None)
    u13.update({"P0%d" % i: "SLOT%d_RST_n" % (i + 1) for i in range(6)})
    u13.update({"P1%d" % i: "SLOT%d_PROG_n" % (i + 1) for i in range(6)})
    part("U13", "jlc:TCA9555PWR", "TCA9555PWR", "jlc:TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL", "C465732", u13)
    u14 = dict(exp, A0="+3V3", A1="GND", A2="GND", P06=None, P07=None, P10="CPU_PRSNT2_n",
               P11="CPU_CARD_ID0", P12="CPU_CARD_ID1", P13="PWR_HI", P14=None, P15=None, P16=None, P17=None)
    u14.update({"P0%d" % i: "SLOT%d_PRSNT2_n" % (i + 1) for i in range(6)})
    part("U14", "jlc:TCA9555PWR", "TCA9555PWR", "jlc:TSSOP-24_L7.8-W4.4-P0.65-LS6.4-BL", "C465732", u14)
    C("C49", "100n", "+3V3")
    C("C50", "100n", "+3V3")

    # ---- the shared SPI bus: MISO pulled up so an empty slot reads $FF; aux header (dev 6)
    group("spi")
    R("R107", "47k", "+3V3", "SPI_MISO")
    part("J4", "Connector_Generic:Conn_02x05_Odd_Even", "AUX SPI", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
         "C42431818", {1: "+3V3", 2: "GND", 3: "SPI_SCK", 4: "GND", 5: "SPI_MOSI", 6: "GND", 7: "SPI_MISO",
                       8: "AUX_CS_n", 9: "+5V", 10: "GND"})
    for net in ("SPI_SCK", "SPI_MOSI", "SPI_MISO"):
        TP(net)

    # ---- the six I/O slots (slot.md)
    names = edgesym.pinout("doc/hardware/slot.md")
    for n in range(1, 7):
        group("slot%d" % n)
        b = 100 * (n + 1)
        part("J%d" % (10 + n), "cupc8:CUPC8_Slot", "Slot %d" % n, sockets.SOCKETS["CUPC8_Slot"][0], "C404113",
             {num: slot_net(n, nm) for num, nm in names.items()})
        v = "SLOT%d_5V" % n
        part("F%d" % b, "Device:Polyfuse", "0.75A", "Fuse:Fuse_1206_3216Metric", "C545214", {1: "+5V", 2: v + "_F"})
        R("R%d" % (b + 1), "0", v + "_F", v + "_L", "Resistor_SMD:R_0805_2012Metric", "C17477")
        R("R%d" % (b + 2), "50m", v + "_L", v, "Resistor_SMD:R_1206_3216Metric", "C127691")
        R("R%d" % (b + 3), "4.7k", "+3V3", "SLOT_nIRQ%d" % (n - 1))
        R("R%d" % (b + 4), "10k", "+3V3", "SLOT%d_RST_n" % n)
        R("R%d" % (b + 5), "10k", "+3V3", "SLOT%d_PROG_n" % n)
        R("R%d" % (b + 6), "10k", "+3V3", "SLOT%d_PRSNT2_n" % n)
        R("R%d" % (b + 7), "33", "MUX_CLK%d" % n, "SLOT%d_SWCLK" % n)
        R("R%d" % (b + 8), "33", "MUX_IO%d" % n, "SLOT%d_SWDIO" % n)
        C("C%d" % (b + 1), "10u", v)
        C("C%d" % (b + 2), "100n", v)
        C("C%d" % (b + 3), "100n", "+3V3")
        for net in [v + "_L", v, "SLOT%d_CS_n" % n] + ["SLOT%d_RSVD_A%d" % (n, k) for k in range(1, 6)]:
            TP(net)
    return PARTS


# --------------------------------------------------------------- schematic

FPGA_LIB = os.path.join(ROOT, "hw", "lib", "cupc8_fpga.kicad_sym")
NC_ROOM = 1.6                            # a no-connect cross at a pin's end


def fpga_symbol(unused):
    """hw/lib/cupc8_fpga.kicad_sym: KiCad's ICE40HX4K-TQ144 (its pinout agrees
    with icestorm and pincheck; EasyEDA's symbol for C1521989 has the HX1K's)
    with the `unused` pins that have three-digit numbers made long enough for
    the number and a no-connect cross, as hw/tools/jlcimport.py does for
    imported parts. The body end of each pin stays put."""
    sym = kg.load_symbol("FPGA_Lattice:ICE40HX4K-TQ144")
    sym[1] = kg.Q("ICE40HX4K-TQ144")
    need = kg.text_extent("144")[0] + NC_ROOM
    length = max(3.81, -(-need // 1.27) * 1.27)

    def walk(node):
        for e in node:
            if isinstance(e, list) and e and e[0] == "pin" and int(kg.find1(e, "number")[1]) in unused:
                at, ln = kg.find1(e, "at"), kg.find1(e, "length")
                extra = length - float(ln[1])
                if extra > 1e-6:
                    dx, dy = {0: (-1, 0), 90: (0, -1), 180: (1, 0), 270: (0, 1)}[round(float(at[3])) % 360]
                    at[1], at[2] = round(float(at[1]) + dx * extra, 4), round(float(at[2]) + dy * extra, 4)
                    ln[1] = round(length, 4)
            elif isinstance(e, list):
                walk(e)
    walk(sym)
    text = kg.dump(["kicad_symbol_lib", ["version", 20231120], ["generator", kg.Q("cupc8-main")], sym]) + "\n"
    old = open(FPGA_LIB).read() if os.path.exists(FPGA_LIB) else None
    if text != old:
        with open(FPGA_LIB, "w") as f:
            f.write(text)
    kg._libs.pop("cupc8_fpga", None)

PAPER = "A0"


def _footprint(s):
    return s.fp


def _dry_box(s):
    """The box a part takes with its pins' stubs and labels, placed at (0, 0)."""
    t = kg.Schematic("dry", paper=PAPER)
    p = _add(t, s, (0, 0))
    boxes = [p.extent()] + [kg.seg_box(*w[:4]) for w in t.wires] + [b for b, _, _ in t.labels] + \
            [b for b, _ in t.ncs]
    return kg.union(boxes), p


def _add(sch, s, at):
    fields = {"LCSC": s.lcsc} if s.lcsc else {}
    p = sch.add(s.lib, s.ref, s.value, s.fp, at=at, fields=fields, unit=s.unit)
    for pin, net in s.conns.items():
        if net is None:
            sch.nc(p, pin)
        else:
            sch.connect(p, pin, net)
    left = [n for n in p.pins if n not in p.used]
    if left:
        raise SystemExit("%s unit %d: pins not wired: %s" % (s.ref, s.unit, sorted(left)))
    return p


def _shelf(items, width, gap):
    """Next-fit decreasing-height shelf packing. items: [(w, h, key)].
    Returns ({key: (x, y)}, used width, height)."""
    pos, x, y, row_h, used = {}, 0.0, 0.0, 0.0, 0.0
    for w, h, key in sorted(items, key=lambda t: -t[1]):
        if x > 0 and x + w > width:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        pos[key] = (x, y)
        x += w + gap
        used = max(used, x - gap)
        row_h = max(row_h, h)
    return pos, used, y + row_h


def schematic(path, footprint_libs=("cupc8",)):
    """Each functional group is packed into a block, and the blocks onto the
    sheet, so related parts sit together."""
    parts = build_parts()
    s = kg.Schematic("main", "CUPC/8 main board", paper=PAPER)
    w, h = kg.PAGES[PAPER]
    x0, y0 = kg.FRAME + 5, kg.FRAME + 5
    width, height = w - 2 * kg.FRAME - 10, h - 2 * kg.FRAME - kg.TITLE_BLOCK[1] - 10
    boxes, groups = {}, {}
    for i, spec in enumerate(parts):
        box, _ = _dry_box(spec)
        fw = max(kg.text_extent(spec.ref)[0], kg.text_extent(spec.value)[0]) + 2 * G
        pad = (G, 2.5 * G, fw, 2.5 * G)             # room for the reference and value
        boxes[i] = (box, pad)
        groups.setdefault(spec.group, []).append((box[2] - box[0] + pad[0] + pad[2],
                                                  box[3] - box[1] + pad[1] + pad[3], i))
    blocks = {}
    for g, items in groups.items():
        area = sum(a * b for a, b, _ in items)
        wg = max(max(a for a, _, _ in items), (area * 1.6) ** 0.5)
        pos, bw, bh = _shelf(items, wg, G)
        blocks[g] = (pos, bw, bh)
    where, used, total = _shelf([(bw, bh, g) for g, (pos, bw, bh) in blocks.items()], width, 4 * G)
    if total > height:
        raise SystemExit("schematic: the groups need %.0f mm of %.0f" % (total, height))
    for g, (bx, by) in where.items():
        for i, (px, py) in blocks[g][0].items():
            box, pad = boxes[i]
            x, y = x0 + bx + px, y0 + by + py
            # origin so the padded box's top-left lands at (x, y), on the grid
            ox = round((x + pad[0] - box[0]) / G + 0.5) * G
            oy = round((y + pad[1] - box[1]) / G + 0.5) * G
            _add(s, parts[i], (ox, oy))
    left = s.unconnected()
    if left:
        raise SystemExit("unconnected pins: %s" % left)
    s.write(path, footprint_libs=footprint_libs)


if __name__ == "__main__":
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "hw", "main"))
    os.makedirs(out, exist_ok=True)
    schematic(os.path.join(out, "main.kicad_sch"))
    print("schematic written")
