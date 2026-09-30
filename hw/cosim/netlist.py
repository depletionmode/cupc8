#!/usr/bin/env python3
"""Extract electrical nodes and resistors from a KiCad netlist.

This is the input graph for schematic co-simulation. It deliberately does not
claim to run the FPGA, memory, or card models. Resistors retain their two nets
so a later simulator can insert a delay rather than shorting them together.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from kicadgen import find, find1, parse


def field(node, name):
    child = find1(node, name)
    if child is None or len(child) < 2:
        raise ValueError(f'missing {name}')
    return str(child[1])


@dataclass(frozen=True)
class Resistor:
    ref: str
    value: str
    ends: tuple[str, str]


@dataclass
class Circuit:
    components: dict
    nets: dict
    pins: dict
    resistors: tuple[Resistor, ...]
    pin_names: dict | None = None
    lcsc: dict | None = None

    def net(self, ref, pin):
        return self.pins.get((ref, str(pin)))

    def direct(self, first, second):
        """True only if the pins share a KiCad net, without any component."""
        a, b = self.net(*first), self.net(*second)
        return a is not None and a == b

    def series(self, first, second):
        """The sole resistor between two pins, or None; ambiguity fails closed."""
        a, b = self.net(*first), self.net(*second)
        if not a or not b or a == b:
            return None
        matches = [r for r in self.resistors if set(r.ends) == {a, b}]
        if len(matches) > 1:
            raise ValueError(f'ambiguous parallel resistors between {a} and {b}')
        return matches[0] if matches else None

    def pulls(self, rail):
        """Return resistors tied from a signal net to the given supply rail."""
        return tuple((r, r.ends[1] if r.ends[0] == rail else r.ends[0])
                     for r in self.resistors if rail in r.ends and r.ends[0] != r.ends[1])


def read(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'missing KiCad netlist: {path}')
    tree = parse(path.read_text())
    if tree[0] != 'export':
        raise ValueError('expected a KiCad exported netlist')
    components, lcsc = {}, {}
    for comp in find(find1(tree, 'components') or [], 'comp'):
        ref = field(comp, 'ref')
        if ref in components:
            raise ValueError(f'duplicate component {ref}')
        identities = [field(prop, 'value') for prop in find(comp, 'property')
                      if field(prop, 'name') == 'LCSC']
        for entry in find(find1(comp, 'fields') or [], 'field'):
            if field(entry, 'name') == 'LCSC':
                if len(entry) != 3 or not isinstance(entry[2], str):
                    raise ValueError(f'{ref}: malformed LCSC field')
                identities.append(entry[2])
        if len(set(identities)) > 1:
            raise ValueError(f'{ref}: conflicting LCSC identities')
        if identities: lcsc[ref] = identities[0]
        source = find1(comp, 'libsource')
        components[ref] = (field(comp, 'value'),
                           (field(source, 'lib'), field(source, 'part')) if source else None)
    nets, pins = {}, {}
    for net in find(find1(tree, 'nets') or [], 'net'):
        name = field(net, 'name')
        if name in nets:
            raise ValueError(f'duplicate net {name}')
        nodes = []
        for node in find(net, 'node'):
            pin = (field(node, 'ref'), field(node, 'pin'))
            if pin[0] not in components or pin in pins:
                raise ValueError(f'unknown or multiply connected pin {pin}')
            pins[pin] = name
            nodes.append(pin)
        nets[name] = tuple(nodes)
    resistors = []
    for ref, (value, source) in components.items():
        if source == ('Device', 'R'):
            pairs = [('1', '2')]
        elif source == ('Device', 'R_Pack04'):
            # KiCad's isolated four-resistor pack: opposite pads are paired.
            # The CUPC/8 CPU series terminators, HDMI resistors and storage
            # pull-ups all use this symbol.
            pairs = [('1', '8'), ('2', '7'), ('3', '6'), ('4', '5')]
        else:
            continue
        for index, (pin_a, pin_b) in enumerate(pairs, 1):
            ends = (pins.get((ref, pin_a)), pins.get((ref, pin_b)))
            if ends == (None, None):
                continue  # an unused pack element, explicitly NC in KiCad
            if None in ends:
                raise ValueError(f'resistor {ref} channel {index} has one unconnected pin')
            channel = f'{ref}.{index}' if len(pairs) > 1 else ref
            resistors.append(Resistor(channel, value, ends))
    if not nets:
        raise ValueError('netlist has no nets')
    pin_names = {}
    library = {}
    for libpart in find(find1(tree, 'libparts') or [], 'libpart'):
        key = (field(libpart, 'lib'), field(libpart, 'part'))
        library[key] = {field(pin, 'num'): field(pin, 'name')
                        for pin in find(find1(libpart, 'pins') or [], 'pin')}
    for ref, (_, source) in components.items():
        for number, name in library.get(source, {}).items():
            pin_names[(ref, number)] = name
    return Circuit(components, nets, pins, tuple(resistors), pin_names, lcsc)
