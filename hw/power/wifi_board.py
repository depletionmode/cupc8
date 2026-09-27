"""Bind the Wi-Fi buck model to KiCad components and routed power copper.

Trace resistance uses an assumed 35 um outer copper thickness with a 1.4x
hot-copper multiplier. It is a shortest copper path, with a conservative
10 mOhm allowance for each plated-through via. The fab order does not specify
copper weight, so this assumption cannot close WC-005 on its own.
Ground pours, pad spreading, temperature rise and capacitor ESR are not solved
here; the caller must retain a failed coverage gate for those omissions.
"""
import heapq
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cosim.netlist import read
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from kicadgen import find, find1, parse

COPPER_OHM_MM = 0.01724 / 0.035 * 1.4  # rho / 35 um, 100 C allowance
VIA_OHM = 0.010                 # conservative plated-through via allowance
RAILS = {'/+5V', '/3V3'}
VALUES = {'U2': ('TLV62569DBVR', ('jlc', 'TLV62569DBVR')),
          'L1': ('2.2u', ('Device', 'L')),
          'R9': ('453k', ('Device', 'R')), 'R10': ('100k', ('Device', 'R')),
          'C1': ('22u', ('Device', 'C')), 'C2': ('22u', ('Device', 'C')),
          'C3': ('100n', ('Device', 'C'))}
PINS = {
    ('U2', '1'): '/+5V', ('U2', '2'): '/GND', ('U2', '3'): '/SW',
    ('U2', '4'): '/+5V', ('U2', '5'): '/FB',
    ('L1', '1'): '/SW', ('L1', '2'): '/3V3',
    ('R9', '1'): '/3V3', ('R9', '2'): '/FB',
    ('R10', '1'): '/FB', ('R10', '2'): '/GND',
    ('C1', '1'): '/+5V', ('C1', '2'): '/GND',
    ('C2', '1'): '/3V3', ('C2', '2'): '/GND',
    ('C3', '1'): '/3V3', ('C3', '2'): '/GND',
    ('U1', '3'): '/3V3',
    ('J1', 'A2'): '/+5V', ('J1', 'B1'): '/+5V', ('J1', 'B2'): '/+5V',
}


def topology(path):
    circuit = read(path)
    for ref, expected in VALUES.items():
        if circuit.components.get(ref) != expected:
            raise ValueError(f'{ref}: expected {expected}, got {circuit.components.get(ref)}')
    for pin, net in PINS.items():
        if circuit.net(*pin) != net:
            raise ValueError(f'{pin}: expected {net}, got {circuit.net(*pin)}')
    for net in ('/SW', '/FB'):
        expected = {pin for pin, name in PINS.items() if name == net}
        if set(circuit.nets[net]) != expected:
            raise ValueError(f'{net}: unexpected or missing regulator connection')
    return circuit


def child(item, name):
    value = find1(item, name)
    if value is None:
        raise ValueError(f'missing PCB {name}')
    return value


def point(item, name):
    return tuple(round(float(v), 4) for v in child(item, name)[1:3])


def pad_nodes(tree):
    pads = {}
    for fp in find(tree, 'footprint'):
        props = [p for p in find(fp, 'property') if len(p) > 2 and p[1] == 'Reference']
        if len(props) != 1:
            raise ValueError('footprint missing unique reference')
        ref = str(props[0][2])
        at = child(fp, 'at')
        fx, fy = float(at[1]), float(at[2])
        # KiCad's footprint angle is clockwise in the PCB's Y-down frame.
        angle = -math.radians(float(at[3]) if len(at) > 3 else 0)
        for pad in find(fp, 'pad'):
            if len(pad) < 2:
                raise ValueError(f'{ref}: pad lacks number')
            pin = str(pad[1])
            raw_net = find1(pad, 'net')
            if raw_net is None:
                continue
            net = raw_net[1]
            local = point(pad, 'at')
            center = (round(fx + local[0] * math.cos(angle) - local[1] * math.sin(angle), 4),
                      round(fy + local[0] * math.sin(angle) + local[1] * math.cos(angle), 4))
            size = point(pad, 'size')
            layers = set(child(pad, 'layers')[1:]) & {'F.Cu', 'B.Cu'}
            if (ref, pin) in pads:
                raise ValueError(f'duplicate PCB pad {ref}.{pin}')
            pads[(ref, pin)] = (net, center, max(size) / 2 + 0.025, layers)
    return pads


def routes(board, order, circuit):
    spec = json.loads(Path(order).read_text())
    if spec.get('layers') != 2 or spec.get('thickness_mm') != 1.6:
        raise ValueError('Wi-Fi power model requires the ordered 2-layer 1.6 mm board')
    tree = parse(Path(board).read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('expected KiCad PCB')
    layers = child(tree, 'layers')
    copper = {row[1] for row in layers[1:] if isinstance(row, list) and len(row) > 2 and row[2] == 'signal'}
    if copper != {'F.Cu', 'B.Cu'}:
        raise ValueError(f'PCB copper layers {copper} differ from two-layer order')
    pads = pad_nodes(tree)
    for pin, net in PINS.items():
        if circuit.net(*pin) != net:
            raise ValueError(f'netlist pin {pin} disagrees with {net}')
        if pin not in pads or pads[pin][0] != net:
            raise ValueError(f'PCB pad {pin} disagrees with netlist {net}')
    for net in RAILS:
        if any(child(z, 'net')[1] == net for z in find(tree, 'zone')):
            raise ValueError(f'{net}: power pour resistance is not modelled')
    graphs = {net: {} for net in RAILS}
    endpoints = {net: set() for net in RAILS}
    def edge(net, a, b, resistance):
        graph = graphs[net]
        graph.setdefault(a, []).append((b, resistance))
        graph.setdefault(b, []).append((a, resistance))
    for seg in find(tree, 'segment'):
        net = child(seg, 'net')[1]
        if net not in RAILS:
            continue
        layer = child(seg, 'layer')[1]
        a, b = point(seg, 'start'), point(seg, 'end')
        width = float(child(seg, 'width')[1])
        length = math.dist(a, b)
        if layer not in copper or width <= 0 or length <= 0:
            raise ValueError(f'{net}: invalid copper segment')
        edge(net, (layer, a), (layer, b), COPPER_OHM_MM * length / width / 1000)
        endpoints[net].update(((layer, a), (layer, b)))
    for via in find(tree, 'via'):
        net = child(via, 'net')[1]
        if net not in RAILS:
            continue
        at = point(via, 'at')
        via_layers = set(child(via, 'layers')[1:])
        if via_layers != copper:
            raise ValueError(f'{net}: unsupported via layers {via_layers}')
        edge(net, ('F.Cu', at), ('B.Cu', at), VIA_OHM)
        endpoints[net].update((('F.Cu', at), ('B.Cu', at)))
    for pin, (net, center, radius, pad_layers) in pads.items():
        if net not in RAILS:
            continue
        anchor = ('pad', pin)
        hits = [node for node in endpoints[net]
                if node[0] in pad_layers and math.dist(node[1], center) <= radius]
        if not hits:
            raise ValueError(f'{net}: {pin} has no routed copper at its pad')
        for node in hits:
            edge(net, anchor, node, 0)
    def distance(net, starts, end):
        graph = graphs[net]
        queue = [(0, ('pad', pin)) for pin in starts]
        heapq.heapify(queue)
        best = {}
        while queue:
            cost, node = heapq.heappop(queue)
            if node in best:
                continue
            best[node] = cost
            if node == ('pad', end):
                return cost
            for nxt, r in graph.get(node, ()):
                if nxt not in best:
                    heapq.heappush(queue, (cost + r, nxt))
        raise ValueError(f'{net}: no routed path from {starts} to {end}')
    source = [('J1', pin) for pin in ('A2', 'B1', 'B2')]
    r5 = max(distance('/+5V', source, sink) for sink in (('U2', '1'), ('U2', '4'), ('C1', '1')))
    r3 = max(distance('/3V3', [('L1', '2')], sink)
             for sink in (('U1', '3'), ('C2', '1'), ('C3', '1'), ('R9', '1')))
    if r5 <= 0 or r3 <= 0:
        raise ValueError('routed rail resistance must be positive')
    return r5, r3
