#!/usr/bin/env python3
"""Audit USB openEMS time traces when global FDTD energy stalls.

This is a diagnostic independent of the solver's -40 dB end criterion. A
quiet port tail alone cannot certify S-parameters: the low-frequency spectra
must also remain stable as the integration window grows.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

PORTS = ('ut_1', 'it_1', 'ut_2', 'it_2')
FREQUENCIES = (100e6, 240e6, 480e6)
WINDOWS_NS = (8.5, 12.0, 14.0, 16.0)
REFERENCE_OHMS = 90.0


def spectrum(samples, frequency, cutoff):
    selected = samples[samples[:, 0] <= cutoff]
    if len(selected) < 3:
        raise ValueError('too few port samples in integration window')
    return np.trapezoid(selected[:, 1] * np.exp(-2j * np.pi * frequency * selected[:, 0]),
                        selected[:, 0])


def sparams(traces, frequency, cutoff):
    u1, i1, u2, i2 = (spectrum(traces[name], frequency, cutoff) for name in PORTS)
    incident = (u1 + REFERENCE_OHMS * i1) / 2
    if abs(incident) == 0:
        raise ValueError('zero incident spectrum')
    return ((u1 - REFERENCE_OHMS * i1) / (2 * incident),
            (u2 - REFERENCE_OHMS * i2) / (2 * incident))


def audit(directory):
    traces = {}
    hashes = {}
    for name in PORTS:
        path = directory / f'port_{name}'
        raw = path.read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        traces[name] = np.loadtxt(path, comments='%')
        if traces[name].ndim != 2 or traces[name].shape[1] != 2 or not np.isfinite(traces[name]).all():
            raise ValueError(f'{name}: invalid port samples')
    if min(trace[-1, 0] for trace in traces.values()) < max(WINDOWS_NS) * 1e-9:
        raise ValueError('saved USB run is shorter than last audit window')
    tails = {}
    for name, values in traces.items():
        peak = np.max(np.abs(values[:, 1]))
        late = values[values[:, 0] >= values[-1, 0] - 1e-9, 1]
        if peak == 0 or len(late) < 3:
            raise ValueError(f'{name}: no usable signal or late window')
        tails[name] = round(float(20 * np.log10(np.max(np.abs(late)) / peak)), 3)
    results = []
    for frequency in FREQUENCIES:
        windows = {str(window): sparams(traces, frequency, window * 1e-9)
                   for window in WINDOWS_NS}
        early, late = windows['12.0'], windows['16.0']
        drift = [abs(20 * math.log10(abs(a) / abs(b))) for a, b in zip(early, late)]
        results.append({'frequency_hz': int(frequency),
                        'window_db': {key: {'s11': round(float(20 * math.log10(abs(pair[0]))), 4),
                                            's21': round(float(20 * math.log10(abs(pair[1]))), 4)}
                                      for key, pair in windows.items()},
                        'magnitude_drift_12_to_16_ns_db': {'s11': round(drift[0], 4),
                                                            's21': round(drift[1], 4)}})
    log = (directory / 'run.log').read_text()
    levels = [float(x) for x in re.findall(r'Energy: ~[\deE+.-]+ \(-\s*([\d.]+)dB\)', log)]
    if not levels:
        raise ValueError('openEMS run log has no field energy samples')
    return {'scope': 'USB numerical-convergence diagnosis, not accepted SI evidence',
            'port_file_sha256': hashes, 'reference_ohms': REFERENCE_OHMS,
            'field_energy_best_db': -max(levels), 'field_energy_final_db': -levels[-1],
            'field_end_criterion_met': 'Max. number of timesteps was reached' not in log and
                                       levels[-1] >= 40,
            'port_tail_last_1ns_max_relative_db': tails,
            'frequency_windows': results,
            'spectral_stability_0p05db': all(
                max(row['magnitude_drift_12_to_16_ns_db'].values()) <= .05 for row in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simdir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.simdir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['field_end_criterion_met'] or not report['spectral_stability_0p05db']:
        raise SystemExit('USB field or spectral convergence remains unverified')


if __name__ == '__main__':
    main()
