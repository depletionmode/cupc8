#!/usr/bin/env python3
"""Compare receipt-bound fixed-window USB copper-subset field meshes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import boardevidence

FREQUENCIES = (100000000, 240000000, 480000000)
OLD_REPORTS = {'0.075': 'usb-io-pml-fixed.json',
               '0.090': 'usb-io-pml-mesh-090-fixed.json'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(reports, migration_path, current_report_path, current_fields,
            current_build, current_source, fine_migration_path=None):
    migration = json.loads(migration_path.read_text())
    current_receipt = migration['receipts']['io']['current']
    archived_receipt = migration['receipts']['io']['archived']
    boardevidence.validate('io', current_build, root=current_source)
    if sha(current_build / 'evidence.json') != current_receipt['receipt_sha256']:
        raise ValueError('current IO receipt differs from field-input migration')
    sources = {}
    for mesh, name in OLD_REPORTS.items():
        path = reports / name
        record = json.loads(path.read_text())
        migrated = migration['models']['usb-' + mesh.split('.')[1]]
        if (sha(path) != migrated['report_sha256'] or
            record['board_sha256'] != archived_receipt['board_sha256'] or
            record['netlist_sha256'] != archived_receipt['netlist_sha256'] or
            not migrated['saved_subset_gate']):
            raise ValueError(f'{mesh}: archived report is not migration-validated')
        sources[mesh] = (record, path)
    current = json.loads(current_report_path.read_text())
    fine_receipt = current_receipt
    if fine_migration_path:
        fine_migration = json.loads(fine_migration_path.read_text())
        if (not fine_migration['modeled_input_equivalent'] or
            any(fine_migration['rebuilt_receipt'][key] != current_receipt[key]
                for key in ('receipt_sha256', 'board_sha256', 'netlist_sha256')) or
            fine_migration['saved_report_sha256'] != sha(current_report_path)):
            raise ValueError('0.060 mm migration does not bind the current IO receipt')
        fine_receipt = fine_migration['saved_receipt']
    if (current['board_sha256'] != fine_receipt['board_sha256'] or
        current['netlist_sha256'] != fine_receipt['netlist_sha256'] or
        not current['valid_for_diagnostic_sparams']):
        raise ValueError('0.060 mm report is not valid on current IO receipt')
    if (sha(current_fields / 'usb-io.xml') != current['xml_sha256'] or
        sha(current_fields / 'run.log') != current['run_log_sha256'] or
        any(sha(current_fields / f'port_{name}') != expected for name, expected in
            current['port_window_audit']['port_file_sha256'].items())):
        raise ValueError('0.060 mm saved XML, log or port trace differs from report')
    sources['0.060'] = (current, current_report_path)
    for mesh, (record, _) in sources.items():
        if (not record['fixed_window'] or record['pml_clearance_mm'] != 1 or
            not record['pml_geometry_ok'] or not record['converged'] or
            not record['passivity_ok'] or not record['port_consistency_ok'] or
            not record['spectral_stability_ok'] or record['simulated_ns'] < 16 or
            record['declared_port_ohms'] != 100 or record['reference_ohms'] != 90 or
            tuple(row['frequency_hz'] for row in record['results']) != FREQUENCIES):
            raise ValueError(f'{mesh}: mesh or port gate failed')
    baseline = sources['0.075'][0]
    for mesh, (record, _) in sources.items():
        if (record['material_bounds_mm'] != baseline['material_bounds_mm'] or
            record['routes'] != baseline['routes'] or
            record['port_geometry'] != baseline['port_geometry'] or
            record['stackup'] != baseline['stackup']):
            raise ValueError(f'{mesh}: physical model scope differs')
    comparisons = {}
    for coarser, finer in (('0.090', '0.075'), ('0.075', '0.060')):
        rows = []
        for a, b in zip(sources[coarser][0]['results'], sources[finer][0]['results']):
            rows.append({'frequency_hz': a['frequency_hz'],
                         's11_db': {coarser: a['s11_db'], finer: b['s11_db'],
                                    'finer_minus_coarser': b['s11_db'] - a['s11_db']},
                         's21_db': {coarser: a['s21_db'], finer: b['s21_db'],
                                    'finer_minus_coarser': b['s21_db'] - a['s21_db']}})
        comparisons[f'{coarser}_to_{finer}'] = {
            'results': rows,
            'maximum_absolute_s11_change_db': max(abs(row['s11_db']['finer_minus_coarser'])
                                                  for row in rows),
            'maximum_absolute_s21_change_db': max(abs(row['s21_db']['finer_minus_coarser'])
                                                  for row in rows),
        }
    return {
        'scope': 'three-grid IO USB routed-copper subset sensitivity on migration-equivalent receipts',
        'migration_report_sha256': sha(migration_path),
        'fine_mesh_migration_report_sha256': sha(fine_migration_path) if fine_migration_path else None,
        'current_io_receipt_sha256': current_receipt['receipt_sha256'],
        'current_io_board_sha256': current_receipt['board_sha256'],
        'sources': {mesh: {'report_sha256': sha(path), 'board_sha256': record['board_sha256'],
                           'mesh_mm': record['mesh_mm'], 'timesteps': record['timesteps'],
                           'simulated_ns': record['simulated_ns'],
                           'xml_sha256': record['xml_sha256'],
                           'run_log_sha256': record['run_log_sha256'],
                           'energy_decay_db': record['energy_decay_db'],
                           'passivity_ok': record['passivity_ok'],
                           'port_consistency_ok': record['port_consistency_ok'],
                           'spectral_stability_ok': record['spectral_stability_ok']}
                    for mesh, (record, path) in sources.items()},
        'comparisons': comparisons,
        'full_row_4_6_closed': False,
        'limits': ['three meshes alone do not establish asymptotic mesh convergence',
                   'simplified model omits pads, mask, connector, ESD and finite losses',
                   'lumped-port placement and impedance sensitivity remain unmeasured'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reports', 'migration', 'current-report', 'current-fields', 'current-build',
                 'current-source', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--fine-migration', type=Path)
    args = parser.parse_args()
    result = compare(args.reports.resolve(), args.migration.resolve(),
                     args.current_report.resolve(), args.current_fields.resolve(),
                     args.current_build.resolve(), args.current_source.resolve(),
                     args.fine_migration.resolve() if args.fine_migration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: {key: values[key] for key in
                             ('maximum_absolute_s11_change_db', 'maximum_absolute_s21_change_db')}
                      for name, values in result['comparisons'].items()}, indent=2))


if __name__ == '__main__':
    main()
