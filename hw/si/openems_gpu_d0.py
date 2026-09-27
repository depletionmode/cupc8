#!/usr/bin/env python3
"""openEMS differential S parameters for a routed HDMI pair on the GPU card.

This covers copper between a source resistor pack and the HDMI connector.
Each pair is solved separately; inter-pair coupling, vias, pads, connector
metal, mask and source/sink IBIS behavior are not included. The script records
the exact routed-board hash and fails closed if the selected pair changes
topology. D0 remains the default for its existing saved-field evidence.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from kicadgen import find1, parse
from usb_port_audit import spectrum

# JLCPCB JLC04161H-7628, 1.6 mm: top-to-L2 prepreg 0.2104 mm, Dk 4.4.
# https://jlcpcb.com/impedance (4-layer, 1.6 mm, 1 oz / 0.5 oz)
PREPREG_MM = .2104
DIELECTRIC_ER = 4.4
NETS = ('/HD_D0P', '/HD_D0N')
# A passive, lossless two-port cannot return more power than is incident.
# Allow 0.1% for floating-point and finite-time postprocessing noise. A
# larger excess makes the extracted S parameters unusable as SI evidence.
PASSIVITY_TOLERANCE = .001
PASSIVE_PORT_INCIDENT_TOLERANCE = .01
ROI = (24.5, 28.5, -35.5, -26.2)
# Pad-side trace endpoints on this board revision (x, y, millimetres).
# The FDTD ports extend the line away from the routed copper at these points.
ENDS = {'/HD_D0P': ((26.3, -27.9), (26.0, -33.74)),
        '/HD_D0N': ((27.1, -27.9), (27.0, -33.74))}
PAIR_GEOMETRY = {
    'd0': (NETS, ROI, ENDS),
    'd1': (('/HD_D1P', '/HD_D1N'), (22.2, 26.8, -35.5, -26.2),
           {'/HD_D1P': ((24.1, -27.9), (24.5, -33.74)),
            '/HD_D1N': ((24.9, -27.9), (25.5, -33.74))}),
    'd2': (('/HD_D2P', '/HD_D2N'), (20.7, 25.3, -35.5, -26.2),
           {'/HD_D2P': ((22.5, -27.9), (23.0, -33.74)),
            '/HD_D2N': ((23.3, -27.9), (24.0, -33.74))}),
    'ck': (('/HD_CKP', '/HD_CKN'), (26.0, 30.6, -35.5, -26.2),
           {'/HD_CKP': ((27.9, -27.9), (27.5, -33.74)),
            '/HD_CKN': ((28.7, -27.9), (28.5, -33.74))}),
}
PML_CELLS = 8
Z_LINES = [-1, -.8, -.6, -.4, -.3, -PREPREG_MM, -.16,
           -.11, -.06, 0, .05, .1, .2, .35, .55, .8, 1.1, 1.5]


def cleared_axis(low, high, spacing=.05, clearance=1.0):
    """Extend the air mesh without shifting the original routed lattice."""
    count = int(round((high - low) / spacing))
    padding = math.ceil(clearance / spacing)
    return [round(low + i * spacing, 10)
            for i in range(-padding, count + padding + 1)]


def cleared_z_lines():
    lower = [round(Z_LINES[0] - .2 * i, 10)
             for i in range(PML_CELLS, 0, -1)]
    upper = [round(Z_LINES[-1] + .2 * i, 10)
             for i in range(1, PML_CELLS + 1)]
    return lower + Z_LINES + upper


def routed_pair(board, pair='d0'):
    nets, roi, ends = PAIR_GEOMETRY[pair]
    if not board.is_file():
        raise ValueError(f'missing routed GPU board: {board}')
    tree = parse(board.read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('not a KiCad PCB')
    routes = {name: [] for name in nets}
    for item in tree[1:]:
        if not isinstance(item, list) or not item or item[0] not in ('segment', 'via', 'arc'):
            continue
        net = find1(item, 'net')
        if net is None or net[1] not in routes:
            continue
        name = net[1]
        if item[0] != 'segment':
            raise ValueError(f'{name} has {item[0]}: this field model handles only F.Cu straight tracks')
        layer = find1(item, 'layer')[1]
        if layer != 'F.Cu':
            raise ValueError(f'{name} has {layer} copper: the model lacks this layer and its vias')
        a = tuple(float(x) for x in find1(item, 'start')[1:])
        b = tuple(float(x) for x in find1(item, 'end')[1:])
        width = float(find1(item, 'width')[1])
        if width <= 0 or a == b:
            raise ValueError(f'{name} has invalid segment')
        routes[name].append((a, b, width))
    for name, segments in routes.items():
        if not segments:
            raise ValueError(f'{name} has no routed copper')
        # KiCad may serialize the same tracks in a different order after an
        # otherwise identical rebuild. Keep field primitives deterministic so
        # the saved-geometry comparison tests geometry, not file order.
        segments.sort(key=lambda item: (item[0], item[1], item[2]))
        xmin, xmax, ymin, ymax = roi
        if any(not (xmin < x < xmax and ymin < y < ymax)
               for a, b, _ in segments for x, y in (a, b)):
            raise ValueError(f'{name} leaves the field model region')
        graph = {}
        for a, b, _ in segments:
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        start, stop = ends[name]
        for anchor in (start, stop):
            widths = {width for a, b, width in segments if anchor in (a, b)}
            if widths != {.2}:
                raise ValueError(f'{name} changed launch width at {anchor}: {widths}')
        seen, pending = set(), [start]
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(graph.get(node, ()) - seen)
        if stop not in seen:
            raise ValueError(f'{name} does not connect its two pad-side anchors')
    return routes


def add_trace(metal, segments):
    for a, b, width in segments:
        a, b = np.array(a), np.array(b)
        direction = b - a
        normal = np.array((-direction[1], direction[0])) / np.linalg.norm(direction) * width / 2
        polygon = np.array((a + normal, b + normal, b - normal, a - normal)).T
        metal.AddPolygon(polygon, 'z', 0, priority=10)


def completion_decay(runlog):
    """Return openEMS's final energy decay only on a completed -40 dB run."""
    match = re.search(r'RunFDTD: end-criteria of -([\d.]+)dB reached after '
                      r'\d+ timesteps \((-?[\d.]+)dB\)', runlog)
    if match and float(match[1]) >= 40 and float(match[2]) <= -40:
        return float(match[2])
    return None


def port_window_audit(directory, frequencies):
    """Check that adding the last four nanoseconds no longer moves S values."""
    traces = {name: np.loadtxt(directory / f'port_{name}', comments='%')
              for name in ('ut_1', 'it_1', 'ut_2', 'it_2')}
    if any(values.ndim != 2 or values.shape[1] != 2 or
           not np.isfinite(values).all() for values in traces.values()):
        raise ValueError('HDMI port traces are malformed')
    if min(values[-1, 0] for values in traces.values()) < 12e-9:
        return {'unavailable': 'saved HDMI run is shorter than 12 ns'}, False
    rows = []
    for frequency in frequencies:
        windows = {}
        for limit_ns in (8.0, 12.0):
            u1, i1, u2, i2 = (spectrum(traces[name], frequency, limit_ns * 1e-9)
                              for name in ('ut_1', 'it_1', 'ut_2', 'it_2'))
            incident = (u1 + 100 * i1) / 2
            if abs(incident) == 0:
                raise ValueError('zero HDMI incident spectrum')
            windows[str(limit_ns)] = ((u1 - 100 * i1) / (2 * incident),
                                      (u2 - 100 * i2) / (2 * incident))
        early, late = windows['8.0'], windows['12.0']
        drift = [abs(float(20 * np.log10(abs(a) / abs(b))))
                 for a, b in zip(early, late)]
        rows.append({'frequency_hz': int(frequency),
                     's11_db_12ns': float(20 * np.log10(abs(late[0]))),
                     's21_db_12ns': float(20 * np.log10(abs(late[1]))),
                     'drift_8_to_12ns_db': {'s11': drift[0], 's21': drift[1]}})
    return {'frequency_windows': rows, 'limit_db': .05}, all(
        max(row['drift_8_to_12ns_db'].values()) <= .05 for row in rows)


def simulate(board, directory, max_steps=120000, postprocess_only=False,
             straight_control=False, pair='d0', pml_clearance_mm=0,
             geometry_only=False, fixed_window=False, threads=4):
    directory = directory.resolve()
    nets, roi, ends = PAIR_GEOMETRY[pair]
    routes = routed_pair(board, pair)
    if straight_control:
        routes = {name: [(ends[name][0], ends[name][1], .2)] for name in nets}
    fdtd = openEMS(EndCriteria=1e-15 if fixed_window else 1e-4, NrTS=max_steps)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(['PML_8'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    xmin, xmax, ymin, ymax = roi
    x_lines = (cleared_axis(xmin, xmax, clearance=pml_clearance_mm)
               if pml_clearance_mm else np.arange(xmin, xmax + .025, .05))
    y_lines = (cleared_axis(ymin, ymax, clearance=pml_clearance_mm)
               if pml_clearance_mm else np.arange(ymin, ymax + .025, .05))
    z_lines = cleared_z_lines() if pml_clearance_mm else Z_LINES
    grid.AddLine('x', x_lines)
    grid.AddLine('y', y_lines)
    grid.AddLine('z', z_lines)
    pml_inner_bounds = ((float(x_lines[PML_CELLS]), float(x_lines[-PML_CELLS - 1])),
                        (float(y_lines[PML_CELLS]), float(y_lines[-PML_CELLS - 1])),
                        (z_lines[PML_CELLS], z_lines[-PML_CELLS - 1]))
    pml_geometry_ok = (pml_inner_bounds[0][0] < xmin < xmax < pml_inner_bounds[0][1] and
                       pml_inner_bounds[1][0] < ymin < ymax < pml_inner_bounds[1][1] and
                       pml_inner_bounds[2][0] < -PREPREG_MM < 0 < pml_inner_bounds[2][1])
    if not pml_geometry_ok and not (geometry_only or postprocess_only):
        raise ValueError('GPU HDMI substrate/ground overlaps PML; use --pml-clearance-mm 1')
    substrate = csx.AddMaterial('JLC7628', epsilon=DIELECTRIC_ER)
    substrate.AddBox([xmin, ymin, -PREPREG_MM], [xmax, ymax, 0])
    ground = csx.AddMetal('L2_GND')
    ground.AddBox([xmin, ymin, -PREPREG_MM], [xmax, ymax, -PREPREG_MM])
    for name, segments in routes.items():
        metal = csx.AddMetal(name.removeprefix('/'))
        add_trace(metal, segments)
        top, bottom = ends[name]
        metal.AddBox([top[0] - .1, top[1], 0], [top[0] + .1, -26.9, 0], priority=10)
        metal.AddBox([bottom[0] - .1, -34.3, 0],
                     [bottom[0] + .1, bottom[1], 0], priority=10)
    # Keep the port on the same z=0 mesh plane as the PEC traces. A volume
    # extending +/-0.05 mm in z gave a measured 145-ohm passive load for a
    # declared 100-ohm resistor on this mesh, invalidating S21 extraction.
    top_p, bottom_p = ends[nets[0]]
    top_n, bottom_n = ends[nets[1]]
    ports = [fdtd.AddLumpedPort(1, 100, [top_p[0] + .1, -27.10, 0], [top_n[0] - .1, -27.00, 0],
                               'x', excite=1, priority=20),
             fdtd.AddLumpedPort(2, 100, [bottom_p[0] + .1, -34.20, 0],
                                [bottom_n[0] - .1, -34.10, 0],
                               'x', priority=20)]
    directory.mkdir(parents=True, exist_ok=True)
    if geometry_only:
        xml = directory / f'gpu-{pair}.xml'
        csx.Write2XML(str(xml))
        return {'scope': f'GPU HDMI {pair.upper()} field geometry only',
                'board_sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
                'pml_clearance_mm': pml_clearance_mm,
                'fixed_window': fixed_window, 'max_steps': max_steps,
                'solver_threads': threads,
                'air_bounds_mm': [float(x_lines[0]), float(x_lines[-1]),
                                  float(y_lines[0]), float(y_lines[-1])],
                'material_bounds_mm': roi, 'pml_inner_bounds_mm': pml_inner_bounds,
                'pml_geometry_ok': pml_geometry_ok,
                'grid_lines': {'x': len(x_lines), 'y': len(y_lines), 'z': len(z_lines)},
                'xml_sha256': hashlib.sha256(xml.read_bytes()).hexdigest(),
                'valid_for_si_evidence': False}
    if postprocess_only:
        generated = directory / f'gpu-{pair}-check.xml'
        csx.Write2XML(str(generated))
        if not (directory / f'gpu-{pair}.xml').is_file() or generated.read_bytes() != (directory / f'gpu-{pair}.xml').read_bytes():
            raise ValueError('saved openEMS fields do not match the generated geometry')
        generated.unlink()
    else:
        csx.Write2XML(str(directory / f'gpu-{pair}.xml'))
        # openEMS prints the actual termination reason from C++; keep it as
        # evidence because Run() does not return a convergence flag.
        with (directory / 'run.log').open('w') as log:
            stdout, stderr = os.dup(1), os.dup(2)
            try:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
                fdtd.Run(str(directory), cleanup=True, verbose=0, numThreads=threads,
                         dump_statistics=True)
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
                os.dup2(stdout, 1)
                os.dup2(stderr, 2)
                os.close(stdout)
                os.close(stderr)
    energies = []
    for line in (directory / 'openEMS_run_stats.txt').read_text().splitlines():
        if line.startswith('%'):
            continue
        energies.append(float(line.split()[3]))
    if len(energies) < 2 or min(energies) <= 0:
        raise ValueError('openEMS did not write usable convergence statistics')
    runlog = (directory / 'run.log').read_text() if (directory / 'run.log').exists() else ''
    # The statistics file is sampled and can miss the true peak as well as the
    # final timestep. The solver's explicit completion line is authoritative.
    final_decay = completion_decay(runlog)
    levels = [float(x) for x in re.findall(r'Energy: ~[\deE+.-]+ \(-\s*([\d.]+)dB\)', runlog)]
    final_step = int((directory / 'openEMS_run_stats.txt').read_text().splitlines()[-1].split()[1])
    configured_cap = re.search(r'Max\. number of timesteps: (\d+)', runlog)
    if configured_cap is None or int(configured_cap[1]) != max_steps:
        raise ValueError('saved HDMI run has a different timestep cap')
    configured_threads = re.search(r'openEMS - fixed number of threads: (\d+)', runlog)
    if configured_threads is None or int(configured_threads[1]) != threads:
        raise ValueError('saved HDMI run has a different solver thread count')
    cap_reached = 'Max. number of timesteps was reached' in runlog
    actual_steps = max_steps if cap_reached else final_step
    sampled_decay = -levels[-1] if levels else None
    converged = (final_decay is not None or
                 fixed_window and cap_reached and final_step >= .99 * max_steps and
                 sampled_decay is not None and sampled_decay <= -40)
    version = re.search(r'openEMS 64bit -- version (\S+)', runlog)
    timestep_match = re.search(r'FDTD timestep is: ([\deE+.-]+) s', runlog)
    simulated_ns = (actual_steps * float(timestep_match[1]) * 1e9
                    if timestep_match else None)
    frequencies = np.array([.1e9, .48e9, .8e9, 1.26e9])
    for port in ports:
        port.CalcPort(str(directory), frequencies, ref_impedance=100)
    incident = ports[0].uf_inc
    if np.any(np.abs(incident) == 0):
        raise ValueError('openEMS port was not excited')
    s11 = ports[0].uf_ref / incident
    s21 = ports[1].uf_ref / incident
    if not np.all(np.isfinite(s11)) or not np.all(np.isfinite(s21)):
        raise ValueError('openEMS returned non-finite S parameters')
    power_sum = np.abs(s11)**2 + np.abs(s21)**2
    excess = np.maximum(power_sum - 1, 0)
    passivity_ok = bool(np.all(excess <= PASSIVITY_TOLERANCE))
    # The passive port is terminated in its own 100-ohm reference impedance,
    # so its incident wave should vanish. A substantial incident component
    # makes uf_ref/uf_inc a loaded response, not a valid S21 measurement.
    port2_incident_ratio = np.abs(ports[1].uf_inc / incident)
    if not np.all(np.isfinite(port2_incident_ratio)):
        raise ValueError('openEMS returned non-finite passive-port incident wave')
    port_consistency_ok = bool(np.all(port2_incident_ratio <= PASSIVE_PORT_INCIDENT_TOLERANCE))
    if np.any(np.abs(ports[1].if_tot) == 0):
        raise ValueError('openEMS passive-port current is zero')
    passive_load_z = -ports[1].uf_tot / ports[1].if_tot
    if not np.all(np.isfinite(passive_load_z)):
        raise ValueError('openEMS returned non-finite passive-port load impedance')
    spectral_audit, spectral_stability_ok = port_window_audit(directory, frequencies)
    report = {
        'scope': (f'straight-line port control for GPU HDMI {pair.upper()} P/N' if straight_control else
                  f'GPU HDMI {pair.upper()} P/N, source resistor output to connector; partial 4.6 evidence'),
        'board_sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
        'stackup': 'JLC04161H-7628', 'prepreg_mm': PREPREG_MM, 'dielectric_er': DIELECTRIC_ER,
        'model': 'lossless dielectric, PEC copper, rectangular L2 GND, no pads/mask/connector',
        'port_geometry': '100-ohm differential lumped ports in the z=0 copper plane',
        'straight_control': straight_control,
        'fixed_window': fixed_window, 'max_steps': max_steps,
        'solver_threads': threads,
        'pml_clearance_mm': pml_clearance_mm,
        'air_bounds_mm': [float(x_lines[0]), float(x_lines[-1]),
                          float(y_lines[0]), float(y_lines[-1])],
        'material_bounds_mm': roi,
        'pml_inner_bounds_mm': pml_inner_bounds,
        'pml_geometry_ok': pml_geometry_ok,
        'energy_decay_db': final_decay if final_decay is not None else sampled_decay,
        'converged': converged,
        'spectral_stability_ok': spectral_stability_ok,
        'port_window_audit': spectral_audit,
        'passivity_ok': passivity_ok,
        'passivity_tolerance': PASSIVITY_TOLERANCE,
        'maximum_passivity_excess': float(max(excess)),
        'port_consistency_ok': port_consistency_ok,
        'valid_for_si_evidence': converged and passivity_ok and port_consistency_ok and
                                 pml_geometry_ok and spectral_stability_ok,
        'passive_port_incident_tolerance': PASSIVE_PORT_INCIDENT_TOLERANCE,
        'solver_version': version[1] if version else None,
        'timesteps': actual_steps, 'last_energy_sample_step': final_step,
        'simulated_ns': simulated_ns,
        'run_log_sha256': hashlib.sha256(runlog.encode()).hexdigest(),
        'xml_sha256': hashlib.sha256((directory / f'gpu-{pair}.xml').read_bytes()).hexdigest(),
        'routes': {name: {'segments': len(parts),
                          'length_mm_sum': round(sum(math.dist(a, b) for a, b, _ in parts), 4),
                          'widths_mm': sorted({width for _, _, width in parts})}
                   for name, parts in routes.items()},
        'results': [{'frequency_hz': int(f),
                     's11_db': float(20 * np.log10(abs(a))),
                     's21_db': float(20 * np.log10(abs(b))),
                     's11_s21_power_sum': float(power),
                     'passive_port_incident_ratio': float(port2_inc),
                     'passive_port_load_ohm': [float(z.real), float(z.imag)]}
                    for f, a, b, power, port2_inc, z in
                    zip(frequencies, s11, s21, power_sum, port2_incident_ratio,
                        passive_load_z)],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-steps', type=int, default=120000)
    parser.add_argument('--threads', type=int, default=4,
                        help='bounded openEMS worker threads')
    parser.add_argument('--postprocess-only', action='store_true', help='re-evaluate saved fields for the same generated geometry')
    parser.add_argument('--geometry-only', action='store_true', help='write and audit geometry without FDTD')
    parser.add_argument('--fixed-window', action='store_true',
                        help='run to max steps so 8-12 ns spectral stability can be audited')
    parser.add_argument('--pml-clearance-mm', type=float, choices=(0.0, 1.0), default=0.0,
                        help='extend only the air/PML box while keeping traces and substrate fixed')
    parser.add_argument('--require-evidence', action='store_true', help='require a complete, current GPU board pipeline receipt')
    parser.add_argument('--straight-control', action='store_true', help='replace bends and width changes with straight 0.2 mm traces')
    parser.add_argument('--pair', choices=tuple(PAIR_GEOMETRY), default='d0',
                        help='HDMI pair to solve independently; D0 preserves prior saved fields')
    args = parser.parse_args()
    if args.max_steps < 30000:
        parser.error('--max-steps must be at least 30000')
    if not 1 <= args.threads <= 8:
        parser.error('threads must be 1–8')
    if args.postprocess_only and args.geometry_only:
        parser.error('postprocess-only and geometry-only cannot be combined')
    board = args.board.resolve()
    output = args.out.resolve()
    if args.require_evidence:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        import boardevidence
        boardevidence.validate('gpu', board.parent)
    directory = f'gpu-{args.pair}-straight-openems' if args.straight_control else f'gpu-{args.pair}-openems'
    if args.pml_clearance_mm:
        directory += '-pml-clear-1mm'
    if args.geometry_only:
        directory += '-geometry-only'
    if args.fixed_window:
        directory += '-fixed-window'
    report = simulate(board, output.parent / directory, args.max_steps,
                      args.postprocess_only, args.straight_control, args.pair,
                      args.pml_clearance_mm, args.geometry_only, args.fixed_window,
                      args.threads)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if args.geometry_only:
        return
    if not report['pml_geometry_ok']:
        raise SystemExit('GPU HDMI substrate/ground overlaps PML; use --pml-clearance-mm 1')
    if not report['converged']:
        raise SystemExit('openEMS did not reach -40 dB energy convergence')
    if not report['passivity_ok']:
        raise SystemExit('openEMS S parameters violate passive two-port power balance; '
                         'port or mesh calibration is required')
    if not report['port_consistency_ok']:
        raise SystemExit('openEMS passive port does not match its reference impedance; '
                         'S21 is not a valid two-port measurement')
    if not report['spectral_stability_ok']:
        raise SystemExit('openEMS HDMI spectrum is not stable across 8-12 ns windows')


if __name__ == '__main__':
    main()
