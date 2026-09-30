#!/usr/bin/env python3
"""Run catalogue gates on a completed, provenance-checked board build.

Missing coverage is an error. In particular, exporting Gerbers is not a
Gerber re-import DRC, and a regulator budget is not a board transient model.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import boardevidence

ROOT = boardevidence.ROOT
BOARDS = ('main', 'cpu', 'gpu', 'io', 'wifi', 'storage', 'eink', 'system')
POWER = {
    'main': [('buck.py',), ('ldo.py', '1v2'), ('inrush.py',), ('cc.py',), ('budget.py',),
             ('main_bind.py', '{out}'), ('main_input_heat.py', '{out}', '--solver', 'amg',
              '--dump-results', '{out}/../main-thermal-results.json')],
    'cpu': [('ldo.py', 'cpu-card')], 'wifi': [('buck.py', 'wifi-card')],
    'gpu': [('hdmi.py',)], 'io': [('boost.py',), ('io_switch_bind.py', '{out}'), ('io_port_switch.py',)],
    'storage': [('budget.py',)], 'eink': [('budget.py',)], 'system': [('budget.py',)],
}
# These are contract gaps, not accepted waivers. Retain failed rows until
# the specified tests exist; do not silently narrow the catalogue's claims.
GAPS = {
    'power': {
        'cpu': 'bound socket 3V3 feed, minimum finished copper/contact resistance, effective C22/C1-C4 capacitance and ESR, and FPGA maximum core current',
        'gpu': 'RP2040 VREG 1.20 V transient/droop model at 252 MHz',
        'io': 'RP2040 internal regulator transient/droop model',
        'storage': 'SD-card load-step and RP2040 internal regulator model',
        'eink': 'panel load-step and RP2040 internal regulator model',
        'system': 'RP2040 internal regulator transient model',
    },
    'thermal': {name: 'RP2040 internal regulator dissipation at maximum board load'
                for name in ('gpu', 'io', 'storage', 'eink', 'system')},
}


def run(command):
    subprocess.run([str(x) for x in command], cwd=ROOT, check=True)


def check_report(report, check):
    if not {'error', 'warning', 'exclusion'} <= set(report.get('included_severities', ())):
        raise ValueError('%s report omitted a severity class' % check)
    if check == 'erc':
        sheets = report.get('sheets')
        if not isinstance(sheets, list) or not sheets:
            raise ValueError('ERC report missing sheets')
        if any(not isinstance(sheet.get('violations'), list) for sheet in sheets):
            raise ValueError('ERC report missing sheet violations')
        findings = [v for sheet in sheets for v in sheet['violations']]
    else:
        keys = ('violations', 'unconnected_items', 'schematic_parity')
        if any(not isinstance(report.get(k), list) for k in keys):
            raise ValueError('DRC report missing violations, unconnected_items or schematic_parity')
        findings = [v for key in keys for v in report[key]]
    if findings:
        raise ValueError('%s has %d findings (no implicit waivers)' % (check, len(findings)))


def stock_counts(path):
    counts = {}
    with path.open() as source:
        for row in csv.DictReader(source):
            code = row['LCSC Part #']
            refs = [r.strip() for r in row['Designator'].split(',') if r.strip()]
            if not code.startswith('C') or not code[1:].isdigit() or not refs:
                raise ValueError('invalid BOM line')
            counts[code] = counts.get(code, 0) + len(refs)
    if not counts:
        raise ValueError('empty BOM')
    return counts


def check(board, mode, out):
    evidence = boardevidence.validate(board, out)
    if mode in ('erc', 'drc'):
        # Fresh tool execution also catches a modified local KiCad library.
        with tempfile.TemporaryDirectory(prefix='cupc8-boardcheck-') as scratch:
            report = Path(scratch) / 'report.json'
            if mode == 'erc':
                command = ['kicad-cli', 'sch', 'erc']
                artifact = out / (board + '.kicad_sch')
            else:
                command = ['kicad-cli', 'pcb', 'drc', '--schematic-parity']
                artifact = out / (board + '.kicad_pcb')
            run(command + ['--format', 'json', '--severity-all', '--exit-code-violations', '-o', report, artifact])
            check_report(json.loads(report.read_text()), mode)
    elif mode in ('bom', 'footprints'):
        if os.environ.get('CUPC8_OFFLINE'):
            raise ValueError('offline mode cannot certify BOM/footprint library checks')
        run([sys.executable, 'hw/tools/bomcheck.py', board, '--out', out])
        if mode == 'bom':
            import kicadgen
            print(kicadgen.check_stock(stock_counts(out / 'fab/bom.csv'), evidence['boards']))
    elif mode == 'mechanical':
        # All fits: the mainboard and system card must be present. The old
        # stand-in socket row cannot certify manufacture readiness.
        run([sys.executable, 'hw/mech/fit.py'])
    elif mode == 'power':
        for command in POWER[board]:
            args = [sys.executable, 'hw/power/' + command[0],
                    *(out if a == '{out}' else str(a).replace('{out}', str(out)) for a in command[1:])]
            if board in ('wifi', 'cpu'):
                args.append(out)
            run(args)
        if board in GAPS['power']:
            raise ValueError('missing power coverage: ' + GAPS['power'][board])
    elif mode == 'thermal':
        run([sys.executable, 'hw/power/thermal.py'])
        if board == 'wifi':
            run([sys.executable, 'hw/power/thermal.py', 'wifi-card', out])
        if board in GAPS['thermal']:
            raise ValueError('missing thermal coverage: ' + GAPS['thermal'][board])
        if board in ('main', 'cpu'):
            raise ValueError('thermal model still needs regulator/netlist binding')
    elif mode == 'connectors':
        run([sys.executable, 'hw/tools/pincheck.py'])
        import connectorcheck
        count = connectorcheck.check(board, out / (board + '.net'))
        print('%s: %d connector contacts match the specified netlist pinout' % (board, count))
    elif mode == 'strapping':
        if board != 'wifi':
            raise ValueError('strapping check applies only to Wi-Fi card')
        run([sys.executable, 'hw/tools/strapcheck.py', out / 'wifi.net'])
    elif mode == 'fab':
        check_report(json.loads((out / 'drc.json').read_text()), 'drc')
        import fabcheck
        print(fabcheck.check(out))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board', choices=BOARDS)
    parser.add_argument('check', choices=('erc', 'drc', 'bom', 'footprints', 'mechanical', 'power',
                                         'thermal', 'connectors', 'strapping', 'fab'))
    parser.add_argument('--out', type=Path, help='build directory; source hashes must match this checkout')
    args = parser.parse_args()
    try:
        check(args.board, args.check, args.out or ROOT / 'build/hw' / args.board)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print('FAIL %s %s: %s' % (args.board, args.check, error), file=sys.stderr)
        return 1
    print('PASS %s %s' % (args.board, args.check))
    return 0


if __name__ == '__main__':
    sys.exit(main())
