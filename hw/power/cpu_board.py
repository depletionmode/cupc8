"""CC-005: bind the CPU card's RT9013 output to its routed 1V2 copper.

The route result is a centerline scenario using nominal finished copper:
pad spreading, minimum copper thickness and capacitor ESR remain outside
this extractor. The catalogue gate retains those coverage failures.
"""
import heapq
import json
import math
from pathlib import Path
import sys

from wifi_board import COPPER_OHM_MM, child, find, find1, pad_nodes, parse, point
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cosim.netlist import read

NET = '/1V2'
EXPECTED = {
    ('U3', '1'): '/3V3', ('U3', '3'): '/3V3', ('U3', '2'): '/GND',
    ('U3', '5'): NET, ('C21', '1'): '/3V3', ('C21', '2'): '/GND',
    ('C22', '1'): NET, ('C22', '2'): '/GND',
    **{('C%d' % n, '1'): NET for n in range(1, 5)},
    **{('C%d' % n, '2'): '/GND' for n in range(1, 5)},
    **{('U1', str(n)): NET for n in (27, 40, 92, 111)},
}
VALUES = {'U3': ('RT9013-12GB', ('jlc', 'RT9013-12GB')),
          'C21': ('1u', ('Device', 'C')), 'C22': ('4.7u', ('Device', 'C')),
          **{'C%d' % n: ('100n', ('Device', 'C')) for n in range(1, 5)}}
SINKS = [('C22', '1')] + [('C%d' % n, '1') for n in range(1, 5)] + [
    ('U1', str(n)) for n in (27, 40, 92, 111)]


def topology(path):
    circuit = read(path)
    for ref, value in VALUES.items():
        got = circuit.components.get(ref)
        if got != value:
            raise ValueError('%s: expected %s, got %s' % (ref, value, got))
    for pin, net in EXPECTED.items():
        if circuit.net(*pin) != net:
            raise ValueError('%s: expected %s, got %s' % (pin, net, circuit.net(*pin)))
    return circuit


def route_resistance(board, order):
    spec = json.loads(Path(order).read_text())
    if spec.get('layers') != 6 or spec.get('finished_outer_copper_oz') != 1:
        raise ValueError('CPU rail model requires six layers and 1 oz finished outer copper')
    tree = parse(Path(board).read_text())
    pads = pad_nodes(tree)
    for pin, net in EXPECTED.items():
        if pin not in pads or pads[pin][0] != net:
            raise ValueError('PCB pad %s differs from netlist %s' % (pin, net))
    if any((find1(z, 'net') or [None, None])[1] == NET for z in find(tree, 'zone')):
        raise ValueError('1V2 pour needs a plane model')
    if any((find1(v, 'net') or [None, None])[1] == NET for v in find(tree, 'via')):
        raise ValueError('1V2 via needs a barrel model')
    graph = {}
    endpoints = set()
    def edge(a, b, ohms):
        graph.setdefault(a, []).append((b, ohms))
        graph.setdefault(b, []).append((a, ohms))
    segments = 0
    for segment in find(tree, 'segment'):
        if child(segment, 'net')[1] != NET:
            continue
        if child(segment, 'layer')[1] != 'F.Cu':
            raise ValueError('1V2 route leaves modeled top copper')
        a, b = point(segment, 'start'), point(segment, 'end')
        width = float(child(segment, 'width')[1])
        if width <= 0 or a == b:
            raise ValueError('invalid 1V2 track geometry')
        edge(a, b, COPPER_OHM_MM * math.dist(a, b) / width / 1000)
        endpoints.update((a, b))
        segments += 1
    for pin in [('U3', '5'), *SINKS]:
        _, center, radius, layers = pads[pin]
        hits = [node for node in endpoints if 'F.Cu' in layers and math.dist(node, center) <= radius]
        if not hits:
            raise ValueError('%s has no 1V2 track at its pad' % (pin,))
        for node in hits:
            edge(pin, node, 0)
    def distance(target):
        queue = [(0.0, ('U3', '5'))]
        best = {}
        while queue:
            cost, node = heapq.heappop(queue)
            if node in best:
                continue
            best[node] = cost
            if node == target:
                return cost
            for nxt, ohms in graph.get(node, ()):
                if nxt not in best:
                    heapq.heappush(queue, (cost + ohms, nxt))
        raise ValueError('1V2 route does not reach %s' % (target,))
    return segments, {sink: distance(sink) for sink in SINKS}


def check(out):
    out = Path(out)
    topology(out / 'cpu.net')
    segments, sinks = route_resistance(out / 'cpu.kicad_pcb', out / 'fab/order.json')
    farthest = max(sinks, key=sinks.get)
    print('CPU 1V2: %d top-layer tracks; longest centerline scenario U3.5 to %s: %.1f mOhm'
          % (segments, farthest, 1e3 * sinks[farthest]))
    print('CPU output parts: C22 4.7 uF + C1-C4 100 nF nominal; LDO deck uses 1.4 uF')
    return sinks
