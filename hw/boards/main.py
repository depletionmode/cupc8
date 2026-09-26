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

# The power path, as hw/power/design.py assumes it (power.md, "Assumptions the
# boards must meet"): name -> (value, LCSC). The power scripts can read it here.
POWER = {
    "CC_RD": ("5.1k 1%", "C23186"),                   # R1, R2
    # --- the input: PTC, TVS, eFuse (a 3.0 A source, power.md) ---
    "FUSE_IN": ("3.5A SMD1812P350TF/16", "C46970911"),   # F1
    "TVS": ("SMF5.0A", "C193402"),                    # D1
    "VBUS_C_AHEAD": ("1u", "C15849"),                 # C1: the only capacitance ahead of the eFuse
    "EFUSE": ("TPS259470ARPWR", "C3662799"),          # U2: EN/UVLO from the on/off controller
    # --- the POWER button (David, 2026-09-26): a toggle, always powered from VBUS_F ---
    "ONOFF": ("MAX16054AZT+T", "C79401"),             # U16: debounced toggle, OUT low at power-up
    "STBY_LDO": ("HT7533-2 (30 V in, 2.5 uA)", "C82217"),   # U15: 3V3_STBY for U16, off VBUS_F
    "STBY_LDO_COUT": ("1u", "C15849"),                # C17 (C16 100n at its input)
    "EFUSE_RILM": ("1.13k 1%", "C22833"),             # R3: 3340 / 1.13k -> 2.63 / 2.96 / 3.21 A
    "EFUSE_OVLO_R1": ("37.4k 0.1%", "C326727"),       # R58, IN -> OVLO
    "EFUSE_OVLO_R2": ("10k 0.1%", "C95204"),          # R59, OVLO -> GND
    "EFUSE_DVDT": ("680p", "C107055"),                # C15
    # --- 5V_SYS and the rails ---
    "5V_SYS_BULK": ("22u", "C45783"),                 # C3
    "SLOT_PTC": ("1.1A SMD1206P110TFT", "C143975"),   # F200..F700: 0.80 A per card (slot.md)
    "SLOT_LINK": ("0R 0805, <= 50 mOhm", "C17477"),   # R201.. (each slot's isolation link)
    "BUCK": ("TLV62569PDDCR", "C398365"),             # U3 (THM-001 T2)
    "BUCK_L": ("2.2uH HPC5020NF-2R2M, Isat 4.1 A, DCR 32 mOhm", "C357060"),   # L1
    "BUCK_CIN": ("10u", "C19702"),                    # C5
    "BUCK_COUT": ("22u", "C45783"),                   # C7
    "BUCK_R1": ("453k 0.1%", "C861412"),              # R5
    "BUCK_R2": ("100k 0.1%", "C2912578"),             # R6
    "3V3_DECOUPLING": ("3 x 22u + 100n at each load", "C45783"),   # C35, C43, C45 (~45 uF effective)
    "LDO_COUT": ("1u + 4 x 100n at the iCE40 VCC pins", "C15849"),  # C10, C20-C23
    "CC_AVG_R": ("1M 1%", "C22935"),                  # R13, R14
    "CC_REF_R1": ("41.2k 1%", "C23166"),              # R15: 0.648 V, PWR_HI = a 3.0 A source
    "CC_REF_R2": ("10k 1%", "C25804"),                # R16
}

# LCSC numbers of the passives (JLC basic parts unless noted)
R0603 = {"0": "C21189", "33": "C23140", "100": "C22775", "1k": "C21190", "2.2k": "C4190", "3k": "C4211",
         "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804", "22k": "C31850", "27k": "C22967",
         "47k": "C25819", "100k": "C25803", "1M": "C22935"}
C0603 = {"100n": "C14663", "1u": "C15849", "4.7u": "C19666", "10u": "C19702"}
FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
TP_FP = "cupc8:TestPad_D1.0mm"           # its silk ring 0.3 mm off the pad (KiCad's is 0.14)


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
    71: "FL0_nCS", 72: "+3V3", 108: "+3V3", 109: None, 54: "VCCPLL0", 126: "VCCPLL1",
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
    # JLC's own footprint for C165948 (its pads are what JLC places: bomcheck)
    part("J1", "jlc:TYPE-C-31-M-12", "USB-C power", "jlc:USB-C_SMD-TYPE-C-31-M-12_1", "C165948",
         {"A4B9": "VBUS", "B4A9": "VBUS", "A1B12": "GND", "B1A12": "GND", "1": "GND", "2": "GND", "3": "GND",
          "4": "GND", "A5": "CC1", "B5": "CC2",
          "A6": None, "A7": None, "B6": None, "B7": None, "A8": None, "B8": None})   # power only
    R("R1", "5.1k", "CC1", "GND")
    R("R2", "5.1k", "CC2", "GND")
    part("U1", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", "C7519",
         {1: "CC1", 6: "CC1", 3: "CC2", 4: "CC2", 2: "GND", 5: "VBUS_F"})
    # the input path, all values from POWER (hw/power/design.py decides them)
    # KiCad's 1812 resistor footprint: pads identical to Fuse_1812_4532Metric,
    # which KiCad ships no 3D model for (the render showed bare pads)
    part("F1", "Device:Polyfuse", "3.5A", "Resistor_SMD:R_1812_4532Metric", POWER["FUSE_IN"][1],
         {1: "VBUS", 2: "VBUS_F"})
    part("D1", "Device:D_Zener", "SMF5.0A", "cupc8:D_SOD-123FL", POWER["TVS"][1],
         {"K": "VBUS_F", "A": "GND"})              # a unidirectional TVS
    C("C1", "1u", "VBUS_F")                        # the only capacitance ahead of the eFuse (POW-004)
    part("U2", "jlc:TPS259470ARPWR", "TPS259470ARPWR", "jlc:VQFN-10_L2.0-W2.0-P0.45-TL", POWER["EFUSE"][1],
         {"IN": "VBUS_F", "EN/UVLO": "PWR_EN", "OVLO/OVCSEL": "EFUSE_OVLO", "GND": "GND", "OUT": "5V_SYS",
          "ILM": "EFUSE_ILM", "DVDT": "EFUSE_DVDT", "ITIMER": None,          # open: fastest overcurrent response
          "PG/AUXOFF": None, "~{FLT}/PGTH": None})   # open-drain flags nobody reads
    R("R3", "1.13k", "EFUSE_ILM", "GND", lcsc=POWER["EFUSE_RILM"][1])
    R("R58", "37.4k", "VBUS_F", "EFUSE_OVLO", lcsc=POWER["EFUSE_OVLO_R1"][1])
    R("R59", "10k", "EFUSE_OVLO", "GND", lcsc=POWER["EFUSE_OVLO_R2"][1])
    part("C15", "Device:C", "680p", FP_C, POWER["EFUSE_DVDT"][1], {1: "EFUSE_DVDT", 2: "GND"})
    C("C3", "22u", "5V_SYS")
    R("R4", "0", "5V_SYS", "+5V", "Resistor_SMD:R_1206_3216Metric", "C17888")     # 5V isolation link

    # ---- the POWER button (David, 2026-09-26; power.md, "On/off"): press to
    # turn on, press again to turn off; the machine starts off when USB is
    # plugged in. A MAX16054 toggle (UVLO holds OUT low at power-up) drives the
    # eFuse's EN/UVLO; it runs from its own 3.3 V micropower LDO off VBUS_F
    # (30 V in: the TVS clamp and the OVLO case are both inside it), so it is
    # always powered. Only the MAX16054's 63k pull-up current goes through
    # the button. R44 holds EN low while the LDO comes up.
    part("U15", "jlc:HT7533-2_C82217", "HT7533-2", "jlc:SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR", POWER["STBY_LDO"][1],
         {"VIN": "VBUS_F", "GND": "GND", "VOUT": "3V3_STBY", 4: None, 5: None})     # 4, 5: NC
    C("C16", "100n", "VBUS_F")
    C("C17", "1u", "3V3_STBY")
    part("U16", "jlc:MAX16054AZT+T", "MAX16054AZT", "jlc:TSOT-23-6_L2.9-W1.6-P0.95-LS2.8-TL", POWER["ONOFF"][1],
         {"IN": "PWR_BTN", "GND": "GND", "CLEAR": "GND", "OUT": "PWR_EN", "#OUT": None, "VCC": "3V3_STBY"})
    C("C18", "100n", "3V3_STBY")
    R("R44", "100k", "PWR_EN", "GND")
    part("SW2", "jlc:TS-1187A-B-A-B", "POWER", "jlc:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5", "C318884",
         {1: "PWR_BTN", 4: "GND", 2: None, 3: None})

    # ---- 3V3 buck, 1V2 LDO
    # the DDC package (thermal: THM-001 T2 fails the DBV with slots 4-6 at their 300 mA)
    part("U3", "jlc:TLV62569PDDCR", "TLV62569PDDCR", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", "C398365",
         {"VIN": "5V_SYS", "EN": "5V_SYS", "GND": "GND", "SW": "BUCK_SW", "FB": "BUCK_FB", "PG": None})
    part("L1", "Device:L", "2.2uH", "jlc:IND-SMD_L5.0-W5.0", POWER["BUCK_L"][1],     # Isat 4.1 A, 32 mOhm
         {1: "BUCK_SW", 2: "3V3_BUCK"})
    R("R5", "453k", "3V3_BUCK", "BUCK_FB", lcsc=POWER["BUCK_R1"][1])   # 0.6 V x (1 + 453k/100k) = 3.318 V, 0.1 %
    R("R6", "100k", "BUCK_FB", "GND", lcsc=POWER["BUCK_R2"][1])
    C("C5", "10u", "5V_SYS")
    C("C6", "100n", "5V_SYS")
    C("C7", "22u", "3V3_BUCK")
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

    # ---- USB-C power policy (power.md): PWR_HI when the source is a 3.0 A one.
    # Only one CC line carries the source's Rp; the other sits at 0 V on its
    # Rd, so the mean of the two is half the active one: compare it with 0.648 V.
    R("R13", "1M", "CC1", "CC_AVG")
    R("R14", "1M", "CC2", "CC_AVG")
    C("C11", "100n", "CC_AVG")
    R("R15", "41.2k", "+3V3", "CC_REF", lcsc=POWER["CC_REF_R1"][1])   # 3.3 V x 10k / 51.2k = 0.645 V
    R("R16", "10k", "CC_REF", "GND")
    part("U5", "jlc:TLV7011DBVR", "TLV7011DBVR", "jlc:TSOT-23-5_L2.9-W1.6-P0.95-LS2.8-BL", "C702117",
         {"VCC": "+3V3", "VEE": "GND", "IN+": "CC_AVG", "IN": "CC_REF", "OUT": "PWR_HI"})
    C("C12", "100n", "+3V3")
    for net in ("VBUS_F", "5V_SYS", "+5V", "3V3_BUCK", "+3V3", "1V2_LDO", "+1V2", "CC1", "CC2", "PWR_HI"):
        TP(net)
    for net in ("GND", "+3V3", "+1V2", "VCCPLL0", "VCCPLL1"):
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
    main_symbols({n for n in unused if n >= 100})
    sym = kg.load_symbol("cupc8_main:ICE40HX4K-TQ144")
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
        part("U7", "cupc8_main:ICE40HX4K-TQ144", "ICE40HX4K-TQ144", "jlc:TQFP-144_L20.0-W20.0-P0.50-LS22.0-BL",
             "C1521989", conns, unit=unit)
    for i, sig in enumerate(s for s in sorted(set(chip.values()), key=str) if s and s.endswith("_SRC")):
        base = sig[:-4]
        R("R%d" % (20 + i), "33", sig, far_net(base))
    # VCC 1V2: one 100 nF per pin, and bulk; VCCIO: one per pin; PLL filter
    for i, net in enumerate(["+1V2"] * 4 + ["+3V3"] * 10):
        C("C%d" % (20 + i), "100n", net)
    C("C35", "22u", "+3V3")
    # each PLL supply pin its own 100 ohm / 10 uF + 100 nF filter, beside it
    R("R50", "100", "+1V2", "VCCPLL0")
    C("C36", "10u", "VCCPLL0")
    C("C37", "100n", "VCCPLL0")
    R("R49", "100", "+1V2", "VCCPLL1")
    C("C34", "10u", "VCCPLL1")
    C("C38", "100n", "VCCPLL1")
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
    # the power LED, 3 mm in from the top-left corner like every board's (milestone-1.md)
    R("R57", "1k", "+3V3", "LED_PWR")
    LED("D6", "LED_PWR", "GND")
    # GPO LEDs D1-D8 of the docs are D11-D18 here
    for i in range(8):
        R("R%d" % (60 + i), "1k", "GPO%d" % i, "LED_GPO%d" % i)
        LED("D%d" % (11 + i), "LED_GPO%d" % i, "GND")
    for net in ("CHIPSET_nCRESET", "CHIPSET_CDONE", "FL0_SCK", "FL0_MOSI", "FL0_MISO", "FL0_nCS",
                "BR_SCK", "BR_MOSI", "BR_MISO", "BR_nCS"):
        TP(net)

    # ---- memory: SRAM (all 19 address lines: banked extended RAM, doc/proposals/extended-ram.md
    # option A; in M1 the chipset drives A16-A18 low for RAM cycles) and ROM
    group("memory")
    sram = {"A%d" % i: "MEM_A%d" % i for i in range(16)}
    sram.update({"A16": "MEM_A16", "A17": "MEM_A17", "A18": "MEM_A18", "~{WE}": "MEM_nWE", "~{OE}": "MEM_nOE",
                 "~{CS}": "MEM_nCE_RAM", "VDD": "+3V3", "GND": "GND"})
    sram.update({"I/O%d" % i: "MEM_D%d" % i for i in range(8)})
    part("U9", "jlc:IS62WV5128EBLL-45HLI", "IS62WV5128EBLL-45HLI", "jlc:STSOP-32_L8.0-W11.8-P0.50-LS13.4-TL",
         "C1348955", sram)
    C("C40", "100n", "+3V3")
    rom = {"A%d" % i: "MEM_A%d" % i for i in range(19)}
    rom.update({"DQ%d" % i: "MEM_D%d" % i for i in range(8)})
    rom.update({"~{CE}": "MEM_nCE_ROM", "~{OE}": "MEM_nOE", "~{WE}": "MEM_nWE", "VDD": "+3V3", "VSS": "GND"})
    part("U10", "jlc:SST39VF040-70-4I-NHE", "SST39VF040", "Package_LCC:PLCC-32_11.4x14.0mm_P1.27mm", "C645939", rom)
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
    C("C43", "22u", "+3V3")
    C("C44", "100n", "+3V3")
    for net in ["CPU_nRST", "CPU_CDONE", "CPUCARD_nCRESET", "FL1_SCK", "FL1_MOSI", "FL1_MISO", "FL1_nCS"] + \
            sorted({cpu_net(n) for n in names.values() if n.startswith("RSVD")}):
        TP(net)

    # ---- system slot (system-slot.md)
    group("system")
    names = edgesym.pinout("doc/hardware/system-slot.md")
    conns = {x4_socket_pad(num): sys_net(n) for num, n in names.items()}
    conns["65"] = "GND"                              # the hold-downs
    part("J3", "cupc8_main:" + X4_SOCKET, "System slot", sockets.SOCKETS["CUPC8_SystemSlot"][0], "C19188869",
         conns)
    R("R100", "1k", "+1V2", "V1V2_SENSE")          # sysctl's ADC on the 1V2 rail
    for i, net in enumerate(("MUX_SEL0", "MUX_SEL1", "MUX_SEL2", "SYS_PRSNT2_n")):
        R("R%d" % (101 + i), "10k", "+3V3", net)   # MUX_SEL high: channel 7, nothing
    R("R105", "4.7k", "+3V3", "I2C_SDA")
    R("R106", "4.7k", "+3V3", "I2C_SCL")
    C("C45", "22u", "+3V3")
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
    group("misc")
    for i in range(len(HOLES)):                     # M3, plain: not on any net
        part("H%d" % (i + 1), "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", "", {})

    # ---- the six I/O slots (slot.md)
    names = edgesym.pinout("doc/hardware/slot.md")
    for n in range(1, 7):
        group("slot%d" % n)
        b = 100 * (n + 1)
        part("J%d" % (10 + n), "cupc8:CUPC8_Slot", "Slot %d" % n, sockets.SOCKETS["CUPC8_Slot"][0], "C404113",
             {num: slot_net(n, nm) for num, nm in names.items()})
        v = "SLOT%d_5V" % n
        part("F%d" % b, "Device:Polyfuse", "1.1A", "Fuse:Fuse_1206_3216Metric", POWER["SLOT_PTC"][1],
             {1: "+5V", 2: v + "_F"})
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
    group("power")
    for net in ("3V3_STBY", "PWR_EN"):              # last, so the other pads keep their numbers
        TP(net)
    return PARTS


# --------------------------------------------------------------- schematic

MAIN_LIB = os.path.join(ROOT, "hw", "lib", "cupc8_main.kicad_sym")
NC_ROOM = 1.6                            # a no-connect cross at a pin's end
X4_SOCKET = "CUPC8_SystemSlot_64P11L"


def fpga_symbol(unused):
    """KiCad's ICE40HX4K-TQ144 (its pinout agrees with Lattice's HX4K pinout,
    hw/datasheets/iCE40HX4K-TQ144-pinout.csv; EasyEDA's symbol for C1521989
    has the HX1K's) with the `unused` pins that have three-digit numbers made
    long enough for the number and a no-connect cross, as jlcimport.py does
    for imported parts. The body end of each pin stays put."""
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
    return sym


x4_socket_pad = sockets.x4_pad


def x4_socket_symbol():
    """cupc8:CUPC8_SystemSlot with its pins numbered as the socket's pads
    (sockets.x4_pad), so the board uses JLC's own footprint for the part, and
    pin 65 for the two hold-down pads (GND)."""
    sym = kg.load_symbol("cupc8:CUPC8_SystemSlot")
    sym[1] = kg.Q(X4_SOCKET)
    low = 0.0
    for sub in kg.find(sym, "symbol"):
        sub[1] = kg.Q(X4_SOCKET + str(sub[1])[len("CUPC8_SystemSlot"):])
        for pin in kg.find(sub, "pin"):
            num = kg.find1(pin, "number")
            num[1] = kg.Q(x4_socket_pad(str(num[1])))
            low = min(low, float(kg.find1(pin, "at")[2]))
        for rect in kg.find(sub, "rectangle"):
            low = min(low, float(kg.find1(rect, "end")[2]))
    font = ["effects", ["font", ["size", 1.27, 1.27]]]
    unit1 = [e for e in kg.find(sym, "symbol") if str(e[1]).endswith("_1_1")][0]
    unit1.append(["pin", "passive", "line", ["at", 0, round(low - 2 * G, 2), 90], ["length", 2 * G],
                  ["name", kg.Q("MP"), font], ["number", kg.Q("65"), font]])
    for prop in kg.find(sym, "property"):
        if prop[1] == "Footprint":
            prop[2] = kg.Q(sockets.SOCKETS["CUPC8_SystemSlot"][0])
        elif prop[1] == "Value":
            prop[2] = kg.Q(X4_SOCKET)
        elif prop[1] == "Reference":
            kg.find1(prop, "at")[2] = round(float(kg.find1(prop, "at")[2]), 2)
    return sym


def main_symbols(unused):
    """hw/lib/cupc8_main.kicad_sym: the two symbols only this board uses."""
    text = kg.dump(["kicad_symbol_lib", ["version", 20231120], ["generator", kg.Q("cupc8-main")],
                    fpga_symbol(unused), x4_socket_symbol()]) + "\n"
    old = open(MAIN_LIB).read() if os.path.exists(MAIN_LIB) else None
    if text != old:
        with open(MAIN_LIB, "w") as f:
            f.write(text)
    kg._libs.pop("cupc8_main", None)

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


# ------------------------------------------------------------------ board
#
# Mechanics (doc/hardware/slot.md, "One row of cards"): the CPU socket and
# the six I/O slots lie east-west in one row, 20.32 mm apart, all the same
# way round with contact 1 (finger B1) at x = PIN1_X, so the seven cards,
# which share one outline, stand in line: top edges, M3 holes and LEDs
# aligned. Both sockets are UMAX 3183 parts, one drawing, one height
# (11.25 mm). Each card's component (B) side faces south. The chipset,
# memory and clock sit east of the CPU socket, the slot expanders and mux
# east of the I/O slots. The system slot (its own card, system-slot.md) is
# off the row in the south-east, power in along the south-west edge. The
# LEDs are in one row along the top edge with the power LED (milestone-1.md,
# Indicator LEDs), east of the CPU socket; the reset button and AUX header
# are on the east edge, beyond the cards.

W, H = 125.0, 184.0
OUTLINE = (0, 0, W, H)
PIN1_X = 12.0
ROW_CPU = 12.0
SLOT_PITCH = 20.32
SYS_PIN1_X, ROW_SYS = 66.0, 162.0               # the system slot, off the row


def row_slot(n):
    return ROW_CPU + SLOT_PITCH * n


# LEDs say what they show (kicadgen prints these in place of the designator);
# the GPO LEDs are bits 0-7 of $f000, the POST code
LABELS = {"D2": "5V", "D3": "3V3", "D4": "1V2", "D5": "CDONE", "D6": "PWR"}
LABELS.update({"D%d" % (11 + i): str(i) for i in range(8)})
LABELS.update({"SW2": "POWER", "SW1": "RESET"})        # the front-edge buttons
LABEL_SIDE = {d: "S" for d in LABELS if d != "D6"}   # the LED row's labels south of them (no room north)
LABEL_SIDE.update({"SW1": "N", "SW2": "N"})            # the buttons' north of them (the edge is south)
# the LED row's resistors: designators south, in a row under the labels; the
# two NPNs and their base resistors, west of the row above the CPU socket: north
LABEL_SIDE.update({r: "S" for r in ["R9", "R10", "R12", "R56"] + ["R%d" % (60 + i) for i in range(8)]})
LABEL_SIDE.update({r: "N" for r in ("Q1", "Q2", "R11", "R55")})
LED_X0 = 67.5                                     # the row's first LED after PWR: east of the CPU socket (J2)

FPGA = (97.0, 47.0)                               # centre of U7
LOGO_MM = 12
LOGO_AT = (113.0, 164.0)
TITLE, REVISION = "CUPC/8 main board", "A"
BUTTONS_X = 42.0                                  # POWER; RESET 14 mm east, their controller between
REV_AT = (W - 10.0, H - 1.5)                       # bottom-right of "<title> rev <rev>", clear of H4


def rev_box():
    w, h = _text_w("%s rev %s" % (TITLE, REVISION))
    return (REV_AT[0] - w, REV_AT[1] - h, REV_AT[0], REV_AT[1])
# the row's cards have their M3 hole 52 mm east of contact B1 and 40 mm up
# (slot.md, Mechanical), so all seven line up on x = RAIL_X: a mounting rail
# there carries a standoff per card, on two posts screwed to the board
# between slots 1 and 2 and south of slot 6 (east of the slot channels' parts)
RAIL_X = PIN1_X + kg.IO_CARD_HOLE[0]
RAIL_POSTS = [(RAIL_X, row_slot(1) + SLOT_PITCH / 2), (RAIL_X, row_slot(6) + SLOT_PITCH / 2)]
HOLES = [(4.5, 10.0), (W - 4.5, 4.5), (4.5, H - 4.5), (W - 4.5, H - 4.5), (W - 4.5, 56.0), (W - 4.5, 128.0)] + \
    RAIL_POSTS


def wanted(parts):
    """ref -> (x, y, rot): where each part should go. legalize() then moves
    the small parts to the nearest free spot."""
    import pcbnew
    by_net = {}
    for p in parts:
        for n in set(p.conns.values()):
            if n:
                by_net.setdefault(n, []).append(p.ref)

    def refs(prefix, net):
        return sorted((r for r in by_net.get(net, []) if r.startswith(prefix) and not r.startswith("TP")),
                      key=lambda r: int(r[len(prefix):]))

    def tp(net):
        return [r for r in by_net[net] if r.startswith("TP")][0]

    def pin1_offset(fpid):
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(kg.footprint_dir(lib), name)
        a1 = "1" if fpid == sockets.SOCKETS["CUPC8_SystemSlot"][0] else "A1"    # C19188869 numbers 1-64
        return -pcbnew.ToMM([q for q in fp.Pads() if q.GetNumber() == a1][0].GetPosition().x)

    at = {}
    at["J2"] = (PIN1_X + pin1_offset(sockets.SOCKETS["CUPC8_CPUSocket"][0]), ROW_CPU, 0)
    at["J3"] = (SYS_PIN1_X + pin1_offset(sockets.SOCKETS["CUPC8_SystemSlot"][0]), ROW_SYS, 0)
    for n in range(1, 7):
        at["J%d" % (10 + n)] = (PIN1_X + pin1_offset(sockets.SOCKETS["CUPC8_Slot"][0]), row_slot(n), 0)
    fx, fy = FPGA
    # JLC's TQFP-144 has pin 1 bottom left, pins 1-36 along the bottom; turned
    # a quarter clockwise it is the KiCad/JEDEC view pin_xy() below assumes:
    # pin 1 top left, 1-36 down the left side (the CPU bus, facing the socket)
    at["U7"] = (fx, fy, 270)
    at["U10"] = (88.5, 21.0, 0)                  # ROM, north of the chipset's memory pins
    at["U9"] = (104.5, 24.0, 90)                 # SRAM
    at["J1"] = (30.0, H - 4.58, 0)               # USB-C, opening south: the edge 5.79 mm off the pegs (y -1.21)
    at["J4"] = (116.6, 107.0, 0)                 # AUX SPI header, east edge
    # POWER and RESET side by side on the front (south) edge, between the
    # USB-C inlet and the system slot's pads: in front of every card
    at["SW2"] = (BUTTONS_X, H - 3.4, 0)
    at["SW1"] = (BUTTONS_X + 14.0, H - 3.4, 0)
    at["D6"] = kg.power_led_at(OUTLINE) + (0,)   # the power LED, where every board has it
    at["R57"] = (at["D6"][0] + 4.0, at["D6"][1], 0)
    for i, (x, y) in enumerate(HOLES):
        at["H%d" % (i + 1)] = (x, y, 0)

    # TQFP-144 pad positions around U7, for its decoupling and series parts
    def pin_xy(n, out=0.0):
        d = 10.85 + out
        if n <= 36:
            return fx - d, fy - 8.75 + (n - 1) * 0.5
        if n <= 72:
            return fx - 8.75 + (n - 37) * 0.5, fy + d
        if n <= 108:
            return fx + d, fy + 8.75 - (n - 73) * 0.5
        return fx + 8.75 - (n - 109) * 0.5, fy - d

    def side_rot(n):
        return 90 if n <= 36 or 73 <= n <= 108 else 0

    chip = {}
    for spec in parts:
        if spec.ref == "U7":
            for num, net in spec.conns.items():
                chip.setdefault(net, []).append(int(num))
    decap = {"+1V2": [27, 40, 92, 111], "+3V3": [6, 30, 46, 57, 72, 89, 100, 108, 123, 131]}
    for net, pins_ in decap.items():
        caps = [r for r in refs("C", net) if 20 <= int(r[1:]) <= 33]
        for r, n in zip(caps, pins_):
            # in the corner nearest the pin, where no pins fan out: the planes
            # (In1 GND, In2 3V3) and the pins' own vias carry the current
            x, y = pin_xy(n)
            cx = fx + (13.5 if x > fx else -13.5)
            cy = fy + (13.5 if y > fy else -13.5)
            at[r] = (cx, cy, 45)
    x, y = pin_xy(54, 2.9)
    at["C37"] = (x, y, 0)
    x, y = pin_xy(126, 2.9)
    at["C38"] = (x, y, 0)
    at["R50"] = (fx - 1.0, fy + 17.0, 0)
    at["C36"] = (fx - 1.0, fy + 20.0, 0)
    at["R49"] = (fx + 1.0, fy - 17.0, 0)
    at["C34"] = (fx + 1.0, fy - 20.0, 0)
    at["C35"] = (fx + 16.5, fy - 8.0, 90)
    # series resistors next to their chipset pin, one step further out
    for spec in parts:
        if spec.ref.startswith("R") and 20 <= int(spec.ref[1:]) <= 43:
            src = [n for n in spec.conns.values() if n.endswith("_SRC")][0]
            n = chip[src][0]
            x, y = pin_xy(n, 7.0)
            at[spec.ref] = (x, y, 0 if side_rot(n) == 90 else 90)
    # configuration flash and pulls, below the config pins
    at["U8"] = (104.5, 69.0, 0)
    at["C39"] = (104.5, 74.0, 0)
    for i, r in enumerate(("R51", "R52", "R53", "R54")):
        at[r] = (111.0, 64.0 + 2.2 * i, 0)
    # clock and reset
    at["Y1"] = (78.0, 30.0, 0)
    at["C14"] = (78.0, 26.5, 0)
    at["R17"] = (80.0, 38.0, 0)
    at["R18"] = (72.5, 30.0, 0)
    at["U6"] = (112.0, 141.0, 0)
    at["C13"] = (112.0, 144.5, 0)
    # memory decoupling and pulls
    at["C41"] = (80.0, 17.0, 90)
    at["C40"] = (104.5, 16.5, 0)
    for i, r in enumerate(("R70", "R71", "R72")):
        at[r] = (112.0, 19.0 + 2.2 * i, 0)
    # top edge (milestone-1.md, Indicator LEDs): one row in line with the
    # power LED, east of the CPU socket, where no card stands: 5V, 3V3, 1V2,
    # CDONE, then GPO 7..0 (the POST code, read as a binary number). Each
    # label just south of its LED (LABEL_SIDE), its resistor south of that.
    # The two NPNs (1V2, CDONE) and their base resistors west of the row, in
    # the strip above the CPU socket. Spaced by the labels' widths, so
    # "CDONE" clears its neighbours'.
    row = [("D2", "R9"), ("D3", "R10"), ("D4", "R12"), ("D5", "R56")] + \
        [("D%d" % (11 + i), "R%d" % (60 + i)) for i in reversed(range(8))]
    x, y = LED_X0, at["D6"][1]
    for i, (d, r) in enumerate(row):
        if i:
            x += max(3.6, (_text_w(LABELS[row[i - 1][0]])[0] + _text_w(LABELS[d])[0]) / 2 + 0.8)
        at[d] = (x, y, 0)
        at[r] = (x, y + 4.9, 90)
    for i, ref in enumerate(("R55", "Q2", "R11", "Q1")):
        at[ref] = (LED_X0 - 17.5 + 4.5 * i, y + 1.3, 0)
    # CPU socket channel (between the CPU socket and the system slot)
    cpu_r = ["R%d" % i for i in list(range(80, 88)) + list(range(90, 98))]
    for i, r in enumerate(cpu_r):
        at[r] = (20.0 + 3.7 * i, ROW_CPU + 8.4, 0)
    for i, r in enumerate(("C42", "C43", "C44")):
        at[r] = (8.0 + 3.6 * i, ROW_CPU + 8.6, 0)
    cpu_tp = [tp(n) for n in ("CPU_nRST", "CPU_CDONE", "CPUCARD_nCRESET", "FL1_SCK", "FL1_MOSI", "FL1_MISO",
                              "FL1_nCS")]
    cpu_tp += [tp("CPU_RSVD_A%d" % k) for k in range(2, 9)] + [tp("CPU_RSVD_B1")]
    for i, r in enumerate(cpu_tp):
        at[r] = (8.0 + 4.0 * i, ROW_CPU + 12.6, 0)
    # system slot channel
    sys_parts = ["R100", "R101", "R102", "R103", "R104", "R105", "R106", "C45", "C46"]
    for i, r in enumerate(sys_parts):
        at[r] = (SYS_PIN1_X + 3.8 * i, ROW_SYS + 9.0, 0)
    sys_tp = [tp(n) for n in ("SYS_PRSNT2_n", "I2C_SDA", "I2C_SCL", "PROG_CLK", "PROG_IO", "MUX_SEL0", "MUX_SEL1",
                              "MUX_SEL2", "SYS_RSVD_A1", "SYS_RSVD_A2", "SYS_RSVD_A3", "SYS_RSVD_B1", "SYS_RSVD_B2")]
    for i, r in enumerate(sys_tp):
        at[r] = (SYS_PIN1_X - 4.0 + 4.2 * (i % 11), ROW_SYS + 13.0 + 3.4 * (i // 11), 0)
    for i, net in enumerate(("CHIPSET_nCRESET", "CHIPSET_CDONE", "FL0_SCK", "FL0_MOSI", "FL0_MISO", "FL0_nCS",
                             "BR_SCK", "BR_MOSI", "BR_MISO", "BR_nCS", "MEM_nCE_RAM", "CLK12", "CPU_CLK", "nPOR",
                             "nMR", "SPI_SCK", "SPI_MOSI", "SPI_MISO")):
        at[tp(net)] = (68.5 + 3.5 * (i % 3), 37.8 + 3.2 * (i // 3), 0)
    # each I/O slot: its feed, pulls and pads in the channel south of it
    for n in range(1, 7):
        y0 = row_slot(n)
        b = 100 * (n + 1)
        rowa = ["F%d" % b, "R%d" % (b + 1), "R%d" % (b + 2), "C%d" % (b + 1), "C%d" % (b + 2), "C%d" % (b + 3),
                "R%d" % (b + 7), "R%d" % (b + 8)]
        xs = [7.5, 13.2, 18.8, 24.4, 28.6, 32.8, 37.0, 41.2]
        for r, x in zip(rowa, xs):
            at[r] = (x, y0 + 8.2, 0)
        for i, r in enumerate(["R%d" % (b + k) for k in (3, 4, 5, 6)]):
            at[r] = (6.5 + 4.2 * i, y0 + 12.4, 0)
        pads = [tp("SLOT%d_5V_L" % n), tp("SLOT%d_5V" % n), tp("SLOT%d_CS_n" % n)] + \
               [tp("SLOT%d_RSVD_A%d" % (n, k)) for k in range(1, 6)]
        for i, r in enumerate(pads):
            at[r] = (24.0 + 4.0 * i, y0 + 12.4, 0)
    # slot expanders, programming-port mux and their pulls: east of the slots
    at["U13"] = (74.0, row_slot(1) + 8, 90)
    at["U14"] = (74.0, row_slot(2) + 4, 90)
    at["U11"] = (74.0, row_slot(3) + 2, 90)
    at["U12"] = (74.0, row_slot(4) + 2, 90)
    for r, u in (("C49", "U13"), ("C50", "U14"), ("C47", "U11"), ("C48", "U12")):
        at[r] = (at[u][0] + 6.0, at[u][1], 90)
    at["R107"] = (70.0, row_slot(5), 0)
    # power: south edge, around the USB-C inlet
    y, dx = H - 9.0, -40.0                      # the south-west corner
    power = {"R1": (62.0, y - 2), "R2": (78.0, y - 2), "U1": (70.0, y - 9, 0), "F1": (58.0, y - 9, 90),
             "D1": (53.0, y - 9, 90), "C1": (62.0, y - 14), "U2": (58.0, y - 19),
             "R3": (58.0, y - 23), "R58": (62.5, y - 21), "R59": (62.5, y - 24), "C15": (54.0, y - 24), "C3": (51.0, y - 19, 90),
             "R4": (51.0, y - 27, 0), "U3": (78.0, y - 19, 90), "L1": (84.0, y - 20), "R5": (86.5, y - 15),
             "R6": (86.5, y - 12), "C5": (74.0, y - 19, 90), "C6": (72.0, y - 23), "C7": (89.5, y - 19, 90),
             "R7": (90.0, y - 25), "U4": (98.0, y - 19, 90), "C9": (95.0, y - 13, 0),
             "C10": (101.0, y - 13, 0), "R8": (101.0, y - 25), "R13": (84.0, y - 5), "R14": (84.0, y - 2),
             "C11": (88.0, y - 5), "R15": (91.5, y - 5), "R16": (91.5, y - 2), "U5": (95.0, y - 5, 90),
             "C12": (95.0, y - 8.6)}         # C12 north of U5: the RESET label under it
    for r, v in power.items():
        east = v[0] > 105                       # the LEDs on the east edge stay
        at[r] = (v[0] + (0 if east else dx), v[1], v[2] if len(v) > 2 else 0)
    # the POWER button's controller between the buttons; its LDO, EN's
    # pull-down and their pads in the free corner west of the eFuse
    at["U16"] = (BUTTONS_X + 7.0, H - 3.4, 0)
    at["C18"] = (BUTTONS_X + 7.0, H - 9.6, 0)
    at["U15"] = (6.5, 162.0, 90)
    at["C16"] = (6.5, 158.0, 0)
    at["C17"] = (6.5, 166.0, 0)
    at["R44"] = (6.5, 170.5, 0)
    at[tp("3V3_STBY")] = (11.0, 163.0, 0)
    at[tp("PWR_EN")] = (11.0, 168.0, 0)
    for i, net in enumerate(("VBUS_F", "5V_SYS", "+5V", "3V3_BUCK", "+3V3", "1V2_LDO", "+1V2", "CC1", "CC2",
                             "PWR_HI")):
        at[tp(net)] = (44.0 + 3.8 * (i % 5), y - 26.0 + 3.2 * (i // 5), 0)
    return at


def _box(fp):
    """Courtyard and pads of a placed footprint, mm."""
    import pcbnew
    to = pcbnew.ToMM
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    for p in fp.Pads():
        bb.Merge(p.GetBoundingBox())
    return (to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom()))


_FP_CACHE = {}
_BOARDS = []


def legalize(parts, at, margin=0.35, extra=None):
    """Sockets, the chipset and the memory stay where they are put; every
    other part moves to the nearest spot where its courtyard and pads clear
    everything placed before it (a spiral search)."""
    import math
    import pcbnew
    mm = pcbnew.FromMM
    # the LEDs (one row), the buttons and their controller (the front edge) stay put too
    fixed = ("J", "U7", "U9", "U10", "H", "D", "SW", "U16")
    order = sorted(at, key=lambda r: (not r.startswith(fixed), r))
    fps = {}
    for s in parts:
        if s.fp and s.ref not in fps:
            if s.ref not in _FP_CACHE:
                lib, name = s.fp.split(":")
                _FP_CACHE[s.ref] = pcbnew.FootprintLoad(kg.footprint_dir(lib), name)
            fps[s.ref] = _FP_CACHE[s.ref]
    placed = [rev_box()]
    placed.append((LOGO_AT[0] - LOGO_MM / 2 - 0.5, LOGO_AT[1] - LOGO_MM / 2 - 0.5,
                   LOGO_AT[0] + LOGO_MM / 2 + 0.5, LOGO_AT[1] + LOGO_MM / 2 + 0.5))
    out = {}
    for r in order:
        x, y, rot = at[r]
        fp = fps[r]
        fp.SetOrientationDegrees(rot)
        found = None
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        e = 0.0 if r.startswith(fixed) else (extra or {}).get(r, 0.0)
        b0 = _box(fp)
        b0 = (b0[0] - e, b0[1] - e, b0[2] + e, b0[3] + e)
        for k in range(0, 20000):
            a, rad = k * 0.5, 0.25 * math.sqrt(k)
            dx, dy = rad * math.cos(a), rad * math.sin(a)
            b = (b0[0] + dx, b0[1] + dy, b0[2] + dx, b0[3] + dy)
            if r != "J1" and (b[0] < 0.6 or b[1] < 0.6 or b[2] > W - 0.6 or b[3] > H - 0.6):
                continue
            if any(kg.overlap(b, o, margin) for o in placed):
                continue
            found = (round(x + dx, 3), round(y + dy, 3), rot)
            placed.append(b)
            break
        if found is None or (r.startswith(fixed) and found[:2] != (round(x, 3), round(y, 3))):
            raise SystemExit("%s: no room at (%.1f, %.1f)" % (r, x, y))
        out[r] = found
    return out


def placement():
    """legalize(), then make room wherever kicadgen cannot fit a designator:
    that part gets a wider berth and everything is legalized again."""
    parts = build_parts()
    at = wanted(parts)
    missing = sorted({s.ref for s in parts if s.fp} - set(at))
    if missing:
        raise SystemExit("no placement for: %s" % ", ".join(missing))
    extra = {}
    for _ in range(200):
        pl = legalize(parts, at, extra=extra)
        bad = _designators(parts, pl) or _designators_kicad(parts, pl)
        if not bad:
            return pl
        for r in bad:
            extra[r] = extra.get(r, 0.0) + 0.5
    raise SystemExit("placement: no room for the designators of %s" % ", ".join(bad))


_TEXT_W = {}


def _text_w(text):
    """Width of a designator in kicadgen's silkscreen font (SILK_TEXT)."""
    import pcbnew
    if text not in _TEXT_W:
        t = pcbnew.PCB_TEXT(pcbnew.BOARD())
        t.SetText(text)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(kg.SILK_TEXT[0]), pcbnew.FromMM(kg.SILK_TEXT[0])))
        t.SetTextThickness(pcbnew.FromMM(kg.SILK_TEXT[1]))
        bb = t.GetBoundingBox()
        _TEXT_W[text] = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
    return _TEXT_W[text]


def _designators(parts, pl):
    """kicadgen.place_designators' search, run on the cached footprints: the
    refs that would find no room (all of them, not just the first)."""
    import pcbnew
    to = pcbnew.ToMM

    def box(bb, grow=0.0):
        return (to(bb.GetLeft()) - grow, to(bb.GetTop()) - grow, to(bb.GetRight()) + grow, to(bb.GetBottom()) + grow)
    courts, pads = {}, []
    for ref, (x, y, rot) in pl.items():
        fp = _FP_CACHE[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        courts[ref] = box(cy.BBox()) if cy.OutlineCount() else box(fp.GetBoundingBox(False))
        pads += [box(p.GetBoundingBox(), 0.15) for p in fp.Pads()]
    lx, ly = LOGO_AT
    courts["G1"] = (lx - LOGO_MM / 2, ly - LOGO_MM / 2, lx + LOGO_MM / 2, ly + LOGO_MM / 2)
    courts["REV"] = rev_box()
    x0, y0, x1, y1 = OUTLINE
    inside = (x0 + 0.3, y0 + 0.3, x1 - 0.3, y1 - 0.3)
    placed, bad, gap = [], [], 0.3
    for ref in sorted(pl):
        w, h = _text_w(LABELS.get(ref, ref))
        cx0, cy0, cx1, cy1 = courts[ref]
        mx, my = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        others = [c for r, c in courts.items() if r != ref]
        spots = {"E": [(cx1 + gap + w / 2, my)], "N": [(mx, cy0 - gap - h / 2)],
                 "S": [(mx, cy1 + gap + h / 2)]}.get(LABEL_SIDE.get(ref), [])
        for shift in (0, 1, -1, 2, -2, 3, -3):
            spots += [(mx + shift, cy0 - gap - 0.6), (mx + shift, cy1 + gap + 0.6),
                      (cx0 - gap - 1.5, my + shift), (cx1 + gap + 1.5, my + shift)]
        for sx, sy in spots:
            t = (sx - w / 2, sy - h / 2, sx + w / 2, sy + h / 2)
            if t[0] < inside[0] or t[1] < inside[1] or t[2] > inside[2] or t[3] > inside[3]:
                continue
            if any(kg.overlap(t, o, 0.12) for o in pads + others + placed):
                continue
            placed.append(t)
            break
        else:
            bad.append(ref)
    return bad


def _designators_kicad(parts, pl):
    """The same check with kicadgen's own place_designators, which has the last
    word: [the ref it stops at], or []. The board is kept: freeing a pcbnew
    BOARD breaks later SWIG calls in this process."""
    import re
    import pcbnew
    board = pcbnew.BOARD()
    _BOARDS.append(board)
    seen = set()
    items = [(s.ref, s.fp) for s in parts if s.fp and not (s.ref in seen or seen.add(s.ref))]
    items += [("G%d" % (i + 1), g[0]) for i, g in enumerate(_graphics())]
    where = dict(pl, **{"G%d" % (i + 1): (g[1], g[2], g[3]) for i, g in enumerate(_graphics())})
    for ref, fpid in items:
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(kg.footprint_dir(lib), name)
        fp.SetReference(ref)
        board.Add(fp)
        x, y, rot = where[ref][:3]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientationDegrees(rot)
    try:
        kg.place_designators(board, OUTLINE, labels=LABELS, label_side=LABEL_SIDE)
    except ValueError as e:
        return [re.match(r"(\S+):", str(e)).group(1)]
    return []


def _graphics():
    return [("cupc8:KaplanLabs_Logo_%gmm" % LOGO_MM, LOGO_AT[0], LOGO_AT[1], 0)]


# the nets that carry amps: 0.5 mm tracks (kicadgen's Power class)
POWER_NETS = ("/VBUS", "/+5V", "/SLOT*_5V*", "/3V3_BUCK", "/BUCK_SW")
# the eFuse's input and output: 0.5 mm tracks, but the QFN's pins are
# 0.15-0.19 mm apart, so Fine's clearance (kicadgen FinePower). In the Fine
# class they were routed 0.15 mm wide, 77 mm of them, for 3.5 A.
FINE_POWER_NETS = ("/VBUS_F", "/5V_SYS")
# In1 a solid GND plane; In2 carries signals too (two signal layers leave ~80
# connections unrouted), with a +3V3 pour filled round them after routing
# 6 layers, as the CPU card: F.Cu / In1 GND / In2 / In3 / In4 +3V3 / B.Cu.
# Four signal layers are what the routing needs: with two (4 layers, In1 and
# In2 planes) Freerouting stalled at ~80 unrouted connections; with four
# (4 layers, the pours routed round) it completed, but a +3V3 pour cut up by
# signals left 60 +3V3 pieces unjoined and GND islands round the chipset.
# Solid GND and +3V3 planes, reached by a via at every SMD pad, fix both.
LAYERS = 6
ZONES = ("/GND", ("/GND", ("In1.Cu",)), ("/+3V3", ("In4.Cu",)))
# the nets on fine-pitch pins route at 0.15 mm (kicadgen's Fine class), as on
# the CPU card: at the Default 0.2 mm no track passes between two 0.5 mm-pitch
# pins of the TQ144 or the sTSOP-32
FINE_PARTS = ("U7", "U9", "U2")            # U2: the eFuse's 0.45 mm-pitch QFN
# at most 30 + 60 + 90 passes. On 6 layers try 1 left 4 connections
# (CPU_HALTED, SLOT1_PROG_n, SLOT5_SWDIO, SLOT6_RSVD_A1), try 2 one (MEM_A5)
ROUTE_PASSES, ROUTE_TRIES = 30, 3
ROUTE_TIMEOUT = 90 * 60                    # each Freerouting run's wall-time cap, s (kicadgen route_timeout)
ROUTE_PARALLEL = 8                          # orderings routed at once per try (kicadgen route_parallel)
# the fan-out vias a clearance off their own pads, 0.05 mm further from other
# nets' and clear of the NPTH holes' keep-outs, as Freerouting judges them:
# at KiCad's own margins they were ~117 violations it carried through every
# pass (kicadgen ground_fanout). 4 remain: the eFuse QFN's own pins, 0.15-0.19
# mm apart, which Freerouting holds to 0.2 whatever their class.
FANOUT_MARGIN = 0.05


def fine_nets():
    # the eFuse's VBUS_F and 5V_SYS carry the input current: FINE_POWER_NETS
    power = {"GND", "+3V3", "+1V2", "+5V", "VCCPLL0", "VCCPLL1", "VBUS_F", "5V_SYS"}
    return sorted({"/" + n for s in build_parts() if s.ref in FINE_PARTS for n in s.conns.values()
                   if n and n not in power} | {"unconnected-(U2-*", "/GND"})   # GND: the eFuse QFN GND pad sits 0.18 mm from DVDT


def prepare(board):
    """Before routing: a GND via for the eFuse's pin 8. ground_fanout puts an
    IC's vias under it, which a 2 x 2 mm QFN has no room for, so this one
    goes straight out from the pad, clear of the package."""
    import math
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    fp = board.FindFootprintByReference("U2")
    pad = [p for p in fp.Pads() if p.GetNumber() == "8"][0]
    px, py = to(pad.GetPosition().x), to(pad.GetPosition().y)
    cx, cy = to(fp.GetPosition().x), to(fp.GetPosition().y)
    # out along the pad's own axis (the side it sits on), 1.2 mm past it
    dx, dy = px - cx, py - cy
    ax, ay = (math.copysign(1, dx), 0) if abs(dx) > abs(dy) else (0, math.copysign(1, dy))
    vx, vy = px + 1.2 * ax, py + 1.2 * ay
    net = pad.GetNet()
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pad.GetPosition())
    t.SetEnd(pcbnew.VECTOR2I(mm(vx), mm(vy)))
    t.SetWidth(mm(0.2))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)
    _plane_pads(board)
    nets = _efuse_escapes(board, fp)
    return nets + _standby_preroute(board)


def _standby_preroute(board):
    """Locked copper for the connections the router left open in most runs
    once the POWER button was added: VBUS_F from IN's escape end straight
    across to R58 (the OVLO divider, on the same line); 5V_SYS from OUT's
    escape end west and up to C3 (its bulk capacitor); and the standby
    LDO's VIN (U15 pin 2, between GND and VOUT) up to C16, with a via to
    the inner layers beside C16. Returns the nets (checked on KiCad's
    connectivity after routing)."""
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM

    def pad(ref, num):
        p = [q for q in board.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
        return p, (to(p.GetPosition().x), to(p.GetPosition().y))

    def track(pts, width, net):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
            t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
            t.SetWidth(mm(width))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)
    bar, (bx, by) = pad("U2", "5")
    r58, (rx, ry) = pad("R58", "1")
    top = to(bar.GetBoundingBox().GetTop()) - 0.8          # the escape's end (_efuse_escapes)
    if abs(top - ry) < 0.05 and rx > bx:
        track([(bx, top), (rx, ry)], 0.5, bar.GetNet())
    out, (ox, oy) = pad("U2", "6")
    c3, (qx, qy) = pad("C3", "1")
    bottom = to(out.GetBoundingBox().GetBottom()) + 0.8     # OUT's escape end
    if qx < ox and qy < bottom:
        track([(ox, bottom), (qx, bottom), (qx, qy)], 0.5, out.GetNet())
    vin, (vx, vy) = pad("U15", "2")
    c16, (cx, cy) = pad("C16", "1")
    track([(vx, vy), (vx, cy + 1.2), (cx, cy + 0.4), (cx, cy)], 0.3, vin.GetNet())
    via = (cx - 1.3, cy)
    track([(cx, cy), via], 0.3, vin.GetNet())
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(via[0]), mm(via[1])))
    v.SetWidth(mm(0.6))
    v.SetDrill(mm(0.3))
    v.SetNet(vin.GetNet())
    v.SetLocked(True)
    board.Add(v)
    return [vin.GetNetname()]


def _efuse_escapes(board, fp):
    """The eFuse's IN and OUT bars (pads 5 and 6, 0.19 mm apart) and pin 1
    (EN/UVLO) get locked tracks out past the package, IN's on pin 1's side,
    OUT's the other way. Pin 1 was joined to IN's escape while EN was tied to
    IN; it is PWR_EN now (the POWER button), so its stub stops beside IN's
    and the router takes it from there. Freerouting holds its own pins to 0.2 mm whatever
    their class, so it counts these pins violations and never starts a route
    from them (every run left VBUS_F and 5V_SYS one connection short); it
    joins the tracks' ends instead. Returns the nets, which the pipeline
    then checks with KiCad's connectivity."""
    import math
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    pads = {p.GetNumber(): p for p in fp.Pads()}

    def xy(p):
        return to(p.GetPosition().x), to(p.GetPosition().y)

    def track(a, b, width, net):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        t.SetWidth(mm(width))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)

    def out(bar, toward):
        """The point 0.8 mm past `bar`'s end on `toward`'s side, and the unit step."""
        bb = bar.GetBoundingBox()
        bx, by = xy(bar)
        tx, ty = xy(toward)
        if to(bb.GetWidth()) > to(bb.GetHeight()):
            u = (math.copysign(1, tx - bx), 0.0)
            half = to(bb.GetWidth()) / 2
        else:
            u = (0.0, math.copysign(1, ty - by))
            half = to(bb.GetHeight()) / 2
        return (bx + u[0] * (half + 0.8), by + u[1] * (half + 0.8)), u
    e5, u = out(pads["5"], pads["1"])
    track(xy(pads["5"]), e5, 0.3, pads["5"].GetNet())
    p1 = xy(pads["1"])
    # pin 1 on IN's net (EN tied to IN): straight out to the bar's escape
    # line, then across to its end. On its own net (PWR_EN, the POWER
    # button): out the package's side, away from IN's escape, never joined
    # to it (routed beside IN's escape, 0.4 mm off, it left VBUS_F unrouted
    # in most runs)
    same = pads["1"].GetNetname() == pads["5"].GetNetname()
    if same:
        k = (e5[0] - p1[0]) * u[0] + (e5[1] - p1[1]) * u[1]
        c1 = (p1[0] + u[0] * k, p1[1] + u[1] * k)
        track(p1, c1, 0.25, pads["1"].GetNet())
        track(c1, e5, 0.25, pads["1"].GetNet())
    else:
        cx, cy = xy(fp)
        side = (math.copysign(1, p1[0] - cx), 0.0) if u[0] == 0 else (0.0, math.copysign(1, p1[1] - cy))
        track(p1, (p1[0] + side[0] * 1.1, p1[1] + side[1] * 1.1), 0.2, pads["1"].GetNet())
    e6, _ = out(pads["6"], pads["7"])
    track(xy(pads["6"]), e6, 0.3, pads["6"].GetNet())
    return [pads["5"].GetNetname(), pads["6"].GetNetname()] + ([] if same else [pads["1"].GetNetname()])


PLANE_NETS = ("/GND", "/+3V3")
FINE_PITCH = ("U2", "U7", "U9")


def _plane_pads(board):
    """Every GND and +3V3 pad of the fine-pitch parts reaches its plane by a
    via of its own (ground_fanout's, or one placed here further in under the
    part when the pins around took the near spots), and the outer-layer GND
    pour keeps clear of those pads: between 0.5 mm-pitch pins it could only
    reach one through a sliver (DRC: connection width)."""
    import math
    import pcbnew
    mm, to = pcbnew.FromMM, pcbnew.ToMM
    tracks = board.Tracks()
    items = [tracks[i] for i in range(len(tracks))]
    starts = [(to(t.GetStart().x), to(t.GetStart().y)) for t in items if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [(to(t.GetStart().x), to(t.GetStart().y)) for t in items if t.Type() == pcbnew.PCB_VIA_T]
    # other nets' copper already there: (net, segment or via, half width)
    segs = [(t.GetNetname(), to(t.GetStart().x), to(t.GetStart().y), to(t.GetEnd().x), to(t.GetEnd().y),
             to(t.GetWidth()) / 2 if t.Type() == pcbnew.PCB_TRACE_T else 0.3) for t in items]

    def seg_dist(x, y, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        k = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - ax - k * dx, y - ay - k * dy)

    def clear(net, x, y, r):
        """(x, y) with radius r keeps 0.2 mm from other nets' tracks and vias"""
        return all(n == net or seg_dist(x, y, ax, ay, bx, by) >= r + hw + 0.2 for n, ax, ay, bx, by, hw in segs)
    pads = [(p, fp) for fp in board.GetFootprints() for p in fp.Pads()]
    others = []
    for p, _ in pads:
        bb = p.GetBoundingBox()
        others.append((p.GetNetname(), to(bb.GetLeft()), to(bb.GetTop()), to(bb.GetRight()), to(bb.GetBottom())))
    for ref in FINE_PITCH:
        fp = board.FindFootprintByReference(ref)
        cx, cy = to(fp.GetPosition().x), to(fp.GetPosition().y)
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net not in PLANE_NETS:
                continue
            if net == "/GND":
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_NONE)
            px, py = to(pad.GetPosition().x), to(pad.GetPosition().y)
            if any(math.hypot(px - x, py - y) < 0.05 for x, y in starts):
                continue                            # fanned out already
            # in, under the part, square to the side the pad sits on (along
            # the pad's long axis), so the path runs between its neighbours
            bb = pad.GetBoundingBox()
            if bb.GetHeight() > bb.GetWidth():
                base = math.pi / 2 if cy > py else -math.pi / 2
            elif bb.GetWidth() > bb.GetHeight():
                base = 0.0 if cx > px else math.pi
            else:
                base = math.atan2(cy - py, cx - px)

            def path_clear(pts):
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    for k in range(1, 21):
                        sx, sy = ax + (bx - ax) * k / 20, ay + (by - ay) * k / 20
                        if any(n != net and x0 - 0.3 < sx < x1 + 0.3 and y0 - 0.3 < sy < y1 + 0.3
                               for n, x0, y0, x1, y1 in others) or not clear(net, sx, sy, 0.075):
                            return False
                return True

            # straight in past the pad row (d1), then out to the side at an
            # angle (a dog-leg round the neighbours' vias) to the via
            # in under the part first; failing that out, past the pad's outer end
            found = None
            ext = max(to(pad.GetSize().x), to(pad.GetSize().y)) / 2
            for d1, heading in [(d, base) for d in (1.2, 1.6, 2.0, 2.4)] + \
                               [(d, base + math.pi) for d in (ext + 0.7, ext + 1.1)]:
                kx, ky = px + d1 * math.cos(heading), py + d1 * math.sin(heading)
                for r in (0.0, 0.9, 1.3, 1.8, 2.4, 3.0, 3.8):
                    for da in ((0,) if r == 0 else (0, 45, -45, 90, -90, 30, -30, 60, -60)):
                        a = heading + math.radians(da)
                        vx, vy = kx + r * math.cos(a), ky + r * math.sin(a)
                        if any(math.hypot(vx - x, vy - y) < 0.6 + 0.3 for x, y in vias) or \
                                not clear(net, vx, vy, 0.3):
                            continue
                        if any(n != net and x0 - 0.55 < vx < x1 + 0.55 and y0 - 0.55 < vy < y1 + 0.55
                               for n, x0, y0, x1, y1 in others):
                            continue
                        pts = [(px, py), (kx, ky), (vx, vy)] if r else [(px, py), (kx, ky)]
                        if path_clear(pts):
                            found = pts
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                raise SystemExit("%s pad %s (%s): no room for a via to its plane" % (ref, pad.GetNumber(), net))
            for (ax, ay), (bx, by) in zip(found, found[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
                t.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
                t.SetWidth(mm(0.15))
                t.SetLayer(pcbnew.F_Cu)
                t.SetNet(pad.GetNet())
                t.SetLocked(True)
                board.Add(t)
                segs.append((net, ax, ay, bx, by, 0.075))
            vx, vy = found[-1]
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(mm(vx), mm(vy)))
            v.SetWidth(mm(0.6))
            v.SetDrill(mm(0.3))
            v.SetNet(pad.GetNet())
            v.SetLocked(True)
            board.Add(v)
            vias.append((vx, vy))
            segs.append((net, vx, vy, vx, vy, 0.3))


def main():
    import pcbnew  # noqa: F401 - first, so its start-up noise comes before the step lines
    import logo
    import pincheck
    build_parts()                                   # writes cupc8_main.kicad_sym, which the check reads
    sockets.derive()
    bad = sockets.selftest() + sockets.check()
    if bad:
        raise SystemExit("sockets:\n  " + "\n  ".join(bad))
    print("%-28s ok (card fingers land on their contacts, 3 sockets)" % "socket mating")
    logo.footprint(LOGO_MM)
    pl = placement()
    out = sys.argv[1] if len(sys.argv) > 1 else None
    lcsc = kg.pipeline("main", schematic, pl, OUTLINE, out=out, layers=LAYERS, zones=ZONES,
                       fine_nets=fine_nets(), passes=ROUTE_PASSES, route_tries=ROUTE_TRIES,
                       route_parallel=ROUTE_PARALLEL, route_timeout=ROUTE_TIMEOUT, fanout_margin=FANOUT_MARGIN,
                       prepare=prepare,
                       power_nets=POWER_NETS, fine_power_nets=FINE_POWER_NETS, graphics=_graphics(), labels=LABELS,
                       label_side=LABEL_SIDE,
                       boards=3, title=TITLE, revision=REVISION, revision_at=REV_AT)
    net = os.path.join(os.path.abspath(out or os.path.join(ROOT, "build", "hw", "main")), "main.net")
    n = pincheck.check_mainboard(load_pins(), net)
    if pincheck.errors:
        raise SystemExit("pincheck:\n  " + "\n  ".join(pincheck.errors))
    print("%-28s ok (%d socket contacts and memory chips)" % ("pincheck, main board", n))
    print("LCSC:", " ".join(sorted(lcsc)))


if __name__ == "__main__":
    main()
