#!/usr/bin/env python3
"""Compare complex USB port response from the migration-bound saved traces."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from usb_port_audit import FREQUENCIES, PORTS, sparams, spectrum

RUNS = {
    '0.075': ('usb-io-pml-fixed.json', 'usb-io-openems-pml-clear-1mm-fixed-window'),
    '0.090': ('usb-io-pml-mesh-090-fixed.json',
              'usb-io-openems-pml-clear-1mm-mesh-0p090mm-fixed-window'),
}
CUTOFF_SECONDS = 16e-9


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parts(value):
    return [float(value.real), float(value.imag)]


def compare(reports, fields, migration_path, fine_report_path=None,
            fine_fields=None, fine_migration_path=None):
    migration = json.loads(migration_path.read_text())
    runs = {mesh: (reports / report_name, fields / field_name)
            for mesh, (report_name, field_name) in RUNS.items()}
    fine_migration = None
    if any(value is not None for value in
           (fine_report_path, fine_fields, fine_migration_path)):
        if not all(value is not None for value in
                   (fine_report_path, fine_fields, fine_migration_path)):
            raise ValueError('fine report, fields and migration must be supplied together')
        fine_migration = json.loads(fine_migration_path.read_text())
        if (not fine_migration['modeled_input_equivalent'] or
            any(fine_migration['rebuilt_receipt'][key] !=
                migration['receipts']['io']['current'][key]
                for key in ('receipt_sha256', 'board_sha256', 'netlist_sha256')) or
            fine_migration['saved_report_sha256'] != sha(fine_report_path)):
            raise ValueError('fine mesh migration does not match rebuilt IO receipt')
        runs['0.060'] = (fine_report_path, fine_fields)
    rows_by_mesh = {}
    source = {}
    for mesh, (report_path, directory) in runs.items():
        report = json.loads(report_path.read_text())
        if mesh == '0.060':
            migrated_hash = fine_migration['saved_report_sha256']
            migrated_board = fine_migration['saved_receipt']['board_sha256']
        else:
            model = migration['models']['usb-' + mesh.split('.')[1]]
            migrated_hash = model['report_sha256']
            migrated_board = migration['receipts']['io']['archived']['board_sha256']
        if (sha(report_path) != migrated_hash or
            report['board_sha256'] != migrated_board or
            not report['valid_for_diagnostic_sparams'] or
            not report['port_window_audit']['spectral_stability_0p05db'] or
            sha(directory / 'usb-io.xml') != report['xml_sha256'] or
            sha(directory / 'run.log') != report['run_log_sha256']):
            raise ValueError(f'{mesh}: saved field provenance or gate failed')
        hashes = report['port_window_audit']['port_file_sha256']
        if any(sha(directory / f'port_{name}') != hashes[name] for name in PORTS):
            raise ValueError(f'{mesh}: saved port trace differs from report')
        traces = {name: np.loadtxt(directory / f'port_{name}', comments='%') for name in PORTS}
        if min(values[-1, 0] for values in traces.values()) < CUTOFF_SECONDS:
            raise ValueError(f'{mesh}: trace ends before 16 ns')
        rows = []
        for frequency, audit in zip(FREQUENCIES,
                                    report['port_window_audit']['frequency_windows']):
            if int(frequency) != audit['frequency_hz']:
                raise ValueError(f'{mesh}: frequency audit mismatch')
            s11, s21 = sparams(traces, frequency, CUTOFF_SECONDS)
            u1 = spectrum(traces['ut_1'], frequency, CUTOFF_SECONDS)
            i1 = spectrum(traces['it_1'], frequency, CUTOFF_SECONDS)
            if abs(i1) == 0:
                raise ValueError(f'{mesh}: zero input current')
            z = u1 / i1
            s11_db = 20 * math.log10(abs(s11))
            s21_db = 20 * math.log10(abs(s21))
            if (abs(s11_db - audit['window_db']['16.0']['s11']) > .0001 or
                abs(s21_db - audit['window_db']['16.0']['s21']) > .0001):
                raise ValueError(f'{mesh}: complex transform disagrees with saved audit')
            rows.append({'frequency_hz': int(frequency),
                         's11_complex': parts(s11),
                         's21_complex': parts(s21),
                         's11_phase_degrees': float(math.degrees(np.angle(s11))),
                         'loaded_input_ohms': parts(z)})
        rows_by_mesh[mesh] = rows
        source[mesh] = {'report_sha256': sha(report_path),
                        'xml_sha256': report['xml_sha256'],
                        'run_log_sha256': report['run_log_sha256'],
                        'port_file_sha256': hashes,
                        'board_sha256': report['board_sha256']}
    def differences(coarser, finer):
        comparisons = []
        for coarse, fine in zip(rows_by_mesh[coarser], rows_by_mesh[finer]):
            s_fine = complex(*fine['s11_complex'])
            s_coarse = complex(*coarse['s11_complex'])
            z_fine = complex(*fine['loaded_input_ohms'])
            z_coarse = complex(*coarse['loaded_input_ohms'])
            comparisons.append({'frequency_hz': fine['frequency_hz'],
                                'complex_s11_delta_abs': float(abs(s_coarse - s_fine)),
                                'loaded_input_delta_ohms': parts(z_coarse - z_fine)})
        return comparisons
    result = {'scope': '16 ns complex-port and loaded-input diagnostic for ' +
                       ('three' if fine_migration else 'two') + ' USB subset meshes',
            'migration_report_sha256': sha(migration_path),
            'reference_ohms': 90,
            'fourier_cutoff_ns': 16,
            'sources': source,
            'results': rows_by_mesh,
            'mesh_differences_090_minus_075': differences('0.090', '0.075'),
            'characteristic_impedance_convergence_evaluated': False,
            'full_row_4_6_closed': False,
            'limits': ['loaded input impedance includes finite line length and 90-ohm termination; '
                       'it is not trace characteristic impedance',
                       'the 100-ohm lumped launch and omitted pads/connector/ESD/mask/losses remain',
                       'these meshes do not establish port or mesh convergence']}
    if fine_migration:
        result['fine_mesh_migration_report_sha256'] = sha(fine_migration_path)
        result['mesh_differences_075_minus_060'] = differences('0.075', '0.060')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reports', 'fields', 'migration', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('fine-report', 'fine-fields', 'fine-migration'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    result = compare(args.reports.resolve(), args.fields.resolve(), args.migration.resolve(),
                     args.fine_report.resolve() if args.fine_report else None,
                     args.fine_fields.resolve() if args.fine_fields else None,
                     args.fine_migration.resolve() if args.fine_migration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['mesh_differences_090_minus_075'], indent=2))


if __name__ == '__main__':
    main()
