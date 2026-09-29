#!/usr/bin/env python3
"""Routed-copper transmission-line extraction for the GC/IC/YC-007 SI rows.

For a pair of nets on a routed KiCad board this finds each net's copper path
between two pads (tracks, vias and pads, shortest routed path), samples it
every `STEP_MM`, and at each sample solves the 2-D quasi-static cross-section
perpendicular to the track (`xsection.py`) with **all** copper the cut meets
on all four layers: both signal conductors, zone fills, pads, via pads and
every other net's tracks.  Other nets are held at ground.

Why the numbers are defensible without a field-convergence study:
- the finite-element capacitance is an upper bound (Dirichlet principle), so
  each reported impedance is a rigorous LOWER bound on the quasi-TEM
  impedance of that cross-section;
- holding other copper at ground, the grounded outer box, every pad polygon
  taken slightly outside its true outline, and solder mask everywhere on the
  outer surfaces can only add capacitance, so they keep it a lower bound;
- the upper estimate adds the observed nested-grid change (geometric tail,
  three grids) plus a fixed 1 % allowance for those deliberate additions.
A verdict of "above the limit" therefore rests on the lower bound alone.

Stackup: JLC04161H-7628 (https://jlcpcb.com/impedance, read 2026-09-28):
1 oz outer / 0.5 oz inner copper, 7628 prepreg 0.2104 mm Dk 4.4, core
1.065 mm Dk 4.6, LPI mask Dk 3.8, 1.2 mil over substrate, 0.6 mil over trace.
"""
import hashlib
import heapq
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'tools'))
sys.path.insert(0, str(HERE.parent / 'cosim'))
from kicadgen import find1, parse  # noqa: E402
import xsection  # noqa: E402

CU_OUT, CU_IN, PREPREG, CORE = .035, .0152, .2104, 1.065
ER_PREPREG, ER_CORE, ER_MASK = 4.4, 4.6, 3.8
MASK_SUBSTRATE, MASK_TRACE = 1.2 * .0254, .6 * .0254
LAYERS = {}
LAYERS['F.Cu'] = (0.0, CU_OUT)
LAYERS['In1.Cu'] = (-PREPREG - CU_IN, -PREPREG)
LAYERS['In2.Cu'] = (-PREPREG - CU_IN - CORE - CU_IN, -PREPREG - CU_IN - CORE)
LAYERS['B.Cu'] = (LAYERS['In2.Cu'][0] - PREPREG - CU_OUT, LAYERS['In2.Cu'][0] - PREPREG)
BOARD_BOTTOM = LAYERS['B.Cu'][0]
ER_MAX = max(ER_PREPREG, ER_CORE, ER_MASK)
STEP_MM = .2
WINDOWS = (2.5, 4.0, 8.0)  # mm either side of the sampled track, widened
                           # until no signal copper reaches the grounded wall
AIR = 1.5              # mm of air above and below the board in the section
MODEL_ALLOWANCE = .01  # upper-estimate allowance for the conservative additions


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dielectrics(conductors, box):
    x0, x1 = box[0], box[1]
    top, bot = LAYERS['F.Cu'][0], LAYERS['B.Cu'][1]
    out = [(x0, x1, LAYERS['In1.Cu'][1], top, ER_PREPREG),
           (x0, x1, LAYERS['In1.Cu'][0], LAYERS['In1.Cu'][1], ER_PREPREG),
           (x0, x1, LAYERS['In2.Cu'][1], LAYERS['In1.Cu'][0], ER_CORE),
           (x0, x1, LAYERS['In2.Cu'][0], LAYERS['In2.Cu'][1], ER_PREPREG),
           (x0, x1, bot, LAYERS['In2.Cu'][0], ER_PREPREG),
           (x0, x1, top, top + MASK_SUBSTRATE, ER_MASK),
           (x0, x1, bot - MASK_SUBSTRATE, bot, ER_MASK)]
    for a, b, c, d, _ in conductors:
        if math.isclose(c, top):
            out.append((max(x0, a - MASK_TRACE), min(x1, b + MASK_TRACE), d, d + MASK_TRACE, ER_MASK))
        if math.isclose(d, bot):
            out.append((max(x0, a - MASK_TRACE), min(x1, b + MASK_TRACE), c - MASK_TRACE, c, ER_MASK))
    return out


def section(key, refine):
    """Build a cross-section from a cut key: (window, ((layer, s0, s1, cid), ...))."""
    window, spans = key
    box = (-window, window, BOARD_BOTTOM - AIR, LAYERS['F.Cu'][1] + AIR)
    # Signal ids 1 (P) and 2 (N); a cut meeting only one is solved as 1.
    signals = sorted({cid for *_, cid in spans if cid > 0})
    remap = {0: 0, **{cid: i + 1 for i, cid in enumerate(signals)}}
    conductors = [(s0, s1, *LAYERS[layer], remap[cid]) for layer, s0, s1, cid in spans]
    return xsection.Section(conductors, dielectrics(conductors, box), box,
                            fine=.005, coarse=.15, ratio=1.3, refine=refine)


def solve_key(key, levels=(1, 2, 4)):
    """Lower bound, upper estimate and delay for one cut."""
    results = [xsection.line_parameters(section(key, r)) for r in levels]
    name = 'z_diff' if 'z_diff' in results[0] else 'z_se'
    zs = [r[name] for r in results]
    # Nested grids: the bound can only rise (up to the CG tolerance).
    if any(b < a - 1e-6 * a for a, b in zip(zs, zs[1:])):
        raise RuntimeError(f'nested grids decreased {name}: {zs} (bound violated)')
    d1, d2 = max(zs[1] - zs[0], 0.0), max(zs[2] - zs[1], 0.0)
    if d2 <= 1e-6 * zs[2]:
        tail = 0.0
    elif d1 > 0 and d2 / d1 < .9:
        tail = d2 * (d2 / d1) / (1 - d2 / d1)     # geometric remainder
    else:
        tail = math.inf                           # not contracting: no estimate
    fine = results[-1]
    return {'kind': name, 'z_lower': zs[-1], 'z_grids': zs,
            'z_upper': zs[-1] + tail + MODEL_ALLOWANCE * zs[-1],
            'delay_s_per_m': fine['delay'],
            'c_per_m': fine.get('c_per_m', fine.get('c_diff_per_m')),
            'z_se_pair': fine['z_se'] if name == 'z_diff' else None,
            'c_self_per_m': fine['c_self']}


def _solve_one(key):
    return key, solve_key(key)


def solve_all(keys, jobs=None):
    """Solve distinct cut keys in parallel; returns {key: result}."""
    import multiprocessing
    keys = sorted(set(keys))
    with multiprocessing.get_context('fork').Pool(jobs) as pool:
        return dict(pool.map(_solve_one, keys, chunksize=1))


class Board:
    """Copper of a routed KiCad board, per layer, as polygons with nets."""

    def __init__(self, path):
        self.file = Path(path)
        self.sha256 = sha256(self.file)
        tree = parse(self.file.read_text())
        if tree[0] != 'kicad_pcb':
            raise ValueError('not a KiCad PCB')
        self.tracks, self.vias = [], []
        seen = set()
        for item in tree[1:]:
            if not isinstance(item, list) or not item or item[0] not in ('segment', 'arc', 'via'):
                continue
            net = find1(item, 'net')
            net = net[1] if net else ''
            if item[0] == 'arc':
                raise ValueError(f'{net}: arc tracks are not modelled')
            if item[0] == 'via':
                at = tuple(float(v) for v in find1(item, 'at')[1:3])
                layers = find1(item, 'layers')[1:]
                if tuple(layers) != ('F.Cu', 'B.Cu'):
                    raise ValueError(f'{net}: only through vias are modelled, found {layers}')
                self.vias.append((at, float(find1(item, 'size')[1]), net))
                continue
            a = tuple(float(v) for v in find1(item, 'start')[1:3])
            b = tuple(float(v) for v in find1(item, 'end')[1:3])
            width = float(find1(item, 'width')[1])
            layer = find1(item, 'layer')[1]
            if layer not in LAYERS:
                raise ValueError(f'{net}: unknown copper layer {layer}')
            key = (layer, net, width) + tuple(sorted((a, b)))
            if a == b or key in seen:      # Freerouting writes exact duplicates
                continue
            seen.add(key)
            self.tracks.append((a, b, width, layer, net))
        self._load_pcbnew()

    def _load_pcbnew(self):
        import pcbnew
        board = pcbnew.LoadBoard(str(self.file))
        ids = {'F.Cu': pcbnew.F_Cu, 'In1.Cu': pcbnew.In1_Cu,
               'In2.Cu': pcbnew.In2_Cu, 'B.Cu': pcbnew.B_Cu}
        self.polys = {layer: [] for layer in LAYERS}   # (Nx2 array, net)
        self.pads = {}                                  # (ref, number) -> info
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                pos = pad.GetPosition()
                info = {'net': pad.GetNetname(), 'at': (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)),
                        'layers': [], 'polys': {}}
                for layer, lid in ids.items():
                    if not pad.IsOnLayer(lid):
                        continue
                    shape = pcbnew.SHAPE_POLY_SET()
                    # ERROR_OUTSIDE: the polygon contains the true pad.
                    pad.TransformShapeToPolygon(shape, lid, 0, 500, pcbnew.ERROR_OUTSIDE)
                    for poly in _outlines(shape, pcbnew):
                        self.polys[layer].append((poly, info['net']))
                        info['polys'].setdefault(layer, []).append(poly)
                    info['layers'].append(layer)
                self.pads[(fp.GetReference(), pad.GetNumber())] = info
        for zone in board.Zones():
            if zone.GetIsRuleArea() or not zone.IsFilled():
                continue
            for layer, lid in ids.items():
                if zone.GetLayerSet().Contains(lid):
                    for poly in _outlines(zone.GetFilledPolysList(lid), pcbnew):
                        self.polys[layer].append((poly, zone.GetNetname()))

    # -- cutting ---------------------------------------------------------
    def cut(self, point, normal, nets, window=WINDOWS[0]):
        """Conductor intervals along point + s*normal, |s| <= window."""
        cid = {net: i + 1 for i, net in enumerate(nets)}
        p, n = np.array(point), np.array(normal)
        raw = {layer: [] for layer in LAYERS}
        reach = window + 3.0
        for a, b, width, layer, net in self.tracks:
            if _seg_dist(p, np.array(a), np.array(b)) > reach:
                continue
            span = _capsule(p, n, np.array(a), np.array(b), width / 2, window)
            if span:
                raw[layer].append((span, cid.get(net, 0)))
        for at, size, net in self.vias:
            if math.dist(at, point) > reach:
                continue
            span = _disk(p, n, np.array(at), size / 2, window)
            if span:
                for layer in LAYERS:
                    raw[layer].append((span, cid.get(net, 0)))
        for layer, polys in self.polys.items():
            for poly, net in polys:
                lo, hi = poly.min(axis=0), poly.max(axis=0)
                if (p[0] < lo[0] - reach or p[0] > hi[0] + reach or
                        p[1] < lo[1] - reach or p[1] > hi[1] + reach):
                    continue
                for span in _polygon(p, n, poly, window):
                    raw[layer].append((span, cid.get(net, 0)))
        key = []
        for layer, spans in raw.items():
            merged = _merge(spans)
            key += [(layer, round(float(a), 4), round(float(b), 4), int(c)) for a, b, c in merged]
        # A cut and its mirror image are the same line; share one solve.
        mirror = tuple(sorted((layer, -b, -a, c) for layer, a, b, c in key))
        return (window, min(tuple(sorted(key)), mirror))

    # -- routed paths ----------------------------------------------------
    def path(self, net, start, stop):
        """Shortest routed copper path between two (ref, pad) of one net.

        Returns segments on the path, oriented start to stop, as
        (a, b, width, layer); via hops (xy, from layer, to layer); the net's
        other segments (stubs); copper crossed inside pads; total length.
        """
        for end in (start, stop):
            if end not in self.pads or self.pads[end]['net'] != net:
                raise ValueError(f'{end}: pad missing or not on {net}')
        tracks = [t for t in self.tracks if t[4] == net]
        vias = [v for v in self.vias if v[2] == net]
        graph = {}

        def link(u, v, length, item):
            graph.setdefault(u, []).append((v, length, item))
            graph.setdefault(v, []).append((u, length, item))
        for index, (a, b, width, layer, _) in enumerate(tracks):
            link((layer, _key(a)), (layer, _key(b)), math.dist(a, b), ('track', index))
        nodes = list(graph)
        for index, (at, size, _) in enumerate(vias):
            hub = ('via', index)
            for layer, xy in nodes:
                if math.dist(xy, at) <= size / 2 + 1e-4:
                    link(hub, (layer, xy), 0.0, None)
            graph.setdefault(hub, [])
        for ref in self.pads:
            info = self.pads[ref]
            if info['net'] != net:
                continue
            for layer, xy in nodes:
                if layer in info['polys'] and any(
                        _inside(xy, poly) for poly in info['polys'][layer]):
                    link(('pad', ref), (layer, xy), math.dist(xy, info['at']), None)
        distance = {('pad', start): 0.0}
        previous = {}
        queue = [(0.0, ('pad', start))]
        while queue:
            length, node = heapq.heappop(queue)
            if node == ('pad', stop):
                break
            if length > distance[node]:
                continue
            for other, step, item in graph.get(node, []):
                proposed = length + step
                if proposed < distance.get(other, math.inf):
                    distance[other] = proposed
                    previous[other] = (node, item)
                    heapq.heappush(queue, (proposed, other))
        if ('pad', stop) not in distance:
            raise ValueError(f'{net}: {start} to {stop} is not connected by routed copper')
        chain, node = [], ('pad', stop)
        while node != ('pad', start):
            before, item = previous[node]
            chain.append((before, node, item))
            node = before
        chain.reverse()
        path, hops, used, pad_mm = [], [], set(), 0.0
        for before, after, item in chain:
            if item:
                a, b, width, layer, _ = tracks[item[1]]
                if before[1] != _key(a):
                    a, b = b, a
                path.append((a, b, width, layer))
                used.add(item[1])
            elif before[0] == 'pad' or after[0] == 'pad':
                pad_mm += distance[after] - distance[before]
        # A via hop is layer node -> via hub -> layer node.
        for index, (before, after, item) in enumerate(chain):
            if after[0] == 'via' and index + 1 < len(chain):
                hops.append((vias[after[1]][0], before[0], chain[index + 1][1][0]))
        stubs = [tracks[i][:4] for i in range(len(tracks)) if i not in used]
        return {'segments': path, 'vias': hops, 'stubs': stubs,
                'pad_mm': pad_mm, 'length_mm': distance[('pad', stop)]}

    def pad_polys(self, net):
        return [(layer, poly) for info in self.pads.values() if info['net'] == net
                for layer, polys in info['polys'].items() for poly in polys]


def _key(xy):
    return (round(xy[0], 4), round(xy[1], 4))


def _outlines(shape, pcbnew):
    out = []
    for i in range(shape.OutlineCount()):
        chain = shape.Outline(i)
        pts = np.array([(pcbnew.ToMM(chain.CPoint(k).x), pcbnew.ToMM(chain.CPoint(k).y))
                        for k in range(chain.PointCount())])
        if shape.HoleCount(i):
            raise ValueError('unfractured copper polygon with holes')
        if len(pts) >= 3:
            out.append(pts)
    return out


def _inside(xy, poly):
    x, y = xy
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _seg_dist(p, a, b):
    d = b - a
    t = np.clip(np.dot(p - a, d) / max(np.dot(d, d), 1e-18), 0, 1)
    return float(np.linalg.norm(p - (a + t * d)))


def _cross(u, v):
    return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]


def _polygon(p, n, poly, window):
    q = poly
    d = np.roll(poly, -1, axis=0) - q
    denom = _cross(n, d)
    ok = np.abs(denom) > 1e-15
    w = q - p
    s = np.where(ok, _cross(w, d) / np.where(ok, denom, 1), 0)
    u = np.where(ok, _cross(w, n) / np.where(ok, denom, 1), -1)
    hits = np.sort(s[ok & (u >= 0) & (u < 1)])
    spans = []
    for a, b in zip(hits[::2], hits[1::2]):
        a, b = max(a, -window), min(b, window)
        if b > a:
            spans.append((a, b))
    return spans


def _disk(p, n, c, r, window):
    t = float(np.dot(c - p, n))
    off = float(np.linalg.norm(c - p - t * n))
    if off >= r:
        return None
    h = math.sqrt(r * r - off * off)
    a, b = max(t - h, -window), min(t + h, window)
    return (a, b) if b > a else None


def _capsule(p, n, a, b, r, window):
    d = b - a
    length = float(np.linalg.norm(d))
    ortho = np.array((-d[1], d[0])) / length * r
    rect = np.array((a + ortho, b + ortho, b - ortho, a - ortho))
    parts = [s for s in _polygon(p, n, rect, window)]
    parts += [s for s in (_disk(p, n, a, r, window), _disk(p, n, b, r, window)) if s]
    if not parts:
        return None
    return (min(s[0] for s in parts), max(s[1] for s in parts))


def _merge(spans):
    """Union intervals per conductor id; different ids must not overlap."""
    out = []
    for (a, b), cid in sorted(spans):
        if out and a <= out[-1][1] + 1e-6:
            if out[-1][2] != cid:
                # A signal overlapping ground or the other signal is a short
                # in the copper data, not something to approximate.
                raise ValueError(f'conductors {out[-1][2]} and {cid} overlap in a cut')
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b, cid])
    return [tuple(x) for x in out]


def sample_path(board, route, nets, own):
    """Cut every STEP_MM along a path; own is 1 or 2 (which net the path is).

    Returns a list of samples: position along path, length represented,
    layer, cut key, and a class: 'trace', 'pad' (the cut meets a pad of the
    pair: breakout region) or 'via' (within a via pad of the path).
    """
    samples, travelled = [], 0.0
    vias = [hop[0] for hop in route['vias']]
    segments = route['segments']
    pair_pads = [(layer, poly) for net in nets for layer, poly in board.pad_polys(net)]
    for a, b, width, layer in segments:
        a, b = np.array(a), np.array(b)
        length = float(np.linalg.norm(b - a))
        count = max(1, round(length / STEP_MM))
        direction = (b - a) / length
        normal = np.array((-direction[1], direction[0]))
        for k in range(count):
            s = (k + .5) * length / count
            point = a + direction * s
            for window in WINDOWS:
                key = board.cut(tuple(point), tuple(normal), nets, window)
                if not any(c[3] > 0 and (c[1] <= -window + 1e-6 or c[2] >= window - 1e-6)
                           for c in key[1]):
                    break
            else:
                # Other signal copper runs along the cut (it crosses this
                # track's direction), so it is no parallel line here.  Holding
                # it at ground only adds capacitance: this track's impedance
                # stays a lower bound and its capacitance an upper bound.  The
                # sampled track itself must never reach the wall.
                spans = []
                for c in key[1]:
                    edge = c[1] <= -window + 1e-6 or c[2] >= window - 1e-6
                    if edge and c[3] == own and c[1] <= 1e-4 and c[2] >= -1e-4:
                        raise ValueError(f'sampled copper reaches the {window} mm cut window at {point}')
                    spans.append(c[:3] + (0,) if edge and c[3] > 0 else c)
                key = (window, tuple(sorted(spans)))
            here = [c for c in key[1] if c[0] == layer and c[3] == own and c[1] <= 1e-4 and c[2] >= -1e-4]
            if len(here) != 1:
                raise ValueError(f'sample at {point} does not lie on its own track')
            kind = 'trace'
            if any(math.dist(point, v) < .5 for v in vias):
                kind = 'via'
            elif any(pl == layer and _near_poly(point, poly, width / 2)
                     for pl, poly in pair_pads):
                kind = 'pad'
            samples.append({'s_mm': travelled + s, 'len_mm': length / count, 'layer': layer,
                            'xy': [round(float(point[0]), 4), round(float(point[1]), 4)],
                            'key': key, 'kind': kind})
        travelled += length
    return samples


def _near_poly(point, poly, margin):
    if _inside(point, poly):
        return True
    return min(_seg_dist(np.array(point), a, b)
               for a, b in zip(poly, np.roll(poly, -1, axis=0))) <= margin


def ohms(value):
    """KiCad resistor value text to ohms: 27R, 27, 270, 4R7, 1k5, 360."""
    text = value.strip().upper().replace('Ω', '').replace('OHM', '')
    for mark, scale in (('R', 1), ('K', 1e3), ('M', 1e6)):
        if mark in text:
            whole, _, frac = text.partition(mark)
            return float((whole or '0') + '.' + (frac or '0')) * scale
    return float(text)


def via_barrel_mm(route):
    """Barrel length of each via hop between the two copper layers used."""
    mid = {layer: sum(span) / 2 for layer, span in LAYERS.items()}
    return sum(abs(mid[a] - mid[b]) for _, a, b in route['vias'])


def se_bounds(result, which):
    """Single-ended (lower, upper) impedance of signal `which` (0 P, 1 N).

    For a coupled cut this is the line with its partner held at ground,
    which is still a lower bound on its own quasi-TEM impedance."""
    if result['kind'] == 'z_se':
        return result['z_lower'], result['z_upper']
    z = result['z_se_pair'][which]
    return z, z * result['z_upper'] / result['z_lower']


def diff_profile(samples, partner, results, own):
    """Differential (lower, upper, coupled) along one net's samples.

    Where the cut meets both conductors the coupled solution is used.  Where
    it meets only its own line, the pair is uncoupled there and its
    differential impedance is the sum of both single-ended impedances, the
    partner taken at the same fraction of its own routed length."""
    total = sum(s['len_mm'] for s in samples)
    other_total = sum(s['len_mm'] for s in partner)
    out = []
    for sample in samples:
        result = results[sample['key']]
        if result['kind'] == 'z_diff':
            out.append((result['z_lower'], result['z_upper'], True))
            continue
        fraction = sample['s_mm'] / total
        mate = min(partner, key=lambda s: abs(s['s_mm'] / other_total - fraction))
        mine = se_bounds(result, own - 1)
        theirs = se_bounds(results[mate['key']], 2 - own)
        out.append((mine[0] + theirs[0], mine[1] + theirs[1], False))
    return out


def path_delay(samples, results, route):
    """One-way delay (s) of a routed path: quasi-TEM delay per sample, plus
    via barrels and pad copper at the largest dielectric constant."""
    t = sum(s['len_mm'] * 1e-3 * results[s['key']]['delay_s_per_m'] for s in samples)
    extra = via_barrel_mm(route) + route['pad_mm']
    return t + extra * 1e-3 * math.sqrt(ER_MAX) / xsection.C_LIGHT
