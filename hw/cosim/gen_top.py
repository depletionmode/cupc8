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


def named_pin(circuit, ref, name):
    pins = [pin for (component, pin), label in circuit.pin_names.items()
            if component == ref and label == name and (ref, pin) in circuit.pins]
    if len(pins) != 1:
        raise ValueError(f'{ref} pin {name}: expected one connected package pad')
    return (ref, pins[0])


def ohms(value):
    scale = {'k': 1e3, 'M': 1e6}
    return float(value[:-1]) * scale[value[-1]] if value[-1] in scale else float(value)


def resistor_between(circuit, a, b):
    resistor = circuit.series(a, b)
    if resistor is None:
        raise ValueError(f'{a} to {b}: required resistor missing')
    return resistor


def check(cards, main, pcb=None):
    """Return a physical wiring manifest; a missing/swapped net raises ValueError."""
    manifest = {'boards': ['main', *CARDS], 'contacts': [], 'paths': [], 'pulls': [], 'runtime': {}}
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
        endpoints = [(ref, pin) for (ref, pin), attached in main.pins.items()
                     if ref in ('U7', 'U9', 'U10') and attached == net]
        for target in endpoints[1:]:
            path(main, endpoints[0], target)
            manifest['paths'].append({'from': f'main.{endpoints[0][0]}.{endpoints[0][1]}',
                                      'to': f'main.{target[0]}.{target[1]}', 'net': net.lstrip('/')})
    for net, chips in (('MEM_nOE', ('U9', 'U10')), ('MEM_nWE', ('U9', 'U10')),
                       ('MEM_nCE_RAM', ('U9',)), ('MEM_nCE_ROM', ('U10',))):
        source = [(ref, pin) for (ref, pin), attached in main.pins.items()
                  if ref == 'U7' and attached == f'/{net}']
        if len(source) != 1:
            raise ValueError(f'{net}: chipset driver missing')
        for chip in chips:
            sinks = [(ref, pin) for (ref, pin), attached in main.pins.items()
                     if ref == chip and attached == f'/{net}']
            if len(sinks) != 1:
                raise ValueError(f'{net}: {chip} pin missing')
            path(main, source[0], sinks[0])
            manifest['paths'].append({'from': f'main.U7.{source[0][1]}',
                                      'to': f'main.{chip}.{sinks[0][1]}', 'net': net})
    def chip_map(ref, prefix, count):
        mapping = []
        for i in range(count):
            name = f'{prefix}{i}'
            physical = [(pin, net) for (r, pin), net in main.pins.items()
                        if r == ref and main.pin_names.get((r, pin)) == name]
            if len(physical) != 1:
                raise ValueError(f'{ref} physical {name}: expected one package pad')
            net = physical[0][1].lstrip('/')
            if not net.startswith(f'MEM_{"A" if prefix == "A" else "D"}'):
                raise ValueError(f'{ref}.{name}: attached to unexpected {net}')
            bit = int(net.rsplit('_', 1)[-1][1:])
            mapping.append(bit)
        if sorted(mapping) != list(range(count)):
            raise ValueError(f'{ref} {prefix} pin map is not a permutation: {mapping}')
        return mapping
    manifest['runtime']['ram_address'] = chip_map('U9', 'A', 19)
    manifest['runtime']['rom_address'] = chip_map('U10', 'A', 19)
    manifest['runtime']['ram_data'] = chip_map('U9', 'I/O', 8)
    manifest['runtime']['rom_data'] = chip_map('U10', 'DQ', 8)
    output_bits = {'SPI_SCK': 0, 'SPI_MOSI': 1,
                   **{f'SLOT{k}_CS_n': k + 1 for k in range(1, 7)}}
    manifest['runtime']['slots'] = []
    for slot in range(1, 7):
        ref = f'J{10 + slot}'
        signals = {key: node(main, ref, contact).lstrip('/')
                   for key, contact in (('sck', 'B13'), ('mosi', 'B15'), ('cs', 'A14'),
                                        ('miso', 'B16'), ('irq', 'B10'))}
        manifest['runtime']['slots'].append({
            'sck': output_bits[signals['sck']], 'mosi': output_bits[signals['mosi']],
            'cs': output_bits[signals['cs']], 'irq': int(signals['irq'].removeprefix('SLOT_nIRQ')),
            'miso': signals['miso'] == 'SPI_MISO'})
    manifest['runtime']['miso_idle'] = 1  # verified 47k pull-up above
    manifest['runtime']['series_delay_ns'] = round(2.2 * 33 * 15e-12 * 1e9, 3)
    # Datasheet worst-case tAA: ISSI 45 ns, SST39VF040 70 ns. Route delay is
    # charged on launch and return using the slow FR4 stripline bound of
    # 7 ps/mm (the same assumption as hw/timing/*_budget.py).
    route = {}
    if pcb is not None and Path(pcb).is_file():
        sys.path.insert(0, str(ROOT / 'hw/timing'))
        from extract_lengths import copper_lengths
        route = copper_lengths(Path(pcb))
    address = max((route.get(f'MEM_A{i}', 0) for i in range(19)), default=0)
    data = max((route.get(f'MEM_D{i}', 0) for i in range(8)), default=0)
    def access(ns, ce):
        launch = max(address, route.get(ce, 0), route.get('MEM_nOE', 0))
        return round(ns + (launch + data) * 0.007, 3)
    manifest['runtime']['memory_timing_ns'] = {
        'ram': access(45, 'MEM_nCE_RAM'), 'rom': access(70, 'MEM_nCE_ROM')}
    required_routes = {f'MEM_A{i}' for i in range(19)} | {f'MEM_D{i}' for i in range(8)} | \
                      {'MEM_nOE', 'MEM_nCE_RAM', 'MEM_nCE_ROM'}
    manifest['runtime']['routed_timing'] = all(route.get(net, 0) > 0 for net in required_routes)
    required_top = required_routes | {f'CPU_A{i}' for i in range(16)} | \
                   {f'CPU_D{i}' for i in range(8)} | \
                   {f'SLOT{i}_CS_n' for i in range(1, 7)} | \
                   {f'SLOT_nIRQ{i}' for i in range(6)} | \
                   {'CPU_CLK', 'CPU_nRST', 'CPU_nRDY', 'CPU_nSTB', 'CPU_RW',
                    'CPU_SYNC', 'SPI_SCK', 'SPI_MOSI', 'SPI_MISO',
                    'BR_SCK', 'BR_MOSI', 'BR_MISO', 'BR_nCS', 'nPOR', 'PWR_HI'}
    manifest['runtime']['routed_top'] = all(route.get(net, 0) > 0 for net in required_top)
    manifest['runtime']['missing_routes'] = sorted(net for net in required_top if route.get(net, 0) <= 0)
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
    def cpu_map(prefix, count):
        mapping = []
        for i in range(count):
            net = f'/CPU_{prefix}{i}'
            main_pins = [p for (ref, p), n in main.pins.items() if ref == 'J2' and n == net]
            if len(main_pins) != 1:
                raise ValueError(f'{net}: main CPU socket contact missing')
            card_net = node(cards['cpu'], 'J1', main_pins[0]).lstrip('/')
            if not card_net.startswith(f'CPU_{prefix}'):
                raise ValueError(f'{net}: connected to wrong CPU-card bus {card_net}')
            mapping.append(int(card_net[len(f'CPU_{prefix}'):]))
        if sorted(mapping) != list(range(count)):
            raise ValueError(f'CPU {prefix} physical contacts are not a permutation')
        return mapping
    manifest['runtime']['cpu_address'] = cpu_map('A', 16)
    manifest['runtime']['cpu_data'] = cpu_map('D', 8)
    bridge = {}
    bridge_source = {'BR_SCK': 0, 'BR_MOSI': 1, 'BR_nCS': 2}
    for destination in ('BR_SCK', 'BR_MOSI', 'BR_nCS', 'BR_MISO'):
        pads = [pin for (ref, pin), net in main.pins.items()
                if ref == 'J3' and net == f'/{destination}']
        if len(pads) != 1:
            raise ValueError(f'system bridge {destination}: main socket contact missing')
        number = int(pads[0])
        contact = f'A{number}' if number <= 32 else f'B{number-32}'
        card_net = node(cards['system'], 'J2', contact).lstrip('/')
        if destination == 'BR_MISO':
            if card_net != 'BR_MISO':
                raise ValueError('system bridge MISO contact swapped')
            bridge['miso'] = True
            fpga = [pin for (ref, pin), net in main.pins.items()
                    if ref == 'U7' and net == '/BR_MISO_SRC']
            if len(fpga) != 1:
                raise ValueError('system bridge MISO FPGA driver missing')
            resistor = path(main, ('U7', fpga[0]), ('J3', pads[0]), '33')
            manifest['paths'].append({'from': f'main.U7.{fpga[0]}', 'to': f'main.J3.{pads[0]}',
                                      'series': resistor, 'ohms': 33})
        else:
            if card_net not in bridge_source:
                raise ValueError(f'system bridge {destination}: wired to {card_net}')
            bridge[destination.removeprefix('BR_').lower()] = bridge_source[card_net]
            fpga = [pin for (ref, pin), net in main.pins.items()
                    if ref == 'U7' and net == f'/{destination}']
            if len(fpga) != 1:
                raise ValueError(f'system bridge {destination}: FPGA input missing')
            path(main, ('U7', fpga[0]), ('J3', pads[0]))
            mcu = [pin for (ref, pin), net in cards['system'].pins.items()
                   if ref == 'U1' and net == f'/{card_net}_MCU']
            if len(mcu) != 1:
                raise ValueError(f'system bridge {card_net}: MCU driver missing')
            resistor = path(cards['system'], ('U1', mcu[0]), ('J2', contact), '33')
            manifest['paths'].append({'from': f'system.U1.{mcu[0]}', 'to': f'system.J2.{contact}',
                                      'series': resistor, 'ohms': 33})
    manifest['runtime']['bridge'] = bridge
    # Reset, oscillator and Type-C source policy reach actual chipset pads.
    for source_ref, source_pin, destination_net in (
            ('U5', 'OUT', '/PWR_HI'), ('U6', '~{RESET}', '/nPOR')):
        fpga = [(ref, pin) for (ref, pin), net in main.pins.items()
                if ref == 'U7' and net == destination_net]
        if len(fpga) != 1:
            raise ValueError(f'{destination_net}: chipset pad missing')
        path(main, named_pin(main, source_ref, source_pin), fpga[0])
        manifest['paths'].append({'from': f'main.{source_ref}.{source_pin}',
                                  'to': f'main.U7.{fpga[0][1]}', 'net': destination_net.lstrip('/')})
    # The USB-C symbol names these pads A5/B5, whereas the comparator names
    # its actual package pins. Preserve resistor values in the policy model.
    cc1, cc2 = ('J1', 'A5'), ('J1', 'B5')
    plus, minus = named_pin(main, 'U5', 'IN+'), named_pin(main, 'U5', 'IN')
    vcc, vee = named_pin(main, 'U5', 'VCC'), named_pin(main, 'U5', 'VEE')
    r_cc1 = resistor_between(main, cc1, plus)
    r_cc2 = resistor_between(main, cc2, plus)
    r_top = resistor_between(main, vcc, minus)
    r_bottom = resistor_between(main, minus, vee)
    for contact in (cc1, cc2):
        rd = resistor_between(main, contact, vee)
        if not 4500 <= ohms(rd.value) <= 5600:
            raise ValueError(f'{contact}: invalid Type-C Rd {rd.value}')
    reference = 3.3 * ohms(r_bottom.value) / (ohms(r_top.value) + ohms(r_bottom.value))
    fractions = (ohms(r_cc2.value) / (ohms(r_cc1.value) + ohms(r_cc2.value)),
                 ohms(r_cc1.value) / (ohms(r_cc1.value) + ohms(r_cc2.value)))
    manifest['runtime']['cc_trip_volts'] = [round(reference / f, 6) for f in fractions]
    # The USB host lives on the IO card. Its two RP2040 PHY pads must reach
    # the actual receptacle contacts through the fitted 27 ohm series parts.
    for signal, connector_pin in (('DM', '2'), ('DP', '3')):
        source = named_pin(cards['io'], 'U1', f'USB_{signal}')
        resistor = path(cards['io'], source, ('J2', connector_pin), '27R')
        manifest['paths'].append({'from': f'io.U1.{source[1]}',
                                  'to': f'io.J2.{connector_pin}',
                                  'series': resistor, 'ohms': 27,
                                  'runtime': 'io_usb_host'})
    manifest['runtime']['io_usb_host'] = True
    clock = named_pin(main, 'Y1', 'OUT')
    fpga_clk = [(ref, pin) for (ref, pin), net in main.pins.items()
                if ref == 'U7' and net == '/CLK12']
    if len(fpga_clk) != 1:
        raise ValueError('chipset CLK12 package pad missing')
    for target in (fpga_clk[0], ('J2', next(pin for (ref, pin), net in main.pins.items()
                                       if ref == 'J2' and net == '/CPU_CLK'))):
        resistor = path(main, clock, target, '33')
        manifest['paths'].append({'from': f'main.Y1.{clock[1]}',
                                  'to': f'main.{target[0]}.{target[1]}', 'series': resistor, 'ohms': 33})
    for i in range(8):
        net = node(main, 'J2', next(pin for (ref, pin), attached in main.pins.items()
                                    if ref == 'J2' and attached == f'/CPU_D{i}'))
        if not any(value == '47k' for _, value in
                   ((r.ref, r.value) for r, other in main.pulls('/+3V3') if other == net)):
            raise ValueError(f'CPU_D{i}: missing weak keeper')
    circuits = {'main': main, **cards}
    structural = set()
    for connection in manifest['contacts']:
        for endpoint in connection:
            board, ref, pin = endpoint.split('.', 2)
            structural.add((board, circuits[board].net(ref, pin)))
    for connection in manifest['paths']:
        for key in ('from', 'to'):
            if key in connection:
                board, ref, pin = connection[key].split('.', 2)
                if (ref, pin) in circuits[board].pins:
                    structural.add((board, circuits[board].net(ref, pin)))
    # Runtime coverage is deliberately narrower than validated topology.
    # These signals are used to build pin permutations, SPI/bridge mapping,
    # memory timing, or the Type-C policy calculation consumed by the native
    # machine. A checked resistor or connector alone is not an executed model.
    executed = set()
    available_nets = {board: set(circuit.nets) for board, circuit in circuits.items()}
    def runtime_net(board, name):
        key = (board, f'/{name}')
        if key[1] not in available_nets[board]:
            raise ValueError(f'{board}:{name}: runtime signal missing from netlist')
        executed.add(key)
    for i in range(19):
        runtime_net('main', f'MEM_A{i}')
    for i in range(8):
        runtime_net('main', f'MEM_D{i}')
        runtime_net('main', f'CPU_D{i}')
        runtime_net('cpu', f'CPU_D{i}')
    for i in range(16):
        runtime_net('main', f'CPU_A{i}')
        runtime_net('cpu', f'CPU_A{i}')
    for name in ('MEM_nOE', 'MEM_nCE_RAM', 'MEM_nCE_ROM',
                 'SPI_SCK', 'SPI_MOSI', 'SPI_MISO', 'BR_SCK', 'BR_MOSI',
                 'BR_MISO', 'BR_nCS', 'PWR_HI', 'CC1', 'CC2', 'CC_AVG', 'CC_REF'):
        runtime_net('main', name)
    for slot in range(1, 7):
        runtime_net('main', f'SLOT{slot}_CS_n')
        runtime_net('main', f'SLOT_nIRQ{slot-1}')
    for name in ('BR_SCK', 'BR_MOSI', 'BR_MISO', 'BR_nCS'):
        runtime_net('system', name)
    for name in ('USB_DM', 'USB_DP', 'USB_CONN_DM', 'USB_CONN_DP'):
        runtime_net('io', name)
    unmodeled, structural_only = [], []
    for board, circuit in circuits.items():
        for net in circuit.nets:
            if net.startswith('unconnected-'):
                continue  # KiCad's explicit no-connect marker, no electrical node
            if (board, net) not in executed:
                unmodeled.append(f'{board}:{net.lstrip("/")}')
                if (board, net) in structural:
                    structural_only.append(f'{board}:{net.lstrip("/")}')
    manifest['unmodeled_nets'] = sorted(unmodeled)
    manifest['structural_only_nets'] = sorted(structural_only)
    manifest['runtime_nets'] = sorted(f'{board}:{net.lstrip("/")}' for board, net in executed)
    manifest['coverage_complete'] = not unmodeled
    return manifest


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--require-route', action='store_true', help='fail unless memory nets have routed copper')
    parser.add_argument('--require-coverage', action='store_true', help='fail on any modeled/waiver coverage gap')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-') as temporary:
        manifest = check(exported_cards(Path(temporary)), read(args.main_netlist),
                         args.main_netlist.with_suffix('.kicad_pcb'))
    if args.require_route and not manifest['runtime']['routed_top']:
        missing = manifest['runtime']['missing_routes']
        raise ValueError(f'main-board co-sim paths lack routed copper: {", ".join(missing)}')
    if args.require_coverage and not manifest['coverage_complete']:
        missing = manifest['unmodeled_nets']
        raise ValueError(f'{len(missing)} netlist nets lack a model or explicit waiver: {", ".join(missing[:25])}')
    output = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main_cli()
