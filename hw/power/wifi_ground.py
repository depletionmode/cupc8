"""Raster path sensitivity through saved KiCad GND fills and vias.

A filled grid point is accepted only after eroding its polygon by half a
fixed 0.25 mm corridor width. Each cardinal hop is charged hot 1 oz sheet
resistance times its length divided by that width. This is a conservative
fixed-width path scenario, not the effective resistance of the filled plane.
Two pitches expose raster error. Pad thermal spokes and track-to-pour contact
also need validation before WC-005 can be certified.
"""
import heapq
import math
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Polygon

from wifi_board import child, find, find1, pad_nodes, parse, point, COPPER_OHM_MM, VIA_OHM

DEFAULT_PITCH_MM = 0.25
PATH_WIDTH_MM = 0.25
LAYERS = ('F.Cu', 'B.Cu')
CARD_EDGE_GND = {
    'A': ('A3', 'A5', 'A8', 'A11', 'A12', 'A13', 'A15', 'A17'),
    'B': ('B3', 'B5', 'B8', 'B11', 'B12', 'B14', 'B17'),
}
# The extractor's COPPER_OHM_MM is per millimetre of a 1 mm-wide strip,
# after the hot-copper factor.
SHEET_OHM = COPPER_OHM_MM / 1000


def polygons(tree):
    result = {layer: [] for layer in LAYERS}
    for zone in find(tree, 'zone'):
        if (find1(zone, 'net') or [None, None])[1] != '/GND':
            continue
        layer = child(zone, 'layer')[1]
        if layer not in result:
            raise ValueError(f'GND pour has unsupported layer {layer}')
        filled = find(zone, 'filled_polygon')
        if not filled:
            raise ValueError(f'{layer} GND zone has no saved fill')
        for polygon in filled:
            if child(polygon, 'layer')[1] != layer:
                raise ValueError('GND filled polygon layer mismatch')
            vertices = np.array([[float(v) for v in item[1:]]
                                 for item in child(polygon, 'pts')[1:]], dtype=float)
            if len(vertices) < 3:
                raise ValueError('GND fill polygon has too few vertices')
            result[layer].append(vertices)
    if any(not result[layer] for layer in LAYERS):
        raise ValueError('both outer GND fills are required')
    return result


def raster(fills, pitch):
    all_points = np.concatenate([poly for group in fills.values() for poly in group])
    xmin, ymin = all_points.min(axis=0)
    xmax, ymax = all_points.max(axis=0)
    xs = np.arange(xmin + pitch / 2, xmax, pitch)
    ys = np.arange(ymin + pitch / 2, ymax, pitch)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack((xx.ravel(), yy.ravel()))
    masks = []
    for layer in LAYERS:
        mask = np.zeros(len(points), dtype=bool)
        for vertices in fills[layer]:
            # Matplotlib's radius is a full-width parameter, so -0.25 mm
            # keeps each point approximately 0.125 mm inside the fill.
            mask |= Polygon(vertices).contains_points(points, radius=-PATH_WIDTH_MM)
        masks.append(mask.reshape(xx.shape))
    return xs, ys, np.stack(masks)


def within(xs, ys, mask, center, radius, layer, pitch):
    if layer not in LAYERS:
        return []
    li = LAYERS.index(layer)
    ix0 = max(0, int((center[0] - radius - xs[0]) / pitch) - 1)
    ix1 = min(len(xs), int((center[0] + radius - xs[0]) / pitch) + 2)
    iy0 = max(0, int((center[1] - radius - ys[0]) / pitch) - 1)
    iy1 = min(len(ys), int((center[1] + radius - ys[0]) / pitch) + 2)
    return [(li, iy, ix) for iy in range(iy0, iy1) for ix in range(ix0, ix1)
            if mask[li, iy, ix] and math.hypot(xs[ix] - center[0], ys[iy] - center[1]) <= radius]


def pad_cells(pads, xs, ys, mask, pins, pitch):
    found = set()
    for pin in pins:
        net, center, radius, layers = pads[pin]
        if net != '/GND':
            raise ValueError(f'{pin}: expected GND pad')
        for layer in layers:
            found.update(within(xs, ys, mask, center, radius, layer, pitch))
    if not found:
        raise ValueError(f'GND pads {pins} do not touch represented filled copper')
    return found


def via_links(tree, xs, ys, mask, pitch):
    links = {}
    count = 0
    for via in find(tree, 'via'):
        if child(via, 'net')[1] != '/GND':
            continue
        if set(child(via, 'layers')[1:]) != set(LAYERS):
            raise ValueError('GND via has unsupported layer span')
        center = point(via, 'at')
        radius = float(child(via, 'size')[1]) / 2
        a = within(xs, ys, mask, center, radius, LAYERS[0], pitch)
        b = within(xs, ys, mask, center, radius, LAYERS[1], pitch)
        if not a or not b:
            continue  # stitching via outside one saved fill cannot bridge it
        count += 1
        # Link every covered cell on each side to the via barrel.  This is
        # pessimistic about the barrel and optimistic about pad spreading;
        # the caller retains the independent coverage failure.
        barrel = ('via', count)
        for nodes in (a, b):
            for node in nodes:
                links.setdefault(node, []).append((barrel, VIA_OHM / 2))
                links.setdefault(barrel, []).append((node, VIA_OHM / 2))
    if not count:
        raise ValueError('GND fills have no through-via bridge')
    return links, count


def shortest(mask, links, starts, targets, pitch):
    rows, cols = mask.shape[1:]
    pending = [(0.0, node) for node in starts]
    heapq.heapify(pending)
    best = {}
    target = set(targets)
    while pending:
        cost, node = heapq.heappop(pending)
        if node in best:
            continue
        best[node] = cost
        if node in target:
            return cost
        if node[0] != 'via':
            layer, iy, ix = node
            for ny, nx in ((iy - 1, ix), (iy + 1, ix), (iy, ix - 1), (iy, ix + 1)):
                if 0 <= ny < rows and 0 <= nx < cols and mask[layer, ny, nx]:
                    nxt = (layer, ny, nx)
                    if nxt not in best:
                        heapq.heappush(pending, (cost + SHEET_OHM * pitch / PATH_WIDTH_MM, nxt))
        for nxt, resistance in links.get(node, ()):
            if nxt not in best:
                heapq.heappush(pending, (cost + resistance, nxt))
    raise ValueError('GND filled copper does not connect return pads')


def estimate(board, pitch=DEFAULT_PITCH_MM):
    if pitch <= 0 or pitch > 0.5:
        raise ValueError('GND raster pitch must be in (0, 0.5] mm')
    tree = parse(Path(board).read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('expected KiCad PCB')
    fills = polygons(tree)
    xs, ys, mask = raster(fills, pitch)
    pads = pad_nodes(tree)
    links, via_count = via_links(tree, xs, ys, mask, pitch)
    esp = [pin for pin, (net, _, _, _) in pads.items() if pin[0] == 'U1' and net == '/GND']
    source = pad_cells(pads, xs, ys, mask, esp, pitch)
    paths = {}
    for sink in (('C2', '2'), ('C3', '2'), ('U2', '2')):
        target = pad_cells(pads, xs, ys, mask, [sink], pitch)
        paths[sink] = shortest(mask, links, source, target, pitch)
    return max(paths.values()), via_count, tuple(int(mask[i].sum()) for i in range(2))


def compare(board):
    """Return conservative scenario and explicit two-pitch discrepancy."""
    coarse = estimate(board, 0.25)
    fine = estimate(board, 0.125)
    if coarse[1] != fine[1]:
        raise ValueError('GND via contact changes between 0.25 and 0.125 mm meshes')
    discrepancy = abs(fine[0] - coarse[0]) / max(fine[0], coarse[0])
    return max(coarse[0], fine[0]), coarse, fine, discrepancy


def card_edge_returns(board, pitch=DEFAULT_PITCH_MM):
    """Path scenarios from fitted U1/U2 GND pads to each J1 GND face.

    A shortest fixed-width corridor is not an effective plane resistance or
    a bound on parallel current spreading, pad entry and mated contacts.
    """
    if pitch <= 0 or pitch > 0.5:
        raise ValueError('GND raster pitch must be in (0, 0.5] mm')
    tree = parse(Path(board).read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('expected KiCad PCB')
    xs, ys, mask = raster(polygons(tree), pitch)
    pads = pad_nodes(tree)
    links, via_count = via_links(tree, xs, ys, mask, pitch)
    sinks = {face: pad_cells(pads, xs, ys, mask,
                             [('J1', pin) for pin in pins], pitch)
             for face, pins in CARD_EDGE_GND.items()}
    result = {}
    for name, pin in (('esp', ('U1', '1')), ('buck', ('U2', '2'))):
        starts = pad_cells(pads, xs, ys, mask, [pin], pitch)
        for face, targets in sinks.items():
            result[f'{name}_to_J1_{face}'] = shortest(mask, links, starts, targets, pitch)
    return result, via_count


def compare_card_edge(board):
    """Report both mesh pitches and reject a changed via bridge count."""
    coarse, coarse_vias = card_edge_returns(board, 0.25)
    fine, fine_vias = card_edge_returns(board, 0.125)
    if coarse_vias != fine_vias:
        raise ValueError('GND via contact changes between card-edge meshes')
    result = {name: max(coarse[name], fine[name]) for name in coarse}
    errors = {name: abs(coarse[name] - fine[name]) / result[name] for name in result}
    return result, coarse, fine, errors
