#!/usr/bin/env python3
"""openEMS diagnostic for IO-card USB D+/D- after R14/R15 to J2.

This models the routed F.Cu copper and L2 plane but omits pad geometry,
ESD-device capacitance, connector metal, solder mask and finite losses.
The wide-separation launch/receive ports require control and mesh checks
before the S-parameters can support the 90-ohm row-4.6 gate.
"""
import argparse
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
import pcbnew
from CSXCAD import ContinuousStructure
from openEMS import openEMS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cosim'))
from kicadgen import find1, parse
from netlist import read as read_netlist
from openems_gpu_d0 import add_trace, completion_decay
from usb_port_audit import audit as audit_ports

NETS = ('/USB_CONN_DP', '/USB_CONN_DM')
CONTACTS = {'/USB_CONN_DP': (('R15', '2'), ('J2', '3')),
            '/USB_CONN_DM': (('R14', '2'), ('J2', '2'))}
PREPREG_MM = .2104
DIELECTRIC_ER = 4.4
ROI = (34.5, 43.5, -34.5, -18.5)
Z_LINES = [-1, -.8, -.6, -.4, -.3, -PREPREG_MM, -.16,
           -.11, -.06, 0, .05, .1, .2, .35, .55, .8, 1.1, 1.5]
PML_CELLS = 8


def cleared_axis(base_lo, base_hi, mesh_mm, clearance_mm):
    """Keep the original mesh phase while placing PML outside fixed geometry."""
    first = -math.ceil(clearance_mm / mesh_mm)
    last = math.ceil((base_hi - base_lo + clearance_mm) / mesh_mm)
    lines = [round(base_lo + index * mesh_mm, 10)
             for index in range(first, last + 1)]
    if not lines[PML_CELLS] < base_lo or not lines[-PML_CELLS - 1] > base_hi:
        raise ValueError('PML clearance is fewer than eight mesh cells')
    return lines


def cleared_z_lines():
    """Pad the legacy z mesh so neither the L2 plane nor copper enters PML_8."""
    lower = [round(Z_LINES[0] - .2 * index, 10) for index in range(PML_CELLS, 0, -1)]
    upper = [round(Z_LINES[-1] + .2 * index, 10) for index in range(1, PML_CELLS + 1)]
    lines = lower + Z_LINES + upper
    if not lines[PML_CELLS] < -PREPREG_MM or not lines[-PML_CELLS - 1] > 0:
        raise ValueError('z mesh overlaps PML_8')
    return lines


def pads(board):
    result = {}
    pcb = pcbnew.LoadBoard(str(board))
    for net, contacts in CONTACTS.items():
        pair = []
        for ref, number in contacts:
            footprint = pcb.FindFootprintByReference(ref)
            if footprint is None:
                raise ValueError(f'{ref}: missing USB endpoint footprint')
            matches = [p for p in footprint.Pads() if p.GetNumber() == number]
            if len(matches) != 1 or matches[0].GetNetname() != net:
                raise ValueError(f'{ref}.{number}: missing/swapped {net} pad')
            pos = matches[0].GetPosition()
            pair.append((round(pcbnew.ToMM(pos.x), 4), round(pcbnew.ToMM(pos.y), 4)))
        result[net] = pair
    return result


def routed_pair(board):
    tree = parse(board.read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('not a KiCad PCB')
    endpoints = pads(board)
    routes = {net: [] for net in NETS}
    for item in tree[1:]:
        if not isinstance(item, list) or not item or item[0] not in ('segment', 'via', 'arc'):
            continue
        attached = find1(item, 'net')
        if attached is None or attached[1] not in routes:
            continue
        net = attached[1]
        if item[0] != 'segment':
            raise ValueError(f'{net}: {item[0]} needs a multilayer field model')
        if find1(item, 'layer')[1] != 'F.Cu':
            raise ValueError(f'{net}: non-F.Cu segment needs a multilayer field model')
        a, b = (tuple(round(float(x), 4) for x in find1(item, tag)[1:])
                for tag in ('start', 'end'))
        width = float(find1(item, 'width')[1])
        if width <= 0 or a == b:
            raise ValueError(f'{net}: invalid routed segment')
        routes[net].append((a, b, width))
    for net, segments in routes.items():
        if not segments:
            raise ValueError(f'{net}: no routed copper')
        graph = {}
        for a, b, width in segments:
            if not math.isclose(width, .2, abs_tol=1e-5):
                raise ValueError(f'{net}: expected 0.2 mm controlled track, found {width}')
            if not (ROI[0] < a[0] < ROI[1] and ROI[2] < a[1] < ROI[3] and
                    ROI[0] < b[0] < ROI[1] and ROI[2] < b[1] < ROI[3]):
                raise ValueError(f'{net}: route leaves field region')
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        start, stop = endpoints[net]
        seen, pending = set(), [start]
        while pending:
            point = pending.pop()
            if point in seen:
                continue
            seen.add(point)
            pending.extend(graph.get(point, set()) - seen)
        if stop not in seen:
            raise ValueError(f'{net}: R14/R15 to J2 copper is disconnected')
    return routes, endpoints


def signal_path_length(segments, start, stop):
    """Shortest resistor-to-connector track length, excluding ESD branches."""
    graph = {}
    for a, b, _ in segments:
        length = math.dist(a, b)
        graph.setdefault(a, []).append((b, length))
        graph.setdefault(b, []).append((a, length))
    distance, queue = {start: 0.0}, [(0.0, start)]
    while queue:
        length, point = heapq.heappop(queue)
        if point == stop:
            return length
        if length > distance[point]:
            continue
        for other, step in graph.get(point, []):
            proposed = length + step
            if proposed < distance.get(other, math.inf):
                distance[other] = proposed
                heapq.heappush(queue, (proposed, other))
    raise ValueError('USB signal path disconnected')


def validate_series(netlist):
    circuit = read_netlist(netlist)
    for signal, connector, chip in (('DM', '2', '46'), ('DP', '3', '47')):
        part = circuit.series(('U1', chip), ('J2', connector))
        if part is None or part.value != '27R':
            raise ValueError(f'USB {signal}: RP2040-to-J2 path lacks 27-ohm series resistor')
    return hashlib.sha256(netlist.read_bytes()).hexdigest()


def simulate(board, directory, mesh_mm=.075, max_steps=120000, straight_control=False,
             port_ohms=100, postprocess_only=False, netlist=None, boundary_margin_mm=0,
             pml_clearance_mm=0, geometry_only=False, fixed_window=False,
             threads=4):
    routes, endpoints = routed_pair(board)
    schematic_hash = validate_series(netlist) if netlist else None
    if straight_control:
        routes = {net: [(pair[0], pair[1], .2)] for net, pair in endpoints.items()}
    # A normal -40 dB stop can precede the 16 ns port-window audit.  A
    # fixed-window run uses a much lower automatic threshold and judges the
    # sampled final field against the same -40 dB requirement instead.
    fdtd = openEMS(EndCriteria=1e-15 if fixed_window else 1e-4, NrTS=max_steps)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(['PML_8'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    xmin, xmax, ymin, ymax = ROI
    if pml_clearance_mm and boundary_margin_mm:
        raise ValueError('PML clearance and legacy boundary expansion are separate controls')
    if pml_clearance_mm:
        x_regular = cleared_axis(xmin, xmax, mesh_mm, pml_clearance_mm)
        y_regular = cleared_axis(ymin, ymax, mesh_mm, pml_clearance_mm)
        air_bounds = (x_regular[0], x_regular[-1], y_regular[0], y_regular[-1])
        material_bounds = ROI
        z_lines = cleared_z_lines()
    else:
        xmin -= boundary_margin_mm
        xmax += boundary_margin_mm
        ymin -= boundary_margin_mm
        ymax += boundary_margin_mm
        air_bounds = material_bounds = (xmin, xmax, ymin, ymax)
        x_regular = np.arange(xmin, xmax + mesh_mm / 2, mesh_mm)
        y_regular = np.arange(ymin, ymax + mesh_mm / 2, mesh_mm)
        z_lines = Z_LINES
    # Put pad and port edges on the grid without making a tiny CFL cell where
    # a regular line nearly coincides with one of those coordinates.
    def axis_lines(regular, axis):
        anchors = sorted({round(point[axis] + delta, 5)
                          for pair in endpoints.values() for point in pair
                          for delta in (-.1, 0, .1)})
        keep = [value for value in regular
                if all(abs(value - anchor) >= mesh_mm * .45 for anchor in anchors)]
        return sorted(set(float(v) for v in keep) | set(anchors))
    x_lines = axis_lines(x_regular, 0)
    y_lines = axis_lines(y_regular, 1)
    grid.AddLine('x', x_lines)
    grid.AddLine('y', y_lines)
    grid.AddLine('z', z_lines)
    material_xmin, material_xmax, material_ymin, material_ymax = material_bounds
    pml_inner_bounds = ((x_lines[PML_CELLS], x_lines[-PML_CELLS - 1]),
                        (y_lines[PML_CELLS], y_lines[-PML_CELLS - 1]),
                        (z_lines[PML_CELLS], z_lines[-PML_CELLS - 1]))
    pml_geometry_ok = (pml_inner_bounds[0][0] < material_xmin < material_xmax < pml_inner_bounds[0][1] and
                       pml_inner_bounds[1][0] < material_ymin < material_ymax < pml_inner_bounds[1][1] and
                       pml_inner_bounds[2][0] < -PREPREG_MM < 0 < pml_inner_bounds[2][1])
    substrate = csx.AddMaterial('JLC7628', epsilon=DIELECTRIC_ER)
    substrate.AddBox([material_xmin, material_ymin, -PREPREG_MM],
                     [material_xmax, material_ymax, 0])
    ground = csx.AddMetal('L2_GND')
    ground.AddBox([material_xmin, material_ymin, -PREPREG_MM],
                  [material_xmax, material_ymax, -PREPREG_MM])
    for net, segments in routes.items():
        metal = csx.AddMetal(net.lstrip('/'))
        add_trace(metal, segments)
        for x, y in endpoints[net]:
            metal.AddBox([x - .1, y - .1, 0], [x + .1, y + .1, 0], priority=10)
    dp_in, dp_out = endpoints['/USB_CONN_DP']
    dm_in, dm_out = endpoints['/USB_CONN_DM']
    if not (dp_in[0] == dm_in[0] and dp_out[1] == dm_out[1]):
        raise ValueError('USB launch geometry changed; differential ports need recalibration')
    ports = [fdtd.AddLumpedPort(1, port_ohms, [dp_in[0], dp_in[1], 0],
                               [dm_in[0], dm_in[1], 0], 'y', excite=1, priority=20),
             fdtd.AddLumpedPort(2, port_ohms, [dp_out[0], dp_out[1], 0],
                                [dm_out[0], dm_out[1], 0], 'x', priority=20)]
    directory.mkdir(parents=True, exist_ok=True)
    if geometry_only:
        csx.Write2XML(str(directory / 'usb-io.xml'))
        return {'scope': 'IO USB-A field geometry only; no FDTD or S-parameters',
                'board_sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
                'netlist_sha256': schematic_hash, 'mesh_mm': mesh_mm,
                'straight_control': straight_control,
                'fixed_window': fixed_window, 'max_steps': max_steps,
                'solver_threads': threads,
                'boundary_margin_mm': boundary_margin_mm,
                'pml_clearance_mm': pml_clearance_mm,
                'air_bounds_mm': air_bounds, 'material_bounds_mm': material_bounds,
                'pml_inner_bounds_mm': pml_inner_bounds,
                'pml_geometry_ok': pml_geometry_ok,
                'grid_lines': {'x': len(x_lines), 'y': len(y_lines), 'z': len(z_lines)},
                'xml_sha256': hashlib.sha256((directory / 'usb-io.xml').read_bytes()).hexdigest(),
                'valid_for_row_4_6': False}
    if postprocess_only:
        probe = directory / 'usb-io-check.xml'
        csx.Write2XML(str(probe))
        if not (directory / 'usb-io.xml').exists() or probe.read_bytes() != (directory / 'usb-io.xml').read_bytes():
            raise ValueError('saved USB fields do not match generated geometry')
        probe.unlink()
    else:
        csx.Write2XML(str(directory / 'usb-io.xml'))
        with (directory / 'run.log').open('w') as log:
            stdout, stderr = os.dup(1), os.dup(2)
            try:
                sys.stdout.flush(); sys.stderr.flush()
                os.dup2(log.fileno(), 1); os.dup2(log.fileno(), 2)
                fdtd.Run(str(directory), cleanup=True, verbose=0, numThreads=threads,
                         dump_statistics=True)
            finally:
                sys.stdout.flush(); sys.stderr.flush()
                os.dup2(stdout, 1); os.dup2(stderr, 2)
                os.close(stdout); os.close(stderr)
    log = (directory / 'run.log').read_text()
    decay = completion_decay(log)
    energy_samples = re.findall(r'Energy: ~[\deE+.-]+ \(-\s*([\d.]+)dB\)', log)
    measured_decay = -float(energy_samples[-1]) if energy_samples else None
    stats = (directory / 'openEMS_run_stats.txt').read_text().splitlines()
    final_step = int(stats[-1].split()[1])
    configured_cap = re.search(r'Max\. number of timesteps: (\d+)', log)
    if configured_cap is None or int(configured_cap[1]) != max_steps:
        raise ValueError('saved USB run has a different timestep cap')
    configured_threads = re.search(r'openEMS - fixed number of threads: (\d+)', log)
    if configured_threads is None or int(configured_threads[1]) != threads:
        raise ValueError('saved USB run has a different solver thread count')
    cap_reached = 'Max. number of timesteps was reached' in log
    actual_steps = max_steps if cap_reached else final_step
    timestep_match = re.search(r'FDTD timestep is: ([\deE+.-]+) s', log)
    simulated_ns = (actual_steps * float(timestep_match[1]) * 1e9
                    if timestep_match else None)
    version = re.search(r'openEMS 64bit -- version (\S+)', log)
    frequencies = np.array([.1e9, .24e9, .48e9])
    for port in ports:
        port.CalcPort(str(directory), frequencies, ref_impedance=90)
    incident = ports[0].uf_inc
    if np.any(np.abs(incident) == 0):
        raise ValueError('USB source port was not excited')
    s11, s21 = ports[0].uf_ref / incident, ports[1].uf_ref / incident
    power = np.abs(s11)**2 + np.abs(s21)**2
    passive_incident = np.abs(ports[1].uf_inc / incident)
    load_z = -ports[1].uf_tot / ports[1].if_tot
    if not all(np.all(np.isfinite(x)) for x in (s11, s21, power, passive_incident, load_z)):
        raise ValueError('USB solver returned non-finite port values')
    passivity_ok = bool(np.all(power <= 1.001))
    port_ok = bool(np.all(passive_incident <= .01) and
                   np.all(np.abs(load_z - 90) <= .01 * 90))
    try:
        window_audit = audit_ports(directory)
        spectral_stability_ok = window_audit['spectral_stability_0p05db']
    except ValueError as error:
        window_audit = {'unavailable': str(error)}
        spectral_stability_ok = False
    field_ok = (measured_decay is not None and measured_decay <= -40 and
                (fixed_window and cap_reached and final_step >= .99 * max_steps or
                 decay is not None))
    valid = field_ok and passivity_ok and port_ok and spectral_stability_ok and pml_geometry_ok
    return {'scope': 'IO USB-A D+/D- R14/R15-to-J2 routed F.Cu subset',
            'board_sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
            'netlist_sha256': schematic_hash,
            'stackup': 'JLC04161H-7628', 'prepreg_mm': PREPREG_MM, 'dielectric_er': DIELECTRIC_ER,
            'model': 'lossless dielectric, PEC copper, rectangular L2 GND; pads/ESD/mask/connector absent',
            'mesh_mm': mesh_mm, 'straight_control': straight_control,
            'fixed_window': fixed_window, 'max_steps': max_steps,
            'solver_threads': threads,
            'boundary_margin_mm': boundary_margin_mm,
            'pml_clearance_mm': pml_clearance_mm,
            'air_bounds_mm': air_bounds, 'material_bounds_mm': material_bounds,
            'pml_inner_bounds_mm': pml_inner_bounds,
            'pml_geometry_ok': pml_geometry_ok,
            'port_geometry': '2D differential lumped ports at resistor/connector pad centers',
            'declared_port_ohms': port_ohms, 'reference_ohms': 90,
            'energy_decay_db': decay if decay is not None else measured_decay,
            'converged': field_ok, 'passivity_ok': passivity_ok,
            'port_consistency_ok': port_ok,
            'spectral_stability_ok': spectral_stability_ok,
            'port_window_audit': window_audit,
            'solver_version': version[1] if version else None,
            'timesteps': actual_steps, 'last_energy_sample_step': final_step,
            'simulated_ns': simulated_ns,
            'run_log_sha256': hashlib.sha256(log.encode()).hexdigest(),
            'xml_sha256': hashlib.sha256((directory / 'usb-io.xml').read_bytes()).hexdigest(),
            'valid_for_diagnostic_sparams': valid,
            'valid_for_row_4_6': False,
            'routes': {net: {'segments': len(parts),
                             'length_mm_sum': round(sum(math.dist(a, b) for a, b, _ in parts), 4),
                             'signal_path_mm': round(signal_path_length(parts, *endpoints[net]), 4)}
                       for net, parts in routes.items()},
            'results': [{'frequency_hz': int(f), 's11_db': float(20*np.log10(abs(a))),
                         's21_db': float(20*np.log10(abs(b))),
                         'power_sum': float(p), 'passive_incident_ratio': float(i),
                         'passive_load_ohm': [float(z.real), float(z.imag)]}
                        for f, a, b, p, i, z in zip(frequencies, s11, s21, power, passive_incident, load_z)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, required=True)
    parser.add_argument('--netlist', type=Path,
                        help='KiCad exported IO netlist; default is io.net beside the board')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--mesh-mm', type=float, default=.075)
    parser.add_argument('--max-steps', type=int, default=120000)
    parser.add_argument('--threads', type=int, default=4,
                        help='bounded openEMS worker threads')
    parser.add_argument('--boundary-margin-mm', type=float, choices=(0.0, 1.0), default=0.0,
                        help='legacy sensitivity: expand the field, dielectric and ground together')
    parser.add_argument('--pml-clearance-mm', type=float, choices=(0.0, 1.0), default=0.0,
                        help='extend only the air/PML box and z mesh, keeping copper and dielectric fixed')
    parser.add_argument('--port-ohms', type=float, default=100,
                        help='declared lumped resistance; compare measured passive load to 90 ohms')
    parser.add_argument('--postprocess-only', action='store_true',
                        help='reuse saved fields only when generated geometry is byte-identical')
    parser.add_argument('--geometry-only', action='store_true',
                        help='write the XML and mesh/clearance report without running FDTD')
    parser.add_argument('--fixed-window', action='store_true',
                        help='run to max steps for the 12-16 ns spectral audit, then judge final field energy')
    parser.add_argument('--straight-control', action='store_true')
    parser.add_argument('--require-evidence', action='store_true')
    args = parser.parse_args()
    if not .035 <= args.mesh_mm <= .1 or args.max_steps < 30000:
        parser.error('mesh must be 0.035–0.1 mm and max steps >= 30000')
    if not 1 <= args.threads <= 8:
        parser.error('threads must be 1–8')
    if args.pml_clearance_mm and args.boundary_margin_mm:
        parser.error('choose PML clearance or the legacy boundary-margin comparison')
    if args.geometry_only and args.postprocess_only:
        parser.error('geometry-only and postprocess-only cannot be combined')
    board, output = args.board.resolve(), args.out.resolve()
    netlist = args.netlist.resolve() if args.netlist else board.with_suffix('.net')
    if not netlist.is_file():
        parser.error(f'USB netlist missing: {netlist}')
    if args.require_evidence:
        import boardevidence
        boardevidence.validate('io', board.parent)
    run_name = 'usb-io-control-openems' if args.straight_control else 'usb-io-openems'
    if args.boundary_margin_mm:
        run_name += '-margin-1mm'
    if args.pml_clearance_mm:
        run_name += '-pml-clear-1mm'
    if not math.isclose(args.mesh_mm, .075, abs_tol=1e-9):
        run_name += f'-mesh-{args.mesh_mm:.3f}'.replace('.', 'p') + 'mm'
    if args.geometry_only:
        run_name += '-geometry-only'
    if args.fixed_window:
        run_name += '-fixed-window'
    directory = output.parent / run_name
    report = simulate(board, directory, args.mesh_mm, args.max_steps,
                      args.straight_control, args.port_ohms, args.postprocess_only,
                      netlist, args.boundary_margin_mm, args.pml_clearance_mm,
                      args.geometry_only, args.fixed_window, args.threads)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not args.geometry_only and not report['valid_for_diagnostic_sparams']:
        raise SystemExit('USB openEMS port or convergence validation failed')


if __name__ == '__main__':
    main()
