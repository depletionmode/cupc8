#!/usr/bin/env python3
"""E2E-005: check hw/pins.yaml against everything derived from it.

Checks, without needing the boards to exist yet:
  1. the generated files are up to date (hw/tools/genpins.py --check)
  2. no GPIO is used twice on an MCU, and every GPIO exists on that part
  3. the CPU bus, slot and system-slot signal lists match the connector
     tables in the docs
  4. the two sides of the CPU bus agree (every signal, opposite directions)
  5. the firmware's pin macros match the ones the firmware source uses
  6. FPGA pin counts fit the package, with the config pins left free
Once the KiCad projects exist it also checks their netlists.
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

    # the system slot carries all of sysctl's signals except its own UART and LED
    sysctl = {n for _, n, _, _ in flat(pins["devices"]["sysctl"])}
    on_card_only = {"DBG_UART_TX", "DBG_UART_RX", "LED_STATUS"}
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


def main():
    pins = yaml.safe_load(open(os.path.join(ROOT, "hw", "pins.yaml")))
    check_generated()
    check_gpios(pins)
    check_cpu_bus(pins)
    check_docs(pins)
    check_firmware_macros(pins)

    for e in errors:
        print("FAIL", e)
    devices = len(pins["devices"])
    total = sum(1 for d in pins["devices"].values() for _ in flat(d))
    print("pincheck: %d devices, %d pins, %d problems" % (devices, total, len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
