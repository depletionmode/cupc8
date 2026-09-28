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
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from netlist import read
from coverage import audit
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


def card_slot_routes(cards, board_paths):
    """Bind each slot card's GPIO and buffered MISO legs to its PCB copper."""
    rows, paths, missing = {}, [], []
    contacts = {'sck': ('SCK', 'B13'), 'mosi': ('MOSI', 'B15'),
                'cs': ('CS_n', 'A14'), 'irq': ('IRQ_n', 'B10')}
    for card in ('gpu', 'io', 'storage', 'wifi', 'eink'):
        circuit = cards[card]
        board = board_paths.get(card) if board_paths else None
        routed = board is not None and Path(board).is_file()
        if routed:
            sys.path.insert(0, str(ROOT / 'hw/si'))
            from ibis_bus import routed_distances
        links = {}

        def leg(name, net, first, last):
            path(circuit, first, last)
            length = None
            if routed:
                length = routed_distances(Path(board), f'/{net}', first, [last])[
                    f'{last[0]}.{last[1]}']
            paths.append({'from': f'{card}.{first[0]}.{first[1]}',
                          'to': f'{card}.{last[0]}.{last[1]}',
                          'route_mm': length, 'runtime': f'{card}_{name}_connected'})
            return length is not None

        for signal, (net, contact) in contacts.items():
            targets = [(ref, pin) for (ref, pin), attached in circuit.pins.items()
                       if ref == 'U1' and attached == f'/{net}']
            if len(targets) != 1:
                raise ValueError(f'{card}:{net}: expected one MCU GPIO')
            links[signal] = leg(signal, net, ('J1', contact), targets[0])
        buffer_ref = 'U3' if card == 'wifi' else 'U4'
        internal = 'MISO_INT' if card == 'wifi' else 'MISO_OUT'
        source = [(ref, pin) for (ref, pin), attached in circuit.pins.items()
                  if ref == 'U1' and attached == f'/{internal}']
        if len(source) != 1:
            raise ValueError(f'{card}:{internal}: expected one MCU MISO output')
        miso_input = leg('miso', internal, source[0], (buffer_ref, '2'))
        miso_output = leg('miso', 'MISO', (buffer_ref, '4'), ('J1', 'B16'))
        miso_enable = leg('miso', 'CS_n', ('J1', 'A14'), (buffer_ref, '1'))
        links['cs'] &= miso_enable
        links['miso'] = miso_input and miso_output and miso_enable
        rows[card] = links
        for signal, connected in links.items():
            if not connected:
                missing.append(f'{card}:{signal}_slot_copper')
    return rows, paths, missing


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
    if cpu.components.get('RN5') != ('33', ('Device', 'R_Pack04')):
        raise ValueError('CPU strobe/RW: missing 33-ohm isolated series pack')
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
                path(cpu, source, finger, '33') != series_ref or \
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
    if main.components.get('R33') != ('33', ('Device', 'R')) or \
            set(main.nets.get('/CPU_nRDY_SRC', ())) != {source, series_in} or \
            set(main.nets.get('/CPU_nRDY', ())) != {series_out, socket} or \
            set(cpu.nets.get('/CPU_nRDY', ())) != {finger, receiver} or \
            path(main, source, socket, '33') != 'R33':
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
    if cpu.components.get('RN5') != ('33', ('Device', 'R_Pack04')) or \
            set(cpu.nets.get('/FPGA_SYNC', ())) != {source, series_in} or \
            set(cpu.nets.get('/CPU_SYNC', ())) != {series_out, finger} or \
            set(main.nets.get('/CPU_SYNC', ())) != {socket, receiver} or \
            path(cpu, source, finger, '33') != 'RN5.3':
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


def sysctl_manual_reset_route(main, system, main_board, system_board):
    """Bind the system MCU's reset GPIO across J2/J3 to supervisor MR."""
    system_nodes = {('U1', '35'), ('J2', 'B4')}
    main_nodes = {('J3', '36'), ('SW1', '1'), ('TP14', '1'), ('U6', '3')}
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
            if path(card, source[0], finger[0], '33') is None:
                raise ValueError(f'CPU {prefix}{card_bit}: 33-ohm driver channel missing')
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
    resistor = path(main, source, socket, '33')
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
    manifest['runtime']['routed_top'] = not manifest['runtime']['missing_routes']
    manifest['runtime']['routed_timing'] &= all(write_links.values()) and \
        manifest['runtime']['rom_read_d0_connected']
    # Each slot-select source crosses one 33-ohm resistor. Verify both copper
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
        if resistor is None or resistor.value != '33':
            raise ValueError(f'{source_net}: slot-select series resistor missing')
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
    cpu_links, cpu_paths, cpu_missing = cpu_bus_routes(
        cards['cpu'], cpu_board, manifest['runtime']['cpu_address'], manifest['runtime']['cpu_data'])
    manifest['runtime']['cpu_address_links'] = cpu_links['address']
    manifest['runtime']['cpu_data_links'] = cpu_links['data']
    manifest['paths'].extend(cpu_paths)
    manifest['runtime']['missing_routes'].extend(cpu_missing)
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
    # All four HDMI differential lanes leave the RP2040 through the 270 ohm
    # packs; the capture endpoint represents the receptacle, not MCU GPIOs.
    hdmi_contacts = {'D2P': '1', 'D2N': '3', 'D1P': '4', 'D1N': '6',
                     'D0P': '7', 'D0N': '9', 'CKP': '10', 'CKN': '12'}
    for lane, connector_pin in hdmi_contacts.items():
        source = [(ref, pin) for (ref, pin), net in cards['gpu'].pins.items()
                  if ref == 'U1' and net == f'/TMDS_{lane}']
        if len(source) != 1:
            raise ValueError(f'gpu TMDS_{lane}: RP2040 pad missing')
        resistor = path(cards['gpu'], source[0], ('J2', connector_pin), '270')
        manifest['paths'].append({'from': f'gpu.U1.{source[0][1]}',
                                  'to': f'gpu.J2.{connector_pin}', 'series': resistor,
                                  'ohms': 270, 'runtime': 'gpu_hdmi_link'})
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
    manual_reset, manual_reset_paths, manual_reset_missing = sysctl_manual_reset_route(
        main, cards['system'], pcb, system_board)
    manifest['paths'].extend(manual_reset_paths)
    manifest['runtime']['sysctl_manual_reset_connected'] = manual_reset['sysctl']
    manifest['runtime']['button_manual_reset_connected'] = manual_reset['button']
    manifest['runtime']['missing_routes'].extend(manual_reset_missing)
    manifest['runtime']['routed_top'] &= not manual_reset_missing
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
    for name in ('USB_DM', 'USB_DP', 'USB_CONN_DM', 'USB_CONN_DP'):
        runtime_net('io', name)
    for name in sd_contacts:
        runtime_net('storage', name)
    for name in hdmi_contacts:
        runtime_net('gpu', f'TMDS_{name}')
        runtime_net('gpu', f'HD_{name}')
    for name in epd_contacts:
        runtime_net('eink', name)
        runtime_net('eink', f'{name}_J')
    for card in ('gpu', 'io', 'storage', 'wifi', 'eink'):
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
    if manual_reset['sysctl']:
        runtime_net('system', 'SYS_nRST')
    if all(manual_reset.values()):
        runtime_net('main', 'nMR')
    manifest.update(audit(circuits, executed, structural))
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
        raise ValueError(f'{len(missing)} netlist nets lack a model or explicit waiver: {", ".join(missing[:25])}')
    output = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main_cli()
