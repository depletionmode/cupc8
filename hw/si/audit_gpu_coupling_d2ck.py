#!/usr/bin/env python3
"""Audit two GPU HDMI D2/CK four-port field excitations and their receipt."""
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


def audit(board, source, reports, fields, model_source):
    spec = importlib.util.spec_from_file_location('gpu_receipt_validator',
                                                   source / 'hw/tools/boardevidence.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate('gpu', board.parent, root=source)
    receipt_sha, board_sha = sha(board.parent / 'evidence.json'), sha(board)
    runs, spectra = {}, {}
    for driven in ('d2', 'ck'):
        report_path = reports / f'gpu-coupled-{driven}-fixed.json'
        directory = fields / f'gpu-coupled-{driven}-openems'
        report = json.loads(report_path.read_text())
        xml = directory / f'gpu-coupled-{driven}.xml'
        log = directory / 'run.log'
        if (report['board_sha256'] != board_sha or
            report['gpu_receipt_sha256'] != receipt_sha or
            report['model_source_sha256'] != sha(model_source) or
            report['xml_sha256'] != sha(xml) or
            report['run_log_sha256'] != sha(log) or
            report['excite_pair'] != driven or
            tuple(report['port_order']) != PORTS or
            not report['fixed_window'] or
            report['max_steps'] != 180000 or report['solver_threads'] != 2):
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
        if min(values[-1, 0] for values in traces.values()) < 12e-9:
            raise ValueError(f'{driven}: incomplete Fourier window')
        rows = []
        driven_index = 1 if driven == 'd2' else 3
        for frequency in FREQUENCIES:
            windows = {}
            for cutoff in (8, 12, 16):
                ports = {}
                for index, name in enumerate(PORTS, 1):
                    u = spectrum(traces[f'ut_{index}'], frequency, cutoff * 1e-9)
                    i = spectrum(traces[f'it_{index}'], frequency, cutoff * 1e-9)
                    ports[name] = ((u + 100 * i) / 2, (u - 100 * i) / 2)
                incoming = ports[PORTS[driven_index - 1]][0]
                windows[cutoff] = {name: outgoing / incoming
                                   for name, (_, outgoing) in ports.items()}
            values = windows[12]
            rows.append({'frequency_hz': frequency,
                         's_complex': {name: [float(value.real), float(value.imag)]
                                       for name, value in values.items()},
                         'magnitude_drift_db': {
                             label: {name: float(abs(20 * np.log10(
                                 abs(windows[first][name]) / abs(windows[last][name]))))
                                     for name in PORTS}
                             for label, first, last in (('8_to_12ns', 8, 12),
                                                        ('12_to_16ns', 12, 16))}})
        runs[driven] = {
            'report_sha256': sha(report_path), 'xml_sha256': sha(xml),
            'run_log_sha256': sha(log), 'raw_port_sha256': hashes,
            'passive_geometry_fingerprint': geometry_fingerprint(xml),
            'converged': report['converged'],
            'passivity_ok': report['passivity_ok'],
            'port_consistency_ok': report['port_consistency_ok'],
            'spectral_stability_ok': report['spectral_stability_ok'],
            'valid_for_coupled_subset': report['valid_for_coupled_subset'],
            'maximum_12_to_16ns_drift_db': max(
                value for row in rows
                for value in row['magnitude_drift_db']['12_to_16ns'].values()),
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
    return {'scope': 'GPU HDMI D2/CK four-port copper-subset field audit',
            'gpu_receipt_sha256': receipt_sha, 'board_sha256': board_sha,
            'model_source_sha256': sha(model_source),
            'excitation_runs': runs, 's_parameters_12ns': spectra,
            'reciprocity_s31_vs_s13': reciprocity,
            'both_subset_gates_pass': all(row['valid_for_coupled_subset']
                                          for row in runs.values()),
            'full_row_4_6_closed': False,
            'limits': ['only D2/CK routed copper with four ideal differential ports',
                       'D0/D1 interaction, pads, connector, mask, finite losses and source/sink remain open',
                       'two-source excitation does not determine the full four-port S matrix']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('board', 'source', 'reports', 'fields', 'model-source', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    result = audit(*(getattr(args, name.replace('-', '_')).resolve() for name in
                     ('board', 'source', 'reports', 'fields', 'model-source')))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('D2/CK coupled subset gates:', result['both_subset_gates_pass'])


if __name__ == '__main__':
    main()
