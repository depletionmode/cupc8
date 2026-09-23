#!/usr/bin/env python3
"""Generate hw/lib/cupc8.kicad_sym: the card-edge connector symbols, with the
pin names from the pinout tables in the docs, so a schematic shows our
signals and not the PCIe names. The drawing and pin numbers (A1..., B1...)
come from KiCad's Bus_PCI_Express_* symbol with the same contact count,
which also matches KiCad's BUS_PCIexpress_* footprints.

    python3 hw/tools/edgesym.py            write the library
    python3 hw/tools/edgesym.py --check    fail if it is out of date
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import kicadgen as kg  # noqa: E402

OUT = os.path.join(ROOT, "hw", "lib", "cupc8.kicad_sym")

# symbol name: (KiCad base symbol, pinout doc, footprint)
SYMBOLS = {
    "CUPC8_Slot": ("Bus_PCI_Express_x1", "doc/hardware/slot.md", "Connector_PCBEdge:BUS_PCIexpress_x1"),
    "CUPC8_SystemSlot": ("Bus_PCI_Express_x4", "doc/hardware/system-slot.md", "Connector_PCBEdge:BUS_PCIexpress_x4"),
    "CUPC8_CPUSocket": ("Bus_PCI_Express_x8", "doc/hardware/cpu-bus.md", "Connector_PCBEdge:BUS_PCIexpress_x8"),
}


def pinout(doc):
    """{"A1": name, "B1": name, ...} from the doc's `| n | side B | side A |` table."""
    names = {}
    for line in open(os.path.join(ROOT, doc)):
        m = re.match(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
        if m:
            names["B" + m.group(1)] = m.group(2)
            names["A" + m.group(1)] = m.group(3)
    return names


def symbol(name, base, doc, footprint):
    sym = kg.load_symbol("Connector:" + base)
    names = pinout(doc)
    seen = set()

    def walk(node):
        for e in node:
            if not isinstance(e, list):
                continue
            if e and e[0] == "pin":
                num = str(kg.find1(e, "number")[1])
                if num not in names:
                    raise SystemExit("%s: pin %s is not in %s" % (name, num, doc))
                seen.add(num)
                e[1] = "passive"          # the nets decide; a connector's pins are passive
                kg.find1(e, "name")[1] = kg.Q(names[num])
            elif e and e[0] == "symbol":
                e[1] = kg.Q(name + str(e[1])[len(base):])
                walk(e)
    walk(sym)
    if seen != set(names):
        raise SystemExit("%s: %s has pins the symbol lacks: %s" % (name, doc, sorted(set(names) - seen)))
    sym[1] = kg.Q(name)
    for p in kg.find(sym, "property"):
        if p[1] == "Value":
            p[2] = kg.Q(name)
        elif p[1] == "Footprint":
            p[2] = kg.Q(footprint)
        elif p[1] == "Description":
            p[2] = kg.Q("CUPC/8 card edge, pinout in " + doc)
        elif p[1] == "Datasheet":
            p[2] = kg.Q("")
    return sym


def generate():
    lib = ["kicad_symbol_lib", ["version", 20231120], ["generator", kg.Q("cupc8-edgesym")]]
    lib += [symbol(n, *v) for n, v in SYMBOLS.items()]
    return kg.dump(lib) + "\n"


def main():
    text = generate()
    if "--check" in sys.argv:
        if not os.path.exists(OUT) or open(OUT).read() != text:
            raise SystemExit("%s is out of date: run hw/tools/edgesym.py" % OUT)
        return
    with open(OUT, "w") as f:
        f.write(text)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
