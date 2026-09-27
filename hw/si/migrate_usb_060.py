#!/usr/bin/env python3
"""Bind a saved 0.060 mm USB field run to a rebuilt IO receipt."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from compare_field_inputs import (board_physical_fingerprint, generate,
                                  route_fingerprint, sha, xml_fingerprint)


def receipt(source, build):
    spec = importlib.util.spec_from_file_location('receipt_validator_' + hashlib.sha256(
        str(source).encode()).hexdigest()[:12], source / 'hw/tools/boardevidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate('io', build, root=source)
    return {
        'receipt_sha256': sha(build / 'evidence.json'),
        'board_sha256': sha(build / 'io.kicad_pcb'),
        'netlist_sha256': sha(build / 'io.net'),
    }


def compare(old_build, old_source, new_build, new_source, report_path, fields):
    old = receipt(old_source, old_build)
    new = receipt(new_source, new_build)
    report = json.loads(report_path.read_text())
    if (report['board_sha256'] != old['board_sha256'] or
        report['netlist_sha256'] != old['netlist_sha256'] or
        not report['valid_for_diagnostic_sparams'] or
        not all(report[key] for key in ('pml_geometry_ok', 'converged',
                                      'passivity_ok', 'port_consistency_ok',
                                      'spectral_stability_ok'))):
        raise ValueError('saved run does not pass its old receipt and field gates')
    if (sha(fields / 'usb-io.xml') != report['xml_sha256'] or
        sha(fields / 'run.log') != report['run_log_sha256']):
        raise ValueError('saved XML or solver log changed')
    ports = report['port_window_audit']['port_file_sha256']
    if any(sha(fields / f'port_{name}') != expected for name, expected in ports.items()):
        raise ValueError('saved port trace changed')
    old_board = old_build / 'io.kicad_pcb'
    new_board = new_build / 'io.kicad_pcb'
    routes = {label: route_fingerprint(board, 'io') for label, board in
              (('saved', old_board), ('rebuilt', new_board))}
    physical = {label: board_physical_fingerprint(board) for label, board in
                (('saved', old_board), ('rebuilt', new_board))}
    if len(set(routes.values())) != 1 or len(set(physical.values())) != 1:
        raise ValueError('rebuilt IO physical or routed copper geometry changed')
    model_source = 'hw/si/openems_usb_io.py'
    producing_model = Path(__file__).with_name('openems_usb_io.py')
    if sha(producing_model) != sha(new_source / model_source):
        raise ValueError('USB model source changed')
    with TemporaryDirectory(prefix='cupc8-usb060-migration-') as temp:
        temp = Path(temp)
        generated = {
            label: generate(build / 'io.kicad_pcb', build / 'io.net', 'usb-060',
                            report, temp / label)
            for label, build in (('saved', old_build), ('rebuilt', new_build))
        }
        fingerprints = {'field_run': xml_fingerprint(fields / 'usb-io.xml'),
                        **{label: xml_fingerprint(path) for label, path in generated.items()}}
    if len(set(fingerprints.values())) != 1:
        raise ValueError('rebuilt solver input differs from saved field XML')
    return {
        'scope': '0.060 mm USB routed-copper field input migration to rebuilt IO receipt',
        'saved_receipt': old, 'rebuilt_receipt': new,
        'saved_report_sha256': sha(report_path),
        'saved_xml_sha256': report['xml_sha256'],
        'saved_run_log_sha256': report['run_log_sha256'],
        'saved_port_file_sha256': ports,
        'model_source_sha256': sha(new_source / model_source),
        'route_fingerprints': routes,
        'physical_fingerprints': physical,
        'solver_xml_fingerprints': fingerprints,
        'modeled_input_equivalent': True,
        'full_row_4_6_closed': False,
        'limits': ['field run used saved PCB bytes; regenerated rebuilt inputs are equivalent',
                   'model omits pads, mask, connector, ESD, source/sink and finite losses',
                   'three mesh samples alone do not prove asymptotic convergence'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-build', 'old-source', 'new-build', 'new-source',
                 'report', 'fields', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(*(getattr(args, name.replace('-', '_')).resolve() for name in
                       ('old-build', 'old-source', 'new-build', 'new-source',
                        'report', 'fields')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('0.060 mm USB modeled inputs match rebuilt IO receipt')


if __name__ == '__main__':
    main()
