#!/usr/bin/env python3
"""Build a schematic-derived interconnect manifest for the native machine.

Each endpoint below is a KiCad component pin. Connector contacts are joined
by their *number*, never by their signal name. The manifest preserves series
resistors and weak pulls so a simulator can assign delay and idle levels.
This is the wiring prerequisite for E2E-001; it does not itself run RTL.
"""
import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from netlist import read
import kicadgen

CARDS = ('cpu', 'system', 'gpu', 'io', 'storage', 'wifi', 'eink')


def exported_cards(directory):
    result = {}
    for name in CARDS:
        spec = importlib.util.spec_from_file_location(f'cupc8_board_{name}', ROOT / 'hw/boards' / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sch = directory / f'{name}.kicad_sch'
        net = directory / f'{name}.net'
        module.schematic(str(sch), ())
        kicadgen.export_netlist(str(sch), str(net))
        result[name] = read(net)
    return result


def node(circuit, ref, pin):
    net = circuit.net(ref, pin)
    if net is None:
        raise ValueError(f'{ref}.{pin}: missing physical connection')
    return net


def path(circuit, first, last, resistance=None):
    """Check direct or one-resistor connectivity; reject an unintended bypass."""
    a, b = node(circuit, *first), node(circuit, *last)
    if resistance is None:
        if a != b:
            raise ValueError(f'{first} to {last}: missing/direct wire swapped ({a}, {b})')
        return None
    resistor = circuit.series(first, last)
    if resistor is None or resistor.value != resistance:
        raise ValueError(f'{first} to {last}: expected {resistance} series resistor ({a}, {b})')
    return resistor.ref


def check(cards, main):
    """Return a physical wiring manifest; a missing/swapped net raises ValueError."""
    manifest = {'boards': ['main', *CARDS], 'contacts': [], 'paths': [], 'pulls': []}
    fittings = [('cpu', 'J2', 'J1'), ('system', 'J3', 'J2')]
    # Every possible card is checked in every slot. Runtime chooses which
    # contacts are populated; e-ink and GPU may replace each other.
    fittings += [(kind, f'J{10 + slot}', 'J1')
                 for slot in range(1, 7)
                 for kind in ('gpu', 'io', 'storage', 'wifi', 'eink')]
    for card, main_ref, card_ref in fittings:
        card_pins = {pin for ref, pin in cards[card].pins if ref == card_ref}
        def main_pin(pin):
            return str(int(pin[1:]) + (32 if pin[0] == 'B' else 0)) if card == 'system' else pin
        common = sorted(pin for pin in card_pins if (main_ref, main_pin(pin)) in main.pins)
        if not common:
            raise ValueError(f'{card}: no shared contacts on {main_ref}/{card_ref}')
        for pin in common:
            manifest['contacts'].append([f'main.{main_ref}.{main_pin(pin)}', f'{card}.{card_ref}.{pin}'])
    for slot in range(1, 7):
        ref = f'J{10 + slot}'
        expected = {'B13': 'SPI_SCK', 'B15': 'SPI_MOSI', 'B16': 'SPI_MISO',
                    'A14': f'SLOT{slot}_CS_n', 'B10': f'SLOT_nIRQ{slot-1}'}
        card_expected = {'B13': 'SCK', 'B15': 'MOSI', 'B16': 'MISO',
                         'A14': 'CS_n', 'B10': 'IRQ_n'}
        for contact, net in expected.items():
            got = node(main, ref, contact)
            if got.lstrip('/') != net:
                raise ValueError(f'{ref}.{contact}: expected {net}, got {got}')
            for card in ('gpu', 'io', 'storage', 'wifi', 'eink'):
                card_net = node(cards[card], 'J1', contact)
                if card_net.lstrip('/') != card_expected[contact]:
                    raise ValueError(f'{card}.J1.{contact}: expected {card_expected[contact]}, got {card_net}')
                target_net = ('/MISO_INT' if card == 'wifi' else '/MISO_OUT') if contact == 'B16' else card_net
                pins = [pin for (component, pin), attached in cards[card].pins.items()
                        if component == 'U1' and attached == target_net]
                if len(pins) != 1:
                    raise ValueError(f'{card} {card_net}: card model pin missing or duplicated')
                if card == 'wifi' and contact == 'B16':
                    for value in ('/MISO_INT', '/MISO', '/CS_n'):
                        # KiCad exports numeric pin identifiers for the buffer.
                        matching = [p for (r, p), n in cards[card].pins.items() if r == 'U3' and n == value]
                        if len(matching) != 1:
                            raise ValueError(f'wifi MISO output enable: {value} missing at U3')
                manifest['paths'].append({'from': f'{card}.J1.{contact}',
                                          'to': f'{card}.U1.{pins[0]}', 'net': card_net.lstrip('/')})
            manifest['paths'].append({'from': f'main.{ref}.{contact}', 'net': net,
                                      'cards': 'slot', 'slot': slot})
        for contact, source in (('B13', 'SPI_SCK_SRC'), ('B15', 'SPI_MOSI_SRC'),
                                ('A14', f'SPI_nCS{slot-1}_SRC')):
            pins = [p for (r, p), attached in main.pins.items()
                    if r == 'U7' and attached == f'/{source}']
            if len(pins) != 1:
                raise ValueError(f'{source}: chipset model pin missing')
            resistor = path(main, ('U7', pins[0]), (ref, contact), '33')
            manifest['paths'].append({'from': f'main.U7.{pins[0]}', 'to': f'main.{ref}.{contact}',
                                      'series': resistor, 'ohms': 33})
    # The shared SPI return needs an idle high level when no card drives it.
    miso = node(main, 'J11', 'B16')
    pulls = [(r.ref, r.value) for r, other in main.pulls('/+3V3') if other == miso]
    if not any(v == '47k' for _, v in pulls):
        raise ValueError('SPI MISO lacks a 47k pull-up on the main board')
    manifest['pulls'].append({'net': 'SPI_MISO', 'rail': '+3V3', 'resistors': pulls,
                              'idle': 1, 'strength': 'weak'})
    # Memory models attach to actual SRAM/ROM pins on the same electrical
    # nodes as the FPGA, rather than to an independently typed bus list.
    for i in range(19):
        fpga_net = f'/MEM_A{i}'
        fpga = [p for (ref, p), n in main.pins.items() if ref == 'U7' and n == fpga_net]
        if len(fpga) != 1:
            raise ValueError(f'{fpga_net}: expected one FPGA package pin')
        for ref in ('U9', 'U10'):
            pins = [p for (r, p), n in main.pins.items() if r == ref and n == fpga_net]
            if len(pins) != 1:
                raise ValueError(f'{fpga_net}: {ref} missing or multiply attached')
            path(main, ('U7', fpga[0]), (ref, pins[0]))
            manifest['paths'].append({'from': f'main.U7.{fpga[0]}', 'to': f'main.{ref}.{pins[0]}',
                                      'net': f'MEM_A{i}', 'delay_ns': 0})
    for i in range(8):
        net = f'/MEM_D{i}'
        if sum(n == net for (ref, _), n in main.pins.items() if ref in ('U7', 'U9', 'U10')) != 3:
            raise ValueError(f'{net}: FPGA/SRAM/ROM data pin missing')
    # CPU driver pack channels must remain explicit; the native board model
    # may use these channel values as edge delays after E2E-001 integration.
    import cpu
    for pin, (signal, direction) in cpu.PINS.items():
        fingers = [p for (ref, p), n in cards['cpu'].pins.items()
                   if ref == 'J1' and n == f'/{signal}']
        if len(fingers) != 1 or node(main, 'J2', fingers[0]) != f'/{signal}':
            raise ValueError(f'CPU {signal}: main socket contact swapped or missing')
        if signal not in cpu.DRIVEN:
            continue
        resistor = path(cards['cpu'], ('U1', str(pin)), ('J1', fingers[0]), '33')
        manifest['paths'].append({'from': f'cpu.U1.{pin}', 'to': f'cpu.J1.{fingers[0]}',
                                  'series': resistor, 'ohms': 33})
    return manifest


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-') as temporary:
        manifest = check(exported_cards(Path(temporary)), read(args.main_netlist))
    output = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main_cli()
