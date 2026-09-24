#!/usr/bin/env python3
"""Generate everything that depends on hw/pins.yaml (E2E-005).

  genpins.py            write the generated files
  genpins.py --check    fail if any generated file is out of date

Generated:
  build/hw/chipset.pcf      iCE40 constraints (chipset), pin numbers where known
  build/hw/cpucard.pcf      iCE40 constraints (CPU card)
  fw/*/pins.h               firmware pin headers
  build/hw/nets.json        signal → net name map for the schematic generator
"""
import argparse
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "build", "hw")
BANNER = "/* Generated from hw/pins.yaml by hw/tools/genpins.py. Do not edit. */"


def load():
    with open(os.path.join(ROOT, "hw", "pins.yaml")) as f:
        return yaml.safe_load(f)


def signals(dev):
    """Flatten a device's groups into (group, signal) pairs."""
    for gname, group in dev.get("groups", {}).items():
        for sig in group["signals"]:
            yield gname, sig


def expand(sig):
    """A signal becomes one name, or name[i] for each bit of a bus."""
    width = sig.get("width", 1)
    if width == 1:
        return [(sig["name"], sig.get("gpio"))]
    gpio = sig.get("gpio")
    out = []
    for i in range(width):
        g = gpio[i] if isinstance(gpio, list) else None
        out.append(("%s[%d]" % (sig["name"], i), g))
    return out


def pcf(dev, name):
    lines = ["# %s constraints, generated from hw/pins.yaml" % name,
             "# Pin numbers are assigned during layout; unassigned pins are listed as TODO."]
    for gname, sig in signals(dev):
        pins = sig.get("pin")
        for i, (sname, _) in enumerate(expand(sig)):
            pin = pins[i] if isinstance(pins, list) else pins
            if pin:
                lines.append("set_io %-16s %s" % (sname, pin))
            else:
                lines.append("# TODO set_io %-16s   (%s)" % (sname, gname))
    return "\n".join(lines) + "\n"


def header(dev, guard):
    lines = [BANNER, "#ifndef %s" % guard, "#define %s" % guard, ""]
    for gname, sig in signals(dev):
        note = sig.get("note")
        if note:
            lines.append("/* %s: %s */" % (gname, note))
        for sname, gpio in expand(sig):
            if gpio is None:
                continue
            macro = "PIN_" + sname.replace("[", "").replace("]", "").upper()
            lines.append("#define %-22s %d" % (macro, gpio))
    lines += ["", "#endif", ""]
    return "\n".join(lines)


def outputs(pins):
    """path → contents for every generated file."""
    devs = pins["devices"]
    files = {
        os.path.join(OUT, "chipset.pcf"): pcf(devs["chipset"], "chipset"),
        os.path.join(OUT, "cpucard.pcf"): pcf(devs["cpu_fpga"], "CPU card"),
        os.path.join(ROOT, "fw", "sysctl", "pins.h"): header(devs["sysctl"], "SYSCTL_PINS_H"),
        os.path.join(ROOT, "fw", "gpu", "pins.h"): header(devs["gpu_mcu"], "GPU_PINS_H"),
        os.path.join(ROOT, "fw", "io", "pins.h"): header(devs["io_mcu"], "IO_PINS_H"),
        os.path.join(ROOT, "fw", "wifi", "pins.h"): header(devs["wifi_mcu"], "WIFI_PINS_H"),
        os.path.join(ROOT, "fw", "storage", "pins.h"): header(devs["storage_mcu"], "STORAGE_PINS_H"),
        os.path.join(ROOT, "fw", "eink", "pins.h"): header(devs["eink_mcu"], "EINK_PINS_H"),
    }
    nets = {}
    for dname, dev in devs.items():
        nets[dname] = {"board": dev["board"], "part": dev["part"],
                       "signals": [s for _, sig in signals(dev) for s, _ in expand(sig)]}
    files[os.path.join(OUT, "nets.json")] = json.dumps(nets, indent=1) + "\n"
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = outputs(load())
    stale = []
    for path, text in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = open(path).read() if os.path.exists(path) else None
        if old == text:
            continue
        if args.check:
            stale.append(os.path.relpath(path, ROOT))
        else:
            with open(path, "w") as f:
                f.write(text)
            print("wrote", os.path.relpath(path, ROOT))
    if stale:
        print("out of date (run hw/tools/genpins.py): " + ", ".join(stale))
        return 1
    if args.check:
        print("generated files are up to date (%d)" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
