#!/usr/bin/env python3
"""Diagnose whether three saved USB mesh results show asymptotic behavior.

This uses the receipt-bound magnitude and complex-port comparisons. It does
not estimate a continuum answer from a sequence that fails the leading-order
monotonicity check, and it never marks the physical USB gate complete.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

MESHES = ('0.090', '0.075', '0.060')
QUANTITIES = ('s11_db', 's21_db')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(magnitude_path, complex_path):
    magnitude = json.loads(magnitude_path.read_text())
    complex_port = json.loads(complex_path.read_text())
    if (magnitude['full_row_4_6_closed'] or complex_port['full_row_4_6_closed'] or
        set(magnitude['sources']) != set(MESHES) or
        set(complex_port['sources']) != set(MESHES) or
        magnitude['migration_report_sha256'] != complex_port['migration_report_sha256'] or
        magnitude['fine_mesh_migration_report_sha256'] !=
            complex_port['fine_mesh_migration_report_sha256']):
        raise ValueError('USB mesh evidence scope or migration differs')
    for mesh in MESHES:
        if (magnitude['sources'][mesh]['report_sha256'] !=
                complex_port['sources'][mesh]['report_sha256'] or
            magnitude['sources'][mesh]['xml_sha256'] !=
                complex_port['sources'][mesh]['xml_sha256'] or
            magnitude['sources'][mesh]['run_log_sha256'] !=
                complex_port['sources'][mesh]['run_log_sha256'] or
            magnitude['sources'][mesh]['board_sha256'] !=
                complex_port['sources'][mesh]['board_sha256']):
            raise ValueError(f'{mesh}: magnitude and complex reports refer to different fields')
        if not all(magnitude['sources'][mesh][key] for key in
                   ('passivity_ok', 'port_consistency_ok', 'spectral_stability_ok')):
            raise ValueError(f'{mesh}: numerical/port gate failed')
    frequencies = [row['frequency_hz'] for row in complex_port['results']['0.090']]
    if any([row['frequency_hz'] for row in complex_port['results'][mesh]] != frequencies
           for mesh in MESHES):
        raise ValueError('complex-port frequencies differ')
    rows = []
    comparisons = magnitude['comparisons']
    for index, frequency in enumerate(frequencies):
        coarse = comparisons['0.090_to_0.075']['results'][index]
        fine = comparisons['0.075_to_0.060']['results'][index]
        if coarse['frequency_hz'] != frequency or fine['frequency_hz'] != frequency:
            raise ValueError('magnitude and complex-port frequencies differ')
        metrics = {}
        for quantity in QUANTITIES:
            values = [coarse[quantity]['0.090'], coarse[quantity]['0.075'],
                      fine[quantity]['0.060']]
            if values[1] != fine[quantity]['0.075'] or not all(map(math.isfinite, values)):
                raise ValueError(f'{quantity}: shared 0.075 mm result differs')
            first, second = values[1] - values[0], values[2] - values[1]
            metrics[quantity] = {
                'values_db': dict(zip(MESHES, values)),
                'coarse_to_middle_db': first,
                'middle_to_fine_db': second,
                'increment_sign_reversal': first * second < 0,
                'fine_to_coarse_increment_abs_ratio': abs(second / first) if first else None,
                'observed_span_db': max(values) - min(values),
            }
        s = [complex(*complex_port['results'][mesh][index]['s11_complex'])
             for mesh in MESHES]
        first, second = s[1] - s[0], s[2] - s[1]
        if not all(math.isfinite(part) for value in s for part in (value.real, value.imag)):
            raise ValueError('nonfinite complex reflection')
        for mesh, reflection in zip(MESHES, s):
            if reflection == 0 or abs(20 * math.log10(abs(reflection)) -
                                      metrics['s11_db']['values_db'][mesh]) > .0001:
                raise ValueError(f'{mesh}: complex and magnitude S11 differ')
        turn = math.degrees(math.acos(max(-1.0, min(1.0,
            (first.conjugate() * second).real / (abs(first) * abs(second)))))) if first and second else None
        rows.append({'frequency_hz': frequency, **metrics,
                     'complex_s11_increment_turn_degrees': turn,
                     'complex_s11_fine_to_coarse_increment_abs_ratio':
                         abs(second / first) if first else None})
    return {
        'scope': 'three-grid USB copper-subset asymptotic-behavior diagnostic',
        'magnitude_report_sha256': sha(magnitude_path),
        'complex_port_report_sha256': sha(complex_path),
        'mesh_mm_descending': [float(mesh) for mesh in MESHES],
        'frequencies': rows,
        'all_s11_magnitudes_monotone': not any(
            row['s11_db']['increment_sign_reversal'] for row in rows),
        'single_leading_power_law_rejected_on_sampled_meshes': any(
            row[quantity]['increment_sign_reversal'] for row in rows for quantity in QUANTITIES),
        'continuum_extrapolation_performed': False,
        'characteristic_impedance_convergence_evaluated': False,
        'full_row_4_6_closed': False,
        'interpretation': ('The equal 0.015 mm refinements reverse S11 magnitude direction at '
                           'every sampled frequency. A single nonzero C*h^p leading error term '
                           'would be monotone for real S11 dB, so these three samples cannot '
                           'support a Richardson extrapolation. This does not prove divergence.'),
        'next_evidence': ('Run an independent finer mesh with the same physical model and a '
                          'fixed phase/port definition, then compare complex S parameters and '
                          'launch-control sensitivity; model pads, ESD, connector and losses '
                          'before judging physical impedance.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--magnitude', type=Path, required=True)
    parser.add_argument('--complex-port', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.magnitude, args.complex_port)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'all_s11_magnitudes_monotone': report['all_s11_magnitudes_monotone'],
                      'single_leading_power_law_rejected_on_sampled_meshes':
                          report['single_leading_power_law_rejected_on_sampled_meshes']}, indent=2))


if __name__ == '__main__':
    main()
