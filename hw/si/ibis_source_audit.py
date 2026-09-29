#!/usr/bin/env python3
"""Audit pinned IBIS assumptions and FPGA source-pin copper paths.

This validates source data and a routed main/CPU board subset. It does
not substitute measured planar paths into the diagnostic transmission lines.
"""
import argparse
import csv
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import re
import sys

from fetch_ice40_ibis import verify
from ibis_bus import (CORNER, FIXTURE_C, FIXTURE_R, MODELS, VDD, VIH, VIL,
                      VENDOR_TQ144_TYPICAL, model_sections, number,
                      routed_distances, run_spice)

ROOT = Path(__file__).resolve().parents[2]
PINOUT_SHA256 = 'f93acd663a6e62441cae3fe552c0fbe25e34fe9923ee475e84108f9645fbd71e'
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/cosim'))
import boardevidence
from netlist import read as read_netlist


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same(actual, expected):
    return math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-15)


def model_block(data, model):
    text = data.decode('ascii').replace('\r', '')
    marker = re.search(r'^\[Model\]\s+' + re.escape(model) + r'\s*$', text, re.M)
    if marker is None:
        raise ValueError(f'IBIS model {model} absent')
    tail = text[marker.end():]
    end = re.search(r'^\[Model\]', tail, re.M)
    return tail[:end.start()] if end else tail


def line_value(lines, key):
    matches = [re.match(r'^' + re.escape(key) + r'\s*=\s*(\S+)', line)
               for line in lines]
    values = [number(match[1]) for match in matches if match]
    if len(values) != 1:
        raise ValueError(f'{key}: expected one IBIS value, found {len(values)}')
    return values[0]


def vendor_contract(data):
    result = {}
    for model in MODELS:
        block = model_block(data, model)
        sections = model_sections(data, model)
        if not re.search(r'^Model_type\s+I/O\s*$', block, re.M):
            raise ValueError(f'{model}: not an I/O buffer')
        lines = block.splitlines()
        thresholds = {'vil_v': line_value(lines, 'Vinl'),
                      'vih_v': line_value(lines, 'Vinh')}
        if not same(thresholds['vil_v'], VIL) or not same(thresholds['vih_v'], VIH):
            raise ValueError(f'{model}: code threshold differs from vendor model')
        vline = re.search(r'^\[Voltage Range\]\s+(\S+)\s+(\S+)\s+(\S+)', block, re.M)
        cline = re.search(r'^C_comp\s+(\S+)\s+(\S+)\s+(\S+)', block, re.M)
        if vline is None or cline is None:
            raise ValueError(f'{model}: missing voltage range or C_comp')
        vdd = {corner: number(vline[1 + index]) for corner, index in CORNER.items()}
        comp = {corner: number(cline[1 + index]) for corner, index in CORNER.items()}
        if any(not same(vdd[corner], VDD[corner]) for corner in CORNER):
            raise ValueError(f'{model}: code VDD differs from vendor voltage range')
        fixtures = {}
        for edge, section in (('rise', 'Rising Waveform'), ('fall', 'Falling Waveform')):
            values = sections[section]
            fixture = {key: line_value(values, key) for key in
                       ('R_fixture', 'C_fixture', 'V_fixture',
                        'V_fixture_min', 'V_fixture_max')}
            if not same(fixture['R_fixture'], FIXTURE_R) or not same(fixture['C_fixture'], FIXTURE_C):
                raise ValueError(f'{model}/{edge}: code fixture differs from vendor')
            for corner, key in (('typ', 'V_fixture'), ('min', 'V_fixture_min'),
                                ('max', 'V_fixture_max')):
                target = 0 if edge == 'rise' else VDD[corner]
                if not same(fixture[key], target):
                    raise ValueError(f'{model}/{edge}: {key} differs from vendor')
            fixtures[edge] = fixture
        result[model] = {'model_type': 'I/O', 'thresholds': thresholds,
                         'voltage_range_v': vdd, 'c_comp_f': comp,
                         'waveform_fixtures': fixtures}
    return result


def tq144_candidates(data):
    text = data.decode('ascii').replace('\r', '')
    package = text.split('[Package]', 1)[1].split('[Pin]', 1)[0]
    lines = package.splitlines()
    candidates = []
    for index, line in enumerate(lines):
        if line.strip() != '| TQ144':
            continue
        rows = {}
        for candidate in lines[index + 1:index + 8]:
            fields = candidate.lstrip('| ').split()
            if fields and fields[0] in ('R_pkg', 'L_pkg', 'C_pkg'):
                if len(fields) != 4:
                    raise ValueError('TQ144 package row lacks typ/min/max')
                rows[fields[0]] = [number(value) for value in fields[1:]]
        if set(rows) != {'R_pkg', 'L_pkg', 'C_pkg'}:
            raise ValueError('TQ144 candidate lacks R/L/C')
        candidates.append({'r_ohm': rows['R_pkg'], 'l_h': rows['L_pkg'],
                           'c_f': rows['C_pkg']})
    if len(candidates) != 2 or not (same(candidates[0]['l_h'][0], 7.98e-9) and
                                     same(candidates[1]['l_h'][0], 10.53e-9)):
        raise ValueError('unexpected vendor TQ144 candidate tables')
    return candidates


def pin_banks(pinout):
    with pinout.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    banks = {}
    for row in rows:
        pin = row['TQ144']
        if pin in banks:
            raise ValueError(f'duplicate TQ144 pin {pin}')
        banks[pin] = row['Bank']
    if len(banks) != 144:
        raise ValueError('incomplete TQ144 pin table')
    return banks


def model_for_pin(pin, banks):
    bank = banks.get(pin)
    if bank not in ('0', '1', '2', '3'):
        raise ValueError(f'pin {pin}: no I/O bank assignment')
    return 'lvc330_b3io' if bank == '3' else 'lvc330io'


def source_paths(main_build, cpu_build, top, banks):
    paths = top['paths']
    main_netlist = read_netlist(main_build / 'main.net')
    cpu_netlist = read_netlist(cpu_build / 'cpu.net')
    main_board = main_build / 'main.kicad_pcb'
    cpu_board = cpu_build / 'cpu.kicad_pcb'
    slot = routed_distances(main_board, '/SPI_SCK', ('R36', '2'),
                            [(f'J{number}', 'B13') for number in range(11, 17)])
    slot_rows = []
    source_pins = set()
    for number in range(11, 17):
        contact = f'J{number}.B13'
        links = [p for p in paths if p.get('to') == 'main.' + contact and
                 p.get('from', '').startswith('main.U7.') and p.get('ohms') == 33]
        if len(links) != 1:
            raise ValueError(f'{contact}: no unique FPGA 33-ohm source path')
        link = links[0]
        pin = link['from'].split('.')[-1]
        resistor = main_netlist.series(('U7', pin), (f'J{number}', 'B13'))
        if resistor is None or resistor.ref != 'R36' or resistor.value != '33':
            raise ValueError(f'{contact}: archived netlist disagrees with source path')
        routed = [p for p in paths if p.get('from') == 'main.R36.2' and
                  p.get('to') == 'main.' + contact]
        if len(routed) != 1 or routed[0].get('route_mm') != slot[contact]:
            raise ValueError(f'{contact}: top copper path differs from archived board')
        if slot[contact] is None:
            raise ValueError(f'{contact}: archived copper path is open')
        source_pins.add(pin)
        slot_rows.append({'connector': contact, 'source_pin': pin,
                          'bank': banks[pin], 'model': model_for_pin(pin, banks),
                          'resistor': resistor.ref, 'planar_copper_mm': slot[contact]})
    if len(source_pins) != 1:
        raise ValueError('slot SCK has multiple FPGA source pins')
    cpu_rows = []
    selected = [p for p in paths if p.get('from', '').startswith('cpu.U1.') and
                p.get('to', '').startswith('cpu.J1.') and p.get('ohms') == 68]
    if len(selected) != 31:
        raise ValueError(f'CPU card expected 31 FPGA series outputs, found {len(selected)}')
    for link in selected:
        pin = link['from'].split('.')[-1]
        contact = link['to'].split('.')[-1]
        net = cpu_netlist.net('J1', contact)
        resistor = cpu_netlist.series(('U1', pin), ('J1', contact))
        if resistor is None or resistor.value != '68' or resistor.ref != link.get('series'):
            raise ValueError(f'CPU {pin}->{contact}: top/netlist series mismatch')
        ref = resistor.ref.split('.')[0]
        far_pads = [pad for (part, pad), attached in cpu_netlist.pins.items()
                    if part == ref and attached == net]
        if len(far_pads) != 1:
            raise ValueError(f'CPU {pin}->{contact}: ambiguous resistor far pad')
        length = routed_distances(cpu_board, net, (ref, far_pads[0]),
                                  [('J1', contact)])[f'J1.{contact}']
        if length is None:
            raise ValueError(f'CPU {pin}->{contact}: archived copper path is open')
        cpu_rows.append({'fpga_pin': pin, 'connector': f'J1.{contact}',
                         'bank': banks[pin], 'model': model_for_pin(pin, banks),
                         'resistor': resistor.ref, 'resistor_far_pad': far_pads[0],
                         'planar_copper_mm': length})
    cpu_rows.sort(key=lambda row: (int(row['fpga_pin']), row['connector']))
    return slot_rows, cpu_rows


def case_key(case):
    return tuple(case[key] for key in ('model', 'topology', 'corner', 'edge',
                                       'assumed_length_mm', 'assumed_receiver_pf',
                                       'commented_tq144_l_nh'))


def case_unstable(case):
    return not all(node['threshold_stable'] for node in case['receivers'])


def audit(ibis, main_build, cpu_build, top_path, pinout, source_root,
          diagnostic_path=None, vendor_diagnostic_path=None,
          current_route=False):
    data = ibis.read_bytes()
    vendor_sha = verify(data)
    if b'Bank3(left bank) IOs have strong drive and use model lvc330_b3io' not in data:
        raise ValueError('vendor bank-3 model assignment statement changed')
    if sha(pinout) != PINOUT_SHA256:
        raise ValueError('TQ144 pinout CSV differs from reviewed source')
    receipts = {}
    validator = boardevidence
    if current_route and source_root != ROOT:
        spec = importlib.util.spec_from_file_location('current_boardevidence',
                        source_root / 'hw/tools/boardevidence.py')
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
    for board, build in (('main', main_build), ('cpu', cpu_build)):
        receipt = validator.validate(board, build, root=source_root)
        receipts[board] = {'receipt_sha256': sha(build / 'evidence.json'),
                           'board_sha256': receipt['artifacts'][f'{board}.kicad_pcb'],
                           'netlist_sha256': receipt['artifacts'][f'{board}.net']}
    top = json.loads(top_path.read_text())
    if not top.get('runtime', {}).get('routed_top'):
        raise ValueError('archived co-simulation top is not routed')
    banks = pin_banks(pinout)
    slot, cpu = source_paths(main_build, cpu_build, top, banks)
    counts = {name: sum(row['model'] == name for row in cpu) for name in MODELS}
    packages = tq144_candidates(data)
    for declared, candidate in zip(VENDOR_TQ144_TYPICAL, packages):
        expected = (candidate['l_h'][0] * 1e9, candidate['c_f'][0] * 1e12,
                    candidate['r_ohm'][0])
        if any(not same(actual, value) for actual, value in zip(declared, expected)):
            raise ValueError('coded TQ144 typical package differs from pinned vendor file')
    modeled_package_c = inspect.signature(run_spice).parameters['package_pf'].default * 1e-12
    modeled_package_r = inspect.signature(run_spice).parameters['package_ohm'].default
    result = {
        'scope': 'pinned vendor IBIS source and ' +
                 ('current' if current_route else 'archived') +
                 ' main/CPU FPGA source-path audit',
        'ibis_sha256': vendor_sha, 'pinout_sha256': sha(pinout),
        'top_sha256': sha(top_path), 'receipts': receipts,
        'vendor_model_contract': vendor_contract(data),
        'tq144_commented_package_candidates': packages,
        'diagnostic_bus_model_package_c_f': modeled_package_c,
        'diagnostic_bus_model_package_r_ohm': modeled_package_r,
        'diagnostic_bus_model_package_c_matches_typical_candidates': any(
            same(modeled_package_c, item['c_f'][0]) for item in packages),
        'diagnostic_bus_model_package_r_matches_typical_candidates': any(
            same(modeled_package_r, item['r_ohm'][0]) for item in packages),
        'slot_sck': {'source_pin': slot[0]['source_pin'], 'bank': slot[0]['bank'],
                     'applicable_ibis_model': slot[0]['model'], 'paths': slot},
        'cpu_card': {'source_count': len(cpu), 'models_by_source_pin': counts,
                     'minimum_planar_copper_mm': min(row['planar_copper_mm'] for row in cpu),
                     'maximum_planar_copper_mm': max(row['planar_copper_mm'] for row in cpu),
                     'paths': cpu},
        'valid_for_full_bus_si': False,
        'limits': ['these planar lengths exclude via/barrel length, branch topology and return-plane changes',
                   'the diagnostic still uses assumed 120/180 mm line lengths and loads',
                   'the two commented TQ144 package rows are not assigned to HX4K by this file',
                   'the present linear driver omits nonlinear I/V and receiver IBIS behavior',
                   'the loaded physical bus remains unverified' if current_route else
                   'the main-board current route and loaded physical bus remain unverified'],
    }
    if diagnostic_path is not None:
        diagnostic = json.loads(diagnostic_path.read_text())
        if (diagnostic['source_sha256'] != vendor_sha or
            diagnostic['top_sha256'] != sha(top_path) or
            diagnostic['main_board_sha256'] != receipts['main']['board_sha256'] or
            len(diagnostic['cases']) != 96 or
            not diagnostic['top_routed_signals'] or
            not diagnostic['measured_copper_paths_complete'] or
            {row['connector']: row['planar_copper_mm'] for row in slot} !=
                diagnostic['measured_copper_paths_mm']['slot_sck']):
            raise ValueError('ngspice diagnostic does not match pinned source and routed snapshot')
        unstable = {model: sum(case['model'] == model and
                               case['topology'] == 'six_slot_sck' and
                               not all(node['threshold_stable'] for node in case['receivers'])
                               for case in diagnostic['cases']) for model in MODELS}
        result['diagnostic'] = {
            'report_sha256': sha(diagnostic_path), 'case_count': len(diagnostic['cases']),
            'maximum_fixture_replay_error_v': max(case['fixture_max_error_v']
                                                   for case in diagnostic['cases']),
            'unstable_six_slot_cases_by_model': unstable,
            'applicable_sck_model_unstable_cases': unstable[slot[0]['model']],
            'waveform_line_lengths_are_assumed': True,
            'valid_for_physical_bus_si': False,
        }
        if vendor_diagnostic_path is not None:
            vendor = json.loads(vendor_diagnostic_path.read_text())
            if (vendor['source_sha256'] != vendor_sha or
                vendor['top_sha256'] != sha(top_path) or
                vendor['main_board_sha256'] != receipts['main']['board_sha256'] or
                not vendor['vendor_package_typical_sweep'] or
                len(vendor['cases']) != len(diagnostic['cases']) or
                any(case_key(a) != case_key(b)
                    for a, b in zip(diagnostic['cases'], vendor['cases']))):
                raise ValueError('vendor-package ngspice sweep differs in source or case scope')
            for case in vendor['cases']:
                package = next(item for item in VENDOR_TQ144_TYPICAL
                               if same(item[0], case['commented_tq144_l_nh']))
                if (not same(case['package_c_pf'], package[1]) or
                    not same(case['package_r_ohm'], package[2])):
                    raise ValueError('ngspice case does not use vendor TQ144 typical R/L/C')
            counts = {model: sum(case['model'] == model and
                                 case['topology'] == 'six_slot_sck' and case_unstable(case)
                                 for case in vendor['cases']) for model in MODELS}
            flips = []
            for old, new in zip(diagnostic['cases'], vendor['cases']):
                changed = [a['node'] for a, b in zip(old['receivers'], new['receivers'])
                           if a['threshold_stable'] != b['threshold_stable']]
                if changed:
                    flips.append({'case': case_key(old), 'receiver_nodes': changed})
            result['package_sensitivity'] = {
                'vendor_report_sha256': sha(vendor_diagnostic_path),
                'vendor_case_count': len(vendor['cases']),
                'vendor_fixture_replay_error_max_v': max(case['fixture_max_error_v']
                                                          for case in vendor['cases']),
                'vendor_unstable_six_slot_cases_by_model': counts,
                'applicable_sck_model_unstable_cases': counts[slot[0]['model']],
                'cases_with_receiver_status_change': len(flips),
                'receiver_status_changes': flips,
                'valid_for_physical_bus_si': False,
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, required=True)
    parser.add_argument('--main-build', type=Path, required=True)
    parser.add_argument('--cpu-build', type=Path, required=True)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--pinout', type=Path,
                        default=ROOT / 'hw/datasheets/iCE40HX4K-TQ144-pinout.csv')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--diagnostic', type=Path,
                        help='optional saved 96-case ngspice report to bind to this audit')
    parser.add_argument('--vendor-diagnostic', type=Path,
                        help='same 96 cases with both vendor TQ144 typical R/L/C candidates')
    parser.add_argument('--current-route', action='store_true',
                        help='label validated main/CPU inputs as the current routed builds')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.vendor_diagnostic and not args.diagnostic:
        parser.error('--vendor-diagnostic requires --diagnostic')
    result = audit(args.ibis.resolve(), args.main_build.resolve(),
                   args.cpu_build.resolve(), args.top.resolve(),
                   args.pinout.resolve(), args.source_root.resolve(),
                   args.diagnostic.resolve() if args.diagnostic else None,
                   args.vendor_diagnostic.resolve() if args.vendor_diagnostic else None,
                   args.current_route)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"vendor/fixture checked; SCK bank {result['slot_sck']['bank']}; "
          f"CPU model counts {result['cpu_card']['models_by_source_pin']}")


if __name__ == '__main__':
    main()
