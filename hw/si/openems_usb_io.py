#!/usr/bin/env python3
"""openEMS diagnostic for IO-card USB D+/D- after R14/R15 to J2.

This models the routed F.Cu copper and L2 plane but omits pad geometry,
ESD-device capacitance, connector metal, solder mask and finite losses.
The wide-separation launch/receive ports require control and mesh checks
before the S-parameters can support the 90-ohm row-4.6 gate.
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
import pcbnew
from CSXCAD import ContinuousStructure
from openEMS import openEMS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cosim'))
from kicadgen import find1, parse
from netlist import read as read_netlist
from openems_gpu_d0 import add_trace, completion_decay

NETS = ('/USB_CONN_DP', '/USB_CONN_DM')
CONTACTS = {'/USB_CONN_DP': (('R15', '2'), ('J2', '3')),
            '/USB_CONN_DM': (('R14', '2'), ('J2', '2'))}
PREPREG_MM = .2104
DIELECTRIC_ER = 4.4
ROI = (34.5, 43.5, -34.5, -18.5)


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


def validate_series(netlist):
    circuit = read_netlist(netlist)
    for signal, connector, chip in (('DM', '2', '46'), ('DP', '3', '47')):
        part = circuit.series(('U1', chip), ('J2', connector))
        if part is None or part.value != '27R':
            raise ValueError(f'USB {signal}: RP2040-to-J2 path lacks 27-ohm series resistor')
    return hashlib.sha256(netlist.read_bytes()).hexdigest()


def simulate(board, directory, mesh_mm=.075, max_steps=120000, straight_control=False,
             port_ohms=100, postprocess_only=False, netlist=None):
    routes, endpoints = routed_pair(board)
    schematic_hash = validate_series(netlist) if netlist else None
    if straight_control:
        routes = {net: [(pair[0], pair[1], .2)] for net, pair in endpoints.items()}
    fdtd = openEMS(EndCriteria=1e-4, NrTS=max_steps)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(['PML_8'] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    grid = csx.GetGrid()
    grid.SetDeltaUnit(1e-3)
    xmin, xmax, ymin, ymax = ROI
    # Put pad and port edges on the grid without making a tiny CFL cell where
    # a regular line nearly coincides with one of those coordinates.
    def axis_lines(lo, hi, axis):
        anchors = sorted({round(point[axis] + delta, 5)
                          for pair in endpoints.values() for point in pair
                          for delta in (-.1, 0, .1)})
        regular = np.arange(lo, hi + mesh_mm / 2, mesh_mm)
        keep = [value for value in regular
                if all(abs(value - anchor) >= mesh_mm * .45 for anchor in anchors)]
        return sorted(set(float(v) for v in keep) | set(anchors))
    grid.AddLine('x', axis_lines(xmin, xmax, 0))
    grid.AddLine('y', axis_lines(ymin, ymax, 1))
    grid.AddLine('z', [-1, -.8, -.6, -.4, -.3, -PREPREG_MM, -.16,
                       -.11, -.06, 0, .05, .1, .2, .35, .55, .8, 1.1, 1.5])
    substrate = csx.AddMaterial('JLC7628', epsilon=DIELECTRIC_ER)
    substrate.AddBox([xmin, ymin, -PREPREG_MM], [xmax, ymax, 0])
    ground = csx.AddMetal('L2_GND')
    ground.AddBox([xmin, ymin, -PREPREG_MM], [xmax, ymax, -PREPREG_MM])
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
                fdtd.Run(str(directory), cleanup=True, verbose=0, numThreads=4,
                         dump_statistics=True)
            finally:
                sys.stdout.flush(); sys.stderr.flush()
                os.dup2(stdout, 1); os.dup2(stderr, 2)
                os.close(stdout); os.close(stderr)
    log = (directory / 'run.log').read_text()
    decay = completion_decay(log)
    energy_samples = re.findall(r'Energy: ~[\deE+.-]+ \(-\s*([\d.]+)dB\)', log)
    measured_decay = -float(energy_samples[-1]) if energy_samples else None
    steps = re.search(r'(?:after|for) (\d+) (?:timesteps|iterations)', log)
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
    valid = decay is not None and passivity_ok and port_ok
    return {'scope': 'IO USB-A D+/D- R14/R15-to-J2 routed F.Cu subset',
            'board_sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
            'netlist_sha256': schematic_hash,
            'stackup': 'JLC04161H-7628', 'prepreg_mm': PREPREG_MM, 'dielectric_er': DIELECTRIC_ER,
            'model': 'lossless dielectric, PEC copper, rectangular L2 GND; pads/ESD/mask/connector absent',
            'mesh_mm': mesh_mm, 'straight_control': straight_control,
            'port_geometry': '2D differential lumped ports at resistor/connector pad centers',
            'declared_port_ohms': port_ohms, 'reference_ohms': 90,
            'energy_decay_db': decay if decay is not None else measured_decay,
            'converged': decay is not None, 'passivity_ok': passivity_ok,
            'port_consistency_ok': port_ok,
            'solver_version': version[1] if version else None,
            'timesteps': int(steps[1]) if steps else None,
            'valid_for_diagnostic_sparams': valid,
            'valid_for_row_4_6': False,
            'routes': {net: {'segments': len(parts),
                             'length_mm_sum': round(sum(math.dist(a, b) for a, b, _ in parts), 4)}
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
    parser.add_argument('--port-ohms', type=float, default=100,
                        help='declared lumped resistance; compare measured passive load to 90 ohms')
    parser.add_argument('--postprocess-only', action='store_true',
                        help='reuse saved fields only when generated geometry is byte-identical')
    parser.add_argument('--straight-control', action='store_true')
    parser.add_argument('--require-evidence', action='store_true')
    args = parser.parse_args()
    if not .035 <= args.mesh_mm <= .1 or args.max_steps < 30000:
        parser.error('mesh must be 0.035–0.1 mm and max steps >= 30000')
    board, output = args.board.resolve(), args.out.resolve()
    netlist = args.netlist.resolve() if args.netlist else board.with_suffix('.net')
    if not netlist.is_file():
        parser.error(f'USB netlist missing: {netlist}')
    if args.require_evidence:
        import boardevidence
        boardevidence.validate('io', board.parent)
    directory = output.parent / ('usb-io-control-openems' if args.straight_control else 'usb-io-openems')
    report = simulate(board, directory, args.mesh_mm, args.max_steps,
                      args.straight_control, args.port_ohms, args.postprocess_only,
                      netlist)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['valid_for_diagnostic_sparams']:
        raise SystemExit('USB openEMS port or convergence validation failed')


if __name__ == '__main__':
    main()
