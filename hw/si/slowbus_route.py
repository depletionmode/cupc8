#!/usr/bin/env python3
"""Routed-copper extraction and lossy RLGC ladder emission for slow buses.

`extract(board, net)` turns one net's KiCad tracks, vias and pads into an
electrical graph: track pieces (split at every junction), via and plated-pad
barrels between adjacent copper layers (their unused layers stay as stubs),
and ideal pad joins. `Ladder` turns the graph into ngspice lumped RLGC
sections. Lumped sections are used instead of ideal `T` lines on purpose: the
earlier deck's sub-picosecond `T` elements collapsed ngspice's timestep. A
section is at most `section_mm` long; `slowbus_si` re-runs every case with
half the section length and requires the waveforms to agree.

Line constants come from closed-form formulas over the stackup JLCPCB
publishes for the ordered stack (hw/tools/kicadgen.py order_spec), for the
reference planes the board actually pours (checked on the board). Copper is
lossy at its DC resistance only; skin-effect and dielectric loss would only
damp ringing, so omitting them is the conservative choice for overshoot.
"""
import math
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import find1, parse  # noqa: E402

RHO_CU_OHM_MM = 1.72e-5
C_MM_PER_PS = 0.299792458

# JLCPCB impedance-controlled stack-ups (https://jlcpcb.com/impedance), the
# ones kicadgen.order_spec names for 4 and 6 layers. (name, thickness mm, Dk)
STACKUPS = {
    'JLC04161H-7628': [
        ('F.Cu', .035, None), ('prepreg 7628', .2104, 4.4), ('In1.Cu', .0152, None),
        ('core', 1.065, 4.6), ('In2.Cu', .0152, None), ('prepreg 7628', .2104, 4.4),
        ('B.Cu', .035, None)],
    # 6 layers: 3313 prepreg Dk 4.1, 2116 prepreg Dk 4.16, core Dk 4.6. The
    # same page gives the middle 2116 as 0.1164 mm in its generic 6-layer
    # stack; the named JLC06161H-3313's 0.1088 mm is used (it sets only
    # In2/In3's spacing, far from their In1/In4 references).
    'JLC06161H-3313': [
        ('F.Cu', .035, None), ('prepreg 3313', .0994, 4.1), ('In1.Cu', .0152, None),
        ('core', .55, 4.6), ('In2.Cu', .0152, None), ('prepreg 2116', .1088, 4.16),
        ('In3.Cu', .0152, None), ('core', .55, 4.6), ('In4.Cu', .0152, None),
        ('prepreg 3313', .0994, 4.1), ('B.Cu', .035, None)],
    # JLC's 2-layer 1.6 mm FR-4 (Dk 4.5 assumed; wifi card only)
    'JLC-2L-1.6': [('F.Cu', .035, None), ('core FR-4', 1.53, 4.5), ('B.Cu', .035, None)],
}

BOARDS = {
    'main': ('JLC06161H-3313', {'In1.Cu': '/GND', 'In4.Cu': '/+3V3'}),
    'cpu': ('JLC06161H-3313', {'In1.Cu': '/GND', 'In4.Cu': '/3V3'}),
    'storage': ('JLC04161H-7628', {'In1.Cu': '/GND'}),
    'eink': ('JLC04161H-7628', {'In1.Cu': '/GND'}),
    'gpu': ('JLC04161H-7628', {'In1.Cu': '/GND'}),
    'io': ('JLC04161H-7628', {'In1.Cu': '/GND'}),
    'wifi': ('JLC-2L-1.6', {'B.Cu': '/GND'}),
}


# ------------------------------------------------------------ line constants
def _z_microstrip(w, h, t, er):
    """Hammerstad-Jensen microstrip with Wheeler's thickness correction.

    Returns (Z0 ohm, effective Dk)."""
    u = w / h
    if t > 0:
        dw1 = t / math.pi * math.log(1 + 4 * math.e / (t / h / math.tanh(math.sqrt(6.517 * u)) ** 2))
        dwr = .5 * (1 + 1 / math.cosh(math.sqrt(max(er - 1, 0)))) * dw1
    else:
        dw1 = dwr = 0.0
    u1, ur = (w + dw1) / h, (w + dwr) / h

    def z01(x):
        f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / x) ** .7528)
        return 60 * math.log(f / x + math.sqrt(1 + 4 / x ** 2))

    def ee(x):
        a = 1 + math.log((x ** 4 + (x / 52) ** 2) / (x ** 4 + .432)) / 49 + \
            math.log(1 + (x / 18.1) ** 3) / 18.7
        b = .564 * ((er - .9) / (er + 3)) ** .053
        return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / x) ** (-a * b)

    e_r = ee(ur)
    z0 = z01(ur) / math.sqrt(e_r)
    e_eff = e_r * (z01(u1) / z01(ur)) ** 2
    return z0, e_eff


def _z_stripline_sym(w, b, t, er):
    """IPC-2141A symmetric stripline, plane spacing b."""
    return 60 / math.sqrt(er) * math.log(4 * b / (.67 * math.pi * (.8 * w + t)))


def line_constants(stackup, planes, layer, width):
    """(Z0 ohm, delay ps/mm, R ohm/mm, geometry note) for a track."""
    layers = STACKUPS[stackup]
    z, pos, spans = 0.0, {}, []
    for name, thick, dk in layers:
        if dk is None:
            pos[name] = (z, z + thick, dk)
        spans.append((z, z + thick, dk))
        z += thick
    if layer not in pos:
        raise ValueError(f'{stackup}: no layer {layer}')
    top, bottom, _ = pos[layer]
    t = bottom - top

    def dielectric(z0, z1):
        span = [(max(a, z0), min(b, z1), dk) for a, b, dk in spans
                if dk is not None and min(b, z1) > max(a, z0)]
        thick = sum(b - a for a, b, _ in span)
        return thick, sum((b - a) * dk for a, b, dk in span) / thick

    above = [pos[p][1] for p in planes if pos[p][1] <= top]
    below = [pos[p][0] for p in planes if pos[p][0] >= bottom]
    ref_above = max(above) if above else None
    ref_below = min(below) if below else None
    r = RHO_CU_OHM_MM / (width * t)
    outer = layer in ('F.Cu', 'B.Cu')
    if ref_above is not None and ref_below is not None:
        a, er_a = dielectric(ref_above, top)
        b, er_b = dielectric(bottom, ref_below)
        er = (a * er_a + b * er_b) / (a + b)
        z1 = _z_stripline_sym(width, 2 * a + t, t, er)
        z2 = _z_stripline_sym(width, 2 * b + t, t, er)
        z0 = 2 * z1 * z2 / (z1 + z2)
        return z0, math.sqrt(er) / C_MM_PER_PS, r, f'offset stripline a={a:.4f} b={b:.4f} Dk={er:.3f}'
    if ref_above is None and ref_below is None:
        raise ValueError(f'{layer}: no reference plane in {stackup}')
    if ref_below is not None:
        h, er = dielectric(bottom, ref_below)
        cover = dielectric(0, top)[0] if not outer else 0.0
    else:
        h, er = dielectric(ref_above, top)
        cover = dielectric(bottom, z)[0] if not outer else 0.0
    if outer:
        z0, e_eff = _z_microstrip(width, h, t, er)
        return z0, math.sqrt(e_eff) / C_MM_PER_PS, r, f'microstrip h={h:.4f} Dk={er:.3f}'
    # buried microstrip (Wadell 3.5.3): Dk' = Dk(1 - exp(-1.55 (h+cover)/h))
    z_air, _ = _z_microstrip(width, h, t, 1.0)
    e_eff = er * (1 - math.exp(-1.55 * (h + t + cover) / h))
    return z_air / math.sqrt(e_eff), math.sqrt(e_eff) / C_MM_PER_PS, r, \
        f'embedded microstrip h={h:.4f} cover={cover:.4f} Dk={er:.3f}'


def via_constants(stackup, drill, pad, antipad, span_mm):
    """Johnson & Graham via barrel L and pad C (High-Speed Digital Design 7.4)."""
    total = sum(t for _, t, _ in STACKUPS[stackup])
    dk = [d for _, _, d in STACKUPS[stackup] if d]
    er = sum(dk) / len(dk)
    inch = 25.4
    h, d = span_mm / inch, drill / inch
    l_nh = 5.08 * h * (math.log(4 * h / d) + 1) if span_mm > 0 else 0.0
    c_pf = 1.41 * er * (total / inch) * (pad / inch) / ((antipad - pad) / inch)
    return l_nh, c_pf


# ------------------------------------------------------------ cross-sections
XSEC_CACHE = ROOT / 'build/si-slowbus/cache/xsec.json'
_XSEC = {}
GAP_STEP, GAP_MAX = .05, 1.5
AIR = 3.0


def _solver_id():
    import hashlib
    here = Path(__file__).resolve().parent
    return hashlib.sha256((here / 'slowbus_field.py').read_bytes() +
                          repr(STACKUPS).encode()).hexdigest()


def load_xsec_cache():
    """Cached field solutions, valid only for the same solver and stack-ups."""
    import json
    if XSEC_CACHE.is_file() and not _XSEC:
        data = json.loads(XSEC_CACHE.read_text())
        if data.get('solver') == _solver_id():
            _XSEC.update({k: tuple(v) for k, v in data['entries'].items()})


def save_xsec_cache():
    import json
    XSEC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = XSEC_CACHE.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps({'solver': _solver_id(), 'entries': _XSEC}, sort_keys=True))
    tmp.replace(XSEC_CACHE)


@lru_cache(maxsize=16)
def _fills(path, kind):
    """Filled copper of the board's plane nets (GND and the power planes)."""
    import numpy as np
    from matplotlib.path import Path as MPath
    _, tree = _board(path)
    nets = {'/GND'} | set(BOARDS[kind][1].values())
    out = {}
    for item in tree[1:]:
        if not (isinstance(item, list) and item and item[0] == 'zone'):
            continue
        net = find1(item, 'net')
        if not net or net[1] not in nets:
            continue
        for poly in item[1:]:
            if isinstance(poly, list) and poly and poly[0] == 'filled_polygon':
                layer = find1(poly, 'layer')[1]
                pts = [(float(v[1]), float(v[2])) for v in find1(poly, 'pts')[1:]
                       if isinstance(v, list) and v[0] == 'xy']
                if len(pts) >= 3:
                    out.setdefault(layer, []).append(MPath(np.array(pts)))
    return out


def _covered(paths, points):
    import numpy as np
    inside = np.zeros(len(points), bool)
    for path in paths:
        inside |= path.contains_points(points)
    return inside


def cross_section(board_path, kind, layer, width, p, q):
    """Key of the local cross-section of a track piece from p to q (1e-4 mm).

    A copper layer is a reference for the piece if plane-net fill covers the
    piece's projection there (at 1/4, 1/2 and 3/4 of its length); same-layer
    fill within 1.5 mm is coplanar ground, with the largest sampled gap."""
    import numpy as np
    stackup, _ = BOARDS[kind]
    fills = _fills(str(Path(board_path).resolve()), kind)
    a, b = np.array(p, float) / 1e4, np.array(q, float) / 1e4
    d = b - a
    n = np.array([-d[1], d[0]]) / max(np.hypot(*d), 1e-12)
    samples = np.array([a + f * d for f in (.25, .5, .75)])
    refs = [other for other in board_layers(stackup) if other != layer and
            other in fills and _covered(fills[other], samples).sum() >= 2]
    gaps = []
    for side in (1, -1):
        first = []
        steps = np.arange(GAP_STEP, GAP_MAX + 1e-9, GAP_STEP)
        for s in samples:
            pts = s + np.outer(width / 2 + steps, n * side)
            hit = _covered(fills.get(layer, []), pts)
            first.append(steps[np.argmax(hit)] if hit.any() else None)
        gaps.append('none' if any(g is None for g in first) else f'{max(first):.2f}')
    if not refs and gaps == ['none', 'none']:
        # over a plane clearance (antipad, pad keep-out): the nearest return
        # is the declared plane; the length is reported as unreferenced
        refs = ['void'] + [l for l in BOARDS[kind][1] if l != layer]
    return f'{stackup}|{layer}|{width:.4f}|{",".join(refs)}|{gaps[0]}|{gaps[1]}'


def _geometry(key):
    """Field-solver slabs and conductors for a cross-section key."""
    stackup, layer, width, refs, g1, g2 = key.split('|')
    width = float(width)
    refs = [r for r in refs.split(',') if r and r != 'void']
    stack = STACKUPS[stackup]
    total = sum(t for _, t, _ in stack)
    z, zr, slabs = total, {}, []
    for index, (name, thick, dk) in enumerate(stack):
        z0, z1 = z - thick, z
        if dk is None:
            zr[name] = (z0, z1)
            if 0 < index < len(stack) - 1:
                # resin of the neighbouring prepreg fills an inner copper layer
                slabs.append((z0, z1, max(stack[index - 1][2], stack[index + 1][2])))
        else:
            slabs.append((z0, z1, dk))
        z = z0
    if not refs and g1 == 'none' and g2 == 'none':
        raise ValueError(f'{key}: no reference plane or coplanar ground')
    reach = max([abs(sum(zr[r]) / 2 - sum(zr[layer]) / 2) for r in refs] + [.5])
    box = max(3.0, 8 * reach)
    conductors = [(-width / 2, width / 2, *zr[layer], 0)]
    conductors += [(-box, box, *zr[r], -1) for r in refs]
    if g1 != 'none':
        conductors.append((width / 2 + float(g1), box, *zr[layer], -1))
    if g2 != 'none':
        conductors.append((-box, -width / 2 - float(g2), *zr[layer], -1))
    return slabs, conductors, box, zr, width


def xsec_constants(key):
    """(Z0 ohm, delay ps/mm, R ohm/mm, note) for a cross-section key."""
    if not _XSEC:
        load_xsec_cache()
    if key not in _XSEC:
        from slowbus_field import line
        slabs, conductors, box, zr, width = _geometry(key)
        z0, td = line(slabs, conductors, box, AIR, bottom_air=AIR)
        layer = key.split('|')[1]
        t = zr[layer][1] - zr[layer][0]
        _XSEC[key] = (z0, td * 1e9, RHO_CU_OHM_MM / (width * t), 'field solver ' + key)
    return _XSEC[key]


# ----------------------------------------------------------------- extraction
@dataclass
class Graph:
    board: str
    net: str
    stackup: str
    planes: dict
    tracks: list = field(default_factory=list)   # (a, b, layer, width, length)
    barrels: list = field(default_factory=list)  # (a, b, dz_mm, drill, pad)
    pads: dict = field(default_factory=dict)     # 'REF.PIN' -> node
    vias: int = 0
    xsec: dict = field(default_factory=dict)     # cross-section key -> constants


class _Union:
    def __init__(self):
        self.parent = {}

    def root(self, n):
        self.parent.setdefault(n, n)
        while self.parent[n] != n:
            self.parent[n] = self.parent[self.parent[n]]
            n = self.parent[n]
        return n

    def join(self, a, b):
        ra, rb = self.root(a), self.root(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


@lru_cache(maxsize=16)
def _board(path):
    import pcbnew
    return pcbnew.LoadBoard(path), parse(Path(path).read_text())


def board_layers(stackup):
    return [name for name, _, dk in STACKUPS[stackup] if dk is None]


def layer_z(stackup):
    z, out = 0.0, {}
    for name, thick, dk in STACKUPS[stackup]:
        if dk is None:
            out[name] = z + thick / 2
        z += thick
    return out


def check_planes(board_path, kind):
    """The reference planes assumed for the line constants must be poured."""
    stackup, planes = BOARDS[kind]
    _, tree = _board(str(Path(board_path).resolve()))
    poured = set()
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == 'zone':
            net, layer = find1(item, 'net'), find1(item, 'layer')
            if net and layer:
                poured.add((layer[1], net[1]))
    missing = [f'{net} on {layer}' for layer, net in planes.items() if (layer, net) not in poured]
    if missing:
        raise ValueError(f'{kind}: reference plane(s) not poured: {missing}')
    layers = board_layers(stackup)
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == 'layers':
            copper = [e[1] for e in item[1:] if isinstance(e, list) and len(e) > 1
                      and str(e[1]).endswith('.Cu')]
            if copper != layers:
                raise ValueError(f'{kind}: board copper {copper} differs from {stackup} {layers}')
    return True


def extract(board_path, kind, net, pins):
    """Electrical graph of `net`; `pins` ('REF.PIN') must all be reached."""
    import pcbnew
    board_path = str(Path(board_path).resolve())
    board, tree = _board(board_path)
    stackup, planes = BOARDS[kind]
    layers = board_layers(stackup)
    order = {name: i for i, name in enumerate(layers)}
    zc = layer_z(stackup)
    graph = Graph(board_path, net, stackup, planes)
    uf = _Union()
    raw, via_items = [], []
    for item in tree[1:]:
        if not isinstance(item, list) or not item or item[0] not in ('segment', 'via', 'arc'):
            continue
        n = find1(item, 'net')
        if n is None or n[1] != net:
            continue
        if item[0] == 'arc':
            raise ValueError(f'{net}: arc track needs an exact length model')
        if item[0] == 'segment':
            a = tuple(round(float(v) * 1e4) for v in find1(item, 'start')[1:])
            b = tuple(round(float(v) * 1e4) for v in find1(item, 'end')[1:])
            layer = find1(item, 'layer')[1]
            if layer not in order:
                raise ValueError(f'{net}: track on {layer}')
            raw.append((a, b, layer, float(find1(item, 'width')[1])))
        else:
            at = tuple(round(float(v) * 1e4) for v in find1(item, 'at')[1:3])
            span = find1(item, 'layers')[1:]
            lo, hi = sorted(order[x] for x in span)
            if span == ['F.Cu', 'B.Cu']:
                lo, hi = 0, len(layers) - 1
            via_items.append((at, layers[lo:hi + 1], float(find1(item, 'drill')[1]),
                              float(find1(item, 'size')[1])))
    if not raw:
        raise ValueError(f'{net}: no routed tracks')
    graph.vias = len(via_items)
    anchors = {layer: set() for layer in layers}   # points that split tracks
    barrels = []
    for at, span, drill, size in via_items:
        for layer in span:
            anchors[layer].add(at)
        for x, y in zip(span, span[1:]):
            barrels.append(((at, x), (at, y), abs(zc[y] - zc[x]), drill, size))
    pad_nodes, pad_shapes = {}, []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        front = fp.GetLayerName() == 'F.Cu'
        for pad in fp.Pads():
            if pad.GetNetname() != net:
                continue
            p = pad.GetPosition()
            at = (round(pcbnew.ToMM(p.x) * 1e4), round(pcbnew.ToMM(p.y) * 1e4))
            on = [x for x in layers if pad.IsOnLayer(getattr(pcbnew, x.replace('.', '_')))]
            drill = pcbnew.ToMM(pad.GetDrillSize().x)
            if drill > 0:
                on = layers                       # plated barrel through the stack
                for x, y in zip(on, on[1:]):
                    barrels.append(((at, x), (at, y), abs(zc[y] - zc[x]), drill,
                                    pcbnew.ToMM(pad.GetSize().x)))
            for layer in on:
                anchors[layer].add(at)
                pad_shapes.append((pad, layer, at))
            attach = on[0] if front else on[-1]
            if drill <= 0 and len(on) != 1:
                raise ValueError(f'{ref}.{pad.GetNumber()}: SMD pad on {on}')
            pad_nodes[f'{ref}.{pad.GetNumber()}'] = (at, attach)
    for a, b, layer, _ in raw:
        anchors[layer].update((a, b))
    # join track ends that land inside a pad but off its centre, and ends that
    # land on a via's annular ring
    for a, b, layer, _ in raw:
        for end in (a, b):
            for pad, player, at in pad_shapes:
                if player == layer and end != at and pad.HitTest(
                        pcbnew.VECTOR2I(int(end[0] * 100), int(end[1] * 100)), 0):
                    uf.join((end, layer), (at, layer))
            for at, span, _, size in via_items:
                if layer in span and end != at and math.dist(end, at) <= size * 1e4 / 2:
                    uf.join((end, layer), (at, layer))
    for a, b, layer, width in raw:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        if length2 == 0:
            continue
        hits = []
        for q in anchors[layer]:
            t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / length2
            if -1e-9 <= t <= 1 + 1e-9:
                cross = abs((q[0] - a[0]) * dy - (q[1] - a[1]) * dx) / math.sqrt(length2)
                if cross <= 1.0:                  # 0.1 um
                    hits.append((t, q))
        hits.sort()
        for (_, p), (_, q) in zip(hits, hits[1:]):
            length = math.dist(p, q) / 1e4
            if length > 0:
                graph.tracks.append([(p, layer), (q, layer), layer, width, length])
    graph.barrels = barrels
    for piece in graph.tracks:
        key = cross_section(board_path, kind, piece[2], piece[3], piece[0][0], piece[1][0])
        piece.append(key)
        if key not in graph.xsec:
            graph.xsec[key] = xsec_constants(key)
    # contract ideal joins into canonical nodes
    for piece in graph.tracks:
        piece[0], piece[1] = uf.root(piece[0]), uf.root(piece[1])
    graph.barrels = [(uf.root(a), uf.root(b), dz, d, s) for a, b, dz, d, s in barrels]
    graph.pads = {name: uf.root(node) for name, node in pad_nodes.items()}
    missing = [p for p in pins if p not in graph.pads]
    if missing:
        raise ValueError(f'{net}: pads {missing} not on this net')
    # connectivity from the first pin
    adj = {}
    for a, b, *_ in graph.tracks:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    for a, b, *_ in graph.barrels:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    seen, stack = set(), [graph.pads[pins[0]]]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, ()))
    opened = [p for p in pins if graph.pads[p] not in seen]
    if opened:
        raise ValueError(f'{net}: copper open from {pins[0]} to {opened}')
    # keep only the component reached from the pins (drop unrelated islands)
    graph.tracks = [t for t in graph.tracks if t[0] in seen]
    graph.barrels = [b for b in graph.barrels if b[0] in seen]
    return graph


def summary(graph):
    return {'net': graph.net, 'tracks': len(graph.tracks), 'vias': graph.vias,
            'copper_mm': round(sum(t[4] for t in graph.tracks), 3),
            'unreferenced_mm': round(sum(t[4] for t in graph.tracks
                                         if len(t) > 5 and '|void' in t[5]), 3),
            'z0_range_ohm': [round(min(graph.xsec[t[5]][0] for t in graph.tracks), 1),
                             round(max(graph.xsec[t[5]][0] for t in graph.tracks), 1)]
            if graph.xsec else None,
            'layers_mm': {layer: round(sum(t[4] for t in graph.tracks if t[2] == layer), 3)
                          for layer in sorted({t[2] for t in graph.tracks})}}


# ------------------------------------------------------------------ emission
class Ladder:
    """Emit one graph as ngspice lumped RLGC sections under a node prefix."""

    def __init__(self, graph, prefix, section_mm=2.0, zscale=1.0, antipad_clear_mm=.3):
        self.graph, self.prefix = graph, prefix
        self.section_mm, self.zscale = section_mm, zscale
        self.antipad = antipad_clear_mm
        self.lines, self.names, self.count = [], {}, 0
        self.constants = {}

    def node(self, n):
        if n not in self.names:
            self.names[n] = f'{self.prefix}n{len(self.names)}'
        return self.names[n]

    def _next(self):
        self.count += 1
        return f'{self.prefix}{self.count}'

    def emit(self):
        g = self.graph
        # collapse chains of same-layer, same-width pieces through degree-2 nodes
        degree = {}
        for a, b, *_ in g.tracks:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        for a, b, *_ in g.barrels:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        keep = set(g.pads.values()) | {n for n, d in degree.items() if d != 2}
        keep |= {a for a, b, *_ in g.barrels} | {b for a, b, *_ in g.barrels}
        by_node = {}
        for index, (a, b, layer, width, length, *_) in enumerate(g.tracks):
            by_node.setdefault(a, []).append(index)
            by_node.setdefault(b, []).append(index)

        def piece_key(index):
            piece = g.tracks[index]
            return piece[5] if len(piece) > 5 else (piece[2], piece[3])
        # a change of cross-section is a run boundary
        keep |= {n for n, pieces in by_node.items()
                 if len(pieces) == 2 and piece_key(pieces[0]) != piece_key(pieces[1])}
        used = set()
        runs = []
        for start in sorted(keep | {n for n in by_node if len(by_node[n]) != 2}):
            for index in by_node.get(start, []):
                if index in used:
                    continue
                used.add(index)
                a, b, layer, width, length, *rest = g.tracks[index]
                key = rest[0] if rest else (layer, width)
                here = b if a == start else a
                total = length
                while here not in keep and len(by_node.get(here, [])) == 2:
                    nxt = [i for i in by_node[here] if i not in used]
                    if not nxt:
                        break
                    j = nxt[0]
                    ja, jb, jl, jw, jlen, *jrest = g.tracks[j]
                    if (jrest[0] if jrest else (jl, jw)) != key:
                        keep.add(here)
                        break
                    used.add(j)
                    total += jlen
                    here = jb if ja == here else ja
                runs.append((start, here, layer, width, total, key))
        # a loop left over (no anchor) would be skipped: fail closed
        if len(used) != len(g.tracks):
            raise ValueError(f'{g.net}: {len(g.tracks) - len(used)} track pieces not emitted')
        for a, b, layer, width, length, key in runs:
            if key not in self.constants:
                self.constants[key] = (g.xsec[key] if key in g.xsec else
                                       line_constants(g.stackup, g.planes, layer, width))
            z0, ps_mm, r_mm, _ = self.constants[key]
            z0 *= self.zscale
            if length < .005:
                self.lines.append(f'R{self._next()} {self.node(a)} {self.node(b)} 1e-4')
                continue
            sections = max(1, math.ceil(length / self.section_mm))
            step = length / sections
            l_h = z0 * ps_mm * 1e-12 * step
            c_f = ps_mm * 1e-12 / z0 * step
            r = r_mm * step
            prev = self.node(a)
            for k in range(sections):
                last = k == sections - 1
                nxt = self.node(b) if last else f'{self.prefix}s{self.count}_{k}'
                mid = f'{self.prefix}m{self.count}_{k}'
                name = self._next()
                self.lines += [f'C{name}a {prev} 0 {c_f / 2:.6g}',
                               f'R{name} {prev} {mid} {r:.6g}',
                               f'L{name} {mid} {nxt} {l_h:.6g}',
                               f'C{name}b {nxt} 0 {c_f / 2:.6g}']
                prev = nxt
        for a, b, dz, drill, size in g.barrels:
            l_nh, c_pf = via_constants(g.stackup, drill, size, size + 2 * self.antipad, dz)
            layers = len(board_layers(g.stackup))
            name = self._next()
            mid = f'{self.prefix}v{self.count}'
            self.lines += [f'L{name} {self.node(a)} {mid} {max(l_nh, 1e-4) * 1e-9:.6g}',
                           f'R{name} {mid} {self.node(b)} 1e-4',
                           f'C{name} {self.node(b)} 0 {c_pf / layers * 1e-12:.6g}']
        return self.lines

    def pad(self, name):
        return self.node(self.graph.pads[name])


# ------------------------------------------------------------------ coupling
@lru_cache(maxsize=16)
def _all_segments(path):
    import numpy as np
    _, tree = _board(path)
    rows = []
    for item in tree[1:]:
        if isinstance(item, list) and item and item[0] == 'segment':
            net = find1(item, 'net')
            rows.append((net[1] if net else '', find1(item, 'layer')[1],
                         *(float(v) for v in find1(item, 'start')[1:3]),
                         *(float(v) for v in find1(item, 'end')[1:3]),
                         float(find1(item, 'width')[1])))
    nets = np.array([r[0] for r in rows])
    layers = np.array([r[1] for r in rows])
    xy = np.array([r[2:6] for r in rows], dtype=float)
    widths = np.array([r[6] for r in rows], dtype=float)
    return nets, layers, xy, widths


def plane_height(stackup, planes, layer):
    """Distance from a signal layer's centre to its nearest declared plane."""
    z = layer_z(stackup)
    return min(abs(z[layer] - z[p]) for p in planes if p != layer)


def coupling_constants(victim_key, layer_a, width_a, dx):
    """(Kb, Kf, delay ps/mm) of an aggressor at lateral offset dx (mm) on
    layer_a, over the victim's reference planes (its coplanar pour is left
    out, which can only increase the coupling)."""
    key = f'{victim_key}|{layer_a}|{width_a:.4f}|{dx:.2f}'
    if not _XSEC:
        load_xsec_cache()
    if key not in _XSEC:
        from slowbus_field import coupled
        slabs, conductors, box, zr, width = _geometry(victim_key)
        conductors = [c for c in conductors if not (c[4] == -1 and c[2:4] == zr[victim_key.split('|')[1]])]
        conductors.append((dx - width_a / 2, dx + width_a / 2, *zr[layer_a], 1))
        box = max(box, abs(dx) + 3)
        _, td, kb, kf = coupled(slabs, conductors, box, AIR, bottom_air=AIR)
        _XSEC[key] = (kb, kf, td * 1e9)
    return _XSEC[key]


def coupling_bound(graph, kind, quiet_nets, t_rise, swing, reach=6.0):
    """Crosstalk on one extracted victim net from every parallel neighbour.

    Pairs of near-parallel pieces on the same layer or on facing signal
    layers (no plane between) within `reach` x the victim's plane height are
    field-solved as coupled lines. Per aggressor: NEXT = Kb, scaled by
    min(1, 2 Tc/tr) for a coupled delay Tc and capped at the largest
    saturated Kb; FEXT = |Kf| Tc/tr. All aggressors switch together."""
    import numpy as np
    stackup, planes = BOARDS[kind]
    nets, layers, xy, widths = _all_segments(graph.board)
    order = board_layers(stackup)
    zc = layer_z(stackup)
    per = {}
    for a, b, layer, width, length, key in graph.tracks:
        if length < .2:
            continue
        refs = [r for r in key.split('|')[3].split(',') if r and r != 'void']
        h = min([abs(zc[r] - zc[layer]) for r in refs] or [plane_height(stackup, planes, layer)])
        near = {layer}
        for step in (-1, 1):
            j = order.index(layer) + step
            if 0 <= j < len(order) and order[j] not in refs:
                near.add(order[j])
        mask = np.isin(layers, list(near)) & (nets != graph.net) & ~np.isin(nets, list(quiet_nets))
        if not mask.any():
            continue
        ax, ay = a[0][0] / 1e4, a[0][1] / 1e4
        bx, by = b[0][0] / 1e4, b[0][1] / 1e4
        ux, uy = (bx - ax) / length, (by - ay) / length
        cand = xy[mask]
        dx_, dy_ = cand[:, 2] - cand[:, 0], cand[:, 3] - cand[:, 1]
        clen = np.hypot(dx_, dy_)
        ok = clen > 1e-6
        sin = np.abs(ux * dy_ - uy * dx_) / np.where(ok, clen, 1)
        s1 = (cand[:, 0] - ax) * ux + (cand[:, 1] - ay) * uy
        s2 = (cand[:, 2] - ax) * ux + (cand[:, 3] - ay) * uy
        d1 = -(cand[:, 0] - ax) * uy + (cand[:, 1] - ay) * ux
        d2 = -(cand[:, 2] - ax) * uy + (cand[:, 3] - ay) * ux
        overlap = np.minimum(np.maximum(s1, s2), length) - np.maximum(np.minimum(s1, s2), 0)
        lateral = (d1 + d2) / 2
        dz = np.array([abs(zc[l] - zc[layer]) for l in layers[mask]])
        hit = ok & (sin < .1) & (overlap > .2) & (np.hypot(lateral, dz) < reach * h)
        for net, olen, lat, la, wa in zip(nets[mask][hit], overlap[hit], lateral[hit],
                                          layers[mask][hit], widths[mask][hit]):
            dxq = round(abs(lat) / .05) * .05
            if la == layer and dxq < (width + wa) / 2 + .05:
                dxq = round(((width + wa) / 2 + .05) / .05) * .05
            kb, kf, ps_mm = coupling_constants(key, la, wa, dxq)
            tc = olen * ps_mm * 1e-12
            e = per.setdefault(str(net), {'next_sum': 0.0, 'next_max': 0.0, 'fext': 0.0,
                                          'coupled_mm': 0.0, 'min_gap_mm': 1e9})
            e['next_sum'] += kb * min(1.0, 2 * tc / t_rise)
            e['next_max'] = max(e['next_max'], kb)
            e['fext'] += abs(kf) * tc / t_rise
            e['coupled_mm'] += olen
            e['min_gap_mm'] = min(e['min_gap_mm'], float(np.hypot(dxq, abs(zc[la] - zc[layer]))))
    out, total = {}, 0.0
    for net, e in per.items():
        v = swing * (min(e['next_sum'], e['next_max']) + e['fext'])
        total += v
        out[net] = {'noise_v': round(float(v), 4), 'coupled_mm': round(float(e['coupled_mm']), 3),
                    'min_centre_distance_mm': round(e['min_gap_mm'], 3)}
    worst = dict(sorted(out.items(), key=lambda kv: -kv[1]['noise_v'])[:5])
    return round(float(total), 4), worst
