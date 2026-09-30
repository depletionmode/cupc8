#!/usr/bin/env python3
"""Build a schematic-derived interconnect manifest for the native machine.

Each endpoint below is a KiCad component pin. Connector contacts are joined
by their *number*, never by their signal name. The manifest preserves series
resistors and weak pulls so a simulator can assign delay and idle levels.
This is the wiring prerequisite for E2E-001; it does not itself run RTL.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from netlist import read
from coverage import audit
import kicadgen

CARDS = ('cpu', 'system', 'gpu', 'io', 'storage', 'wifi', 'eink')


def implemented_checks():
    """Catalogue ids that have a command: an analog waiver may only name these."""
    import tomllib
    rows = tomllib.loads((ROOT / 'test/catalogue.toml').read_text())['test']
    return {row['id'] for row in rows if row.get('cmd')}


def board_module(name):
    spec = importlib.util.spec_from_file_location(f'cupc8_board_{name}', ROOT / 'hw/boards' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exported_cards(directory):
    result = {}
    for name in CARDS:
        module = board_module(name)
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


def card_miso_network(circuit, card):
    """Require the complete pin-exact current external TI/RC network."""
    from slot_spi import network
    network(circuit,card)
    return True


def card_slot_routes(cards, board_paths):
    """Functional DC links through actual fitted passives/TI stages; SI separate."""
    from slot_spi import routed
    sys.path.insert(0,str(ROOT/'hw/si'))
    rows,paths,missing={ },[],[]
    for kind in ('gpu','io','storage','wifi','eink'):
        links,legs,gaps,_=routed(cards[kind],kind,(board_paths or {}).get(kind))
        rows[kind]=links;paths.extend(legs);missing.extend(gaps)
    return rows,paths,missing


def qspi_boot_routes(cards, card_boards, system_board):
    """Digital boot prerequisite: six MCU-to-external-flash copper paths."""
    rows, paths, missing = {}, [], []
    for board in ('system', 'gpu', 'io', 'storage', 'eink'):
        circuit = cards[board]
        pcb = system_board if board == 'system' else (card_boards or {}).get(board)
        routed = pcb is not None and Path(pcb).is_file()
        if routed:
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
        flash = 'U2' if board == 'system' else 'U3'
        nets = ('QSPI_SCLK', 'QSPI_SD0', 'QSPI_SD1', 'QSPI_SD2', 'QSPI_SD3',
                'QSPI_nSS' if board == 'system' else 'QSPI_SS')
        connected = True
        for name in nets:
            net = f'/{name}'
            source = [(ref, pin) for (ref, pin), attached in circuit.pins.items()
                      if ref == 'U1' and attached == net]
            target = [(ref, pin) for (ref, pin), attached in circuit.pins.items()
                      if ref == flash and attached == net]
            if len(source) != 1 or len(target) != 1:
                raise ValueError(f'{board}:{name}: MCU/flash pad mapping missing')
            path(circuit, source[0], target[0])
            mm = None
            if routed:
                mm = routed_distances(Path(pcb), net, source[0], target)[
                    f'{target[0][0]}.{target[0][1]}']
            paths.append({'from': f'{board}.{source[0][0]}.{source[0][1]}',
                          'to': f'{board}.{target[0][0]}.{target[0][1]}',
                          'route_mm': mm, 'runtime': f'{board}_qspi_boot_connected'})
            if mm is None:
                connected = False
                missing.append(f'{board}:{name}_qspi_copper')
        rows[board] = connected
    return rows, paths, missing


def crystal_routes(cards, card_boards, system_board):
    """Digital boot prerequisite: each RP2040's 12 MHz crystal network.

    XIN reaches the crystal and its load capacitor; XOUT reaches its 1k
    series resistor, whose far side reaches the crystal's other terminal
    and load capacitor. Any open leg leaves that card's firmware stopped
    (the RP2040 has no clock to boot from in this model). Oscillator start-up
    margin, drive level and frequency error are analog and are not modeled.
    """
    rows, paths, missing, whole = {}, [], [], {}
    for board in ('system', 'gpu', 'io', 'storage', 'eink'):
        circuit = cards[board]
        pcb = system_board if board == 'system' else (card_boards or {}).get(board)
        routed = pcb is not None and Path(pcb).is_file()
        if routed:
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
        xin, xout = named_pin(circuit, 'U1', 'XIN'), named_pin(circuit, 'U1', 'XOUT')
        xin_net, xout_net = node(circuit, *xin), node(circuit, *xout)
        crystal = [ref for ref, (value, _) in circuit.components.items()
                   if ref.startswith('Y') and value == '12MHz']
        if len(crystal) != 1:
            raise ValueError(f'{board}: expected one 12 MHz crystal')
        crystal = crystal[0]
        ends = sorted((pin for (ref, pin), net in circuit.pins.items()
                       if ref == crystal and net != '/GND'),
                      key=lambda pin: node(circuit, crystal, pin) != xin_net)
        if len(ends) != 2 or node(circuit, crystal, ends[0]) != xin_net:
            raise ValueError(f'{board}: crystal {crystal} must span XIN and the XOUT resistor')
        far_net = node(circuit, crystal, ends[1])
        resistor = circuit.series(xout, (crystal, ends[1]))
        if resistor is None or resistor.value != '1k':
            raise ValueError(f'{board}: XOUT must reach the crystal through its 1k resistor')
        near = next(pin for pin in ('1', '2') if node(circuit, resistor.ref, pin) == xout_net)
        far = '2' if near == '1' else '1'

        def load_cap(net):
            caps = [(ref, pin) for (ref, pin), attached in circuit.pins.items()
                    if attached == net and ref.startswith('C')]
            if len(caps) != 1 or circuit.components[caps[0][0]][0] != '33p' or \
                    node(circuit, caps[0][0], '2' if caps[0][1] == '1' else '1') != '/GND':
                raise ValueError(f'{board}:{net}: expected one grounded 33p load capacitor')
            return caps[0]

        legs = [(xin_net, xin, [(crystal, ends[0]), load_cap(xin_net)]),
                (xout_net, xout, [(resistor.ref, near)]),
                (far_net, (resistor.ref, far), [(crystal, ends[1]), load_cap(far_net)])]
        for net, first, targets in legs:
            # nothing else may load the oscillator nodes
            if set(circuit.nets[net]) != {first, *targets}:
                raise ValueError(f'{board}:{net}: unexpected parts on the crystal network')
        connected = True
        for net, first, targets in legs:
            lengths = {}
            if routed:
                lengths = routed_distances(Path(pcb), net, first, targets)
            for target in targets:
                mm = lengths.get(f'{target[0]}.{target[1]}')
                paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                              'to': f'{board}.{target[0]}.{target[1]}',
                              'route_mm': mm, 'runtime': f'{board}_crystal_connected'})
                whole[(board, net)] = whole.get((board, net), True) and mm is not None
                if mm is None:
                    connected = False
                    missing.append(f'{board}:{net.lstrip("/")}_crystal_copper:{target[0]}.{target[1]}')
        rows[board] = connected
    return rows, paths, missing, whole


def adc_sense_routes(main, system, main_board, system_board):
    """sysctl's ADC inputs: the Type-C CC lines and the 1V2 sense.

    CC1/CC2 run from the power receptacle's CC contacts through the system
    socket to GPIO26/27; V1V2_SENSE from +1V2 through R100 (1k) to GPIO28.
    Returns ({'cc1', 'cc2', 'v1v2'} links, paths, missing, whole_nets). The
    native machine puts the source's CC voltage and 1.2 V on those pins
    (open copper reads 0 V); the analog thresholds are POW-005's.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    boards = {'main': (main, main_board), 'system': (system, system_board)}
    paths, missing, whole, links = [], [], {}, {}

    def leg(board, net, first, last, flag):
        circuit, pcb = boards[board]
        path(circuit, first, last)
        mm = None
        if pcb is not None and Path(pcb).is_file():
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': f'adc_{flag}'})
        whole[(board, f'/{net}')] = whole.get((board, f'/{net}'), True) and mm is not None
        if mm is None:
            missing.append(f'{board}:{net}_adc_{flag}')
        return mm is not None

    def socket(net):
        pads = [p for (r, p), n in main.pins.items() if r == 'J3' and n == f'/{net}']
        if len(pads) != 1:
            raise ValueError(f'main:{net}: expected one system-socket contact')
        number = int(pads[0])
        return ('J3', pads[0]), ('J2', f'A{number}' if number <= 32 else f'B{number - 32}')

    for flag, net, receptacle, gpio in (('cc1', 'CC1', ('J1', 'A5'), 'GPIO26/ADC0'),
                                        ('cc2', 'CC2', ('J1', 'B5'), 'GPIO27/ADC1')):
        main_contact, card_contact = socket(net)
        mcu = named_pin(system, 'U1', gpio)
        if node(system, *card_contact) != f'/{net}' or node(system, *mcu) != f'/{net}':
            raise ValueError(f'system:{net}: socket contact or {gpio} moved')
        links[flag] = leg('main', net, receptacle, main_contact, flag) and \
            leg('system', net, card_contact, mcu, flag)
    main_contact, card_contact = socket('V1V2_SENSE')
    sense = resistor_between(main, main_contact, next(
        (r, p) for (r, p), n in main.pins.items() if n == '/+1V2' and r.startswith('R') and
        main.series((r, p), main_contact) is not None))
    if sense.value != '1k':
        raise ValueError('main: V1V2_SENSE must be +1V2 through a 1k resistor')
    near = next((sense.ref, p) for p in ('1', '2') if node(main, sense.ref, p) == '/V1V2_SENSE')
    mcu = named_pin(system, 'U1', 'GPIO28/ADC2')
    if node(system, *card_contact) != '/V1V2_SENSE' or node(system, *mcu) != '/V1V2_SENSE':
        raise ValueError('system:V1V2_SENSE: socket contact or GPIO28 moved')
    links['v1v2'] = leg('main', 'V1V2_SENSE', near, main_contact, 'v1v2') and \
        leg('system', 'V1V2_SENSE', card_contact, mcu, 'v1v2')
    return links, paths, missing, whole


def i2c_expander_routes(main, cards, main_board, cpu_board, system_board, card_boards=None):
    """sysctl's I2C0 to the two TCA9555s, and the CPU card presence input.

    Returns (rows, paths, missing, whole_nets). rows: the expanders (address
    from their A0-A2 straps, whether SDA and SCL reach them), the CPU-card
    presence path (main J2.B49 to U14 P10 and the card's PRSNT1-PRSNT2 loop),
    the CPU card ID straps (their main-board legs to U14 P11/P12), and each
    slot's presence path: main J1n.B18 to its U14 pin and every card kind's
    own PRSNT loop (J1.A1 to J1.B18, PRSNT1_n grounded on the main board).
    Only the CPU presence bit is read by software (sysctl STATUS); slot
    presence and the ID bits are presented on the bus (the model's input
    registers) but nothing in the firmware reads them.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    system, cpu = cards['system'], cards['cpu']
    boards = {'main': (main, main_board), 'system': (system, system_board), 'cpu': (cpu, cpu_board)}
    for kind in ('gpu', 'io', 'storage', 'wifi', 'eink'):
        boards[kind] = (cards[kind], (card_boards or {}).get(kind))
    paths, missing, whole = [], [], {}

    def leg(board, net, first, last, flag):
        circuit, pcb = boards[board]
        path(circuit, first, last)
        mm = None
        if pcb is not None and Path(pcb).is_file():
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': flag})
        whole[(board, f'/{net}')] = whole.get((board, f'/{net}'), True) and mm is not None
        if mm is None:
            missing.append(f'{board}:{net}_{flag}:{first[0]}.{first[1]}->{last[0]}.{last[1]}')
        return mm is not None

    expanders = sorted(ref for ref, (value, _) in main.components.items() if value == 'TCA9555PWR')
    if len(expanders) != 2:
        raise ValueError(f'main: expected two TCA9555 expanders, found {expanders}')
    lines = {}
    for signal, gpio in (('SDA', 'GPIO24'), ('SCL', 'GPIO25')):
        net = f'I2C_{signal}'
        mcu = named_pin(system, 'U1', gpio)
        if node(system, *mcu) != f'/{net}':
            raise ValueError(f'system: {gpio} is not on {net}')
        pads = [p for (r, p), n in main.pins.items() if r == 'J3' and n == f'/{net}']
        if len(pads) != 1:
            raise ValueError(f'main:{net}: expected one system-socket contact')
        number = int(pads[0])
        contact = ('J2', f'A{number}' if number <= 32 else f'B{number - 32}')
        system_ok = leg('system', net, mcu, contact, 'i2c')
        pulls = [r for r, other in system.pulls('/+3V3') if other == f'/{net}'] + \
                [r for r, other in main.pulls('/+3V3') if other == f'/{net}']
        if not pulls:
            raise ValueError(f'{net}: no pull-up to 3V3')
        lines[signal] = (system_ok, ('J3', pads[0]))
    rows = {'expanders': [], 'cpu_present_link': False, 'card_id': [], 'slot_presence': []}
    for ref in expanders:
        address = 0x20
        for bit, name in enumerate(('A0', 'A1', 'A2')):
            level = node(main, *named_pin(main, ref, name))
            if level not in ('/GND', '/+3V3'):
                raise ValueError(f'main:{ref} {name}: address strap is on {level}')
            address |= (level == '/+3V3') << bit
        link = True
        for signal, (system_ok, contact) in lines.items():
            pad = named_pin(main, ref, signal)
            link &= system_ok and leg('main', f'I2C_{signal}', contact, pad, 'i2c')
        rows['expanders'].append({'ref': ref, 'address': address, 'link': link})
    if sorted(x['address'] for x in rows['expanders']) != [0x20, 0x21]:
        raise ValueError('main: sysctl addresses its expanders at $20 and $21 (power.c)')
    presence = next(x['ref'] for x in rows['expanders'] if x['address'] == 0x21)
    p10 = named_pin(main, presence, 'P10')
    if node(main, *p10) != '/CPU_PRSNT2_n':
        raise ValueError(f'main:{presence} P10 is not CPU_PRSNT2_n')
    contact = next(('J2', p) for (r, p), n in main.pins.items() if r == 'J2' and n == '/CPU_PRSNT2_n')
    first = next(('J1', p) for (r, p), n in cpu.pins.items()
                 if r == 'J1' and n == '/PRSNT' and cpu.pin_names.get(('J1', p)) == 'PRSNT1_n')
    card_contact = ('J1', contact[1])
    if node(cpu, *card_contact) != '/PRSNT' or node(main, 'J2', first[1]) != '/GND':
        raise ValueError('CPU card presence loop: PRSNT2_n must reach PRSNT1_n, grounded on the main board')
    rows['cpu_present_link'] = leg('main', 'CPU_PRSNT2_n', contact, p10, 'cpu_presence') and \
        leg('cpu', 'PRSNT', first, card_contact, 'cpu_presence')
    for bit, name in ((1, 'P11'), (2, 'P12')):
        pad = named_pin(main, presence, name)
        net = node(main, *pad)
        strap = next(p for (r, p), n in main.pins.items() if r == 'J2' and n == net)
        card = cpu.net('J1', strap) or 'NC'
        if not [r for r, other in main.pulls('/+3V3') if other == net]:
            raise ValueError(f'main:{net}: the CPU card ID line has no pull-up')
        rows['card_id'].append({'bit': bit, 'net': net.lstrip('/'),
                                'level': 0 if card == '/GND' else 1,
                                'link': leg('main', net.lstrip('/'), ('J2', strap), pad, 'card_id')})
    # each card kind's presence loop: PRSNT1_n (A1) wired to PRSNT2_n (B18)
    # on the card, PRSNT1_n grounded on the main board
    rows['card_loops'] = {}
    for kind in ('gpu', 'io', 'storage', 'wifi', 'eink'):
        circuit = cards[kind]
        if circuit.pin_names.get(('J1', 'A1'), '').split('_')[0] != 'PRSNT1' or \
                circuit.pin_names.get(('J1', 'B18')) != 'PRSNT2_n' or \
                node(circuit, 'J1', 'A1') != '/PRSNT' or node(circuit, 'J1', 'B18') != '/PRSNT':
            raise ValueError(f'{kind}: PRSNT1_n must be wired to PRSNT2_n on the card')
        rows['card_loops'][kind] = leg(kind, 'PRSNT', ('J1', 'A1'), ('J1', 'B18'), 'slot_presence')
    for slot in range(1, 7):
        net = f'SLOT{slot}_PRSNT2_n'
        socket = f'J{10 + slot}'
        pad = next(((r, p) for (r, p), n in main.pins.items() if r == presence and n == f'/{net}'), None)
        if pad is None or node(main, socket, 'B18') != f'/{net}' or node(main, socket, 'A1') != '/GND' or \
                not [r for r, other in main.pulls('/+3V3') if other == f'/{net}']:
            raise ValueError(f'main:{net}: slot presence must run from {socket}.B18 to {presence}, '
                             'with a 3V3 pull-up and PRSNT1_n on GND')
        rows['slot_presence'].append({
            'slot': slot, 'bit': int(main.pin_names[pad][2]),
            'link': leg('main', net, (socket, 'B18'), pad, 'slot_presence')})
    return rows, paths, missing, whole


def card_led_routes(cards, card_boards, system_board):
    """Firmware-driven indicator LEDs on the RP2040 cards, leg by leg.

    An indicator is an RP2040 GPIO whose net holds only that pad and one
    resistor, whose far net holds only the resistor and an LED anode, the
    LED's cathode on GND. Both signal legs must be on the routed copper for
    the native machine to show the LED (Machine.leds()). LED current and
    brightness are analog and not modelled.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    rows, paths, missing = {}, [], []
    for board in ('system', 'gpu', 'io', 'storage', 'eink'):
        circuit = cards[board]
        pcb = system_board if board == 'system' else (card_boards or {}).get(board)
        routed = pcb is not None and Path(pcb).is_file()
        rows[board] = []
        for (ref, pin), label in sorted(circuit.pin_names.items()):
            if ref != 'U1' or not label.startswith('GPIO') or (ref, pin) not in circuit.pins:
                continue
            source_net = circuit.pins[(ref, pin)]
            others = [n for n in circuit.nets[source_net] if n != (ref, pin)]
            if len(others) != 1 or circuit.components[others[0][0]][1] != ('Device', 'R'):
                continue
            resistor = others[0]
            far = (resistor[0], '2' if resistor[1] == '1' else '1')
            anode_net = circuit.pins.get(far)
            leds = [n for n in circuit.nets.get(anode_net, ()) if n != far]
            if len(leds) != 1 or circuit.components[leds[0][0]][1] != ('Device', 'LED') or \
                    circuit.pin_names.get(leds[0]) != 'A':
                continue
            diode = leds[0][0]
            cathode = named_pin(circuit, diode, 'K')
            if node(circuit, *cathode) != '/GND':
                raise ValueError(f'{board}:{diode}: indicator LED cathode must be on GND')
            connected = True
            for net, first, last in ((source_net, (ref, pin), resistor), (anode_net, far, leds[0])):
                mm = None
                if routed:
                    mm = routed_distances(Path(pcb), net, first, [last])[f'{last[0]}.{last[1]}']
                paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                              'route_mm': mm, 'runtime': f'{board}_led_{source_net.lstrip("/")}'})
                if mm is None:
                    connected = False
                    missing.append(f'{board}:{net.lstrip("/")}_led_copper')
            rows[board].append({'gpio': int(label[4:].split('/')[0]), 'net': source_net.lstrip('/'),
                                'anode_net': anode_net.lstrip('/'), 'led': diode,
                                'connected': connected})
    return rows, paths, missing


RAIL_NET = re.compile(r'/(?:\+?\d+V\d*|5V_SYS)')     # /+3V3 /3V3 /+5V /+1V2 /1V2 /5V_SYS


def rail_indicator_routes(circuits, pcbs):
    """Rail indicator LEDs (power, 5V/3V3/1V2 present), leg by leg on copper.

    Two shapes, found by netlist topology and net names only (never by
    reference): rail -> resistor -> LED anode with the cathode on GND, and
    (the 1V2 indicators) the same with the cathode on an NPN collector whose
    emitter is on GND and whose base is fed from a rail through one
    resistor. An indicator counts as lit while every signal leg is on routed
    copper (the rail and GND pads sit on planes: DRC checks them); the rail
    itself is assumed present, so this models the wiring of the indicator,
    not LED current, brightness or the rail (POW-*, -005 rows).
    Returns ({board: rows}, paths, missing).
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    rows, paths, missing = {}, [], []
    for board, circuit in circuits.items():
        pcb = pcbs.get(board)
        rows[board] = []
        for ref, (_, source) in sorted(circuit.components.items()):
            if source != ('Device', 'LED'):
                continue
            anode, cathode = named_pin(circuit, ref, 'A'), named_pin(circuit, ref, 'K')
            legs = []

            def feeder(net, pad):
                """The one resistor on `net` besides `pad`, if its far side is a rail."""
                others = [n for n in circuit.nets[net] if n != pad]
                if len(others) != 1 or circuit.components[others[0][0]][1] != ('Device', 'R'):
                    return None
                far = circuit.pins.get((others[0][0], '2' if others[0][1] == '1' else '1'))
                return (others[0], far) if far and RAIL_NET.fullmatch(far) else None

            anode_net, cathode_net = node(circuit, *anode), node(circuit, *cathode)
            fed = feeder(anode_net, anode)
            if fed is None:
                continue
            legs.append((anode_net, fed[0], anode))
            transistor = None
            if cathode_net != '/GND':
                pads = [n for n in circuit.nets[cathode_net] if n != cathode]
                if len(pads) != 1 or circuit.components[pads[0][0]][0] != 'MMBT3904' or \
                        circuit.pin_names.get(pads[0]) != 'C':
                    continue
                transistor = pads[0][0]
                base = named_pin(circuit, transistor, 'B')
                base_fed = feeder(node(circuit, *base), base)
                if base_fed is None or node(circuit, *named_pin(circuit, transistor, 'E')) != '/GND':
                    continue
                legs += [(cathode_net, cathode, pads[0]), (node(circuit, *base), base, base_fed[0])]
            connected = True
            nets = []
            for net, first, last in legs:
                mm = None
                if pcb is not None and Path(pcb).is_file():
                    mm = routed_distances(Path(pcb), net, first, [last])[f'{last[0]}.{last[1]}']
                paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                              'route_mm': mm, 'runtime': f'{board}_rail_led_{ref}'})
                nets.append(net.lstrip('/'))
                if mm is None:
                    connected = False
                    missing.append(f'{board}:{net.lstrip("/")}_rail_led_copper')
            rows[board].append({'led': ref, 'rail': fed[1].lstrip('/'), 'transistor': transistor,
                                'nets': nets, 'connected': connected})
    return rows, paths, missing


def fpga_config_routes(main, cpu, system, main_board, cpu_board, system_board):
    """The two iCE40s' configuration chain, leg by leg on routed copper.

    Returns (links, paths, missing, legs_by_net). `links` are the native
    machine's fpga_links (emu/machine/fpgaconfig.h): each is the conjunction
    of its copper legs. legs_by_net maps (board, net) to whether every leg
    on that net is present, so an open leg restores the net's coverage gap.
    Pins are bound by net name and package pin name; a renamed or moved
    net fails here with the name it expected.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    circuits = {'main': (main, main_board), 'cpu': (cpu, cpu_board),
                'system': (system, system_board)}
    paths, missing, legs_by_net = [], [], {}

    def pad(board, ref, net=None, name=None):
        circuit = circuits[board][0]
        if name is not None:
            found = named_pin(circuit, ref, name)
            if net is not None and node(circuit, *found) != f'/{net}':
                raise ValueError(f'{board}:{ref} {name}: expected on {net}, found {node(circuit, *found)}')
            return found
        pads = [(r, p) for (r, p), attached in circuit.pins.items()
                if r == ref and attached == f'/{net}']
        if len(pads) != 1:
            raise ValueError(f'{board}:{net}: expected one {ref} pad, found {pads}')
        return pads[0]

    def leg(board, net, first, last, flag):
        circuit, pcb = circuits[board]
        if node(circuit, *first) != f'/{net}' or node(circuit, *last) != f'/{net}':
            raise ValueError(f'{board}:{net}: {first} or {last} is no longer on this net')
        mm = None
        if pcb is not None and Path(pcb).is_file():
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': f'fpga_{flag}'})
        ok = mm is not None
        legs_by_net[(board, f'/{net}')] = legs_by_net.get((board, f'/{net}'), True) and ok
        if not ok:
            missing.append(f'{board}:{net}_fpga_{flag}:{first[0]}.{first[1]}->{last[0]}.{last[1]}')
        return ok

    def pullup(board, net, rail):
        """The resistor from `net` to `rail`; returns its pad on `net`."""
        circuit = circuits[board][0]
        found = [r for r, other in circuit.pulls(rail) if other == f'/{net}']
        if len(found) != 1 or found[0].value != '10k':
            raise ValueError(f'{board}:{net}: expected one 10k pull-up to {rail}')
        return next((found[0].ref, p) for p in ('1', '2') if node(circuit, found[0].ref, p) == f'/{net}')

    def system_contact(main_pin):
        number = int(main_pin)
        return ('J2', f'A{number}' if number <= 32 else f'B{number - 32}')

    def socket_bridge(main_net, card_board, card_net, main_ref, card_ref):
        """A main socket contact and the card contact it mates with."""
        pins = [p for (r, p), n in main.pins.items() if r == main_ref and n == f'/{main_net}']
        if len(pins) != 1:
            raise ValueError(f'main:{main_net}: expected one {main_ref} contact')
        mate = system_contact(pins[0]) if card_board == 'system' else (card_ref, pins[0])
        if node(circuits[card_board][0], *mate) != f'/{card_net}':
            raise ValueError(f'main.{main_ref}.{pins[0]} ({main_net}) mates with '
                             f'{card_board}.{mate[0]}.{mate[1]}, not {card_net}')
        return (main_ref, pins[0]), mate

    links = {}
    # --- the chipset: U7 boots from U8 over FL0; CRESET_B pulled up by a 10k
    u7 = {k: pad('main', 'U7', name=v) for k, v in (('sck', 'IOB_107_SCK'), ('sdo', 'IOB_105_SDO'),
                                                     ('sdi', 'IOB_106_SDI'), ('ss', 'IOB_108_SS'),
                                                     ('creset', '~{CRESET}'), ('cdone', 'CDONE'))}
    u8 = {k: pad('main', 'U8', name=v) for k, v in (('clk', 'CLK'), ('di', 'DI(IO0)'),
                                                     ('do', 'DO(IO1)'), ('cs', '~{CS}'))}
    config = [leg('main', 'FL0_SCK', u7['sck'], u8['clk'], 'chipset_config'),
              leg('main', 'FL0_MOSI', u7['sdo'], u8['di'], 'chipset_config'),
              leg('main', 'FL0_MISO', u8['do'], u7['sdi'], 'chipset_config'),
              leg('main', 'FL0_nCS', u7['ss'], u8['cs'], 'chipset_config'),
              leg('main', 'CHIPSET_nCRESET', pullup('main', 'CHIPSET_nCRESET', '/+3V3'), u7['creset'],
                  'chipset_config')]
    links['chipsetConfigCopper'] = all(config)
    # --- the CPU card: U1 boots from U2 over FL1; WP/HOLD and CRESET_B pulled up
    c1 = {k: pad('cpu', 'U1', name=v) for k, v in (('sck', 'IOB_107_SCK'), ('sdo', 'IOB_105_SDO'),
                                                    ('sdi', 'IOB_106_SDI'), ('ss', 'IOB_108_SS'),
                                                    ('creset', '~{CRESET}'), ('cdone', 'CDONE'))}
    c2 = {k: pad('cpu', 'U2', name=v) for k, v in (('clk', 'CLK'), ('di', 'DI/IO_{0}'),
                                                    ('do', 'DO/IO_{1}'), ('cs', '~{CS}'),
                                                    ('wp', '~{WP}/IO_{2}'),
                                                    ('hold', '~{HOLD}/~{RESET}/IO_{3}'))}
    wphold = pullup('cpu', 'FL1_WPHOLD', '/3V3')
    config = [leg('cpu', 'FL1_SCK', c1['sck'], c2['clk'], 'cpu_config'),
              leg('cpu', 'FL1_MOSI', c1['sdo'], c2['di'], 'cpu_config'),
              leg('cpu', 'FL1_MISO', c2['do'], c1['sdi'], 'cpu_config'),
              leg('cpu', 'FL1_nCS', c1['ss'], c2['cs'], 'cpu_config'),
              leg('cpu', 'FL1_WPHOLD', wphold, c2['wp'], 'cpu_config'),
              leg('cpu', 'FL1_WPHOLD', wphold, c2['hold'], 'cpu_config'),
              leg('cpu', 'CRESET_n', pullup('cpu', 'CRESET_n', '/3V3'), c1['creset'], 'cpu_config')]
    links['cpuConfigCopper'] = all(config)
    # --- sysctl GPIO6/7/16/17: CRESET_B out (open drain), CDONE in
    s1 = lambda gpio: named_pin(system, 'U1', gpio)  # noqa: E731
    j3, sj2 = socket_bridge('CHIPSET_nCRESET', 'system', 'CHIPSET_nCRESET', 'J3', 'J2')
    links['chipsetCreset'] = all([leg('system', 'CHIPSET_nCRESET', s1('GPIO6'), sj2, 'chipset_creset'),
                                  leg('main', 'CHIPSET_nCRESET', j3, u7['creset'], 'chipset_creset')])
    j3, sj2 = socket_bridge('CHIPSET_CDONE', 'system', 'CHIPSET_CDONE', 'J3', 'J2')
    links['chipsetCdoneSysctl'] = all([
        leg('main', 'CHIPSET_CDONE', u7['cdone'], j3, 'chipset_cdone'),
        leg('main', 'CHIPSET_CDONE', pullup('main', 'CHIPSET_CDONE', '/+3V3'), u7['cdone'], 'chipset_cdone'),
        leg('system', 'CHIPSET_CDONE', sj2, s1('GPIO7'), 'chipset_cdone')])
    j3, sj2 = socket_bridge('CPUCARD_nCRESET', 'system', 'CPUCARD_nCRESET', 'J3', 'J2')
    j2, cj1 = socket_bridge('CPUCARD_nCRESET', 'cpu', 'CRESET_n', 'J2', 'J1')
    links['cpuCreset'] = all([leg('system', 'CPUCARD_nCRESET', s1('GPIO16'), sj2, 'cpu_creset'),
                              leg('main', 'CPUCARD_nCRESET', j3, j2, 'cpu_creset'),
                              leg('cpu', 'CRESET_n', cj1, c1['creset'], 'cpu_creset')])
    j3, sj2 = socket_bridge('CPU_CDONE', 'system', 'CPUCARD_CDONE', 'J3', 'J2')
    j2, cj1 = socket_bridge('CPU_CDONE', 'cpu', 'CDONE', 'J2', 'J1')
    card_leg = leg('cpu', 'CDONE', c1['cdone'], cj1, 'cpu_cdone')
    card_pull = leg('cpu', 'CDONE', pullup('cpu', 'CDONE', '/3V3'), c1['cdone'], 'cpu_cdone')
    main_pull = leg('main', 'CPU_CDONE', pullup('main', 'CPU_CDONE', '/+3V3'), j2, 'cpu_cdone')
    links['cpuCdoneCard'] = card_leg
    links['cpuCdoneMain'] = leg('main', 'CPU_CDONE', j2, pad('main', 'U7', 'CPU_CDONE'), 'cpu_cdone')
    links['cpuCdonePullup'] = main_pull or (card_leg and card_pull)
    links['cpuCdoneSysctl'] = card_leg and all([leg('main', 'CPU_CDONE', j2, j3, 'cpu_cdone'),
                                                leg('system', 'CPUCARD_CDONE', sj2, s1('GPIO17'), 'cpu_cdone')])
    # --- sysctl SPI1 to each flash: MCU pad, 33R, socket, flash pad
    def flash_bus(bus, gpios, flash_pads, via_cpu):
        ok = True
        for signal, gpio, series in (('SCK', gpios[0], True), ('MOSI', gpios[1], True),
                                     ('MISO', gpios[2], False), ('nCS', gpios[3], True)):
            net = f'{bus}_{signal}'
            mcu = s1(gpio)
            j3, sj2 = socket_bridge(net, 'system', net, 'J3', 'J2')
            if series:
                resistor = circuits['system'][0].series(mcu, sj2)
                if resistor is None or resistor.value != '33':
                    raise ValueError(f'system:{net}: expected a 33R from {gpio} to the socket')
                near = next(p for p in ('1', '2') if node(system, resistor.ref, p) == f'/{net}_MCU')
                far = '2' if near == '1' else '1'
                ok &= leg('system', f'{net}_MCU', mcu, (resistor.ref, near), f'{bus.lower()}_sysctl')
                ok &= leg('system', net, (resistor.ref, far), sj2, f'{bus.lower()}_sysctl')
            else:
                ok &= leg('system', net, sj2, mcu, f'{bus.lower()}_sysctl')
            if via_cpu:
                j2, cj1 = socket_bridge(net, 'cpu', net, 'J2', 'J1')
                ok &= leg('main', net, j3, j2, f'{bus.lower()}_sysctl')
                ok &= leg('cpu', net, cj1, flash_pads[signal], f'{bus.lower()}_sysctl')
            else:
                ok &= leg('main', net, j3, flash_pads[signal], f'{bus.lower()}_sysctl')
        return ok
    links['fl0Sysctl'] = flash_bus('FL0', ('GPIO10', 'GPIO11', 'GPIO12', 'GPIO13'),
                                   {'SCK': u8['clk'], 'MOSI': u8['di'], 'MISO': u8['do'],
                                    'nCS': u8['cs']}, False)
    links['fl1Sysctl'] = flash_bus('FL1', ('GPIO14', 'GPIO15', 'GPIO8', 'GPIO9'),
                                   {'SCK': c2['clk'], 'MOSI': c2['di'], 'MISO': c2['do'],
                                    'nCS': c2['cs']}, True) and links['cpuConfigCopper']
    # --- D5 lights with CDONE: U7.65 → R55 → Q2 base; +3V3 → R56 → D5 → Q2 collector
    r55 = circuits['main'][0].series(u7['cdone'], pad('main', 'Q2', name='B'))
    if r55 is None:
        raise ValueError('main: CDONE LED driver resistor missing')
    q2 = {k: pad('main', 'Q2', name=k) for k in ('B', 'C', 'E')}
    d5 = {k: pad('main', 'D5', name=k) for k in ('A', 'K')}
    if node(main, *q2['E']) != '/GND' or node(main, *d5['K']) != node(main, *q2['C']):
        raise ValueError('main: CDONE LED D5 must sink through Q2 to GND')
    anode_res = [r for r, other in main.pulls('/+3V3') if other == node(main, *d5['A'])]
    if len(anode_res) != 1:
        raise ValueError('main: CDONE LED D5 anode resistor to +3V3 missing')
    anode_pad = next((anode_res[0].ref, p) for p in ('1', '2')
                     if node(main, anode_res[0].ref, p) == node(main, *d5['A']))
    near = next(p for p in ('1', '2') if node(main, r55.ref, p) == '/CHIPSET_CDONE')
    far = '2' if near == '1' else '1'
    links['cdoneLed'] = all([
        leg('main', 'CHIPSET_CDONE', u7['cdone'], (r55.ref, near), 'cdone_led'),
        leg('main', node(main, *q2['B']).lstrip('/'), (r55.ref, far), q2['B'], 'cdone_led'),
        leg('main', node(main, *q2['C']).lstrip('/'), q2['C'], d5['K'], 'cdone_led'),
        leg('main', node(main, *d5['A']).lstrip('/'), anode_pad, d5['A'], 'cdone_led')])
    return links, paths, missing, legs_by_net


def system_bridge_source_routes(system, board):
    """RP2040 bridge outputs must cross both legs of their 33-ohm series parts."""
    signals = {'sck': ('BR_SCK_MCU', 'BR_SCK', ('U1', '4'), 'R11', ('J2', 'B13')),
               'mosi': ('BR_MOSI_MCU', 'BR_MOSI', ('U1', '5'), 'R12', ('J2', 'A14')),
               'ncs': ('BR_nCS_MCU', 'BR_nCS', ('U1', '7'), 'R13', ('J2', 'A15'))}
    routed = board is not None and Path(board).is_file()
    if routed:
        sys.path.insert(0, str(ROOT / 'hw/si'))
        from ibis_bus import routed_distances
    links, paths, missing = {}, [], []
    for signal, (source_net, socket_net, mcu, resistor, contact) in signals.items():
        if node(system, *mcu) != f'/{source_net}' or node(system, *contact) != f'/{socket_net}' or \
                path(system, mcu, contact, '33') != resistor:
            raise ValueError(f'system bridge {signal}: wrong MCU, resistor or socket attachment')
        links[signal] = True
        for net, first, last in ((source_net, mcu, (resistor, '1')),
                                 (socket_net, (resistor, '2'), contact)):
            path(system, first, last)
            length = None
            if routed:
                length = routed_distances(Path(board), f'/{net}', first, [last])[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'system.{first[0]}.{first[1]}',
                          'to': f'system.{last[0]}.{last[1]}',
                          'route_mm': length, 'runtime': f'bridge_{signal}_connected'})
            if length is None:
                links[signal] = False
                missing.append(f'system:{net}_bridge_copper')
    return links, paths, missing


def gpo_indicator_routes(main, board):
    """Bind each native GPO bit to its resistor and grounded LED copper."""
    routed = board is not None and Path(board).is_file()
    if routed:
        sys.path.insert(0, str(ROOT / 'hw/si'))
        from ibis_bus import routed_distances
    links, paths, missing = [], [], []
    for bit in range(8):
        source_net, led_net = f'/GPO{bit}', f'/LED_GPO{bit}'
        source = [(ref, pin) for (ref, pin), net in main.pins.items()
                  if ref == 'U7' and net == source_net]
        resistor, diode = f'R{60 + bit}', f'D{11 + bit}'
        if len(source) != 1 or main.components.get(resistor) != ('1k', ('Device', 'R')) or \
                main.components.get(diode, (None, None))[1] != ('Device', 'LED') or \
                set(main.nets.get(source_net, ())) != {source[0], (resistor, '1')} or \
                set(main.nets.get(led_net, ())) != {(resistor, '2'), (diode, '2')} or \
                main.net(diode, '1') != '/GND':
            raise ValueError(f'GPO{bit}: expected chipset → 1k resistor → LED anode → GND')
        connected = True
        for net, first, last in ((source_net, source[0], (resistor, '1')),
                                 (led_net, (resistor, '2'), (diode, '2'))):
            mm = None
            if routed:
                mm = routed_distances(Path(board), net, first, [last])[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'main.{first[0]}.{first[1]}',
                          'to': f'main.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'gpo_led_{bit}'})
            if mm is None:
                connected = False
                missing.append(f'main:{net.lstrip("/")}_gpo_led_copper')
        links.append(connected)
    return links, paths, missing


def cpu_control_routes(main, cpu, main_board, cpu_board):
    """Two CPU-to-chipset control lines through their real series channels."""
    if cpu.components.get('RN5') != ('68', ('Device', 'R_Pack04')):
        raise ValueError('CPU strobe/RW: missing 68-ohm isolated series pack')
    channels = {
        'strobe': ('FPGA_nSTB', 'CPU_nSTB', ('U1', '23'), ('RN5', '1'),
                   ('RN5', '8'), ('J1', 'B17'), ('J2', 'B17'), ('U7', '31'), 'RN5.1'),
        'rw': ('FPGA_RW', 'CPU_RW', ('U1', '25'), ('RN5', '2'),
               ('RN5', '7'), ('J1', 'B20'), ('J2', 'B20'), ('U7', '29'), 'RN5.2'),
    }
    if main.components.get('R80') != ('10k', ('Device', 'R')) or \
            main.net('R80', '1') != '/+3V3' or main.net('R80', '2') != '/CPU_nSTB':
        raise ValueError('CPU strobe: missing 10k chipset-side pull-up')
    links, paths, missing = {}, [], []
    for signal, (source_net, contact_net, source, series_in, series_out,
                 finger, socket, receiver, series_ref) in channels.items():
        if set(cpu.nets.get(f'/{source_net}', ())) != {source, series_in} or \
                set(cpu.nets.get(f'/{contact_net}', ())) != {series_out, finger} or \
                path(cpu, source, finger, '68') != series_ref or \
                node(main, *socket) != f'/{contact_net}' or \
                node(main, *receiver) != f'/{contact_net}':
            raise ValueError(f'CPU {signal}: wrong FPGA, series pack, socket or chipset pad')
        path(main, socket, receiver)
        expected_main = {socket, receiver} | ({('R80', '2')} if signal == 'strobe' else set())
        if set(main.nets[f'/{contact_net}']) != expected_main:
            raise ValueError(f'CPU {signal}: unexpected main-board load')
        connected = True
        for board, pcb, net, first, last in (
                ('cpu', cpu_board, source_net, source, series_in),
                ('cpu', cpu_board, contact_net, series_out, finger),
                ('main', main_board, contact_net, socket, receiver)):
            mm = None
            if pcb is not None and Path(pcb).is_file():
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                mm = routed_distances(Path(pcb), f'/{net}', first, [last])[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                          'to': f'{board}.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'cpu_{signal}_connected'})
            if mm is None:
                connected = False
                missing.append(f'{board}:{net}_cpu_{signal}_copper')
        links[signal] = connected
    return links, paths, missing


def cpu_ready_route(main, cpu, main_board, cpu_board):
    """Bind chipset /RDY through R33 and both boards to the CPU FPGA pad."""
    source, series_in = ('U7', '28'), ('R33', '1')
    series_out, socket = ('R33', '2'), ('J2', 'B19')
    finger, receiver = ('J1', 'B19'), ('U1', '24')
    if main.components.get('R33') != ('56', ('Device', 'R')) or \
            set(main.nets.get('/CPU_nRDY_SRC', ())) != {source, series_in} or \
            set(main.nets.get('/CPU_nRDY', ())) != {series_out, socket} or \
            set(cpu.nets.get('/CPU_nRDY', ())) != {finger, receiver} or \
            path(main, source, socket, '56') != 'R33':
        raise ValueError('CPU /RDY: wrong chipset source, R33, socket or CPU pad')
    paths, missing = [], []
    for board, pcb, net, first, last in (
            ('main', main_board, 'CPU_nRDY_SRC', source, series_in),
            ('main', main_board, 'CPU_nRDY', series_out, socket),
            ('cpu', cpu_board, 'CPU_nRDY', finger, receiver)):
        mm = None
        if pcb is not None and Path(pcb).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[
                f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                      'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': 'cpu_ready_connected'})
        if mm is None:
            missing.append(f'{board}:{net}_cpu_ready_copper')
    return not missing, paths, missing


def cpu_sync_route(main, cpu, main_board, cpu_board):
    """Bind the CPU instruction-boundary output to the chipset trace input."""
    source, series_in = ('U1', '26'), ('RN5', '3')
    series_out, finger = ('RN5', '6'), ('J1', 'B22')
    socket, receiver = ('J2', 'B22'), ('U7', '26')
    if cpu.components.get('RN5') != ('68', ('Device', 'R_Pack04')) or \
            set(cpu.nets.get('/FPGA_SYNC', ())) != {source, series_in} or \
            set(cpu.nets.get('/CPU_SYNC', ())) != {series_out, finger} or \
            set(main.nets.get('/CPU_SYNC', ())) != {socket, receiver} or \
            path(cpu, source, finger, '68') != 'RN5.3':
        raise ValueError('CPU SYNC: wrong FPGA source, RN5, socket or chipset pad')
    paths, missing = [], []
    for board, pcb, net, first, last in (
            ('cpu', cpu_board, 'FPGA_SYNC', source, series_in),
            ('cpu', cpu_board, 'CPU_SYNC', series_out, finger),
            ('main', main_board, 'CPU_SYNC', socket, receiver)):
        mm = None
        if pcb is not None and Path(pcb).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[
                f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                      'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': 'cpu_sync_connected'})
        if mm is None:
            missing.append(f'{board}:{net}_cpu_sync_copper')
    return not missing, paths, missing


def cpu_status_routes(main, cpu, main_board, cpu_board):
    """Bind FPGA HALTED/WAITING through RN8 and the CPU socket to U7."""
    channels = {
        'halted': ('FPGA_HALTED', 'CPU_HALTED', ('U1', '60'), ('RN8', '3'),
                   ('RN8', '6'), ('J1', 'B44'), ('J2', 'B44'), ('U7', '137'), 'RN8.3'),
        'waiting': ('FPGA_WAITING', 'CPU_WAITING', ('U1', '61'), ('RN8', '4'),
                    ('RN8', '5'), ('J1', 'B46'), ('J2', 'B46'), ('U7', '130'), 'RN8.4'),
    }
    if cpu.components.get('RN8') != ('68', ('Device', 'R_Pack04')):
        raise ValueError('CPU status: missing 68-ohm isolated RN8 series pack')
    links, paths, missing = {}, [], []
    for signal, (source_net, contact_net, source, series_in, series_out,
                 finger, socket, receiver, series_ref) in channels.items():
        if set(cpu.nets.get(f'/{source_net}', ())) != {source, series_in} or \
                set(cpu.nets.get(f'/{contact_net}', ())) != {series_out, finger} or \
                set(main.nets.get(f'/{contact_net}', ())) != {socket, receiver} or \
                path(cpu, source, finger, '68') != series_ref:
            raise ValueError(f'CPU {signal}: wrong FPGA, RN8, socket or chipset pad')
        connected = True
        for board, pcb, net, first, last in (
                ('cpu', cpu_board, source_net, source, series_in),
                ('cpu', cpu_board, contact_net, series_out, finger),
                ('main', main_board, contact_net, socket, receiver)):
            mm = None
            if pcb is not None and Path(pcb).is_file():
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                mm = routed_distances(Path(pcb), f'/{net}', first, [last])[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                          'to': f'{board}.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'cpu_{signal}_connected'})
            if mm is None:
                connected = False
                missing.append(f'{board}:{net}_cpu_{signal}_copper')
        links[signal] = connected
    return links, paths, missing


def main_cpu_data_routes(main, board):
    """Bind chipset data pads, eight 56-ohm channels and weak keepers."""
    chipset_pads = ('20', '18', '19', '17', '9', '7', '10', '8')
    socket_pads = ('B23', 'B25', 'B26', 'B28', 'B29', 'B31', 'B32', 'B34')
    loaded_board = parsed_tree = None
    if board is not None and Path(board).is_file():
        sys.path.insert(0, str(ROOT / 'hw/si'))
        from ibis_bus import routed_distances
        loaded_board, parsed_tree = cpu_board_geometry(str(Path(board).resolve()))
    links, paths, missing = [], [], []
    for bit, (chipset_pad, socket_pad) in enumerate(zip(chipset_pads, socket_pads)):
        source_net, contact_net = f'/CPU_D{bit}_SRC', f'/CPU_D{bit}'
        source, series_in = ('U7', chipset_pad), (f'R{21 + bit}', '1')
        series_out, keeper, socket = (f'R{21 + bit}', '2'), \
            (f'R{90 + bit}', '2'), ('J2', socket_pad)
        if main.components.get(series_in[0]) != ('56', ('Device', 'R')) or \
                main.components.get(keeper[0]) != ('47k', ('Device', 'R')) or \
                main.net(keeper[0], '1') != '/+3V3' or \
                set(main.nets.get(source_net, ())) != {source, series_in} or \
                set(main.nets.get(contact_net, ())) != {series_out, keeper, socket} or \
                path(main, source, socket, '56') != series_in[0]:
            raise ValueError(f'CPU D{bit}: wrong chipset pad, series part, keeper or socket')
        connected = True
        for net, first, last in ((source_net, source, series_in),
                                 (contact_net, series_out, socket),
                                 (contact_net, keeper, socket)):
            mm = None
            if loaded_board is not None:
                mm = routed_distances(Path(board), net, first, [last],
                                      loaded_board=loaded_board, parsed_tree=parsed_tree)[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'main.{first[0]}.{first[1]}',
                          'to': f'main.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'main_cpu_data{bit}_connected'})
            if mm is None:
                connected = False
                missing.append(f'main:{net.lstrip("/")}_cpu_data{bit}_copper')
        links.append(connected)
    return links, paths, missing


def cpu_irq_routes(main, cpu, main_board, cpu_board):
    """Bind all four IRQ outputs through main series parts and CPU pads."""
    chipset_pads = ('1', '141', '2', '142')
    fpga_pads = ('47', '48', '49', '52')
    socket_pads = ('B35', 'B37', 'B38', 'B40')
    geometry = {}
    for board_name, board_path in (('main', main_board), ('cpu', cpu_board)):
        if board_path is not None and Path(board_path).is_file():
            geometry[board_name] = cpu_board_geometry(str(Path(board_path).resolve()))
    links, paths, missing = [], [], []
    for bit, (chipset_pad, fpga_pad, socket_pad) in enumerate(
            zip(chipset_pads, fpga_pads, socket_pads)):
        source_net, contact_net = f'/CPU_IRQ{bit}_SRC', f'/CPU_IRQ{bit}'
        resistor = f'R{29 + bit}'
        chipset, series_in = ('U7', chipset_pad), (resistor, '1')
        series_out, main_socket = (resistor, '2'), ('J2', socket_pad)
        cpu_socket, fpga = ('J1', socket_pad), ('U1', fpga_pad)
        if main.components.get(resistor) != ('56', ('Device', 'R')) or \
                set(main.nets.get(source_net, ())) != {chipset, series_in} or \
                set(main.nets.get(contact_net, ())) != {series_out, main_socket} or \
                set(cpu.nets.get(contact_net, ())) != {cpu_socket, fpga} or \
                path(main, chipset, main_socket, '56') != resistor:
            raise ValueError(f'CPU IRQ{bit}: wrong chipset, series part, socket or FPGA pad')
        connected = True
        for board_name, board_path, net, first, last in (
                ('main', main_board, source_net, chipset, series_in),
                ('main', main_board, contact_net, series_out, main_socket),
                ('cpu', cpu_board, contact_net, cpu_socket, fpga)):
            mm = None
            if board_name in geometry:
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                loaded_board, parsed_tree = geometry[board_name]
                mm = routed_distances(Path(board_path), net, first, [last],
                                      loaded_board=loaded_board, parsed_tree=parsed_tree)[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'{board_name}.{first[0]}.{first[1]}',
                          'to': f'{board_name}.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'cpu_irq{bit}_connected'})
            if mm is None:
                connected = False
                missing.append(f'{board_name}:{net.lstrip("/")}_cpu_irq{bit}_copper')
        links.append(connected)
    return links, paths, missing


def cpu_timer_exp_routes(main, cpu, main_board, cpu_board):
    """Bind both CPU timer pulses through RN8, the socket, and chipset pads."""
    geometry = {}
    for board_name, board_path in (('main', main_board), ('cpu', cpu_board)):
        if board_path is not None and Path(board_path).is_file():
            geometry[board_name] = cpu_board_geometry(str(Path(board_path).resolve()))
    if cpu.components.get('RN8') != ('68', ('Device', 'R_Pack04')):
        raise ValueError('CPU timer expiry: wrong RN8 series pack')
    links, paths, missing = [], [], []
    for bit, (fpga_pad, in_pad, out_pad, socket_pad, chipset_pad) in enumerate(
            (('55', '1', '8', 'B41', '136'),
             ('56', '2', '7', 'B43', '129'))):
        source_net, contact_net = f'/FPGA_TMR_EXP{bit}', f'/CPU_TMR_EXP{bit}'
        fpga, series_in = ('U1', fpga_pad), ('RN8', in_pad)
        series_out, cpu_socket = ('RN8', out_pad), ('J1', socket_pad)
        main_socket, chipset = ('J2', socket_pad), ('U7', chipset_pad)
        if set(cpu.nets.get(source_net, ())) != {fpga, series_in} or \
                set(cpu.nets.get(contact_net, ())) != {series_out, cpu_socket} or \
                set(main.nets.get(contact_net, ())) != {main_socket, chipset}:
            raise ValueError(f'CPU timer expiry {bit}: wrong FPGA, RN8, socket or chipset pad')
        connected = True
        for board_name, board_path, net, first, last in (
                ('cpu', cpu_board, source_net, fpga, series_in),
                ('cpu', cpu_board, contact_net, series_out, cpu_socket),
                ('main', main_board, contact_net, main_socket, chipset)):
            mm = None
            if board_name in geometry:
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                loaded_board, parsed_tree = geometry[board_name]
                mm = routed_distances(Path(board_path), net, first, [last],
                                      loaded_board=loaded_board, parsed_tree=parsed_tree)[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'{board_name}.{first[0]}.{first[1]}',
                          'to': f'{board_name}.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'cpu_tmr_exp{bit}_connected'})
            if mm is None:
                connected = False
                missing.append(f'{board_name}:{net.lstrip("/")}_cpu_tmr_exp{bit}_copper')
        links.append(connected)
    return links, paths, missing


def system_usb_routes(system, board):
    """Bind the system MCU CDC PHY through series, Type-C, and ESD branches."""
    loaded_board = parsed_tree = None
    if board is not None and Path(board).is_file():
        loaded_board, parsed_tree = cpu_board_geometry(str(Path(board).resolve()))
    orientation = {'A': True, 'B': True}
    paths, missing = [], []
    if system.components.get('U3') != ('USBLC6-2SC6', ('Power_Protection', 'USBLC6-2SC6')):
        raise ValueError('system USB: wrong Type-C ESD array')
    for signal, mcu_pad, resistor, contacts, esd_pads in (
            ('DM', '46', 'R3', ('A7', 'B7'), ('3', '4')),
            ('DP', '47', 'R2', ('A6', 'B6'), ('1', '6'))):
        source_net, contact_net = f'/USB_{signal}_MCU', f'/USB_{signal}'
        source, series_in, series_out = ('U1', mcu_pad), (resistor, '1'), (resistor, '2')
        contacts_at_j1 = [('J1', pin) for pin in contacts]
        esd = [('U3', pin) for pin in esd_pads]
        if system.components.get(resistor) != ('27', ('Device', 'R')) or \
                set(system.nets.get(source_net, ())) != {source, series_in} or \
                set(system.nets.get(contact_net, ())) != {series_out, *contacts_at_j1, *esd} or \
                path(system, source, contacts_at_j1[0], '27') != resistor:
            raise ValueError(f'system USB {signal}: wrong PHY, series part, contacts or ESD pads')
        for net, first, last, branch in (
                (source_net, source, series_in, 'source'),
                *((contact_net, series_out, target, f'contact_{kind}')
                  for kind, target in zip(('A', 'B'), contacts_at_j1)),
                *((contact_net, series_out, target, 'esd') for target in esd)):
            mm = None
            if loaded_board is not None:
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                mm = routed_distances(Path(board), net, first, [last],
                                      loaded_board=loaded_board, parsed_tree=parsed_tree)[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'system.{first[0]}.{first[1]}',
                          'to': f'system.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'system_usb_{branch}'})
            if mm is None:
                missing.append(f'system:{net.lstrip("/")}_{branch}_copper')
                if branch == 'source':
                    orientation = {'A': False, 'B': False}
                elif branch.startswith('contact_'):
                    orientation[branch[-1]] = False
    # The Type-C Rd on each CC line (5.1 k to GND): the host sees a sink, and
    # so supplies VBUS and talks, only in the orientation whose CC line has
    # its Rd wired. A plug one way round uses CC1 (A5, orientation A), the
    # other CC2 (B5, orientation B).
    for side, net, contact, resistor in (('A', '/USB_CC1', ('J1', 'A5'), 'R4'),
                                         ('B', '/USB_CC2', ('J1', 'B5'), 'R5')):
        if system.components.get(resistor) != ('5.1k', ('Device', 'R')) or \
                set(system.nets.get(net, ())) != {contact, (resistor, '1')} or \
                node(system, resistor, '2') != '/GND':
            raise ValueError(f'system USB {net}: Rd must be 5.1k from the receptacle CC contact to GND')
        mm = None
        if loaded_board is not None:
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            mm = routed_distances(Path(board), net, contact, [(resistor, '1')],
                                  loaded_board=loaded_board, parsed_tree=parsed_tree)[f'{resistor}.1']
        paths.append({'from': f'system.{contact[0]}.{contact[1]}', 'to': f'system.{resistor}.1',
                      'route_mm': mm, 'runtime': f'system_usb_cc_{side}'})
        if mm is None:
            missing.append(f'system:{net.lstrip("/")}_cc_copper')
            orientation[side] = False
    return orientation, paths, missing


def system_usb_vbus_routes(system, board):
    """Bind the host-VBUS sense switch to the sysctl GPIO29 input."""
    expected_parts = {'R10': '10k', 'R22': '100k', 'R23': '10k'}
    for ref, value in expected_parts.items():
        if system.components.get(ref) != (value, ('Device', 'R')):
            raise ValueError(f'system USB VBUS: {ref} must be {value}')
    if system.components.get('Q1') != ('2N7002', ('Transistor_FET', '2N7002')):
        raise ValueError('system USB VBUS: Q1 must be a 2N7002')
    expected_nets = {
        '/USB_VBUS': {('J1', 'A4B9'), ('J1', 'B4A9'), ('R10', '1')},
        '/VBUS_GATE': {('R10', '2'), ('R22', '1'), ('Q1', '1')},
        '/USB_nVBUS': {('Q1', '3'), ('R23', '2'), ('U1', '41')},
    }
    for net, pins in expected_nets.items():
        if set(system.nets.get(net, ())) != pins:
            raise ValueError(f'system USB VBUS: wrong pins on {net}')
    if node(system, 'R22', '2') != '/GND' or node(system, 'Q1', '2') != '/GND' or \
            node(system, 'R23', '1') != '/+3V3':
        raise ValueError('system USB VBUS: sense switch return or pull-up is missing')
    legs = (
        ('/USB_VBUS', ('J1', 'A4B9'), ('R10', '1')),
        ('/USB_VBUS', ('J1', 'B4A9'), ('R10', '1')),
        ('/VBUS_GATE', ('R10', '2'), ('Q1', '1')),
        ('/VBUS_GATE', ('R10', '2'), ('R22', '1')),
        ('/USB_nVBUS', ('Q1', '3'), ('U1', '41')),
        ('/USB_nVBUS', ('R23', '2'), ('U1', '41')),
    )
    loaded_board = parsed_tree = None
    if board is not None and Path(board).is_file():
        loaded_board, parsed_tree = cpu_board_geometry(str(Path(board).resolve()))
    paths, missing = [], []
    route_lengths = []
    for net, first, last in legs:
        mm = None
        if loaded_board is not None:
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            mm = routed_distances(Path(board), net, first, [last],
                                  loaded_board=loaded_board, parsed_tree=parsed_tree)[
                f'{last[0]}.{last[1]}']
        paths.append({'from': f'system.{first[0]}.{first[1]}',
                      'to': f'system.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': 'sysctl_usb_vbus_connected'})
        route_lengths.append(mm)
        if mm is None:
            missing.append(f'system:{net.lstrip("/")}_{first[0]}.{first[1]}_to_{last[0]}.{last[1]}_copper')
    common = all(mm is not None for mm in route_lengths[2:])
    return {'A': common and route_lengths[0] is not None,
            'B': common and route_lengths[1] is not None}, paths, missing


def io_usb_host_routes(io, board):
    """Bind the keyboard host PHY, series parts, receptacle, and ESD copper."""
    loaded_board = parsed_tree = None
    if board is not None and Path(board).is_file():
        loaded_board, parsed_tree = cpu_board_geometry(str(Path(board).resolve()))
    if io.components.get('U6') != ('USBLC6-2SC6', ('Power_Protection', 'USBLC6-2SC6')):
        raise ValueError('IO USB host: wrong ESD array')
    paths, missing = [], []
    host_connected = True
    for signal, mcu_pad, resistor, contact, esd_pads in (
            ('DM', '46', 'R14', '2', ('1', '6')),
            ('DP', '47', 'R15', '3', ('3', '4'))):
        source_net, contact_net = f'/USB_{signal}', f'/USB_CONN_{signal}'
        source, series_in, series_out = ('U1', mcu_pad), (resistor, '1'), (resistor, '2')
        socket, esd = ('J2', contact), [('U6', pin) for pin in esd_pads]
        if io.components.get(resistor) != ('27R', ('Device', 'R')) or \
                set(io.nets.get(source_net, ())) != {source, series_in} or \
                set(io.nets.get(contact_net, ())) != {series_out, socket, *esd} or \
                path(io, source, socket, '27R') != resistor:
            raise ValueError(f'IO USB host {signal}: wrong PHY, series part, contact or ESD pads')
        for net, first, last, branch in (
                (source_net, source, series_in, 'source'),
                (contact_net, series_out, socket, 'contact'),
                *((contact_net, series_out, pad, 'esd') for pad in esd)):
            mm = None
            if loaded_board is not None:
                sys.path.insert(0, str(ROOT / 'hw/si'))
                from ibis_bus import routed_distances
                mm = routed_distances(Path(board), net, first, [last],
                                      loaded_board=loaded_board, parsed_tree=parsed_tree)[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'io.{first[0]}.{first[1]}',
                          'to': f'io.{last[0]}.{last[1]}',
                          'route_mm': mm, 'runtime': f'io_usb_host_{branch}'})
            if mm is None:
                missing.append(f'io:{net.lstrip("/")}_{branch}_copper')
                if branch != 'esd':
                    host_connected = False
    return host_connected, paths, missing


def io_vbus_routes(io, board):
    """The IO card's keyboard VBUS switch: enable, output and the fault flag.

    GPIO7 (VBUS_EN) drives the TPS2553DBVR-1's EN (100 k pull-down); its OUT
    feeds the receptacle's VBUS; its open-drain FAULT reaches GPIO8
    (VBUS_nFAULT), pulled up by R12 (10 k to 3V3). The firmware sets GPIO7
    high and reports GPIO8 low as VBUS_FAULT (and retries by toggling
    EN). Returns ({'vbus_on', 'nfault_low', 'enable', 'out', 'fault',
    'pullup'}, paths, missing). The keyboard is powered only with VBUS on.
    FAULT is low only on a real overcurrent or over-temperature, which the
    emulator does not inject, and every broken leg reads high (the pull-up,
    the RP2040's own): 'nfault_low' is False, and an open FAULT or pull-up
    leg masks a fault rather than raising one.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    if io.components.get('U5', ('', ''))[0] != 'TPS2553DBVR-1':
        raise ValueError('io VBUS: the switch must be a TPS2553DBVR-1 (U5)')
    en, gpio8 = named_pin(io, 'U1', 'GPIO7'), named_pin(io, 'U1', 'GPIO8')
    enable_pin, out_pin = named_pin(io, 'U5', 'EN'), named_pin(io, 'U5', 'OUT')
    fault_pin = named_pin(io, 'U5', 'FAULT')
    receptacle = next(((r, p) for (r, p), name in io.pin_names.items()
                       if r == 'J2' and name == 'VCC'), None)
    if node(io, *en) != '/VBUS_EN' or node(io, *enable_pin) != '/VBUS_EN' or \
            node(io, *gpio8) != '/VBUS_nFAULT' or node(io, *fault_pin) != '/VBUS_nFAULT' or \
            receptacle is None or node(io, *out_pin) != node(io, *receptacle):
        raise ValueError('io VBUS: GPIO7 must reach the switch EN, its OUT the receptacle VCC, '
                         'and its FAULT GPIO8')
    vbus = node(io, *out_pin)
    pullup = next((r for r in io.resistors if r.value == '10k' and set(r.ends) == {'/3V3', '/VBUS_nFAULT'}), None)
    pulldown = next((r for r in io.resistors if r.value == '100k' and set(r.ends) == {'/VBUS_EN', '/GND'}), None)
    if pullup is None or pulldown is None:
        raise ValueError('io VBUS: 10k from 3V3 on the FAULT/GPIO8 net and a 100k EN pull-down: found '
                         f'{sorted(r.value for r in io.resistors if r.ends and "/VBUS_nFAULT" in r.ends)}')
    pad = lambda resistor, net: next((resistor.ref, q) for q in ('1', '2')  # noqa: E731
                                     if io.pins.get((resistor.ref, q)) == net)
    legs = {'enable': ('/VBUS_EN', en, enable_pin), 'out': (vbus, out_pin, receptacle),
            'fault': ('/VBUS_nFAULT', fault_pin, gpio8),
            'pullup': ('/VBUS_nFAULT', pad(pullup, '/VBUS_nFAULT'), gpio8)}
    routed, paths, missing = {}, [], []
    for key, (net, first, last) in legs.items():
        mm = None
        if board is not None and Path(board).is_file():
            mm = routed_distances(Path(board), net, first, [last])[f'{last[0]}.{last[1]}']
        paths.append({'from': f'io.{first[0]}.{first[1]}', 'to': f'io.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': f'io_vbus_{key}'})
        routed[key] = mm is not None
        if mm is None:
            missing.append(f'io:{net.lstrip("/")}_vbus_{key}_copper')
    routed['vbus_on'] = routed['enable'] and routed['out']
    routed['nfault_low'] = False
    return routed, paths, missing


def prog_port_routes(main, cards, main_board, system_board, card_boards):
    """The card programming port: sysctl to the two 4051 muxes to each slot's SWD pins.

    sysctl's PROG_CLK (GPIO18) and PROG_IO (GPIO19) reach the common pins of
    U11 (clock) and U12 (data); its MUX_SEL0-2 (GPIO20-22) reach both muxes'
    S0-S2. Channel Yn of each mux runs through a 33 ohm resistor to a slot's
    SWCLK / SWDIO contacts and, on an RP2040 card, on to the chip's debug pins
    (U1 SWCLK, SWDIO). Everything is bound by netlist topology and net names:
    the mux channel and select bit each signal really reaches are read from
    the pins (a swapped select or a slot on another channel changes the
    decode), and each leg is measured on the routed copper. The Wi-Fi card's
    SWCLK / SWDIO contacts are its UART0 (an ESP ROM bootloader link, not
    modelled here). Returns (config, paths, missing, whole_nets); config:
    {'sel_bit': the mux select input GPIO20-22 drive, 'sel_whole', 'clk',
    'io' (the common legs), 'channel': the mux channel each slot's pair hangs
    on, 'slot_legs': per slot whether both 33 ohm legs of both channels are
    routed, 'card': per RP2040 card kind whether its two debug legs are}.
    """
    sys.path.insert(0, str(ROOT / 'hw/si'))
    from ibis_bus import routed_distances
    system = cards['system']
    boards = {'main': (main, main_board), 'system': (system, system_board)}
    for kind in ('gpu', 'io', 'storage', 'eink'):
        boards[kind] = (cards[kind], (card_boards or {}).get(kind))
    paths, missing, whole = [], [], {}

    def leg(board, net, first, last, tag):
        circuit, pcb = boards[board]
        mm = None
        if pcb is not None and Path(pcb).is_file():
            mm = routed_distances(Path(pcb), net, first, [last], pad_reach=True)[
                f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}', 'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': f'prog_{tag}'})
        whole[(board, net)] = whole.get((board, net), True) and mm is not None
        if mm is None:
            missing.append(f'{board}:{net.lstrip("/")}_prog_{tag}_copper:{first[0]}.{first[1]}->{last[0]}.{last[1]}')
        return mm is not None

    muxes = {}                                    # ref -> role
    for ref, (value, _) in main.components.items():
        if value == 'CD74HC4051PWR':
            common = named_pin(main, ref, 'A')
            net = node(main, *common)
            muxes[net] = ref
    if set(muxes) != {'/PROG_CLK', '/PROG_IO'}:
        raise ValueError(f'main: the two 4051 muxes must have PROG_CLK and PROG_IO on their common pins, found {sorted(muxes)}')
    clk_mux, io_mux = muxes['/PROG_CLK'], muxes['/PROG_IO']

    def system_signal(gpio):
        pad = named_pin(system, 'U1', gpio)
        net = node(system, *pad)
        card_contact = next(((r, p) for (r, p), n in system.pins.items() if r == 'J2' and n == net), None)
        if card_contact is None:
            raise ValueError(f'system:{net}: no system-slot contact')
        # the main board's socket contact for this card contact: A1-A32 are
        # J3.1-32, B1-B32 J3.33-64 (the x4 pad translation)
        number = int(card_contact[1][1:]) + (32 if card_contact[1][0] == 'B' else 0)
        main_contact = ('J3', str(number))
        main_net = node(main, *main_contact)
        return pad, card_contact, main_contact, net, main_net

    config = {}
    for signal, gpio, mux in (('clk', 'GPIO18', clk_mux), ('io', 'GPIO19', io_mux)):
        pad, card_contact, main_contact, net, main_net = system_signal(gpio)
        if main_net != ('/PROG_CLK' if signal == 'clk' else '/PROG_IO'):
            raise ValueError(f'{gpio} reaches {main_net} on the main board, not the {signal.upper()} common line')
        config[signal] = leg('system', net, pad, card_contact, signal) and \
            leg('main', main_net, main_contact, named_pin(main, mux, 'A'), signal)
    config['sel_bit'], config['sel_whole'] = [], []
    for k, gpio in enumerate(('GPIO20', 'GPIO21', 'GPIO22')):
        pad, card_contact, main_contact, net, main_net = system_signal(gpio)
        bits = set()
        ok = leg('system', net, pad, card_contact, f'sel{k}')
        for mux in (clk_mux, io_mux):
            select = next((p for (r, p), n in main.pins.items()
                           if r == mux and n == main_net and main.pin_names.get((r, p), '')[:1] == 'S'), None)
            if select is None:
                raise ValueError(f'{gpio} reaches {main_net}: not a select input of {mux}')
            bits.add(int(main.pin_names[(mux, select)][1:]))
            ok &= leg('main', main_net, main_contact, (mux, select), f'sel{k}')
        if len(bits) != 1:
            raise ValueError(f'{gpio}: the two muxes see it on different select inputs {sorted(bits)}')
        config['sel_bit'].append(bits.pop())
        config['sel_whole'].append(ok)
    if sorted(config['sel_bit']) != [0, 1, 2]:
        raise ValueError(f'the three mux selects are not a permutation: {config["sel_bit"]}')

    config['channel'], config['slot_legs'] = [], []
    for slot in range(1, 7):
        socket = f'J{10 + slot}'
        channels, ok = set(), True
        for contact, signal, mux in (('B6', 'SWCLK', clk_mux), ('B7', 'SWDIO', io_mux)):
            slot_net = node(main, socket, contact)
            if slot_net != f'/SLOT{slot}_{signal}':
                raise ValueError(f'{socket}.{contact}: expected SLOT{slot}_{signal}, got {slot_net}')
            series = next((r for r in main.resistors if slot_net in r.ends), None)
            if series is None or series.value != '33':
                raise ValueError(f'{slot_net}: a 33 ohm series resistor must lead to the mux')
            near = next((series.ref, q) for q in ('1', '2') if main.pins[(series.ref, q)] == slot_net)
            far = next((series.ref, q) for q in ('1', '2') if main.pins[(series.ref, q)] != slot_net)
            far_net = main.pins[far]
            channel = next((p for (r, p), n in main.pins.items() if r == mux and n == far_net), None)
            if channel is None or not main.pin_names.get((mux, channel), '').startswith('A') or \
                    main.pin_names[(mux, channel)] == 'A':
                raise ValueError(f'{far_net}: not a channel input of {mux}')
            channels.add(int(main.pin_names[(mux, channel)][1:]))
            ok &= leg('main', far_net, (mux, channel), far, f'slot{slot}_{signal.lower()}_mux')
            ok &= leg('main', slot_net, near, (socket, contact), f'slot{slot}_{signal.lower()}_socket')
        if len(channels) != 1:
            raise ValueError(f'slot {slot}: the clock and data channels differ ({sorted(channels)})')
        config['channel'].append(channels.pop())
        config['slot_legs'].append(ok)
    if sorted(config['channel']) != sorted(set(config['channel'])) or max(config['channel']) > 5:
        raise ValueError(f'slot channels collide or leave the six modelled inputs: {config["channel"]}')
    config['card'] = {}
    for kind in ('gpu', 'io', 'storage', 'eink'):
        circuit, ok = cards[kind], True
        for contact, name in (('B6', 'SWCLK'), ('B7', 'SWDIO')):
            net = node(circuit, 'J1', contact)
            pad = named_pin(circuit, 'U1', name)
            if node(circuit, *pad) != net:
                raise ValueError(f'{kind}: J1.{contact} must reach the RP2040 {name} pin')
            ok &= leg(kind, net, ('J1', contact), pad, f'{name.lower()}')
        config['card'][kind] = ok
    return config, paths, missing, whole


def reset_monitor_source_binding(main):
    """Bind the fitted rail monitor branch; do not claim analog runtime coverage."""
    packages = {
        'D7': ('BAT54A', ('jlc', 'BAT54ALT1G')),
        'U17': ('REF3425', ('jlc', 'REF3425IDBVR')),
        'U18': ('OPA376', ('jlc', 'OPA376AIDBVR')),
        'U20': ('OPA376', ('jlc', 'OPA376AIDBVR')),
        'C52': ('1u', ('Device', 'C')),
    }
    resistor_values = {'R110': '7.5k 0.1%', 'R111': '4.12k 0.1%',
                       'R112': '10k 0.1%', 'R113': '9.53k 0.1%',
                       'R114': '10k 0.1%', 'R115': '6.8M',
                       'R116': '1k', 'R117': '2.7M'}
    packages.update({ref: (value, ('Device', 'R'))
                     for ref, value in resistor_values.items()})
    if any(main.components.get(ref) != value for ref, value in packages.items()):
        raise ValueError('reset monitor: wrong fitted reference, amplifiers, diode or divider')
    nets = {
        'VREF25': {('C52', '1'), ('R110', '1'), ('U17', '5'), ('U17', '6')},
        'MON_T33': {('R110', '2'), ('R111', '1'), ('U18', '4')},
        'MON_T12': {('R111', '2'), ('R112', '1'), ('U20', '4')},
        'MON33_P': {('R113', '2'), ('R114', '1'), ('R115', '2'), ('U18', '3')},
        'MON12_P': {('R116', '2'), ('R117', '2'), ('U20', '3')},
        'MON33_OK': {('D7', '1'), ('R115', '1'), ('U18', '1')},
        'MON12_OK': {('D7', '2'), ('R117', '1'), ('U20', '1')},
    }
    if any(set(main.nets.get('/' + net, ())) != nodes or
           any(main.net(*pin) != '/' + net for pin in nodes)
           for net, nodes in nets.items()):
        raise ValueError('reset monitor: reference, sensing, hysteresis or output topology changed')
    pins = {
        ('D7', '1'): ('K', '/MON33_OK'), ('D7', '2'): ('K', '/MON12_OK'),
        ('D7', '3'): ('A', '/nMR'),
        ('U17', '1'): ('GND_F', '/GND'), ('U17', '2'): ('GND_S', '/GND'),
        ('U17', '3'): ('ENABLE', '/+3V3'), ('U17', '4'): ('IN', '/+3V3'),
        ('U17', '5'): ('OUT_S', '/VREF25'), ('U17', '6'): ('OUT_F', '/VREF25'),
    }
    for ref, out, inp, threshold in (('U18', '/MON33_OK', '/MON33_P', '/MON_T33'),
                                     ('U20', '/MON12_OK', '/MON12_P', '/MON_T12')):
        pins.update({(ref, str(i)): (name, net) for i, name, net in
                     ((1, 'OUT', out), (2, 'V-', '/GND'), (3, 'IN+', inp),
                      (4, 'IN-', threshold), (5, 'V+', '/+3V3'))})
    if any(main.pin_names.get(pin) != name or main.net(*pin) != net
           for pin, (name, net) in pins.items()):
        raise ValueError('reset monitor: wrong diode polarity, reference or amplifier pin map')
    ends = {('R112', '2'): '/GND', ('R113', '1'): '/+3V3',
            ('R114', '2'): '/GND', ('R116', '1'): '/+1V2', ('C52', '2'): '/GND'}
    if any(main.net(*pin) != net for pin, net in ends.items()):
        raise ValueError('reset monitor: divider rail or return changed')
    return tuple(nets)


def reset_monitor_runtime(main, main_board):
    """Actual DC/hysteretic native model, with individually proven physical legs.

    Slot RUN device response remains the existing card_control model boundary;
    these outputs execute as open-drain wired-AND levels at U13, not MCU resets.
    """
    monitor_nets=reset_monitor_source_binding(main)
    if main.components.get('U19') != ('SN74LVC07A', ('jlc','SN74LVC07APWR')) or \
       main.components.get('U6') != ('MAX811TEUS', ('jlc','MAX811TEUS+T')):
        raise ValueError('reset monitor: wrong supervisor or open-drain buffers')
    if main.components.get('R118') != ('100k', ('Device','R')) or \
       main.net('R118','1') != '/nPOR' or main.net('R118','2') != '/GND':
        raise ValueError('reset monitor: unpowered nPOR pull-down changed')
    pins={('U19','14'):('VCC','/3V3_STBY'),('U19','7'):('GND','/GND'),
          ('U6','4'):('VCC','/+3V3'),('U6','1'):('GND','/GND'),
          ('U6','3'):('~{MR}','/nMR'),('U6','2'):('~{RESET}','/nPOR')}
    for slot,(a,y) in enumerate(((1,2),(3,4),(5,6),(9,8),(11,10),(13,12)),1):
        pins[('U19',str(a))]=(f'{slot}A','/nPOR')
        pins[('U19',str(y))]=(f'{slot}Y',f'/SLOT{slot}_RST_n')
        expected={(f'J{10+slot}','B9'),(f'R{104+100*slot}','2'),
                  ('U13',str(3+slot)),('U19',str(y))}
        pull=f'R{104+100*slot}'
        if main.components.get(pull)!=('10k',('Device','R')) or \
           main.net(pull,'1')!='/+3V3' or \
           main.pin_names.get(('U13',str(3+slot)))!=f'P0{slot-1}':
            raise ValueError('reset monitor: wrong slot pull-up or expander bit')
        if set(main.nets.get(f'/SLOT{slot}_RST_n',())) != expected:
            raise ValueError('reset monitor: unexpected slot reset load')
    if any(main.pin_names.get(pin)!=name or main.net(*pin)!=net
           for pin,(name,net) in pins.items()):
        raise ValueError('reset monitor: U19 power, polarity or channel changed')
    paths,missing=[],[]
    query_cache={}
    supply_targets={
        '/GND': [('U17','1'),('U17','2'),('U18','2'),('U20','2'),('U19','7'),
                 ('R112','2'),('R114','2'),('C52','2'),('R118','2')],
        '/+3V3': [('U17','3'),('U17','4'),('U18','5'),('U20','5'),('R113','1'),
                   *((f'R{104+100*slot}','1') for slot in range(1,7))],
        '/+1V2': [('R116','1')], '/3V3_STBY': [('U19','14')],
    }
    def prove(net,first,last):
        connected=False
        if main_board is not None and Path(main_board).is_file():
            sys.path.insert(0,str(ROOT/'hw/si'))
            from ibis_bus import routed_connectivity
            key=(net,first)
            if key not in query_cache:
                receivers=supply_targets.get(net,main.nets[net])
                receivers=sorted(set(receivers)-{first})
                # Reuse only within this single immutable board-binding call.
                # Native filled-plane connectivity is not an SI path length.
                query_cache[key]=routed_connectivity(Path(main_board),net,first,receivers)
            connected=query_cache[key][f'{last[0]}.{last[1]}']
        paths.append({'from':f'main.{first[0]}.{first[1]}',
                      'to':f'main.{last[0]}.{last[1]}','route_mm':None,
                      'connected':connected,'proof':'native same-net copper connectivity',
                      'runtime':'reset_monitor'})
        if not connected: missing.append(f'main:{net}:{first}->{last}')
        return connected
    for net in monitor_nets:
        nodes=sorted(main.nets['/'+net])
        for target in nodes[1:]:prove('/'+net,nodes[0],target)
    for ref in ('U17','U18','U20','U19'):
        for pin,net in ((p,n) for (r,p),n in main.pins.items() if r==ref):
            if net in ('/+3V3','/GND','/3V3_STBY'):
                anchor={'/+3V3':('U6','4'),'/GND':('U6','1'),'/3V3_STBY':('U15','3')}[net]
                prove(net,anchor,(ref,pin))
    for net,first,last in (
            ('/GND',('U6','1'),('R112','2')),
            ('/GND',('U6','1'),('R114','2')),
            ('/GND',('U6','1'),('C52','2')),
            ('/GND',('U6','1'),('R118','2')),
            ('/nPOR',('U6','2'),('R118','1')),
            ('/+3V3',('U6','4'),('R113','1')),
            ('/+1V2',('R8','2'),('R116','1'))):
        prove(net,first,last)
    core_complete=not missing
    diode33=prove('/nMR',('D7','3'),('U6','3'))
    diode12=diode33
    slots=[]
    for slot,(a,y) in enumerate(((1,2),(3,4),(5,6),(9,8),(11,10),(13,12)),1):
        good=prove('/nPOR',('U6','2'),('U19',str(a)))
        for target in (('U13',str(3+slot)),(f'J{10+slot}','B9')):
            good=prove(f'/SLOT{slot}_RST_n',('U19',str(y)),target) and good
        pull=f'R{104+100*slot}'
        good=prove('/+3V3',('U6','4'),(pull,'1')) and good
        good=prove(f'/SLOT{slot}_RST_n',('U19',str(y)),(pull,'2')) and good
        slots.append(good)
    return {'model':'fitted-dc-hysteresis-max811-v1',
            'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                             for name in ('emu/machine/resetmonitor.h','hw/power/reset_supervisor.py')},
            'baseline':'explicit settled powered rails; not cold-start timing proof',
            'scope':'DC KCL, feedback hysteresis, diode MR, 560ms recovery, U19 electrical slot levels; card RUN whole-chip response excluded by existing card_control boundary',
            'diode33':diode33,'diode12':diode12,'slots':slots,
            'core_complete':core_complete,
            'complete':not missing},paths,missing,monitor_nets


def sysctl_manual_reset_route(main, system, main_board, system_board):
    """Bind the system MCU's reset GPIO across J2/J3 to supervisor MR."""
    system_nodes = {('U1', '35'), ('J2', 'B4')}
    reset_monitor_source_binding(main)
    main_nodes = {('J3', '36'), ('SW1', '1'), ('TP14', '1'), ('U6', '3'), ('D7', '3')}
    if set(system.nets.get('/SYS_nRST', ())) != system_nodes or \
            set(main.nets.get('/nMR', ())) != main_nodes or \
            system.pin_names.get(('U1', '35')) != 'GPIO23' or \
            main.pin_names.get(('U6', '3')) != '~{MR}' or \
            system.net('J2', 'B4') != '/SYS_nRST' or \
            main.net('J3', '36') != '/nMR' or \
            main.net('SW1', '4') != '/GND':
        raise ValueError('system reset: wrong GPIO23, mating contact, switch or supervisor MR')
    links, paths, missing = {'sysctl': True, 'button': True}, [], []
    for kind, board, pcb, net, first, last in (
            ('sysctl', 'system', system_board, 'SYS_nRST', ('U1', '35'), ('J2', 'B4')),
            ('sysctl', 'main', main_board, 'nMR', ('J3', '36'), ('U6', '3')),
            ('button', 'main', main_board, 'nMR', ('SW1', '1'), ('U6', '3'))):
        mm = None
        if pcb is not None and Path(pcb).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            mm = routed_distances(Path(pcb), f'/{net}', first, [last])[
                f'{last[0]}.{last[1]}']
        paths.append({'from': f'{board}.{first[0]}.{first[1]}',
                      'to': f'{board}.{last[0]}.{last[1]}',
                      'route_mm': mm, 'runtime': f'{kind}_manual_reset_connected'})
        if mm is None:
            links[kind] = False
            missing.append(f'{board}:{net}_{kind}_reset_copper')
    return links, paths, missing


@lru_cache(maxsize=2)
def cpu_board_geometry(path):
    """Reuse CPU copper geometry across each route mutation in one audit."""
    import pcbnew
    board = pcbnew.LoadBoard(path)
    return board, kicadgen.parse(Path(path).read_text())


def cpu_bus_routes(card, board, address_map, data_map):
    """Two copper legs per CPU-card address/data resistor channel."""
    routed = board is not None and Path(board).is_file()
    if routed:
        sys.path.insert(0, str(ROOT / 'hw/si'))
        from ibis_bus import routed_distances
        loaded_board, parsed_tree = cpu_board_geometry(str(Path(board).resolve()))
    links, paths, missing = {}, [], []
    for kind, mapping in (('address', address_map), ('data', data_map)):
        prefix = 'A' if kind == 'address' else 'D'
        connected_bits = []
        for main_bit, card_bit in enumerate(mapping):
            source_net = f'/FPGA_{prefix}{card_bit}'
            contact_net = f'/CPU_{prefix}{card_bit}'
            source = [(ref, pin) for (ref, pin), net in card.pins.items()
                      if ref == 'U1' and net == source_net]
            finger = [(ref, pin) for (ref, pin), net in card.pins.items()
                      if ref == 'J1' and net == contact_net]
            source_pad = [(ref, pin) for (ref, pin), net in card.pins.items()
                          if ref.startswith('RN') and net == source_net]
            contact_pad = [(ref, pin) for (ref, pin), net in card.pins.items()
                           if ref.startswith('RN') and net == contact_net]
            if not all(len(items) == 1 for items in (source, finger, source_pad, contact_pad)) or \
                    source_pad[0][0] != contact_pad[0][0]:
                raise ValueError(f'CPU {prefix}{card_bit}: FPGA/series/contact pad mapping missing')
            if path(card, source[0], finger[0], '68') is None:
                raise ValueError(f'CPU {prefix}{card_bit}: 68-ohm driver channel missing')
            legs = (('source', source_net, source[0], source_pad[0]),
                    ('contact', contact_net, contact_pad[0], finger[0]))
            connected = True
            for stage, net, first, last in legs:
                mm = None
                if routed:
                    mm = routed_distances(Path(board), net, first, [last],
                                          loaded_board=loaded_board, parsed_tree=parsed_tree)[
                        f'{last[0]}.{last[1]}']
                paths.append({'from': f'cpu.{first[0]}.{first[1]}',
                              'to': f'cpu.{last[0]}.{last[1]}',
                              'route_mm': mm,
                              'runtime': f'cpu_{kind}{main_bit}_connected'})
                if mm is None:
                    connected = False
                    missing.append(f'cpu:{prefix}{card_bit}_{stage}_copper')
            connected_bits.append(connected)
        links[kind] = connected_bits
    return links, paths, missing


def cpu_clock_route(main, card, main_board, cpu_board):
    """The oscillator branch, resistor output and CPU-card clock copper."""
    oscillator = named_pin(main, 'Y1', 'OUT')
    socket = ('J2', 'B13')
    fpga = ('U1', '21')
    finger = ('J1', 'B13')
    resistor = path(main, oscillator, socket, '33')
    if node(main, resistor, '2') != '/CPU_CLK' or node(card, *finger) != '/CPU_CLK':
        raise ValueError('CPU clock resistor output or card contact is missing')
    path(card, finger, fpga)
    legs = (('main', main_board, '/OSC_OUT', oscillator, (resistor, '1')),
            ('main', main_board, '/CPU_CLK', (resistor, '2'), socket),
            ('cpu', cpu_board, '/CPU_CLK', finger, fpga))
    rows, missing = [], []
    for board_name, board_file, net, source, target in legs:
        path(main if board_name == 'main' else card, source, target)
        length = None
        if board_file is not None and Path(board_file).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            length = routed_distances(Path(board_file), net, source, [target])[
                f'{target[0]}.{target[1]}']
        rows.append({'from': f'{board_name}.{source[0]}.{source[1]}',
                     'to': f'{board_name}.{target[0]}.{target[1]}',
                     'route_mm': length, 'runtime': 'cpu_clock_connected'})
        if length is None:
            missing.append(f'{board_name}:{net.lstrip("/")}_cpu_clock_copper')
    return not missing, rows, missing


def cpu_reset_route(main, card, main_board, cpu_board):
    """All three copper legs carrying chipset reset to the CPU FPGA."""
    source, socket = ('U7', '32'), ('J2', 'B16')
    finger, fpga = ('J1', 'B16'), ('U1', '22')
    resistor = path(main, source, socket, '56')
    if node(main, *source) != '/CPU_nRST_SRC' or \
            node(main, resistor, '1') != '/CPU_nRST_SRC' or \
            node(main, resistor, '2') != '/CPU_nRST' or \
            node(card, *finger) != '/CPU_nRST':
        raise ValueError('CPU reset resistor output or card contact is missing')
    path(card, finger, fpga)
    legs = (('main', main_board, '/CPU_nRST_SRC', source, (resistor, '1')),
            ('main', main_board, '/CPU_nRST', (resistor, '2'), socket),
            ('cpu', cpu_board, '/CPU_nRST', finger, fpga))
    rows, missing = [], []
    for board_name, board_file, net, first, last in legs:
        path(main if board_name == 'main' else card, first, last)
        length = None
        if board_file is not None and Path(board_file).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            length = routed_distances(Path(board_file), net, first, [last])[
                f'{last[0]}.{last[1]}']
        rows.append({'from': f'{board_name}.{first[0]}.{first[1]}',
                     'to': f'{board_name}.{last[0]}.{last[1]}',
                     'route_mm': length, 'runtime': 'cpu_reset_connected'})
        if length is None:
            missing.append(f'{board_name}:{net.lstrip("/")}_reset_copper')
    return not missing, rows, missing


def chipset_clock_route(main, main_board):
    """Trace both copper legs of the 12 MHz oscillator's chipset branch."""
    source = named_pin(main, 'Y1', 'OUT')
    chipset = ('U7', '21')
    if node(main, *source) != '/OSC_OUT' or node(main, *chipset) != '/CLK12':
        raise ValueError('oscillator or chipset clock pad has the wrong net')
    if path(main, source, chipset, '33') != 'R17':
        raise ValueError('chipset clock requires the R17 33-ohm branch')
    legs = (('/OSC_OUT', source, ('R17', '1')),
            ('/CLK12', ('R17', '2'), chipset))
    rows, missing = [], []
    for net, first, last in legs:
        path(main, first, last)
        length = None
        if main_board is not None and Path(main_board).is_file():
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
            length = routed_distances(Path(main_board), net, first, [last])[
                f'{last[0]}.{last[1]}']
        rows.append({'from': f'main.{first[0]}.{first[1]}',
                     'to': f'main.{last[0]}.{last[1]}',
                     'route_mm': length, 'runtime': 'chipset_clock_connected'})
        if length is None:
            missing.append(f'main:{net.lstrip("/")}_chipset_clock_copper')
    return not missing, rows, missing


def check(cards, main, pcb=None, card_boards=None, system_board=None, cpu_board=None):
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
                from slot_spi import network
                signal={'B13':'sck','B15':'mosi','A14':'cs','B16':'miso','B10':'irq'}[contact]
                target=network(cards[card],card)['signals'][signal]
                pins=[target[1]]
                if len(pins) != 1:
                    raise ValueError(f'{card} {card_net}: card model pin missing or duplicated')
                if contact == 'B16':
                    card_miso_network(cards[card], card)
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
            if contact=='A14':
                from slot_spi import main_select
                main_select(main,slot)
            value='68' if contact=='A14' else '33'
            resistor = path(main, ('U7', pins[0]), (ref, contact), value)
            expected_ref=f'R{36+slot}' if contact=='A14' else ('R36' if contact=='B13' else 'R35')
            if resistor != expected_ref:raise ValueError('slot control series reference changed')
            manifest['paths'].append({'from': f'main.U7.{pins[0]}', 'to': f'main.{ref}.{contact}',
                                      'series': resistor, 'ohms': int(value)})
    # Actual permanent low-idle passive bias, not an assumed floating level.
    from slot_spi import main_bias
    main_bias(main)
    miso=node(main,'U7','48')
    if (node(main,'R107','1'),node(main,'R107','2')) != ('/+3V3',miso) or main.components['R107'] != ('100k',('Device','R')):
        raise ValueError('Main MISO requires exact R107 100k pullup')
    if (node(main,'R109','1'),node(main,'R109','2')) != (miso,'/GND') or main.components['R109'] != ('4.7k',('Device','R')):
        raise ValueError('Main MISO requires exact R109 4.7k pulldown')
    if [(r.ref,r.value)for r,n in main.pulls('/+3V3')if n==miso] != [('R107','100k')] or [(r.ref,r.value)for r,n in main.pulls('/GND')if n==miso] != [('R109','4.7k')]:
        raise ValueError('Unexpected parallel Main MISO bias')
    manifest['pulls'].append({'net':'SPI_MISO','idle':0,'pullup_ohms':100000,'pulldown_ohms':4700,'scope':'functional/DC powered baseline; leakage/SI separate'})
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
    manifest['runtime']['miso_idle'] = 0  # fitted 100k pullup / 4.7k pulldown
    # Physical bias branches affect the native bus's actual idle choice.
    sys.path.insert(0,str(ROOT/'hw/si'))
    from ibis_bus import routed_connectivity
    bias_ok={}
    for label,ref,pin,net in (('pullup','R107','1','/+3V3'),('pulldown','R109','2','/GND')):
        anchors=[(r,p)for(r,p),n in main.pins.items()if r=='U7' and n==net]
        if not anchors:raise ValueError('Main bias supply reference absent')
        for first,last,n in ((('U7','48'),(ref,'2' if pin=='1' else '1'),'/SPI_MISO'),((ref,pin),anchors[0],net)):
            ok=bool(pcb and Path(pcb).is_file() and routed_connectivity(Path(pcb),n,first,[last])[f'{last[0]}.{last[1]}'])
            bias_ok[label]=bias_ok.get(label,True) and ok
            manifest['paths'].append({'from':f'main.{first[0]}.{first[1]}','to':f'main.{last[0]}.{last[1]}','net':n,'connected':ok,'runtime':'miso_idle_bias'})
            if not ok:manifest.setdefault('miso_bias_missing',[]).append(f'main:{ref}_{pin}_bias_copper')
    manifest['runtime']['miso_idle']=0 if bias_ok['pulldown'] else 1
    manifest['runtime']['miso_bias_connected']=all(bias_ok.values())

    # 10-90 % of the larger CPU-bus series R (card RN1-8 68 ohm; main R21-R34 are
    # 56) into 15 pF: the same bound as hw/timing/cpubus_budget.py
    manifest['runtime']['series_delay_ns'] = round(2.2 * 68 * 15e-12 * 1e9, 3)
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
                      {'MEM_nOE', 'MEM_nWE', 'MEM_nCE_RAM', 'MEM_nCE_ROM'}
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
    # The supervisor must release the chipset's nPOR input through actual
    # routed copper. This contact decides whether the native board ever leaves
    # reset; a net name or a trace somewhere on nPOR is insufficient.
    supervisor = named_pin(main, 'U6', '~{RESET}')
    por_input = named_pin(main, 'U7', 'IOB_96')
    path(main, supervisor, por_input)
    por_mm = None
    if pcb is not None and Path(pcb).is_file():
        sys.path.insert(0, str(ROOT / 'hw/si'))
        from ibis_bus import routed_distances
        por_mm = routed_distances(Path(pcb), '/nPOR', supervisor, [por_input])[
            f'{por_input[0]}.{por_input[1]}']
    manifest['paths'].append({'from': f'main.{supervisor[0]}.{supervisor[1]}',
                              'to': f'main.{por_input[0]}.{por_input[1]}',
                              'route_mm': por_mm, 'runtime': 'por_connected'})
    manifest['runtime']['por_connected'] = por_mm is not None
    # Both memory chips use the chipset's /WE, but their actual copper branches
    # are independent. An open branch prevents writes only at that chip.
    write_source = ('U7', '114')
    if node(main, *write_source) != '/MEM_nWE':
        raise ValueError('chipset memory write pad is not MEM_nWE')
    write_targets = {'ram': named_pin(main, 'U9', '~{WE}'),
                     'rom': named_pin(main, 'U10', '~{WE}')}
    write_lengths = {}
    for target in write_targets.values():
        path(main, write_source, target)
    if pcb is not None and Path(pcb).is_file():
        from ibis_bus import routed_distances
        write_lengths = routed_distances(Path(pcb), '/MEM_nWE', write_source,
                                         list(write_targets.values()))
    write_links = {}
    for kind, target in write_targets.items():
        length = write_lengths.get(f'{target[0]}.{target[1]}')
        write_links[kind] = length is not None
        manifest['paths'].append({'from': 'main.U7.114',
                                  'to': f'main.{target[0]}.{target[1]}',
                                  'route_mm': length, 'runtime': f'{kind}_write_connected'})
    manifest['runtime']['memory_write_links'] = write_links
    # A ROM DQ0 open is visible during CPU instruction fetch. The digital
    # model uses a deterministic high value for this otherwise floating bit;
    # it is a wiring counterexample, not an analog estimate of an open pad.
    rom_d0, chipset_d0 = ('U10', '13'), ('U7', '119')
    if node(main, *rom_d0) != '/MEM_D0':
        raise ValueError('ROM DQ0 pad is not MEM_D0')
    path(main, rom_d0, chipset_d0)
    rom_d0_mm = None
    if pcb is not None and Path(pcb).is_file():
        from ibis_bus import routed_distances
        rom_d0_mm = routed_distances(Path(pcb), '/MEM_D0', rom_d0, [chipset_d0])[
            f'{chipset_d0[0]}.{chipset_d0[1]}']
    manifest['paths'].append({'from': 'main.U10.13', 'to': 'main.U7.119',
                              'route_mm': rom_d0_mm, 'runtime': 'rom_read_d0_connected'})
    manifest['runtime']['rom_read_d0_connected'] = rom_d0_mm is not None
    for name, connected in (('nPOR:U6.2->U7.61', manifest['runtime']['por_connected']),
                            ('MEM_nWE:U7.114->U9.5', write_links['ram']),
                            ('MEM_nWE:U7.114->U10.31', write_links['rom']),
                            ('MEM_D0:U10.13->U7.119', manifest['runtime']['rom_read_d0_connected'])):
        if not connected:
            manifest['runtime']['missing_routes'].append(name)
    manifest['runtime']['missing_routes'].sort()
    manifest['runtime']['missing_routes'].extend(manifest.pop('miso_bias_missing',[]))
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
    manifest['runtime']['routed_timing'] &= all(write_links.values()) and \
        manifest['runtime']['rom_read_d0_connected']
    # Each slot-select source crosses its fitted 68-ohm resistor. Verify both copper
    # legs from the actual package pads, then use the result to gate the
    # native card select. Net-level route length alone can miss an open pad.
    for slot, wiring in enumerate(manifest['runtime']['slots'], 1):
        source_net = f'/SPI_nCS{slot-1}_SRC'
        output_net = f'/SLOT{slot}_CS_n'
        source = next(((ref, pin) for (ref, pin), net in main.pins.items()
                       if ref == 'U7' and net == source_net), None)
        if source is None:
            raise ValueError(f'{source_net}: chipset source pad missing')
        resistor = main.series(source, (f'J{10+slot}', 'A14'))
        if resistor is None or resistor.value != '68' or resistor.ref != f'R{36+slot}':
            raise ValueError(f'{source_net}: exact slot-select 68-ohm resistor missing')
        base_ref = resistor.ref.split('.')[0]
        source_pad = next(((base_ref, pad) for (ref, pad), net in main.pins.items()
                           if ref == base_ref and net == source_net), None)
        output_pad = next(((base_ref, pad) for (ref, pad), net in main.pins.items()
                           if ref == base_ref and net == output_net), None)
        if source_pad is None or output_pad is None:
            raise ValueError(f'{source_net}: resistor pad mapping missing')
        legs = {'source': None, 'slot': None}
        if pcb is not None and Path(pcb).is_file():
            from ibis_bus import routed_distances
            legs['source'] = routed_distances(Path(pcb), source_net, source, [source_pad])[
                f'{source_pad[0]}.{source_pad[1]}']
            target = (f'J{10+slot}', 'A14')
            legs['slot'] = routed_distances(Path(pcb), output_net, output_pad, [target])[
                f'{target[0]}.{target[1]}']
        wiring['cs_connected'] = all(length is not None for length in legs.values())
        manifest['paths'].append({'from': f'main.{source[0]}.{source[1]}',
                                  'to': f'main.{source_pad[0]}.{source_pad[1]}',
                                  'route_mm': legs['source'], 'runtime': f'slot{slot}_select_connected'})
        manifest['paths'].append({'from': f'main.{output_pad[0]}.{output_pad[1]}',
                                  'to': f'main.J{10+slot}.A14',
                                  'route_mm': legs['slot'], 'runtime': f'slot{slot}_select_connected'})
        if not wiring['cs_connected']:
            for leg, length in legs.items():
                if length is None:
                    manifest['runtime']['missing_routes'].append(
                        f'slot{slot}_select_{leg}:{source_net if leg == "source" else output_net}')
    manifest['runtime']['missing_routes'].sort()
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
    # The clock and outbound data each have one shared source resistor and
    # six routed branches. The return data line has six branches to U7.48.
    # Keep these as per-slot booleans: a damaged connector branch must not
    # silence otherwise connected slots, while a source open affects all six.
    for signal, source_net, output_net, resistor_ref, contact, field in (
            ('sck', '/SPI_SCK_SRC', '/SPI_SCK', 'R36', 'B13', 'sck_connected'),
            ('mosi', '/SPI_MOSI_SRC', '/SPI_MOSI', 'R35', 'B15', 'mosi_connected')):
        source = next(((ref, pin) for (ref, pin), net in main.pins.items()
                       if ref == 'U7' and net == source_net), None)
        source_pad = next(((resistor_ref, pin) for (ref, pin), net in main.pins.items()
                           if ref == resistor_ref and net == source_net), None)
        output_pad = next(((resistor_ref, pin) for (ref, pin), net in main.pins.items()
                           if ref == resistor_ref and net == output_net), None)
        if source is None or source_pad is None or output_pad is None or \
                main.series(source, ('J11', contact)) is None:
            raise ValueError(f'{signal}: source and series resistor mapping missing')
        receivers = [(f'J{10+slot}', contact) for slot in range(1, 7)]
        source_mm, branch_mm = None, {}
        if pcb is not None and Path(pcb).is_file():
            from ibis_bus import routed_distances
            source_mm = routed_distances(Path(pcb), source_net, source, [source_pad])[
                f'{source_pad[0]}.{source_pad[1]}']
            branch_mm = routed_distances(Path(pcb), output_net, output_pad, receivers)
        manifest['paths'].append({'from': f'main.{source[0]}.{source[1]}',
                                  'to': f'main.{source_pad[0]}.{source_pad[1]}',
                                  'route_mm': source_mm, 'runtime': f'slot_{signal}_source_connected'})
        for slot, target in enumerate(receivers, 1):
            mm = branch_mm.get(f'{target[0]}.{target[1]}')
            manifest['runtime']['slots'][slot-1][field] = source_mm is not None and mm is not None
            manifest['paths'].append({'from': f'main.{output_pad[0]}.{output_pad[1]}',
                                      'to': f'main.{target[0]}.{target[1]}',
                                      'route_mm': mm, 'runtime': f'slot{slot}_{signal}_connected'})
            if not manifest['runtime']['slots'][slot-1][field]:
                manifest['runtime']['missing_routes'].append(
                    f'slot{slot}_{signal}:{source_net if source_mm is None else output_net}')
    miso_source = ('U7', '48')
    if node(main, *miso_source) != '/SPI_MISO':
        raise ValueError('shared SPI MISO chipset input is not U7.48')
    miso_receivers = [(f'J{10+slot}', 'B16') for slot in range(1, 7)]
    miso_mm = {}
    if pcb is not None and Path(pcb).is_file():
        from ibis_bus import routed_distances
        miso_mm = routed_distances(Path(pcb), '/SPI_MISO', miso_source, miso_receivers)
    for slot, target in enumerate(miso_receivers, 1):
        mm = miso_mm.get(f'{target[0]}.{target[1]}')
        manifest['runtime']['slots'][slot-1]['miso_connected'] = mm is not None
        manifest['paths'].append({'from': 'main.U7.48',
                                  'to': f'main.{target[0]}.{target[1]}',
                                  'route_mm': mm, 'runtime': f'slot{slot}_miso_connected'})
        if mm is None:
            manifest['runtime']['missing_routes'].append(f'slot{slot}_miso:/SPI_MISO')
    for slot, wiring in enumerate(manifest['runtime']['slots'], 1):
        net = f'/SLOT_nIRQ{slot-1}'
        source = next(((ref, pin) for (ref, pin), attached in main.pins.items()
                       if ref == 'U7' and attached == net), None)
        target = (f'J{10+slot}', 'B10')
        if source is None:
            raise ValueError(f'{net}: chipset IRQ input missing')
        path(main, source, target)
        mm = None
        if pcb is not None and Path(pcb).is_file():
            from ibis_bus import routed_distances
            mm = routed_distances(Path(pcb), net, source, [target])[
                f'{target[0]}.{target[1]}']
        wiring['irq_connected'] = mm is not None
        manifest['paths'].append({'from': f'main.{source[0]}.{source[1]}',
                                  'to': f'main.{target[0]}.{target[1]}',
                                  'route_mm': mm, 'runtime': f'slot{slot}_irq_connected'})
        if mm is None:
            manifest['runtime']['missing_routes'].append(f'slot{slot}_irq:{net}')
    card_links, card_paths, card_missing = card_slot_routes(cards, card_boards)
    manifest['runtime']['card_slot_links'] = card_links
    manifest['paths'].extend(card_paths)
    manifest['runtime']['missing_routes'].extend(card_missing)
    boot_links, boot_paths, boot_missing = qspi_boot_routes(cards, card_boards, system_board)
    manifest['runtime']['qspi_boot_connected'] = boot_links
    manifest['paths'].extend(boot_paths)
    manifest['runtime']['missing_routes'].extend(boot_missing)
    crystal_links, crystal_paths, crystal_missing, crystal_nets = crystal_routes(
        cards, card_boards, system_board)
    manifest['runtime']['crystal_connected'] = crystal_links
    manifest['paths'].extend(crystal_paths)
    manifest['runtime']['missing_routes'].extend(crystal_missing)
    fpga_links, fpga_paths, fpga_missing, fpga_nets = fpga_config_routes(
        main, cards['cpu'], cards['system'], pcb, cpu_board, system_board)
    manifest['runtime']['fpga_links'] = fpga_links
    i2c_rows, i2c_paths, i2c_missing, i2c_nets = i2c_expander_routes(
        main, cards, pcb, cpu_board, system_board, card_boards)
    manifest['runtime']['i2c'] = i2c_rows
    manifest['paths'].extend(i2c_paths)
    manifest['runtime']['missing_routes'].extend(i2c_missing)
    adc_links, adc_paths, adc_missing, adc_nets = adc_sense_routes(main, cards['system'], pcb, system_board)
    manifest['runtime']['sysctl_adc'] = adc_links
    manifest['paths'].extend(adc_paths)
    manifest['runtime']['missing_routes'].extend(adc_missing)
    prog_config, prog_paths, prog_missing, prog_nets = prog_port_routes(
        main, cards, pcb, system_board, card_boards)
    manifest['runtime']['prog_port'] = prog_config
    manifest['paths'].extend(prog_paths)
    manifest['runtime']['missing_routes'].extend(prog_missing)
    led_rows, led_paths, led_missing = card_led_routes(cards, card_boards, system_board)
    manifest['runtime']['card_leds'] = led_rows
    manifest['paths'].extend(led_paths)
    manifest['runtime']['missing_routes'].extend(led_missing)
    rail_rows, rail_paths, rail_missing = rail_indicator_routes(
        {'main': main, **cards}, {'main': pcb, 'cpu': cpu_board, 'system': system_board,
                                  **(card_boards or {})})
    manifest['runtime']['rail_leds'] = rail_rows
    manifest['paths'].extend(rail_paths)
    manifest['runtime']['missing_routes'].extend(rail_missing)
    manifest['paths'].extend(fpga_paths)
    manifest['runtime']['missing_routes'].extend(fpga_missing)
    manifest['runtime']['missing_routes'].sort()
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
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
        resistor = path(cards['cpu'], ('U1', str(pin)), ('J1', fingers[0]), '68')
        manifest['paths'].append({'from': f'cpu.U1.{pin}', 'to': f'cpu.J1.{fingers[0]}',
                                  'series': resistor, 'ohms': 68})
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
    cpu_links, cpu_paths, cpu_missing = cpu_bus_routes(
        cards['cpu'], cpu_board, manifest['runtime']['cpu_address'], manifest['runtime']['cpu_data'])
    main_data_links, main_data_paths, main_data_missing = main_cpu_data_routes(main, pcb)
    manifest['runtime']['cpu_address_links'] = cpu_links['address']
    manifest['runtime']['cpu_data_main_links'] = main_data_links
    manifest['runtime']['cpu_data_links'] = [card and source for card, source in
                                            zip(cpu_links['data'], main_data_links)]
    manifest['paths'].extend(cpu_paths)
    manifest['paths'].extend(main_data_paths)
    manifest['runtime']['missing_routes'].extend(cpu_missing)
    manifest['runtime']['missing_routes'].extend(main_data_missing)
    manifest['runtime']['routed_top'] &= not main_data_missing
    clock_connected, clock_paths, clock_missing = cpu_clock_route(
        main, cards['cpu'], pcb, cpu_board)
    manifest['runtime']['cpu_clock_connected'] = clock_connected
    manifest['paths'].extend(clock_paths)
    manifest['runtime']['missing_routes'].extend(clock_missing)
    reset_connected, reset_paths, reset_missing = cpu_reset_route(
        main, cards['cpu'], pcb, cpu_board)
    manifest['runtime']['cpu_reset_connected'] = reset_connected
    manifest['paths'].extend(reset_paths)
    manifest['runtime']['missing_routes'].extend(reset_missing)
    chipset_clock_connected, chipset_clock_paths, chipset_clock_missing = chipset_clock_route(main, pcb)
    manifest['runtime']['chipset_clock_connected'] = chipset_clock_connected
    manifest['paths'].extend(chipset_clock_paths)
    manifest['runtime']['missing_routes'].extend(chipset_clock_missing)
    manifest['runtime']['missing_routes'].sort()
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
    bridge = {}
    bridge_miso_main = True
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
            fpga = [pin for (ref, pin), net in main.pins.items()
                    if ref == 'U7' and net == '/BR_MISO_SRC']
            if len(fpga) != 1:
                raise ValueError('system bridge MISO FPGA driver missing')
            resistor = path(main, ('U7', fpga[0]), ('J3', pads[0]), '33')
            manifest['paths'].append({'from': f'main.U7.{fpga[0]}', 'to': f'main.J3.{pads[0]}',
                                      'series': resistor, 'ohms': 33})
            if (node(main, resistor, '1') != '/BR_MISO_SRC' or
                    node(main, resistor, '2') != '/BR_MISO'):
                raise ValueError('system bridge MISO series pad mapping changed')
            for net, first, last in (('BR_MISO_SRC', ('U7', fpga[0]), (resistor, '1')),
                                     ('BR_MISO', (resistor, '2'), ('J3', pads[0]))):
                path(main, first, last)
                length = None
                if pcb is not None and Path(pcb).is_file():
                    from ibis_bus import routed_distances
                    length = routed_distances(Path(pcb), f'/{net}', first, [last])[
                        f'{last[0]}.{last[1]}']
                manifest['paths'].append({'from': f'main.{first[0]}.{first[1]}',
                                          'to': f'main.{last[0]}.{last[1]}',
                                          'route_mm': length, 'runtime': 'bridge_miso_connected'})
                if length is None:
                    bridge_miso_main = False
                    manifest['runtime']['missing_routes'].append(f'main:{net}_bridge_miso_copper')
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
    bridge_links, bridge_paths, bridge_missing = system_bridge_source_routes(
        cards['system'], system_board)
    manifest['runtime']['bridge_source_links'] = bridge_links
    manifest['paths'].extend(bridge_paths)
    manifest['runtime']['missing_routes'].extend(bridge_missing)
    # The return bit also crosses the system card from the socket to RP2040.
    system_miso_contact, system_miso_input = ('J2', 'B15'), ('U1', '6')
    if (node(cards['system'], *system_miso_contact) != '/BR_MISO' or
            node(cards['system'], *system_miso_input) != '/BR_MISO'):
        raise ValueError('system bridge MISO return pad mapping changed')
    path(cards['system'], system_miso_contact, system_miso_input)
    system_miso_mm = None
    if system_board is not None and Path(system_board).is_file():
        from ibis_bus import routed_distances
        system_miso_mm = routed_distances(Path(system_board), '/BR_MISO',
                                          system_miso_contact, [system_miso_input])['U1.6']
    manifest['paths'].append({'from': 'system.J2.B15', 'to': 'system.U1.6',
                              'route_mm': system_miso_mm, 'runtime': 'bridge_miso_connected'})
    if system_miso_mm is None:
        manifest['runtime']['missing_routes'].append('system:BR_MISO_bridge_copper')
    bridge['miso'] = bridge_miso_main and system_miso_mm is not None
    manifest['runtime']['missing_routes'].sort()
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
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
    io_usb_board = (card_boards or {}).get('io')
    io_usb_host, io_usb_paths, io_usb_missing = io_usb_host_routes(cards['io'], io_usb_board)
    manifest['paths'].extend(io_usb_paths)
    manifest['runtime']['io_usb_host'] = io_usb_host
    manifest['runtime']['missing_routes'].extend(io_usb_missing)
    manifest['runtime']['routed_top'] &= not io_usb_missing
    io_vbus, io_vbus_paths, io_vbus_missing = io_vbus_routes(cards['io'], io_usb_board)
    manifest['runtime']['io_vbus'] = io_vbus
    manifest['paths'].extend(io_vbus_paths)
    manifest['runtime']['missing_routes'].extend(io_vbus_missing)
    manifest['runtime']['routed_top'] &= not io_vbus_missing
    # The microSD socket is a direct seven-wire attachment to the storage
    # RP2040. An absent or swapped contact removes that socket from co-sim.
    sd_contacts = {'SD_DAT2': '1', 'SD_nCS': '2', 'SD_MOSI': '3',
                   'SD_SCK': '5', 'SD_MISO': '7', 'SD_DAT1': '8',
                   'SD_nDETECT': '9'}
    for signal, connector_pin in sd_contacts.items():
        sources = [(ref, pin) for (ref, pin), net in cards['storage'].pins.items()
                   if ref == 'U1' and net == f'/{signal}']
        if len(sources) != 1:
            raise ValueError(f'storage {signal}: RP2040 pad missing')
        path(cards['storage'], sources[0], ('J2', connector_pin))
        manifest['paths'].append({'from': f'storage.U1.{sources[0][1]}',
                                  'to': f'storage.J2.{connector_pin}',
                                  'net': signal, 'runtime': 'storage_sd_socket'})
    manifest['runtime']['storage_sd_socket'] = True
    # All four HDMI differential lanes leave the RP2040 through the series
    # packs (gpu.py TMDS_R, 360 ohm: the RP2040 IIOVSS budget, GC-007); the
    # capture endpoint represents the receptacle, not MCU GPIOs.
    tmds_ohms = board_module('gpu').TMDS_R
    hdmi_contacts = {'D2P': '1', 'D2N': '3', 'D1P': '4', 'D1N': '6',
                     'D0P': '7', 'D0N': '9', 'CKP': '10', 'CKN': '12'}
    for lane, connector_pin in hdmi_contacts.items():
        source = [(ref, pin) for (ref, pin), net in cards['gpu'].pins.items()
                  if ref == 'U1' and net == f'/TMDS_{lane}']
        if len(source) != 1:
            raise ValueError(f'gpu TMDS_{lane}: RP2040 pad missing')
        resistor = path(cards['gpu'], source[0], ('J2', connector_pin), tmds_ohms)
        manifest['paths'].append({'from': f'gpu.U1.{source[0][1]}',
                                  'to': f'gpu.J2.{connector_pin}', 'series': resistor,
                                  'ohms': int(tmds_ohms), 'runtime': 'gpu_hdmi_link'})
    manifest['runtime']['gpu_hdmi_link'] = True
    epd_contacts = {'EPD_DIN': '3', 'EPD_CLK': '4', 'EPD_nCS': '5',
                    'EPD_DC': '6', 'EPD_nRST': '7', 'EPD_BUSY': '8',
                    'EPD_PWR': '9'}
    for signal, connector_pin in epd_contacts.items():
        source = [(ref, pin) for (ref, pin), net in cards['eink'].pins.items()
                  if ref == 'U1' and net == f'/{signal}']
        if len(source) != 1:
            raise ValueError(f'eink {signal}: RP2040 pad missing')
        resistor = path(cards['eink'], source[0], ('J2', connector_pin), '33R')
        manifest['paths'].append({'from': f'eink.U1.{source[0][1]}',
                                  'to': f'eink.J2.{connector_pin}', 'series': resistor,
                                  'ohms': 33, 'runtime': 'eink_panel_link'})
    manifest['runtime']['eink_panel_link'] = True
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
    gpo_led_links, gpo_led_paths, gpo_led_missing = gpo_indicator_routes(main, pcb)
    manifest['paths'].extend(gpo_led_paths)
    manifest['runtime']['gpo_led_connected'] = gpo_led_links
    manifest['runtime']['missing_routes'].extend(gpo_led_missing)
    manifest['runtime']['routed_top'] &= not gpo_led_missing
    cpu_controls, control_paths, control_missing = cpu_control_routes(
        main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(control_paths)
    manifest['runtime']['cpu_control_connected'] = cpu_controls
    manifest['runtime']['missing_routes'].extend(control_missing)
    manifest['runtime']['routed_top'] &= not control_missing
    ready_connected, ready_paths, ready_missing = cpu_ready_route(
        main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(ready_paths)
    manifest['runtime']['cpu_ready_connected'] = ready_connected
    manifest['runtime']['missing_routes'].extend(ready_missing)
    manifest['runtime']['routed_top'] &= not ready_missing
    sync_connected, sync_paths, sync_missing = cpu_sync_route(
        main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(sync_paths)
    manifest['runtime']['cpu_sync_connected'] = sync_connected
    manifest['runtime']['missing_routes'].extend(sync_missing)
    manifest['runtime']['routed_top'] &= not sync_missing
    status_links, status_paths, status_missing = cpu_status_routes(
        main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(status_paths)
    manifest['runtime']['cpu_status_connected'] = status_links
    manifest['runtime']['missing_routes'].extend(status_missing)
    manifest['runtime']['routed_top'] &= not status_missing
    irq_links, irq_paths, irq_missing = cpu_irq_routes(main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(irq_paths)
    manifest['runtime']['cpu_irq_connected'] = irq_links
    manifest['runtime']['missing_routes'].extend(irq_missing)
    manifest['runtime']['routed_top'] &= not irq_missing
    timer_links, timer_paths, timer_missing = cpu_timer_exp_routes(
        main, cards['cpu'], pcb, cpu_board)
    manifest['paths'].extend(timer_paths)
    manifest['runtime']['cpu_tmr_exp_connected'] = timer_links
    manifest['runtime']['missing_routes'].extend(timer_missing)
    manifest['runtime']['routed_top'] &= not timer_missing
    manual_reset, manual_reset_paths, manual_reset_missing = sysctl_manual_reset_route(
        main, cards['system'], pcb, system_board)
    manifest['paths'].extend(manual_reset_paths)
    monitor, monitor_paths, monitor_missing, monitor_nets = reset_monitor_runtime(main, pcb)
    manifest['runtime']['reset_monitor'] = monitor
    manifest['paths'].extend(monitor_paths)
    manifest['runtime']['missing_routes'].extend(monitor_missing)
    manifest['runtime']['routed_top'] &= not monitor_missing
    manifest['runtime']['sysctl_manual_reset_connected'] = manual_reset['sysctl']
    manifest['runtime']['button_manual_reset_connected'] = manual_reset['button']
    manifest['runtime']['missing_routes'].extend(manual_reset_missing)
    manifest['runtime']['routed_top'] &= not manual_reset_missing
    usb_links, usb_paths, usb_missing = system_usb_routes(cards['system'], system_board)
    manifest['paths'].extend(usb_paths)
    manifest['runtime']['system_usb_connected'] = usb_links
    manifest['runtime']['system_usb_complete'] = not usb_missing
    manifest['runtime']['missing_routes'].extend(usb_missing)
    manifest['runtime']['routed_top'] &= not usb_missing
    vbus_contacts, vbus_paths, vbus_missing = system_usb_vbus_routes(cards['system'], system_board)
    manifest['paths'].extend(vbus_paths)
    manifest['runtime']['sysctl_usb_vbus_contacts'] = vbus_contacts
    manifest['runtime']['sysctl_usb_vbus_connected'] = all(vbus_contacts.values())
    manifest['runtime']['missing_routes'].extend(vbus_missing)
    manifest['runtime']['routed_top'] &= not vbus_missing
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
    if monitor['complete']:
        for name in (*monitor_nets,'+3V3','3V3_STBY','GND'):
            runtime_net('main',name)
        for slot in range(1,7):runtime_net('main',f'SLOT{slot}_RST_n')
    for i in range(19):
        runtime_net('main', f'MEM_A{i}')
    for i in range(8):
        runtime_net('main', f'MEM_D{i}')
        runtime_net('main', f'CPU_D{i}')
        runtime_net('cpu', f'CPU_D{i}')
        if main_data_links[i]:
            runtime_net('main', f'CPU_D{i}_SRC')
    for i in range(16):
        runtime_net('main', f'CPU_A{i}')
        runtime_net('cpu', f'CPU_A{i}')
    for name in ('MEM_nOE', 'MEM_nWE', 'MEM_nCE_RAM', 'MEM_nCE_ROM',
                 'SPI_SCK', 'SPI_MOSI', 'SPI_MISO', 'BR_SCK', 'BR_MOSI',
                 'BR_MISO', 'BR_MISO_SRC', 'BR_nCS', 'PWR_HI', 'CC1', 'CC2', 'CC_AVG', 'CC_REF',
                 'nPOR'):
        runtime_net('main', name)
    for name in ('SPI_SCK_SRC', 'SPI_MOSI_SRC'):
        runtime_net('main', name)
    for slot in range(1, 7):
        runtime_net('main', f'SLOT{slot}_CS_n')
        runtime_net('main', f'SLOT_nIRQ{slot-1}')
        runtime_net('main', f'SPI_nCS{slot-1}_SRC')
    for name in ('BR_SCK', 'BR_MOSI', 'BR_MISO', 'BR_nCS'):
        runtime_net('system', name)
    for name in ('BR_SCK_MCU', 'BR_MOSI_MCU', 'BR_nCS_MCU'):
        runtime_net('system', name)
    if not io_usb_missing:
        for name in ('USB_DM', 'USB_DP', 'USB_CONN_DM', 'USB_CONN_DP'):
            runtime_net('io', name)
    # the VBUS switch enable and its fault flag (io_vbus_routes)
    if io_vbus['enable']:
        runtime_net('io', 'VBUS_EN')
    if io_vbus['fault'] and io_vbus['pullup']:
        runtime_net('io', 'VBUS_nFAULT')
    for name in sd_contacts:
        runtime_net('storage', name)
    for name in hdmi_contacts:
        runtime_net('gpu', f'TMDS_{name}')
        runtime_net('gpu', f'HD_{name}')
    for name in epd_contacts:
        runtime_net('eink', name)
        runtime_net('eink', f'{name}_J')
    # The panel attachment is usable only when its fitted 3V3→PTC→EPD_VCC
    # feed and the routed signal legs reach the header. This remains a binary
    # continuity model; it does not claim rail voltage, load, return, thermal,
    # or signal-integrity qualification.
    eink_board = card_boards.get('eink') if card_boards else None
    eink_panel_connected = None
    if eink_board is not None and Path(eink_board).is_file():
        from eink_panel import routes as eink_panel_routes
        eink_panel_connected, eink_panel_paths, eink_panel_missing = eink_panel_routes(
            cards['eink'], eink_board)
        manifest['eink_panel_copper'] = {
            'scope': 'binary panel/header continuity',
            'paths': eink_panel_paths,
            'missing': eink_panel_missing,
        }
        manifest['paths'].extend({**row, 'runtime': 'eink_panel_link'}
                                 for row in eink_panel_paths)
        manifest['runtime']['eink_panel_link'] = eink_panel_connected
        manifest['runtime']['eink_panel_copper_connected'] = eink_panel_connected
        manifest['runtime']['missing_routes'].extend(
            f'eink:{item}' for item in eink_panel_missing)
        manifest['runtime']['routed_top'] &= not eink_panel_missing
        if eink_panel_connected:
            runtime_net('eink', 'EPD_VCC')
        else:
            for name in ('EPD_DIN', 'EPD_CLK', 'EPD_nCS', 'EPD_DC',
                         'EPD_nRST', 'EPD_BUSY', 'EPD_PWR', 'EPD_VCC'):
                executed.discard(('eink', '/' + name))
                executed.discard(('eink', '/' + name + '_J'))
    elif eink_board is not None:
        manifest['runtime']['eink_panel_link'] = False
        manifest['runtime']['eink_panel_copper_connected'] = False
    for card in ('gpu', 'io', 'storage', 'wifi', 'eink'):
        from slot_spi import network
        if all(manifest['runtime']['card_slot_links'][card].values()):
            for fitted_net in network(cards[card],card)['nets']:runtime_net(card,fitted_net)
        if card_miso_network(cards[card], card):
            runtime_net(card, 'MISO_SRC')
        for name in ('SCK', 'MOSI', 'CS_n', 'IRQ_n', 'MISO',
                     'MISO_INT' if card == 'wifi' else 'MISO_OUT'):
            runtime_net(card, name)
    for card in ('system', 'gpu', 'io', 'storage', 'eink'):
        for name in ('QSPI_SCLK', 'QSPI_SD0', 'QSPI_SD1', 'QSPI_SD2', 'QSPI_SD3',
                     'QSPI_nSS' if card == 'system' else 'QSPI_SS'):
            runtime_net(card, name)
    for prefix, count in (('A', 16), ('D', 8)):
        for bit in range(count):
            runtime_net('cpu', f'FPGA_{prefix}{bit}')
    # The FPGA configuration chain (fpga_config_routes): a net counts as
    # executed while every one of its legs is on the routed copper.
    for (board, net), whole in fpga_nets.items():
        if whole:
            runtime_net(board, net.lstrip('/'))
    # sysctl's I2C bus and the CPU presence input it reads (i2c_expander_routes)
    for (board, net), ok in i2c_nets.items():
        if ok:
            runtime_net(board, net.lstrip('/'))
    # sysctl's ADC inputs (adc_sense_routes); main CC1/CC2 already execute
    # through the PWR_HI comparator model above
    for (board, net), ok in adc_nets.items():
        if ok and (board, net) not in (('main', '/CC1'), ('main', '/CC2')):
            runtime_net(board, net.lstrip('/'))
    # Firmware-driven LEDs (card_led_routes) execute while both legs are routed.
    for board, rows in led_rows.items():
        for row in rows:
            if row['connected']:
                runtime_net(board, row['net'])
                runtime_net(board, row['anode_net'])
    # The programming port (prog_port_routes): SWD from sysctl through the muxes
    # to an RP2040 card's debug pins; a net executes while its legs are routed.
    for (board, net), whole in prog_nets.items():
        if whole:
            runtime_net(board, net.lstrip('/'))
    # Rail indicators (rail_indicator_routes) execute while every leg is routed.
    for board, rows in rail_rows.items():
        for row in rows:
            if row['connected']:
                for net in row['nets']:
                    runtime_net(board, net)
    # The crystal network gates each RP2040 card's firmware (crystal_routes);
    # a net counts as executed while every one of its legs is routed.
    for (board, net), whole in crystal_nets.items():
        if whole:
            runtime_net(board, net.lstrip('/'))
    runtime_net('main', 'CPU_CLK')
    runtime_net('cpu', 'CPU_CLK')
    runtime_net('main', 'CPU_nRST')
    runtime_net('main', 'CPU_nRST_SRC')
    runtime_net('cpu', 'CPU_nRST')
    runtime_net('main', 'OSC_OUT')
    runtime_net('main', 'CLK12')
    for bit, connected in enumerate(gpo_led_links):
        if connected:
            runtime_net('main', f'GPO{bit}')
            runtime_net('main', f'LED_GPO{bit}')
    for signal, contact, source in (('strobe', 'CPU_nSTB', 'FPGA_nSTB'),
                                    ('rw', 'CPU_RW', 'FPGA_RW')):
        if cpu_controls[signal]:
            runtime_net('main', contact)
            runtime_net('cpu', contact)
            runtime_net('cpu', source)
    if ready_connected:
        runtime_net('main', 'CPU_nRDY_SRC')
        runtime_net('main', 'CPU_nRDY')
        runtime_net('cpu', 'CPU_nRDY')
    if sync_connected:
        runtime_net('cpu', 'FPGA_SYNC')
        runtime_net('cpu', 'CPU_SYNC')
        runtime_net('main', 'CPU_SYNC')
    for signal, contact, source in (('halted', 'CPU_HALTED', 'FPGA_HALTED'),
                                    ('waiting', 'CPU_WAITING', 'FPGA_WAITING')):
        if status_links[signal]:
            runtime_net('cpu', source)
            runtime_net('cpu', contact)
            runtime_net('main', contact)
    for i, connected in enumerate(irq_links):
        if connected:
            runtime_net('main', f'CPU_IRQ{i}_SRC')
            runtime_net('main', f'CPU_IRQ{i}')
            runtime_net('cpu', f'CPU_IRQ{i}')
    for i, connected in enumerate(timer_links):
        if connected:
            runtime_net('cpu', f'FPGA_TMR_EXP{i}')
            runtime_net('cpu', f'CPU_TMR_EXP{i}')
            runtime_net('main', f'CPU_TMR_EXP{i}')
    if manual_reset['sysctl']:
        runtime_net('system', 'SYS_nRST')
    if all(manual_reset.values()):
        runtime_net('main', 'nMR')
    if not usb_missing:
        for name in ('USB_DM', 'USB_DM_MCU', 'USB_DP', 'USB_DP_MCU', 'USB_CC1', 'USB_CC2'):
            runtime_net('system', name)
    if all(vbus_contacts.values()):
        for name in ('USB_VBUS', 'VBUS_GATE', 'USB_nVBUS'):
            runtime_net('system', name)
    manifest.update(audit(circuits, executed, structural, implemented_checks()))
    manifest['runtime_nets'] = sorted(f'{board}:{net.lstrip("/")}' for board, net in executed)
    return manifest


def main_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--card-board-dir', type=Path, default=ROOT / 'build/hw',
                        help='directory containing each generated card PCB under CARD/CARD.kicad_pcb')
    parser.add_argument('--system-board', type=Path,
                        default=ROOT / 'build/hw/system/system-routed.kicad_pcb',
                        help='explicit routed system-card PCB for the QSPI boot prerequisite')
    parser.add_argument('--cpu-board', type=Path, default=ROOT / 'build/hw/cpu/cpu.kicad_pcb',
                        help='routed CPU-card PCB for address/data series links')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--require-route', action='store_true', help='fail unless required board/card paths have routed copper')
    parser.add_argument('--require-coverage', action='store_true', help='fail on any modeled/waiver coverage gap')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-') as temporary:
        manifest = check(exported_cards(Path(temporary)), read(args.main_netlist),
                         args.main_netlist.with_suffix('.kicad_pcb'),
                         {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                          for card in ('gpu', 'io', 'storage', 'wifi', 'eink')},
                         args.system_board, args.cpu_board)
    if args.require_route and not manifest['runtime']['routed_top']:
        missing = manifest['runtime']['missing_routes']
        raise ValueError(f'co-sim paths lack routed copper: {", ".join(missing)}')
    if args.require_coverage and not manifest['coverage_complete']:
        missing = manifest['unmodeled_nets']
        families = ', '.join(f'{name} {len(nets)}' for name, nets in manifest['coverage_families'].items())
        raise ValueError(f'{len(missing)} netlist nets lack a model or explicit waiver ({families}): '
                         f'{", ".join(missing)}')
    output = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main_cli()
