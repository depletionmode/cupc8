#!/usr/bin/env python3
"""Audit two long-window GPU HDMI D2/CK four-port field excitations and their receipt."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

from compare_field_inputs import digest, xml_node
from usb_port_audit import spectrum

FREQUENCIES = (100000000, 480000000, 800000000, 1260000000)
PORTS = ('d2_source', 'd2_load', 'ck_source', 'ck_load')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_fingerprint(xml):
    tree = ET.parse(xml)
    for parent in tree.iter():
        parent.attrib.pop('ID', None)  # CSXCAD renumbers later properties after excitation.
        for child in list(parent):
            if child.tag == 'Excitation':
                parent.remove(child)
    return digest(xml_node(tree.getroot()))


def audit(board, source, reports, fields, model_source, short_reports, short_fields):
    spec = importlib.util.spec_from_file_location('gpu_receipt_validator',
                                                   source / 'hw/tools/boardevidence.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate('gpu', board.parent, root=source)
    receipt_sha, board_sha = sha(board.parent / 'evidence.json'), sha(board)
    runs, spectra = {}, {}
    for driven in ('d2', 'ck'):
        report_path = reports / f'gpu-coupled-{driven}-long-fixed.json'
        directory = fields / f'gpu-coupled-{driven}-long-openems'
        report = json.loads(report_path.read_text())
        xml = directory / f'gpu-coupled-{driven}.xml'
        log = directory / 'run.log'
        short_report_path = short_reports / f'gpu-coupled-{driven}-fixed.json'
        short_report = json.loads(short_report_path.read_text())
        short_xml = short_fields / f'gpu-coupled-{driven}-openems' / f'gpu-coupled-{driven}.xml'
        if (short_report['board_sha256'] != board_sha or
            short_report['xml_sha256'] != sha(short_xml) or
            short_report['xml_sha256'] != report['xml_sha256'] or
            short_report['routes'] != report['routes'] or
            short_report['material_bounds_mm'] != report['material_bounds_mm'] or
            short_report['port_order'] != report['port_order']):
            raise ValueError(f'{driven}: long run changed saved physical field input')
        if (report['board_sha256'] != board_sha or
            report['gpu_receipt_sha256'] != receipt_sha or
            report['model_source_sha256'] != sha(model_source) or
            report['xml_sha256'] != sha(xml) or
            report['run_log_sha256'] != sha(log) or
            report['excite_pair'] != driven or
            tuple(report['port_order']) != PORTS or
            not report['fixed_window'] or
            report['max_steps'] != 280000 or report['solver_threads'] != 2):
            raise ValueError(f'{driven}: field, source or receipt mismatch')
        runlog = log.read_text()
        if (f"Max. number of timesteps: {report['max_steps']}" not in runlog or
            f"openEMS - fixed number of threads: {report['solver_threads']}" not in runlog or
            'Max. number of timesteps was reached' not in runlog or
            not re.search(r'openEMS 64bit -- version (\S+)', runlog)):
            raise ValueError(f'{driven}: solver runtime mismatch')
        traces, hashes = {}, {}
        for index in range(1, 5):
            for kind in ('ut', 'it'):
                name = f'port_{kind}_{index}'
                path = directory / name
                hashes[name] = sha(path)
                traces[f'{kind}_{index}'] = np.loadtxt(path, comments='%')
        if min(values[-1, 0] for values in traces.values()) < 24e-9:
            raise ValueError(f'{driven}: incomplete Fourier window')
        rows = []
        driven_index = 1 if driven == 'd2' else 3
        for frequency in FREQUENCIES:
            windows = {}
            for cutoff in (16, 20, 24):
                ports = {}
                for index, name in enumerate(PORTS, 1):
                    u = spectrum(traces[f'ut_{index}'], frequency, cutoff * 1e-9)
                    i = spectrum(traces[f'it_{index}'], frequency, cutoff * 1e-9)
                    ports[name] = ((u + 100 * i) / 2, (u - 100 * i) / 2)
                incoming = ports[PORTS[driven_index - 1]][0]
                windows[cutoff] = {name: outgoing / incoming
                                   for name, (_, outgoing) in ports.items()}
            values = windows[24]
            rows.append({'frequency_hz': frequency,
                         's_complex': {name: [float(value.real), float(value.imag)]
                                       for name, value in values.items()},
                         'magnitude_drift_db': {
                             label: {name: float(abs(20 * np.log10(
                                 abs(windows[first][name]) / abs(windows[last][name]))))
                                     for name in PORTS}
                             for label, first, last in (('16_to_20ns', 16, 20),
                                                        ('20_to_24ns', 20, 24))}})
        independent_drift = {
            row['frequency_hz']: max(row['magnitude_drift_db']['20_to_24ns'].values())
            for row in rows}
        reported_drift = {
            row['frequency_hz']: row['maximum_20_to_24ns_magnitude_drift_db']
            for row in report['port_window_audit']}
        if (independent_drift.keys() != reported_drift.keys() or
            any(not np.isclose(independent_drift[frequency], reported_drift[frequency],
                               rtol=0, atol=1e-9)
                for frequency in independent_drift)):
            raise ValueError(f'{driven}: reported spectrum differs from raw port traces')
        passivity = all(row['power_sum'] <= 1.001 for row in report['results'])
        passive_ports = all(max(row['passive_port_incident_ratio'].values()) <= .01
                            for row in report['results'])
        spectral = all(value <= .05 for value in independent_drift.values())
        converged = report['energy_decay_db'] is not None and report['energy_decay_db'] <= -40
        valid = all((converged, report['pml_geometry_ok'], passivity,
                     passive_ports, spectral))
        if (report['passivity_ok'] != passivity or
            report['port_consistency_ok'] != passive_ports or
            report['spectral_stability_ok'] != spectral or
            report['converged'] != converged or
            report['valid_for_coupled_subset'] != valid):
            raise ValueError(f'{driven}: reported numerical gate differs from audited values')
        runs[driven] = {
            'report_sha256': sha(report_path), 'xml_sha256': sha(xml),
            'short_run_report_sha256': sha(short_report_path),
            'short_run_xml_sha256': sha(short_xml),
            'physical_input_identical_to_short_run': True,
            'run_log_sha256': sha(log), 'raw_port_sha256': hashes,
            'passive_geometry_fingerprint': geometry_fingerprint(xml),
            'converged': converged,
            'passivity_ok': passivity,
            'port_consistency_ok': passive_ports,
            'spectral_stability_ok': spectral,
            'valid_for_coupled_subset': valid,
            'maximum_20_to_24ns_drift_db': max(
                value for row in rows
                for value in row['magnitude_drift_db']['20_to_24ns'].values()),
        }
        spectra[driven] = rows
    if runs['d2']['passive_geometry_fingerprint'] != runs['ck']['passive_geometry_fingerprint']:
        raise ValueError('passive four-port geometry differs between runs')
    reciprocity = []
    for d0, d1 in zip(spectra['d2'], spectra['ck']):
        s31 = complex(*d0['s_complex']['ck_source'])
        s13 = complex(*d1['s_complex']['d2_source'])
        reciprocity.append({'frequency_hz': d0['frequency_hz'],
                            's31_abs': float(abs(s31)), 's13_abs': float(abs(s13)),
                            's31_minus_s13_abs': float(abs(s31 - s13))})
    return {'scope': 'GPU HDMI D2/CK long-window four-port copper-subset field audit',
            'gpu_receipt_sha256': receipt_sha, 'board_sha256': board_sha,
            'model_source_sha256': sha(model_source),
            'excitation_runs': runs, 's_parameters_24ns': spectra,
            'reciprocity_s31_vs_s13': reciprocity,
            'both_subset_gates_pass': all(row['valid_for_coupled_subset']
                                          for row in runs.values()),
            'full_row_4_6_closed': False,
            'limits': ['only D2/CK routed copper with four ideal differential ports',
                       'D0/D1 interaction, pads, connector, mask, finite losses and source/sink remain open',
                       'two-source excitation does not determine the full four-port S matrix']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('board', 'source', 'reports', 'fields', 'model-source',
                 'short-reports', 'short-fields', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    result = audit(*(getattr(args, name.replace('-', '_')).resolve() for name in
                     ('board', 'source', 'reports', 'fields', 'model-source',
                      'short-reports', 'short-fields')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('D2/CK coupled subset gates:', result['both_subset_gates_pass'])


if __name__ == '__main__':
    main()
