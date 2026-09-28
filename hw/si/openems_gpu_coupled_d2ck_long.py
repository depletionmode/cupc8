#!/usr/bin/env python3
"""Long-window four-port HDMI D2/CK copper coupling diagnostic on one GPU board.

One differential pair is excited per run. Both pairs, the shared dielectric
and ground plane, and all four 100-ohm ports occupy the same FDTD domain.
This still omits pads, mask, connector metal, loss, and source/sink behavior.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

from openems_gpu_d0 import (DIELECTRIC_ER, PAIR_GEOMETRY, PREPREG_MM,
                            add_trace, cleared_axis, cleared_z_lines,
                            routed_pair)
from usb_port_audit import spectrum

PAIRS = ('d2', 'ck')
ROI = (20.7, 30.6, -35.5, -26.2)
PML_CELLS = 8
FREQUENCIES = (.1e9, .48e9, .8e9, 1.26e9)
PORT_NAMES = ('d2_source', 'd2_load', 'ck_source', 'ck_load')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(board, source):
    spec = importlib.util.spec_from_file_location('current_boardevidence',
                                                   source / 'hw/tools/boardevidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate('gpu', board.parent, root=source)
    return sha(board.parent / 'evidence.json')


def port_windows(directory, driven):
    traces = {name: np.loadtxt(directory / f'port_{name}', comments='%')
              for name in ('ut_1', 'it_1', 'ut_2', 'it_2', 'ut_3', 'it_3', 'ut_4', 'it_4')}
    if any(values.ndim != 2 or values.shape[1] != 2 or
           not np.isfinite(values).all() or values[-1, 0] < 24e-9
           for values in traces.values()):
        raise ValueError('four-port traces are malformed or shorter than 24 ns')
    rows = []
    driven_port = 1 if driven == 'd2' else 3
    for frequency in FREQUENCIES:
        windows = {}
        for cutoff in (20.0, 24.0):
            values = {}
            for index, name in enumerate(PORT_NAMES, 1):
                u = spectrum(traces[f'ut_{index}'], frequency, cutoff * 1e-9)
                i = spectrum(traces[f'it_{index}'], frequency, cutoff * 1e-9)
                values[name] = ((u + 100 * i) / 2, (u - 100 * i) / 2)
            incident = values[PORT_NAMES[driven_port - 1]][0]
            if abs(incident) == 0:
                raise ValueError('zero incident spectrum')
            windows[cutoff] = {name: value[1] / incident
                               for name, value in values.items()}
        rows.append({'frequency_hz': int(frequency),
                     'maximum_20_to_24ns_magnitude_drift_db':
                         max(abs(float(20 * np.log10(abs(windows[20.0][name]) /
                                                           abs(windows[24.0][name]))))
                             for name in PORT_NAMES)})
    return rows


def simulate(board, directory, excite_pair, max_steps, threads, geometry_only,
             source_root):
    receipt_sha = receipt(board, source_root)
    routes = {pair: routed_pair(board, pair) for pair in PAIRS}
    directory.mkdir(parents=True, exist_ok=True)
    fdtd = openEMS(EndCriteria=1e-15, NrTS=max_steps)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(['PML_8'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    xmin, xmax, ymin, ymax = ROI
    axes = {'x': cleared_axis(xmin, xmax, clearance=1),
            'y': cleared_axis(ymin, ymax, clearance=1),
            'z': cleared_z_lines()}
    for axis, lines in axes.items():
        grid.AddLine(axis, lines)
    pml = {axis: [lines[PML_CELLS], lines[-PML_CELLS - 1]]
           for axis, lines in axes.items()}
    pml_ok = (pml['x'][0] < xmin < xmax < pml['x'][1] and
              pml['y'][0] < ymin < ymax < pml['y'][1] and
              pml['z'][0] < -PREPREG_MM < 0 < pml['z'][1])
    if not pml_ok:
        raise ValueError('HDMI coupled material overlaps PML')
    substrate = csx.AddMaterial('JLC7628', epsilon=DIELECTRIC_ER)
    substrate.AddBox([xmin, ymin, -PREPREG_MM], [xmax, ymax, 0])
    csx.AddMetal('L2_GND').AddBox([xmin, ymin, -PREPREG_MM],
                                  [xmax, ymax, -PREPREG_MM])
    ports = []
    for pair in PAIRS:
        nets, _, ends = PAIR_GEOMETRY[pair]
        for name, segments in routes[pair].items():
            metal = csx.AddMetal(name.removeprefix('/'))
            add_trace(metal, segments)
            top, bottom = ends[name]
            metal.AddBox([top[0] - .1, top[1], 0],
                         [top[0] + .1, -26.9, 0], priority=10)
            metal.AddBox([bottom[0] - .1, -34.3, 0],
                         [bottom[0] + .1, bottom[1], 0], priority=10)
        top_p, bottom_p = ends[nets[0]]
        top_n, bottom_n = ends[nets[1]]
        index = 1 if pair == 'd2' else 3
        ports.extend([
            fdtd.AddLumpedPort(index, 100,
                               [top_p[0] + .1, -27.10, 0],
                               [top_n[0] - .1, -27.00, 0], 'x',
                               excite=int(pair == excite_pair), priority=20),
            fdtd.AddLumpedPort(index + 1, 100,
                               [bottom_p[0] + .1, -34.20, 0],
                               [bottom_n[0] - .1, -34.10, 0], 'x', priority=20),
        ])
    xml = directory / f'gpu-coupled-{excite_pair}.xml'
    csx.Write2XML(str(xml))
    report = {
        'scope': 'GPU HDMI D2/CK four-port routed-copper coupling diagnostic',
        'board_sha256': sha(board), 'gpu_receipt_sha256': receipt_sha,
        'model_source_sha256': sha(Path(__file__)),
        'excite_pair': excite_pair, 'max_steps': max_steps,
        'solver_threads': threads, 'fixed_window': True,
        'stackup': 'JLC04161H-7628', 'prepreg_mm': PREPREG_MM,
        'dielectric_er': DIELECTRIC_ER, 'material_bounds_mm': ROI,
        'pml_inner_bounds_mm': pml, 'pml_geometry_ok': pml_ok,
        'grid_lines': {axis: len(lines) for axis, lines in axes.items()},
        'port_order': PORT_NAMES, 'port_ohms': 100,
        'xml_sha256': sha(xml),
        'routes': {pair: {name: {'segments': len(parts),
                                 'length_mm_sum': round(sum(math.dist(a, b)
                                                            for a, b, _ in parts), 4)}
                          for name, parts in routes[pair].items()}
                   for pair in PAIRS},
        'geometry_only': geometry_only,
        'full_row_4_6_closed': False,
    }
    if geometry_only:
        return report
    with (directory / 'run.log').open('w') as log:
        stdout, stderr = os.dup(1), os.dup(2)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            fdtd.Run(str(directory), cleanup=True, verbose=0,
                     numThreads=threads, dump_statistics=True)
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(stdout, 1)
            os.dup2(stderr, 2)
            os.close(stdout)
            os.close(stderr)
    runlog = (directory / 'run.log').read_text()
    report['run_log_sha256'] = sha(directory / 'run.log')
    report['solver_version'] = (re.search(r'openEMS 64bit -- version (\S+)', runlog) or [None, None])[1]
    steps = re.search(r'Max\. number of timesteps: (\d+)', runlog)
    threads_log = re.search(r'openEMS - fixed number of threads: (\d+)', runlog)
    if (not steps or int(steps[1]) != max_steps or not threads_log or
        int(threads_log[1]) != threads or
        'Max. number of timesteps was reached' not in runlog):
        raise ValueError('solver did not complete configured fixed window')
    time_step = re.search(r'FDTD timestep is: ([\deE+.-]+) s', runlog)
    report['simulated_ns'] = max_steps * float(time_step[1]) * 1e9 if time_step else None
    levels = [float(x) for x in re.findall(r'Energy: ~[\deE+.-]+ \(-\s*([\d.]+)dB\)', runlog)]
    report['energy_decay_db'] = -levels[-1] if levels else None
    report['converged'] = report['energy_decay_db'] is not None and report['energy_decay_db'] <= -40
    for port in ports:
        port.CalcPort(str(directory), np.array(FREQUENCIES), ref_impedance=100)
    driven = 0 if excite_pair == 'd2' else 2
    incident = ports[driven].uf_inc
    report['results'] = []
    for n, frequency in enumerate(FREQUENCIES):
        waves = {name: complex(port.uf_ref[n] / incident[n])
                 for name, port in zip(PORT_NAMES, ports)}
        passive = {name: float(abs(port.uf_inc[n] / incident[n]))
                   for name, port in zip(PORT_NAMES, ports)
                   if name != PORT_NAMES[driven]}
        report['results'].append({
            'frequency_hz': int(frequency),
            's_reflection_db': {name: float(20 * np.log10(abs(value)))
                                for name, value in waves.items()},
            'power_sum': float(sum(abs(value)**2 for value in waves.values())),
            'passive_port_incident_ratio': passive,
        })
    report['port_window_audit'] = port_windows(directory, excite_pair)
    report['passivity_ok'] = all(row['power_sum'] <= 1.001 for row in report['results'])
    report['port_consistency_ok'] = all(
        max(row['passive_port_incident_ratio'].values()) <= .01
        for row in report['results'])
    report['spectral_stability_ok'] = all(
        row['maximum_20_to_24ns_magnitude_drift_db'] <= .05
        for row in report['port_window_audit'])
    report['valid_for_coupled_subset'] = all(report[key] for key in
        ('converged', 'pml_geometry_ok', 'passivity_ok',
         'port_consistency_ok', 'spectral_stability_ok'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--excite-pair', choices=PAIRS, default='d2')
    parser.add_argument('--max-steps', type=int, default=280000)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--geometry-only', action='store_true')
    args = parser.parse_args()
    if args.max_steps < 30000 or not 1 <= args.threads <= 8:
        parser.error('max-steps must be >=30000 and threads 1..8')
    output = args.out.resolve()
    result = simulate(args.board.resolve(), output.parent /
                      f'gpu-coupled-{args.excite_pair}-long-openems',
                      args.excite_pair, args.max_steps, args.threads,
                      args.geometry_only, args.source_root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not args.geometry_only and not result['valid_for_coupled_subset']:
        raise SystemExit('coupled field subset failed convergence/port/spectral gate')


if __name__ == '__main__':
    main()
