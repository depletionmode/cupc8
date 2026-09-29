#!/usr/bin/env python3
"""IBIS-derived ngspice transient subset for slot SCK and CPU socket.

The Lattice file is vendor data, fetched separately. Its 50-ohm/25-pF
waveform fixture is de-embedded to a linear Thevenin source and checked by
re-simulating that fixture. This is an approximation, not a full nonlinear
IBIS buffer conversion. Without routed main-board copper and a resolved
TQ144 package assignment the result is deliberately diagnostic only.
"""
import argparse
import hashlib
import heapq
import json
import math
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_ice40_ibis import verify
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import find1, parse

IBIS = ROOT / 'build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs'
MODELS = ('lvc330io', 'lvc330_b3io')
CORNER = {'typ': 0, 'min': 1, 'max': 2}
VDD = {'typ': 3.30, 'min': 3.14, 'max': 3.47}
VIH, VIL = 2.0, 0.8  # vendor [Model] VinH/VinL
FIXTURE_R, FIXTURE_C = 50.0, 25e-12
TRACE_Z0, TRACE_PS_PER_MM = 50.0, 7.0
COPPER = ('F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'B.Cu')
LEGACY_PACKAGE = ((7.98, 1.55, 0.0), (10.53, 1.55, 0.0))  # L nH, C pF, R ohm
VENDOR_TQ144_TYPICAL = ((7.98, 1.216, .764), (10.53, 1.207, .673))


@lru_cache(maxsize=16)
def routed_geometry(path):
    """Reuse parsed copper and pad geometry during repeated route audits."""
    return pcbnew.LoadBoard(path), parse(Path(path).read_text())


def routed_distances(board_path, net, source, receivers, *, loaded_board=None, parsed_tree=None,
                     pad_reach=False):
    """Measure layer-aware shortest copper paths; report disconnected pads.

    This measures planar track length only. It does not turn branches, vias, pad stubs or
    changing reference planes into an electrical transmission-line model.

    A track is on a pad when it ends at the pad's centre. With `pad_reach` it
    is also on the pad when its end lies within the pad's copper (KiCad's own
    connectivity: a router ends a track on the edge of a long edge finger);
    the extra pad-to-endpoint distance is counted. Off by default: the pinned
    receipts were measured without it.
    """
    if loaded_board is None or parsed_tree is None:
        cached_board, cached_tree = routed_geometry(str(Path(board_path).resolve()))
    board = loaded_board if loaded_board is not None else cached_board
    tree = parsed_tree if parsed_tree is not None else cached_tree
    graph = {}

    def add_edge(a, b, length):
        graph.setdefault(a, []).append((b, length))
        graph.setdefault(b, []).append((a, length))

    for item in tree[1:]:
        if not isinstance(item, list) or not item or item[0] not in ('segment', 'via', 'arc'):
            continue
        attached = find1(item, 'net')
        if attached is None or attached[1] != net:
            continue
        if item[0] == 'arc':
            raise ValueError(f'{net}: arc needs an explicit centerline-length parser')
        if item[0] == 'segment':
            a, b = (tuple(round(float(x), 4) for x in find1(item, tag)[1:])
                    for tag in ('start', 'end'))
            layer = find1(item, 'layer')[1]
            add_edge((a, layer), (b, layer), math.dist(a, b))
        else:
            pos = tuple(round(float(x), 4) for x in find1(item, 'at')[1:])
            via_layers = find1(item, 'layers')[1:]
            if via_layers == ['F.Cu', 'B.Cu']:
                via_layers = COPPER
            for a, b in zip(via_layers, via_layers[1:]):
                add_edge((pos, a), (pos, b), 0.0)

    def pad_nodes(contact):
        ref, number = contact
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            raise ValueError(f'{ref}: missing from routed board')
        pads = [p for p in footprint.Pads() if p.GetNumber() == number]
        if len(pads) != 1 or pads[0].GetNetname() != net:
            raise ValueError(f'{ref}.{number}: missing or wrong {net} pad')
        pad = pads[0]
        pos = pad.GetPosition()
        xy = (round(pcbnew.ToMM(pos.x), 4), round(pcbnew.ToMM(pos.y), 4))
        return [(xy, layer) for layer in COPPER
                if pad.IsOnLayer(getattr(pcbnew, layer.replace('.', '_')))]

    # Plated through-hole connector pads can bridge signal tracks on different
    # copper layers. A path to J11, for example, may pass through J12's barrel.
    # Connecting only the source and queried receiver pads falsely reports it
    # open despite KiCad DRC finding continuous copper.
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != net:
                continue
            pos = pad.GetPosition()
            xy = (round(pcbnew.ToMM(pos.x), 4), round(pcbnew.ToMM(pos.y), 4))
            nodes = [(xy, layer) for layer in COPPER
                     if pad.IsOnLayer(getattr(pcbnew, layer.replace('.', '_')))]
            for a, b in zip(nodes, nodes[1:]):
                add_edge(a, b, 0.0)
            if pad_reach:
                for (point, layer) in list(graph):
                    if point != xy and (xy, layer) in nodes and math.dist(point, xy) < 10.0 and pad.HitTest(
                            pcbnew.VECTOR2I(pcbnew.FromMM(point[0]), pcbnew.FromMM(point[1])),
                            pcbnew.FromMM(0.15)):
                        add_edge((xy, layer), (point, layer), math.dist(point, xy))

    distances, pending = {}, []
    for node in pad_nodes(source):
        distances[node] = 0.0
        heapq.heappush(pending, (0.0, node))
    while pending:
        distance, node = heapq.heappop(pending)
        if distance > distances[node]:
            continue
        for neighbor, length in graph.get(node, []):
            new = distance + length
            if new < distances.get(neighbor, math.inf):
                distances[neighbor] = new
                heapq.heappush(pending, (new, neighbor))
    result = {}
    for ref, number in receivers:
        length = min((distances.get(node, math.inf)
                      for node in pad_nodes((ref, number))), default=math.inf)
        result[f'{ref}.{number}'] = round(length, 3) if math.isfinite(length) else None
    return result


def number(token):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)([munp]?)(?:[A-Za-z]*)', token)
    if not match:
        raise ValueError(f'invalid IBIS number: {token}')
    return float(match[1]) * {'': 1, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12}[match[2]]


def model_sections(data, name):
    text = data.decode('ascii').replace('\r', '')
    start = re.search(r'^\[Model\]\s+' + re.escape(name) + r'\s*$', text, re.M)
    if start is None:
        raise ValueError(f'vendor model {name} missing')
    body = text[start.end():]
    end = re.search(r'^\[Model\]', body, re.M)
    if end:
        body = body[:end.start()]
    sections, key = {}, None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith('|') or not line:
            continue
        section = re.match(r'^\[([^]]+)\]\s*$', line)
        if section:
            key = section[1]
            sections[key] = []
        elif key:
            sections[key].append(line)
    return sections


def table(sections, section, corner):
    rows = []
    for line in sections[section]:
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            rows.append((number(fields[0]), number(fields[1 + CORNER[corner]])))
        except ValueError:
            continue  # fixture metadata, not tabular data
    if len(rows) < 20 or any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError(f'{section}/{corner}: insufficient or unordered IBIS points')
    return np.array(rows)


def source(sections, edge, corner):
    curve = table(sections, 'Rising Waveform' if edge == 'rise' else 'Falling Waveform', corner)
    t, v = curve[:, 0], curve[:, 1]
    supply = VDD[corner]
    final = v[-1]
    resistance = ((supply - final) * FIXTURE_R / final if edge == 'rise' else
                  final * FIXTURE_R / (supply - final))
    if not 5 < resistance < 80:
        raise ValueError(f'{edge}/{corner}: implausible IBIS fixture output resistance {resistance}')
    static = table(sections, 'Pullup' if edge == 'rise' else 'Pulldown', corner)
    x = supply - final if edge == 'rise' else final
    stated_current = -np.interp(x, static[:, 0], static[:, 1]) if edge == 'rise' else np.interp(x, static[:, 0], static[:, 1])
    fixture_current = final / FIXTURE_R if edge == 'rise' else (supply - final) / FIXTURE_R
    if abs(stated_current - fixture_current) > .2 * fixture_current:
        raise ValueError(f'{edge}/{corner}: waveform endpoint disagrees with vendor I/V table')
    dv = np.gradient(v, t)
    load_current = FIXTURE_C * dv + (v / FIXTURE_R if edge == 'rise' else (v - supply) / FIXTURE_R)
    drive = v + resistance * load_current
    # The first few waveform samples contain small vendor extraction offsets.
    drive[0] = 0 if edge == 'rise' else supply
    return t, v, drive, resistance


def run_spice(source_t, drive, resistance, fixture=False, slots=6, length_mm=120,
              package_nh=10.53, package_pf=1.55, receiver_pf=15.0,
              fixture_vref=0.0, package_ohm=0.0):
    with tempfile.TemporaryDirectory(prefix='cupc8-ibis-') as temporary:
        work = Path(temporary)
        deck = work / 'bus.cir'
        result = work / 'wave.dat'
        pwl = ' '.join(f'{t:.12g} {v:.9g}' for t, v in zip(source_t, drive))
        lines = ['IBIS-derived CUPC8 diagnostic', f'Vdrive src 0 PWL({pwl})',
                 f'Rout src drv {resistance:.9g}']
        nodes = []
        if fixture:
            lines += [f'Vref rail 0 {fixture_vref:.9g}', 'Rfixture drv rail 50', 'Cfixture drv 0 25p']
            nodes = ['drv']
        else:
            if package_ohm:
                lines += ['Rterm drv term 33', f'Rpkg term pkg {package_ohm:.9g}']
            else:
                lines += ['Rterm drv pkg 33']
            lines += [f'Lpkg pkg launch {package_nh:.9g}n',
                      f'Cpkg launch 0 {package_pf:.9g}p']
            previous = 'launch'
            step = length_mm / slots
            for i in range(slots):
                node = f'bus{i+1}'
                lines.append(f'T{i+1} {previous} 0 {node} 0 Z0={TRACE_Z0} TD={step * TRACE_PS_PER_MM:.9g}p')
                lines.append(f'Cload{i+1} {node} 0 {receiver_pf:.9g}p')
                nodes.append(node)
                previous = node
        lines += ['.control', 'set noaskquit', 'tran 0.05n 45n',
                  f'wrdata {result} ' + ' '.join(f'v({n})' for n in nodes),
                  'quit', '.endc', '.end']
        deck.write_text('\n'.join(lines) + '\n')
        run = subprocess.run(['ngspice', '-b', str(deck)], cwd=work, capture_output=True, text=True)
        if run.returncode or not result.is_file():
            raise RuntimeError(f'ngspice transient failed: {run.stdout[-1200:]} {run.stderr[-1200:]}')
        data = np.loadtxt(result)
        if data.ndim != 2 or data.shape[1] != 2 * len(nodes) or not np.all(np.isfinite(data)):
            raise RuntimeError('ngspice produced incomplete transient data')
        return data[:, 0], data[:, 1::2]


def evaluate(t, outputs, edge, supply):
    settle = 30e-9
    samples = []
    for index, wave in enumerate(outputs.T):
        late = wave[t >= settle]
        if not len(late):
            raise ValueError('transient ended before settling')
        crossed = np.flatnonzero(wave >= VIH if edge == 'rise' else wave <= VIL)
        first = int(crossed[0]) if len(crossed) else len(wave)
        after = wave[first:]
        stable = bool(len(after) and (np.all(after >= VIH) if edge == 'rise' else np.all(after <= VIL)))
        samples.append({'node': index + 1, 'min_v': round(float(np.min(wave)), 4),
                        'max_v': round(float(np.max(wave)), 4),
                        'first_threshold_ns': round(float(t[first] * 1e9), 4) if len(after) else None,
                        'post_cross_min_v': round(float(np.min(after)), 4) if len(after) else None,
                        'post_cross_max_v': round(float(np.max(after)), 4) if len(after) else None,
                        'late_min_v': round(float(np.min(late)), 4),
                        'late_max_v': round(float(np.max(late)), 4),
                        'threshold_stable': stable})
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, default=IBIS)
    parser.add_argument('--top', type=Path, help='schematic-derived co-simulation manifest to validate 33-ohm sources')
    parser.add_argument('--main-board', type=Path,
                        help='optional routed main PCB for layer-aware copper path audit')
    parser.add_argument('--vendor-package-typical', action='store_true',
                        help='sweep both commented TQ144 typical R/L/C rows instead of legacy 1.55 pF/zero-R assumption')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/hw/si/ibis-bus-diagnostic.json')
    args = parser.parse_args()
    data = args.ibis.read_bytes()
    digest = verify(data)
    report = {'source_sha256': digest, 'models': MODELS, 'scope': 'diagnostic IBIS-derived linear source, assumed copper',
              'routed_evidence': False, 'package_assignment_confirmed': False,
              'vendor_package_typical_sweep': args.vendor_package_typical,
              'cases': []}
    if args.main_board:
        board = args.main_board.resolve()
        slot = routed_distances(board, '/SPI_SCK', ('R36', '2'),
                                [(f'J{number}', 'B13') for number in range(11, 17)])
        cpu = routed_distances(board, '/CPU_CLK', ('R18', '2'), [('J2', 'B13')])
        report['main_board_sha256'] = hashlib.sha256(board.read_bytes()).hexdigest()
        report['measured_copper_paths_mm'] = {'slot_sck': slot, 'cpu_clk': cpu}
        report['measured_copper_paths_complete'] = all(
            length is not None for group in (slot, cpu) for length in group.values())
    if args.top:
        top_bytes = args.top.read_bytes()
        top = json.loads(top_bytes)
        paths = top.get('paths', [])
        for slot in range(1, 7):
            target = f'main.J{10+slot}.B13'
            matches = [p for p in paths if p.get('to') == target and
                       p.get('from', '').startswith('main.U7.') and p.get('ohms') == 33]
            if len(matches) != 1:
                raise ValueError(f'{target}: netlist top lacks unique 33-ohm SCK source path')
        cpu = [p for p in paths if p.get('from', '').startswith('cpu.U1.') and
               p.get('to', '').startswith('cpu.J1.') and p.get('ohms') == 68]
        if len(cpu) != 31:
            raise ValueError(f'CPU card: expected 31 series-terminated driver paths, got {len(cpu)}')
        report['top_sha256'] = hashlib.sha256(top_bytes).hexdigest()
        report['top_routed_signals'] = bool(top.get('runtime', {}).get('routed_top'))
    for model in MODELS:
        sections = model_sections(data, model)
        for corner in CORNER:
            for edge in ('rise', 'fall'):
                t, fixture_v, drive, resistance = source(sections, edge, corner)
                ft, fo = run_spice(t, drive, resistance, fixture=True,
                                   fixture_vref=VDD[corner] if edge == 'fall' else 0)
                fit = np.interp(t, ft, fo[:, 0])
                fixture_error = float(np.max(np.abs(fit - fixture_v)))
                if fixture_error > .08:
                    raise ValueError(f'{model}/{corner}/{edge}: IBIS fixture replay differs by {fixture_error:.3f} V')
                for topology, slots, length, loads in (('cpu_socket', 1, 120, (5.0, 15.0)),
                                                       ('six_slot_sck', 6, 180, (15.0, 30.0))):
                    packages = VENDOR_TQ144_TYPICAL if args.vendor_package_typical else LEGACY_PACKAGE
                    for package_nh, package_pf, package_ohm in packages:
                        for receiver_pf in loads:
                            bt, bo = run_spice(t, drive, resistance, slots=slots, length_mm=length,
                                               package_nh=package_nh, package_pf=package_pf,
                                               package_ohm=package_ohm, receiver_pf=receiver_pf)
                            report['cases'].append({'model': model, 'topology': topology,
                                                    'corner': corner, 'edge': edge,
                                                    'assumed_length_mm': length,
                                                    'assumed_receiver_pf': receiver_pf,
                                                    'commented_tq144_l_nh': package_nh,
                                                    'package_c_pf': package_pf,
                                                    'package_r_ohm': package_ohm,
                                                    'output_resistance_ohm': round(resistance, 3),
                                                    'fixture_max_error_v': round(fixture_error, 5),
                                                    'receivers': evaluate(bt, bo, edge, VDD[corner])})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    failures = [case for case in report['cases'] if not all(n['threshold_stable'] for n in case['receivers'])]
    print(f'{len(report["cases"])} ngspice bus transients, {len(failures)} threshold-instability cases; '
          f'IBIS fixture error <= {max(c["fixture_max_error_v"] for c in report["cases"]):.4f} V')
    print('DIAGNOSTIC ONLY: assumed line lengths/loads; TQ144 package assignment unresolved; MB-007/CC-007 remain pending')
    if args.main_board:
        print('Main-board copper paths:', report['measured_copper_paths_mm'])


if __name__ == '__main__':
    main()
