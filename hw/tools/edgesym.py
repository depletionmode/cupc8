#!/usr/bin/env python3
"""Generate hw/lib/cupc8.kicad_sym: the card-edge connector symbols, with the
pin names from the pinout tables in the docs, so a schematic shows our
signals and not the PCIe names. Pin numbers (A1..., B1...) match KiCad's
BUS_PCIexpress_* footprints.

    python3 hw/tools/edgesym.py            write the library
    python3 hw/tools/edgesym.py --check    fail if it is out of date
"""

import math
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
    """Drawn here, not copied from KiCad's PCIe symbol: that one stacks pins
    that share a PCIe name (B1/B2/A2/A3 are all +12V), which would join
    contacts our pinout gives different signals. Side B is down the left,
    side A down the right, one row per contact."""
    names = pinout(doc)
    rows = max(int(k[1:]) for k in names)
    G = kg.GRID
    text = max(kg.text_extent(n)[0] for n in names.values())
    half = math.ceil((text + 1.5) / G) * G          # a name each side, a gap between
    top = math.ceil(rows / 2) * G
    body = [["rectangle", ["start", -half, top + G], ["end", half, top - rows * G],
             ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]]
    pins = []
    for side, x, ang in (("B", -half - 2 * G, 0), ("A", half + 2 * G, 180)):
        for i in range(1, rows + 1):
            num = side + str(i)
            if num not in names:
                continue
            font = ["effects", ["font", ["size", 1.27, 1.27]]]
            pins.append(["pin", "passive", "line", ["at", x, top - (i - 1) * G, ang], ["length", 2 * G],
                         ["name", kg.Q(names[num]), font], ["number", kg.Q(num), font]])

    def prop(key, value, y, hide=False):
        eff = ["effects", ["font", ["size", 1.27, 1.27]]] + ([["hide", "yes"]] if hide else [])
        return ["property", kg.Q(key), kg.Q(value), ["at", 0, y, 0], eff]
    return (["symbol", kg.Q(name), ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
             prop("Reference", "J", top + 2.5 * G), prop("Value", name, top - rows * G - 1.5 * G),
             prop("Footprint", footprint, 0, True), prop("Datasheet", "", 0, True),
             prop("Description", "CUPC/8 card edge (%s contacts, like %s), pinout in %s" % (len(names), base, doc),
                  0, True),
             ["symbol", kg.Q(name + "_0_1")] + body,
             ["symbol", kg.Q(name + "_1_1")] + pins])


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
