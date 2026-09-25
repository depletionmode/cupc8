#!/usr/bin/env python3
"""E2E-005: check hw/pins.yaml against everything derived from it.

Checks, without needing the boards to exist yet:
  1. the generated files are up to date (hw/tools/genpins.py --check)
  2. no GPIO is used twice on an MCU, and every GPIO exists on that part
  3. the CPU bus, slot and system-slot signal lists match the connector
     tables in the docs
  4. the two sides of the CPU bus agree (every signal, opposite directions)
  5. the firmware's pin macros match the ones the firmware source uses
  6. FPGA pin counts fit the package, with the config pins left free, and
     every FPGA pin is a real I/O of the TQ144, unique, clocks on GBIN pins
Once the KiCad projects exist it also checks their netlists:
  7. the main board (build/hw/main/main.net): every socket contact reaches
     what cpu-bus.md, slot.md, system-slot.md and pins.yaml say, and the
     SRAM and ROM pins are on their chipset memory-bus signals
"""
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "doc", "hardware")

# usable I/O per package (Lattice iCE40 datasheet), and RP2040/ESP32-C3 GPIO
IO_BUDGET = {"ICE40HX4K-TQ144": 107, "RP2040": 30, "ESP32-C3-MINI-1U-N4": 22}
RP2040_ADC = {26, 27, 28, 29}
# ESP32-C3 strapping pins: sampled at reset, so nothing driven from outside
# the card may sit on them; only the boot-mode strap belongs on GPIO9
ESP32C3_STRAPS = {2: None, 8: None, 9: "BOOT_STRAP"}

errors = []


def err(msg):
    errors.append(msg)


def flat(dev):
    for gname, group in dev.get("groups", {}).items():
        for sig in group["signals"]:
            width = sig.get("width", 1)
            gpio = sig.get("gpio")
            for i in range(width):
                name = sig["name"] if width == 1 else "%s[%d]" % (sig["name"], i)
                g = gpio[i] if isinstance(gpio, list) else (gpio if width == 1 else None)
                yield gname, name, sig, g


def pinout_table(path):
    """Signal names from a connector pinout table (the one with Pin / Side B /
    Side A columns). Power, ground, key and reserved pins are skipped."""
    names = set()
    in_table = False
    for line in open(os.path.join(DOCS, path)):
        if line.startswith("| Pin |"):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            in_table = False
        if not in_table or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        for cell in cells[1:]:
            cell = cell.split(" ")[0]
            if (cell in ("GND", "+5V", "+3V3", "—", "*key*", "") or
                    cell.startswith("RSVD") or set(cell) <= set("-")):
                continue
            names.add(cell)
    return names


# connector pin name in the docs -> signal name in pins.yaml (any device)
CPU_SOCKET_MAP = {"RW": "CPU_RW", "/STB": "CPU_nSTB", "/RDY": "CPU_nRDY", "SYNC": "CPU_SYNC",
                  "HALTED": "CPU_HALTED", "WAITING": "CPU_WAITING", "CPU_CLK": "CPU_CLK",
                  "/CPU_RST": "CPU_nRST", "FL1_SCK": "FL1_SCK", "FL1_MOSI": "FL1_MOSI",
                  "FL1_MISO": "FL1_MISO", "FL1_nCS": "FL1_nCS", "CRESET_n": "CPUCARD_nCRESET",
                  "CDONE": "CPU_CDONE"}
# CPU socket pins wired to sysctl's expander U1 (or the presence loop), not an FPGA
CPU_SOCKET_EXPANDER = {"PRSNT1_n", "PRSNT2_n", "CARD_ID0", "CARD_ID1"}
for _i in range(16):
    CPU_SOCKET_MAP["A%d" % _i] = "CPU_A[%d]" % _i
for _i in range(8):
    CPU_SOCKET_MAP["D%d" % _i] = "CPU_D[%d]" % _i
for _i in range(4):
    CPU_SOCKET_MAP["IRQ%d" % _i] = "CPU_IRQ[%d]" % _i
for _i in range(2):
    CPU_SOCKET_MAP["TMR_EXP%d" % _i] = "CPU_TMR_EXP[%d]" % _i

# slot pins: the chipset drives the SPI, sysctl drives the programming port,
# and the I2C expanders drive the rest (so those have no FPGA/MCU pin)
SLOT_MAP = {"SCK": "SPI_SCK", "MOSI": "SPI_MOSI", "MISO": "SPI_MISO",
            "CS_n": "SPI_nCS[0]", "IRQ_n": "SLOT_nIRQ[0]",
            "SWCLK": "PROG_CLK", "SWDIO": "PROG_IO"}
SLOT_EXPANDER = {"CARD_RST_n", "PROG_n", "PRSNT1_n", "PRSNT2_n"}


# system slot pins -> sysctl signals (doc/hardware/system-slot.md); the
# presence loop is wired on the connectors only
SYSTEM_SLOT_MAP = {"CC1": "CC1_SENSE", "CC2": "CC2_SENSE"}
for _i in range(3):
    SYSTEM_SLOT_MAP["MUX_SEL%d" % _i] = "MUX_SEL[%d]" % _i
SYSTEM_SLOT_LOOP = {"PRSNT1_n", "PRSNT2_n"}


# iCE40HX4K-TQ144 (icestorm's 8k-tq144:4k): the package's I/O pins, the
# global-buffer inputs, and the I/O shared with configuration (SPI flash)
HX4K_TQ144_IO = {1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28,
                 29, 31, 32, 33, 34, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 52, 55, 56, 60, 61, 62,
                 63, 64, 67, 68, 70, 71, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 90, 91,
                 93, 94, 95, 96, 97, 98, 99, 101, 102, 104, 105, 106, 107, 110, 112, 113, 114, 115, 116,
                 117, 118, 119, 120, 121, 122, 124, 125, 128, 129, 130, 134, 135, 136, 137, 138, 139,
                 141, 142, 143, 144}
HX4K_TQ144_GBIN = {20, 21, 49, 52, 93, 94, 128, 129}
HX4K_TQ144_CONFIG = {67, 68, 70, 71}


def check_fpga_pins(pins):
    """Every FPGA signal has a package pin: a real I/O, not a configuration
    pin, not used twice, and clocks on global-buffer inputs."""
    for dname, dev in pins["devices"].items():
        if not dev["part"].startswith("ICE40"):
            continue
        used = {}
        for gname, sig in dev["groups"].items():
            for s in sig["signals"]:
                p = s.get("pin")
                plist = p if isinstance(p, list) else [p]
                if p is None or len(plist) != s.get("width", 1):
                    err("%s: %s has no pin for every bit" % (dname, s["name"]))
                    continue
                for q in plist:
                    if q not in HX4K_TQ144_IO:
                        err("%s: %s on pin %s, not an I/O of the TQ144" % (dname, s["name"], q))
                    if q in HX4K_TQ144_CONFIG:
                        err("%s: %s on pin %s, a configuration pin" % (dname, s["name"], q))
                    if q in used:
                        err("%s: pin %s used by %s and %s" % (dname, q, used[q], s["name"]))
                    used[q] = s["name"]
                if s.get("role") == "gbin" and plist[0] not in HX4K_TQ144_GBIN:
                    err("%s: clock %s on pin %s, not a global-buffer input" % (dname, s["name"], plist[0]))


def check_generated():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "hw/tools/genpins.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode:
        err("generated files are stale: " + r.stdout.strip())


def check_gpios(pins):
    for dname, dev in pins["devices"].items():
        part = dev["part"]
        used = {}
        for gname, name, sig, gpio in flat(dev):
            if part == "RP2040" and name in ("USB_DP", "USB_DM") and sig.get("pin") != name:
                err("%s: %s must be on the RP2040's dedicated %s pin" % (dname, name, name))
            if gpio is None:
                continue
            if gpio in used:
                err("%s: GPIO %d used by both %s and %s" % (dname, gpio, used[gpio], name))
            used[gpio] = name
            budget = IO_BUDGET.get(part)
            if budget and gpio >= budget:
                err("%s: %s uses GPIO %d, beyond %s" % (dname, name, gpio, part))
            if part == "RP2040" and sig.get("dir") == "adc" and gpio not in RP2040_ADC:
                err("%s: %s is an ADC input but GPIO %d has no ADC" % (dname, name, gpio))
            if part.startswith("ESP32-C3") and gpio in ESP32C3_STRAPS and ESP32C3_STRAPS[gpio] != name:
                err("%s: %s is on GPIO %d, an ESP32-C3 strapping pin" % (dname, name, gpio))
            if part == "RP2040" and name in ("USB_DP", "USB_DM"):
                err("%s: %s is on GPIO %d, but the RP2040's USB port has its own pins" % (dname, name, gpio))
        if part in IO_BUDGET and part.startswith("ICE40"):
            count = sum(1 for _ in flat(dev))
            if count > IO_BUDGET[part] - 6:          # leave the config pins free
                err("%s: %d signals exceeds %s (%d I/O, 6 reserved for configuration)"
                    % (dname, count, part, IO_BUDGET[part]))


def check_cpu_bus(pins):
    chip = {n: s for _, n, s, _ in flat(pins["devices"]["chipset"])
            if _group_is(pins["devices"]["chipset"], n, "cpu_bus")}
    card = {n: s for _, n, s, _ in flat(pins["devices"]["cpu_fpga"])}
    for name in chip:
        if name not in card:
            err("CPU bus: chipset has %s, the CPU card does not" % name)
    for name in card:
        if name in ("CPU_CLK", "CPU_nRST"):
            continue
        if name not in chip:
            err("CPU bus: the CPU card has %s, the chipset does not" % name)
    # directions must be opposite (or both inout)
    for name, sig in chip.items():
        other = card.get(name)
        if not other:
            continue
        a, b = sig.get("dir"), other.get("dir")
        if a == "inout" and b == "inout":
            continue
        if {a, b} != {"in", "out"}:
            err("CPU bus: %s is %s on the chipset and %s on the CPU card" % (name, a, b))


def _group_is(dev, signal_name, group):
    for gname, name, _, _ in flat(dev):
        if name == signal_name:
            return gname == group
    return False


def check_docs(pins):
    """The connector tables in the docs and the pin map must describe the same
    signals."""
    all_names = {n for dev in pins["devices"].values() for _, n, _, _ in flat(dev)}

    for doc_name in pinout_table("cpu-bus.md"):
        if doc_name in CPU_SOCKET_EXPANDER:
            continue
        mapped = CPU_SOCKET_MAP.get(doc_name)
        if mapped is None:
            err("cpu-bus.md pinout lists %s, which the checker does not know" % doc_name)
        elif mapped not in all_names:
            err("cpu-bus.md lists %s (%s), which is not in pins.yaml" % (doc_name, mapped))
    for doc_name, mapped in CPU_SOCKET_MAP.items():
        if doc_name not in pinout_table("cpu-bus.md"):
            err("pins.yaml has %s but the cpu-bus.md pinout does not list %s" % (mapped, doc_name))

    slot_pins = pinout_table("slot.md")
    for doc_name in slot_pins:
        if doc_name in SLOT_EXPANDER:
            continue
        mapped = SLOT_MAP.get(doc_name)
        if mapped is None:
            err("slot.md pinout lists %s, which the checker does not know" % doc_name)
        elif mapped not in all_names:
            err("slot.md lists %s (%s), which is not in pins.yaml" % (doc_name, mapped))
    for doc_name in set(SLOT_MAP) | SLOT_EXPANDER:
        if doc_name not in slot_pins:
            err("the slot.md pinout is missing %s" % doc_name)

    # the system slot carries all of sysctl's signals except its own LEDs
    sysctl = {n for _, n, _, _ in flat(pins["devices"]["sysctl"])}
    on_card_only = {"LED_USB_TX", "LED_USB_RX", "LED_STATUS"}
    listed = set()
    for doc_name in pinout_table("system-slot.md"):
        if doc_name in SYSTEM_SLOT_LOOP:
            continue
        mapped = SYSTEM_SLOT_MAP.get(doc_name, doc_name)
        listed.add(mapped)
        if mapped not in sysctl:
            err("system-slot.md lists %s (%s), which sysctl does not have" % (doc_name, mapped))
    for name in sysctl - on_card_only - listed:
        err("sysctl has %s, but the system-slot.md pinout does not carry it" % name)

    # one chip select and one IRQ line per slot
    chipset = {n for _, n, _, _ in flat(pins["devices"]["chipset"])}
    for i in range(6):
        for sig in ("SPI_nCS[%d]" % i, "SLOT_nIRQ[%d]" % i):
            if sig not in chipset:
                err("the chipset has no %s" % sig)


def check_firmware_macros(pins):
    """Pin macros the firmware uses must come from the generated headers."""
    for dev, hdr in (("gpu_mcu", "fw/gpu/pins.h"), ("io_mcu", "fw/io/pins.h"),
                     ("sysctl", "fw/sysctl/pins.h"), ("wifi_mcu", "fw/wifi/pins.h")):
        path = os.path.join(ROOT, hdr)
        if not os.path.exists(path):
            err("missing generated header %s" % hdr)
            continue
        defined = set(re.findall(r"#define\s+(PIN_\w+)", open(path).read()))
        src_dir = os.path.dirname(path)
        used = set()
        for dirpath, _, names in os.walk(src_dir):
            for n in names:
                if n.endswith((".c", ".h")) and n != "pins.h":
                    used |= set(re.findall(r"\bPIN_\w+", open(os.path.join(dirpath, n)).read()))
        for macro in used - defined:
            err("%s uses %s, which pins.yaml does not define" % (hdr, macro))


# ------------------------------------------------ the main board's netlist

MAINBOARD_NET = os.path.join(ROOT, "build", "hw", "main", "main.net")
# the chipset's configuration pins (iCE40 TQ144), by the system-slot signal on them
CHIPSET_CONFIG = {"FL0_SCK": 70, "FL0_MOSI": 67, "FL0_MISO": 68, "FL0_nCS": 71,
                  "CHIPSET_nCRESET": 66, "CHIPSET_CDONE": 65}


def read_netlist(path):
    """({ref: (lib, part, value)}, {(ref, pin): net}, {(ref, pin): pinfunction})"""
    sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
    import kicadgen as kg
    net = kg.parse(open(path).read())
    comps = {}
    for c in kg.find(kg.find1(net, "components"), "comp"):
        ls = kg.find1(c, "libsource")
        comps[str(kg.find1(c, "ref")[1])] = (str(kg.find1(ls, "lib")[1]), str(kg.find1(ls, "part")[1]),
                                             str(kg.find1(c, "value")[1]))
    pin_net, func = {}, {}
    for n in kg.find(kg.find1(net, "nets"), "net"):
        name = str(kg.find1(n, "name")[1]).lstrip("/")
        for nd in kg.find(n, "node"):
            key = (str(kg.find1(nd, "ref")[1]), str(kg.find1(nd, "pin")[1]))
            pin_net[key] = name
            f = kg.find1(nd, "pinfunction")
            func[key] = str(f[1]) if f else ""
    return comps, pin_net, func


def check_mainboard(pins, path=MAINBOARD_NET):
    """The connectors of the main board (hw/boards/main.py) against the pinout
    docs and pins.yaml: every contact of every socket must reach the part the
    doc and the pin map say, directly or through one series resistor (the
    33 ohm terminations). Returns the number of contacts checked."""
    if not os.path.exists(path):
        print("pincheck: %s not built, main board netlist not checked" % os.path.relpath(path, ROOT))
        return 0
    sys.path.insert(0, os.path.join(ROOT, "hw", "tools"))
    import edgesym
    comps, pin_net, func = read_netlist(path)
    # the system slot socket (C19188869) numbers its pads 1-64 (A1-A32, then
    # B1-B32; hw/boards/sockets.py): name them by contact, as the docs do
    for ref, c in comps.items():
        if c[1] == "CUPC8_SystemSlot_64P11L":
            comps[ref] = (c[0], "CUPC8_SystemSlot", c[2])
            for key in [k for k in pin_net if k[0] == ref]:
                n = int(key[1])
                if n <= 64:
                    new = (ref, "A%d" % n if n <= 32 else "B%d" % (n - 32))
                    pin_net[new], func[new] = pin_net.pop(key), func.pop(key)
    nodes = {}
    for (ref, pin), n in pin_net.items():
        nodes.setdefault(n, []).append((ref, pin))

    # nets joined by a series termination (a resistor of 100 ohm or less) are one signal
    parent = {}

    def root(n):
        while parent.get(n, n) != n:
            n = parent[n]
        return n
    for ref, (lib, part, value) in comps.items():
        if part == "R" and value in ("33", "22", "0"):
            a, b = pin_net.get((ref, "1")), pin_net.get((ref, "2"))
            if a and b and value != "0":
                parent[root(a)] = root(b)

    def same(a, b):
        return a is not None and b is not None and root(a) == root(b)

    def parts_of(part):
        return sorted(r for r, c in comps.items() if c[1] == part)

    def by_func(ref, f):
        # KiCad writes a pin that shares its net with others as NAME_<number>
        hits = [n for (r, p), n in pin_net.items() if r == ref and func[(r, p)] in (f, "%s_%s" % (f, p))]
        return hits[0] if hits else None

    fpga = [r for r, c in comps.items() if c[1].startswith("ICE40HX4K")]
    if len(fpga) != 1:
        err("main board: expected one chipset FPGA, found %s" % fpga)
        return 0
    fpga = fpga[0]
    chip_pin = {}
    for _, name, sig, _ in flat(pins["devices"]["chipset"]):
        width = sig.get("width", 1)
        p = sig["pin"]
        idx = int(name.split("[")[1][:-1]) if "[" in name else 0
        chip_pin[name] = p[idx] if isinstance(p, list) else p

    def chip_net(signal):
        return pin_net.get((fpga, str(chip_pin[signal])))

    expanders = {}
    for r in parts_of("TCA9555PWR"):
        a = (by_func(r, "A2"), by_func(r, "A1"), by_func(r, "A0"))
        addr = 0x20 + sum(4 >> i for i, n in enumerate(a) if n == "+3V3")
        expanders[addr] = r
    muxes = {by_func(r, "A"): r for r in parts_of("CD74HC4051PWR")}
    supervisor = (parts_of("MAX811TEUS+T") or [None])[0]
    usbc = [r for r, c in comps.items() if c[1].startswith(("USB_C_Receptacle", "TYPE-C"))]

    socket = {"CUPC8_CPUSocket": [], "CUPC8_SystemSlot": [], "CUPC8_Slot": []}
    for r, c in comps.items():
        if c[1] in socket:
            socket[c[1]].append(r)
    if len(socket["CUPC8_CPUSocket"]) != 1 or len(socket["CUPC8_SystemSlot"]) != 1 or \
            len(socket["CUPC8_Slot"]) != 6:
        err("main board: sockets %s, expected 1 CPU, 1 system, 6 slots" % socket)
        return 0
    cpu, sysj = socket["CUPC8_CPUSocket"][0], socket["CUPC8_SystemSlot"][0]
    slots = sorted(socket["CUPC8_Slot"], key=lambda r: int(r[1:]))
    docs = {cpu: "doc/hardware/cpu-bus.md", sysj: "doc/hardware/system-slot.md"}
    docs.update({r: "doc/hardware/slot.md" for r in slots})
    sys_pin = {name.split(" ")[0]: num for num, name in edgesym.pinout(docs[sysj]).items()}

    def sys_net(name):
        return pin_net.get((sysj, sys_pin[name]))

    def via_parts(net, target, depth=3):
        """net reaches target through at most `depth` two-pin series parts."""
        seen, front = {net}, {net}
        for _ in range(depth):
            nxt = set()
            for n in front:
                for ref, pin in nodes.get(n, []):
                    if comps.get(ref, ("", "", ""))[1] in ("R", "Polyfuse"):
                        other = pin_net.get((ref, "2" if pin == "1" else "1"))
                        if other and other not in seen:
                            nxt.add(other)
            if target in nxt:
                return True
            seen |= nxt
            front = nxt
        return False

    checked = 0
    for j in [cpu, sysj] + slots:
        n_slot = slots.index(j) if j in slots else None
        for num, doc_name in edgesym.pinout(docs[j]).items():
            name = doc_name.split(" ")[0]
            net = pin_net.get((j, num))
            want, how, ok = None, None, None
            if name in ("GND", "PRSNT1_n"):
                ok = net == "GND"
            elif name == "+3V3":
                ok = net == "+3V3"
            elif name == "+5V":
                ok = net == "+5V" or via_parts(net, "+5V")
            elif name.startswith("RSVD") or (j == sysj and name == "PRSNT2_n"):
                others = [r for r, p in nodes.get(net, []) if r != j]
                allowed = ("TestPoint",) if name.startswith("RSVD") else ("TestPoint", "R")   # PRSNT2_n: a pull-up
                ok = net is not None and all(comps[r][1] in allowed for r in others) and \
                    sum(1 for (r, p) in nodes[net] if r == j) == 1
                how = "a test pad only"
            elif j == cpu:
                if name in CPU_SOCKET_EXPANDER:
                    bit = {"PRSNT2_n": "P10", "CARD_ID0": "P11", "CARD_ID1": "P12"}[name]
                    want, how = by_func(expanders.get(0x21), bit), "expander $21 " + bit
                elif name.startswith("FL1_"):
                    want, how = sys_net(name), "system slot " + name
                elif name == "CRESET_n":
                    want, how = sys_net("CPUCARD_nCRESET"), "system slot CPUCARD_nCRESET"
                elif name == "CPU_CLK":
                    osc = pin_net.get((fpga, str(chip_pin["CLK12"])))
                    ok = net is not None and same_via(net, osc, comps, pin_net)
                    how = "the oscillator, as CLK12"
                else:
                    sig = CPU_SOCKET_MAP[name]
                    want, how = chip_net(sig), "chipset %s (pin %s)" % (sig, chip_pin[sig])
                    if name == "CDONE" and not same(net, sys_net("CPUCARD_CDONE")):
                        err("main board: CPU socket CDONE is not system slot CPUCARD_CDONE")
            elif j == sysj:
                if name in CHIPSET_CONFIG:
                    want, how = pin_net.get((fpga, str(CHIPSET_CONFIG[name]))), "chipset config pin %d" % \
                        CHIPSET_CONFIG[name]
                elif name.startswith("BR_"):
                    want, how = chip_net(name), "chipset %s" % name
                elif name.startswith("FL1_") or name in ("CPUCARD_nCRESET", "CPUCARD_CDONE"):
                    cpu_name = {"CPUCARD_nCRESET": "CRESET_n", "CPUCARD_CDONE": "CDONE"}.get(name, name)
                    cpu_pin = [k for k, v in edgesym.pinout(docs[cpu]).items() if v == cpu_name][0]
                    want, how = pin_net.get((cpu, cpu_pin)), "CPU socket " + cpu_name
                elif name in ("I2C_SDA", "I2C_SCL"):
                    f = name[4:]
                    ok = all(by_func(r, f) == net for r in expanders.values()) and len(expanders) == 2
                    how = "both expanders' " + f
                elif name.startswith("MUX_SEL"):
                    f = "S" + name[-1]
                    ok = all(by_func(r, f) == net for r in muxes.values()) and len(muxes) == 2
                    how = "both muxes' " + f
                elif name in ("PROG_CLK", "PROG_IO"):
                    ok = net in muxes
                    how = "a mux common pin"
                elif name in ("CC1", "CC2"):
                    want = by_func(usbc[0], name) if usbc else None
                    how = "USB-C " + name
                elif name == "SYS_nRST":
                    want, how = by_func(supervisor, "~{MR}"), "the supervisor's manual reset"
                elif name == "V1V2_SENSE":
                    ok, how = via_parts(net, "+1V2", 1), "+1V2 through a resistor"
                else:
                    err("main board: system slot contact %s (%s) is not known to the checker" % (num, name))
                    continue
            else:
                k = n_slot
                if name in SLOT_MAP and name not in ("SWCLK", "SWDIO"):
                    sig = SLOT_MAP[name].replace("[0]", "[%d]" % k)
                    want, how = chip_net(sig), "chipset %s (pin %s)" % (sig, chip_pin[sig])
                elif name in ("SWCLK", "SWDIO"):
                    common = sys_net("PROG_CLK" if name == "SWCLK" else "PROG_IO")
                    mux = muxes.get(common)
                    want, how = (by_func(mux, "A%d" % k) if mux else None), "mux channel %d of %s" % (k, name)
                elif name in ("CARD_RST_n", "PROG_n"):
                    bit = ("P0%d" if name == "CARD_RST_n" else "P1%d") % k
                    want, how = by_func(expanders.get(0x20), bit), "expander $20 " + bit
                elif name == "PRSNT2_n":
                    want, how = by_func(expanders.get(0x21), "P0%d" % k), "expander $21 P0%d" % k
                else:
                    err("main board: slot contact %s (%s) is not known to the checker" % (num, name))
                    continue
            if ok is None:
                ok = same(net, want)
            if not ok:
                err("main board: %s %s (%s) is on %s, should reach %s" % (j, num, name, net, how or name))
            checked += 1

    # the memory bus: every chip pin on its chipset signal
    for chip_ref, dq in [(r, "I/O") for r in parts_of("IS62WV5128EBLL-45HLI")] + \
                        [(r, "DQ") for r in parts_of("SST39VF040-70-4I-NHE")]:
        rom = dq == "DQ"
        for i in range(19):                       # the SRAM has all 19 too (extended RAM)
            if not same(by_func(chip_ref, "A%d" % i), chip_net("MEM_A[%d]" % i)):
                err("main board: %s A%d is not chipset MEM_A[%d]" % (chip_ref, i, i))
        for i in range(8):
            if not same(by_func(chip_ref, "%s%d" % (dq, i)), chip_net("MEM_D[%d]" % i)):
                err("main board: %s %s%d is not chipset MEM_D[%d]" % (chip_ref, dq, i, i))
        for f, sig in (("~{OE}", "MEM_nOE"), ("~{WE}", "MEM_nWE"),
                       ("~{CE}" if rom else "~{CS}", "MEM_nCE_ROM" if rom else "MEM_nCE_RAM")):
            if not same(by_func(chip_ref, f), chip_net(sig)):
                err("main board: %s %s is not chipset %s" % (chip_ref, f, sig))
        checked += 1
    return checked


def same_via(a, b, comps, pin_net):
    """a and b are the two ends of one resistor, or two resistors from a common net."""
    ends = {}
    for (ref, pin), n in pin_net.items():
        if comps.get(ref, ("", "", ""))[1] == "R":
            ends.setdefault(ref, {})[pin] = n
    nbr = lambda x: {v for e in ends.values() if x in e.values() for v in e.values()} - {x}   # noqa: E731
    return b in nbr(a) or bool(nbr(a) & nbr(b))


def main():
    pins = yaml.safe_load(open(os.path.join(ROOT, "hw", "pins.yaml")))
    check_generated()
    check_gpios(pins)
    check_fpga_pins(pins)
    check_cpu_bus(pins)
    check_docs(pins)
    check_firmware_macros(pins)
    contacts = check_mainboard(pins)
    if contacts:
        print("pincheck: main board netlist, %d socket contacts and memory chips checked" % contacts)

    for e in errors:
        print("FAIL", e)
    devices = len(pins["devices"])
    total = sum(1 for d in pins["devices"].values() for _ in flat(d))
    print("pincheck: %d devices, %d pins, %d problems" % (devices, total, len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
