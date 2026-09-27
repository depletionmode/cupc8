"""Conservative raster path estimate through saved KiCad GND fills and vias.

A filled grid cell is accepted only after eroding its polygon by the cell's
full diagonal. Each cardinal hop uses a one-square, hot 1 oz copper sheet
resistance. This single-path result is an upper bound on the resistance of the
represented fill. Narrow copper omitted by rasterization can make the model
fail closed. Pad thermal spokes, track-to-pour contact and ESR require further
independent checks before this estimate can certify WC-005.
"""
import heapq
import math
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Polygon

from wifi_board import child, find, find1, pad_nodes, parse, point, COPPER_OHM_MM, VIA_OHM

PITCH_MM = 0.25
LAYERS = ('F.Cu', 'B.Cu')
# A square of width=length has rho / copper thickness resistance.  The
# extractor's COPPER_OHM_MM is per millimetre of a 1 mm-wide strip, after the
# hot-copper factor.  No length/width scaling is needed for a grid square.
SHEET_OHM = COPPER_OHM_MM / 1000


def polygons(tree):
    result = {layer: [] for layer in LAYERS}
    for zone in find(tree, 'zone'):
        if child(zone, 'net')[1] != '/GND':
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


def raster(fills):
    all_points = np.concatenate([poly for group in fills.values() for poly in group])
    xmin, ymin = all_points.min(axis=0)
    xmax, ymax = all_points.max(axis=0)
    xs = np.arange(xmin + PITCH_MM / 2, xmax, PITCH_MM)
    ys = np.arange(ymin + PITCH_MM / 2, ymax, PITCH_MM)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack((xx.ravel(), yy.ravel()))
    masks = []
    for layer in LAYERS:
        mask = np.zeros(len(points), dtype=bool)
        for vertices in fills[layer]:
            # Matplotlib contracts the polygon by half the full cell diagonal
            # on each side (its radius is a full-width parameter).
            mask |= Polygon(vertices).contains_points(points, radius=-PITCH_MM * math.sqrt(2))
        masks.append(mask.reshape(xx.shape))
    return xs, ys, np.stack(masks)


def within(xs, ys, mask, center, radius, layer):
    if layer not in LAYERS:
        return []
    li = LAYERS.index(layer)
    ix0 = max(0, int((center[0] - radius - xs[0]) / PITCH_MM) - 1)
    ix1 = min(len(xs), int((center[0] + radius - xs[0]) / PITCH_MM) + 2)
    iy0 = max(0, int((center[1] - radius - ys[0]) / PITCH_MM) - 1)
    iy1 = min(len(ys), int((center[1] + radius - ys[0]) / PITCH_MM) + 2)
    return [(li, iy, ix) for iy in range(iy0, iy1) for ix in range(ix0, ix1)
            if mask[li, iy, ix] and math.hypot(xs[ix] - center[0], ys[iy] - center[1]) <= radius]


def pad_cells(pads, xs, ys, mask, pins):
    found = set()
    for pin in pins:
        net, center, radius, layers = pads[pin]
        if net != '/GND':
            raise ValueError(f'{pin}: expected GND pad')
        for layer in layers:
            found.update(within(xs, ys, mask, center, radius, layer))
    if not found:
        raise ValueError(f'GND pads {pins} do not touch represented filled copper')
    return found


def via_links(tree, xs, ys, mask):
    links = {}
    count = 0
    for via in find(tree, 'via'):
        if child(via, 'net')[1] != '/GND':
            continue
        if set(child(via, 'layers')[1:]) != set(LAYERS):
            raise ValueError('GND via has unsupported layer span')
        center = point(via, 'at')
        radius = float(child(via, 'size')[1]) / 2
        a = within(xs, ys, mask, center, radius, LAYERS[0])
        b = within(xs, ys, mask, center, radius, LAYERS[1])
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


def shortest(mask, links, starts, targets):
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
                        heapq.heappush(pending, (cost + SHEET_OHM, nxt))
        for nxt, resistance in links.get(node, ()):
            if nxt not in best:
                heapq.heappush(pending, (cost + resistance, nxt))
    raise ValueError('GND filled copper does not connect return pads')


def estimate(board):
    tree = parse(Path(board).read_text())
    if tree[0] != 'kicad_pcb':
        raise ValueError('expected KiCad PCB')
    fills = polygons(tree)
    xs, ys, mask = raster(fills)
    pads = pad_nodes(tree)
    links, via_count = via_links(tree, xs, ys, mask)
    esp = [pin for pin, (net, _, _, _) in pads.items() if pin[0] == 'U1' and net == '/GND']
    source = pad_cells(pads, xs, ys, mask, esp)
    paths = {}
    for sink in (('C2', '2'), ('C3', '2'), ('U2', '2')):
        target = pad_cells(pads, xs, ys, mask, [sink])
        paths[sink] = shortest(mask, links, source, target)
    return max(paths.values()), via_count, tuple(int(mask[i].sum()) for i in range(2))
