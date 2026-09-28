#!/usr/bin/env python3
"""Extract the routed six-slot SCK branch graph and an assumed lossless RLGC deck.

The KiCad copper geometry is authoritative. The 50 ohm, 7 ps/mm line model,
ideal vias/pads, ideal return and 15 pF loads are diagnostic assumptions.
This is not a row-4.6 pass/fail simulation.
"""
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import find1, parse  # noqa: E402
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from netlist import read as read_netlist  # noqa: E402

NET = '/SPI_SCK'
LAYERS = ('F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'B.Cu')
RECEIVERS = tuple(f'J{n}.B13' for n in range(11, 17))
Z0_OHM = 50.0
DELAY_PS_PER_MM = 7.0


def xy(tokens):
    return tuple(round(float(v), 4) for v in tokens)


def pin_node(board, ref, pin):
    footprint = board.FindFootprintByReference(ref)
    if footprint is None:
        raise ValueError(f'{ref}: footprint missing')
    pads = [p for p in footprint.Pads() if p.GetNumber() == pin]
    if len(pads) != 1 or pads[0].GetNetname() != NET:
        raise ValueError(f'{ref}.{pin}: expected exactly one {NET} pad')
    pad = pads[0]
    p = pad.GetPosition()
    point = (round(pcbnew.ToMM(p.x), 4), round(pcbnew.ToMM(p.y), 4))
    return [(point, layer) for layer in LAYERS
            if pad.IsOnLayer(getattr(pcbnew, layer.replace('.', '_')))]


def span(layers):
    if layers == ['F.Cu', 'B.Cu']:
        return LAYERS
    if len(layers) != 2 or any(layer not in LAYERS for layer in layers):
        raise ValueError(f'unknown via layer span {layers}')
    a, b = (LAYERS.index(layer) for layer in layers)
    return LAYERS[min(a, b):max(a, b) + 1]


def fraction(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom < 1e-12:
        raise ValueError('zero-length SCK track')
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / denom
    cross = abs((point[0] - a[0]) * dy - (point[1] - a[1]) * dx) / math.sqrt(denom)
    return t if -1e-7 <= t <= 1 + 1e-7 and cross <= 0.00011 else None


class Union:
    def __init__(self):
        self.parent = {}

    def root(self, node):
        self.parent.setdefault(node, node)
        if self.parent[node] != node:
            self.parent[node] = self.root(self.parent[node])
        return self.parent[node]

    def join(self, a, b):
        ra, rb = self.root(a), self.root(b)
        self.parent[max(ra, rb)] = min(ra, rb)


def extract(board_path, netlist_path=None):
    board_path = Path(board_path)
    if netlist_path is not None:
        netlist_path = Path(netlist_path)
        circuit = read_netlist(netlist_path)
        source = circuit.series(('U7', '43'), ('J11', 'B13'))
        if source is None or source.ref != 'R36' or source.value != '33' or \
                circuit.net('R36', '2') != NET:
            raise ValueError('SCK requires FPGA U7.43 through exact 33-ohm R36 source')
    board = pcbnew.LoadBoard(str(board_path))
    tree = parse(board_path.read_text())
    raw, vias = [], []
    for item in tree[1:]:
        if not isinstance(item, list) or not item or item[0] not in ('segment', 'via', 'arc'):
            continue
        net = find1(item, 'net')
        if net is None or net[1] != NET:
            continue
        if item[0] == 'arc':
            raise ValueError('SCK arc needs exact electrical length extraction')
        if item[0] == 'segment':
            layer = find1(item, 'layer')[1]
            if layer not in LAYERS:
                raise ValueError(f'SCK track on unknown layer {layer}')
            raw.append((xy(find1(item, 'start')[1:]), xy(find1(item, 'end')[1:]),
                        layer, float(find1(item, 'width')[1])))
        else:
            vias.append((xy(find1(item, 'at')[1:]), span(find1(item, 'layers')[1:])))
    if not raw:
        raise ValueError('no routed SCK segments')
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != NET:
                continue
            p = pad.GetPosition()
            point = (round(pcbnew.ToMM(p.x), 4), round(pcbnew.ToMM(p.y), 4))
            active = tuple(layer for layer in LAYERS
                           if pad.IsOnLayer(getattr(pcbnew, layer.replace('.', '_'))))
            pads.append((point, active))
    points = {layer: set() for layer in LAYERS}
    for a, b, layer, _ in raw:
        points[layer].update((a, b))
    for point, active in (*vias, *pads):
        for layer in active:
            points[layer].add(point)
    uf = Union()
    for point, active in (*vias, *pads):
        for first, second in zip(active, active[1:]):
            uf.join((point, first), (point, second))

    # Split at every same-layer endpoint/pad/via on the segment, preserving
    # the actual branch junctions instead of replacing the bus by one line.
    tracks = []
    for a, b, layer, width in raw:
        hits = [(t, point) for point in points[layer]
                if (t := fraction(point, a, b)) is not None]
        hits.sort()
        for (_, first), (_, last) in zip(hits, hits[1:]):
            length = math.dist(first, last)
            if length < 1e-6:
                continue
            tracks.append((uf.root((first, layer)), uf.root((last, layer)),
                           length, layer, width))
    roots = sorted({node for edge in tracks for node in edge[:2]} |
                   {uf.root(node) for node in uf.parent})
    ids = {node: index for index, node in enumerate(roots)}
    edges = []
    graph = {index: [] for index in range(len(ids))}
    for a, b, length, layer, width in tracks:
        if a == b:
            raise ValueError(f'{layer}: nonzero SCK track collapses through an ideal pad/via')
        x, y = ids[a], ids[b]
        edges.append({'from': x, 'to': y, 'layer': layer, 'width_mm': width,
                      'length_mm': round(length, 9),
                      'rlgc': {'r_ohm': 0.0,
                               'l_nh': round(length * Z0_OHM * DELAY_PS_PER_MM / 1000, 9),
                               'g_s': 0.0,
                               'c_pf': round(length * DELAY_PS_PER_MM / Z0_OHM, 9)}})
        graph[x].append((y, length))
        graph[y].append((x, length))

    def endpoint(ref, pin):
        matches = [ids[uf.root(node)] for node in pin_node(board, ref, pin)
                   if uf.root(node) in ids]
        if not matches:
            raise ValueError(f'{ref}.{pin}: no SCK copper launch')
        if len(set(matches)) != 1:
            raise ValueError(f'{ref}.{pin}: pad spans unjoined signal layers')
        return matches[0]

    source = endpoint('R36', '2')
    receivers = {name: endpoint(*name.split('.')) for name in RECEIVERS}
    distances = {source: 0.0}
    pending = [(0.0, source)]
    while pending:
        distance, node = heapq.heappop(pending)
        if distance > distances[node]:
            continue
        for neighbor, length in graph[node]:
            next_distance = distance + length
            if next_distance < distances.get(neighbor, math.inf):
                distances[neighbor] = next_distance
                heapq.heappush(pending, (next_distance, neighbor))
    missing = [name for name, node in receivers.items() if node not in distances]
    if missing:
        raise ValueError(f'SCK copper open from R36.2 to {missing}')
    return {
        'scope': 'routed six-slot SCK diagnostic RLGC topology',
        'board_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
        'netlist_sha256': (hashlib.sha256(netlist_path.read_bytes()).hexdigest()
                           if netlist_path is not None else None),
        'net': NET, 'source': {'pad': 'R36.2', 'node': source},
        'receivers': {name: {'node': node, 'shortest_planar_mm': round(distances[node], 3)}
                      for name, node in receivers.items()},
        'nodes': [{'id': ids[node], 'x_mm': node[0][0], 'y_mm': node[0][1],
                   'layer': node[1]} for node in roots],
        'edges': edges,
        'vias': len(vias), 'plated_pads': sum(len(active) > 1 for _, active in pads),
        'branch_nodes': sum(len(neighbors) >= 3 for neighbors in graph.values()),
        'copper_length_mm': round(sum(edge['length_mm'] for edge in edges), 3),
        'assumptions': {'z0_ohm': Z0_OHM, 'delay_ps_per_mm': DELAY_PS_PER_MM,
                        'receiver_load_pf': 15.0, 'r_ohm_per_mm': 0,
                        'g_s_per_mm': 0, 'via_and_pad_impedance': 'ideal zero'},
        'valid_for_row_4_6': False,
        'missing_inputs': ['qualified six-layer dielectric and copper stackup',
                           'return-current topology and discontinuity extraction',
                           'via and connector parasitics', 'RP2040 receiver IBIS',
                           'unambiguous iCE40HX4K-TQ144 package assignment',
                           'nonlinear IBIS driver conversion and fixture validation'],
    }


def spice_deck(report):
    """Emit an experimental synthetic stimulus/load deck; no SI gate claim."""
    # KiCad splits straight copper at routing vertices. A T element for every
    # very short piece makes ngspice's timestep collapse. Collapse degree-2
    # runs only; every physical branch/load/source node remains distinct.
    # Sub-10-um splinters occur where a pad barrel meets a rounded track
    # coordinate. They have sub-0.07-ps delay and make ideal ngspice T lines
    # numerically singular. Keep them in the JSON geometry, but use an ideal
    # node contraction for this diagnostic deck.
    uf = Union()
    for edge in report['edges']:
        if edge['length_mm'] < .01:
            uf.join(edge['from'], edge['to'])
    effective = []
    for edge in report['edges']:
        if edge['length_mm'] < .01:
            continue
        a, b = uf.root(edge['from']), uf.root(edge['to'])
        if a == b:
            raise ValueError('contracted SCK run contains a larger closed loop')
        effective.append((a, b, edge['length_mm']))
    neighbors = {}
    for index, (a, b, _) in enumerate(effective):
        neighbors.setdefault(a, []).append((b, index))
        neighbors.setdefault(b, []).append((a, index))
    anchors = {uf.root(report['source']['node']),
               *(uf.root(receiver['node']) for receiver in report['receivers'].values())}
    anchors.update(node for node, attached in neighbors.items() if len(attached) != 2)
    runs, visited = [], set()
    for start in sorted(anchors):
        for next_node, first_edge in neighbors[start]:
            if first_edge in visited:
                continue
            visited.add(first_edge)
            length = effective[first_edge][2]
            here = next_node
            while here not in anchors:
                candidates = [(node, edge) for node, edge in neighbors[here]
                              if edge not in visited]
                if len(candidates) != 1:
                    raise ValueError(f'SCK serial run at node {here} is ambiguous')
                here, edge = candidates[0]
                visited.add(edge)
                length += effective[edge][2]
            runs.append((start, here, length))
    if len(visited) != len(effective):
        raise ValueError('SCK electrical graph contains an unvisited edge')
    lines = ['CUPC8 routed SCK topology diagnostic; synthetic source and loads',
             '* Experimental deck: transient solver convergence is not qualified.',
             '* Track pieces below 0.01 mm are contracted to ideal nodes.',
             'Vsrc drive 0 PULSE(0 3.3 1n 0.5n 0.5n 20n 40n)',
             f'Rsource drive n{uf.root(report["source"]["node"])} 33']
    for index, (a, b, length) in enumerate(runs, 1):
        delay_ps = length * DELAY_PS_PER_MM
        lines.append(f'T{index} n{a} 0 n{b} 0 '
                     f'Z0={Z0_OHM:g} TD={delay_ps:.9g}p')
    for index, receiver in enumerate(report['receivers'].values(), 1):
        lines.append(f'Cload{index} n{uf.root(receiver["node"])} 0 15p')
    monitor = uf.root(next(iter(report['receivers'].values()))['node'])
    lines.extend(['.tran 0.05n 45n', f'.print tran v(n{monitor})', '.end'])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', type=Path, default=ROOT / 'build/hw/main/main.kicad_pcb')
    parser.add_argument('--netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/hw/si/ibis-sck-topology.json')
    parser.add_argument('--spice', type=Path, default=ROOT / 'build/hw/si/ibis-sck-topology.cir')
    args = parser.parse_args()
    report = extract(args.board, args.netlist)
    for target in (args.out, args.spice):
        target.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    args.spice.write_text(spice_deck(report))
    print(f'SCK: {len(report["edges"])} tracks, {report["vias"]} vias, '
          f'{report["branch_nodes"]} branch nodes; '
          f'{len(report["receivers"])} routed receivers; diagnostic only')


if __name__ == '__main__':
    main()
