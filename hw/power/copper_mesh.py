#!/usr/bin/env python3
"""DC resistance and current density of one net's routed copper, all layers.

Each copper layer inside a window is rasterized on a square grid: zone fills,
tracks and pads of the net, each cell copper or not. Adjacent copper cells on
a layer are joined by one sheet resistance (rho / thickness, whatever the
pitch); every via and plated pad hole joins the cells it lands on through its
barrel (half a full-thickness barrel from each layer to a hub, as copper.py:
a two-layer transfer costs one whole barrel). Terminal pads are ideal
equipotentials, the usual solder-covered-pad assumption; the solder and the
component terminations are allowances outside this model.

The fabrication corner is conservative on every term it models: tracks at
80 % of their drawn width (JLC +-20 %), zone fills eroded by one cell per
edge, finished copper and via plating at the caller's minima, copper
resistivity at the caller's temperature. Copper outside the window or in a
layer's other islands is simply absent, which can only raise the resistance
(Rayleigh: removing a conductor never lowers a network's resistance).

    solve(board, net, sources, sinks, window, pitch, corner) -> Result
"""

from dataclasses import dataclass
import math
import os
import time

from polygon_raster import grid_poly

import numpy as np
from matplotlib.path import Path
import pcbnew

RHO_20C = 17e-6              # ohm mm (TI SLYW038D, copper.py)
ALPHA = 0.00393
K_COPPER = 0.39              # W / (mm K)
LAYERS = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)
OUTER = (pcbnew.F_Cu, pcbnew.B_Cu)


@dataclass(frozen=True)
class Corner:
    """The fabrication and temperature corner of an extraction."""
    temperature_c: float = 115.0
    outer_mm: float = 0.0249        # 1 oz finished, 80 % of 34.8 um less plating spread
    inner_mm: float = 0.0114        # 0.5 oz finished minimum
    barrel_mm: float = 0.015        # via wall
    board_mm: float = 1.76          # high-side board thickness
    track_width_factor: float = 0.80

    @property
    def rho(self):
        return RHO_20C * (1 + ALPHA * (self.temperature_c - 20.0))

    def thickness(self, layer):
        return self.outer_mm if layer in OUTER else self.inner_mm


@dataclass
class Result:
    milliohms: float
    j_max_a_per_mm: dict      # {layer name: peak sheet current density per ampere, outside terminals}
    j_term_a_per_mm: float    # peak inside the terminal zones, per ampere
    via_amps: list            # [(x, y, fraction of the current through that barrel)]
    cells: int
    iterations: int
    grids: dict = None        # {layer name: (sheet density per ampere, ny x nx, 0 off copper; near-terminal mask)}
    pitch: float = 0.0
    transfer_milliohms: dict = None  # probe pad: maximum source-to-pad drop per ampere


def _to(v):
    return pcbnew.ToMM(v)


def _shape_paths(poly_set):
    paths = []
    for o in range(poly_set.OutlineCount()):
        line = poly_set.Outline(o)
        pts = [(_to(line.CPoint(i).x), _to(line.CPoint(i).y)) for i in range(line.PointCount())]
        if len(pts) >= 3:
            paths.append((Path(pts), [Path([(_to(h.CPoint(i).x), _to(h.CPoint(i).y))
                                             for i in range(h.PointCount())])
                                       for h in (poly_set.Hole(o, k) for k in range(poly_set.HoleCount(o)))]))
    return paths


class Grid:
    def __init__(self, window, pitch):
        self.x0, self.y0, x1, y1 = window
        self.pitch = pitch
        self.nx = int(round((x1 - self.x0) / pitch)) + 1
        self.ny = int(round((y1 - self.y0) / pitch)) + 1
        xs = self.x0 + pitch * np.arange(self.nx)
        ys = self.y0 + pitch * np.arange(self.ny)
        self.X, self.Y = np.meshgrid(xs, ys)

    def poly(self, mask, poly_set):
        # Exact Matplotlib crossing parity on row-indexed contour edges.
        # No geometry simplification, division or grid change is performed.
        grid_poly(self, mask, poly_set, _shape_paths)

    def segment(self, mask, a, b, half):
        x0, x1 = min(a[0], b[0]) - half, max(a[0], b[0]) + half
        y0, y1 = min(a[1], b[1]) - half, max(a[1], b[1]) + half
        c0 = max(0, int(math.floor((x0 - self.x0) / self.pitch)))
        c1 = min(self.nx - 1, int(math.ceil((x1 - self.x0) / self.pitch)))
        r0 = max(0, int(math.floor((y0 - self.y0) / self.pitch)))
        r1 = min(self.ny - 1, int(math.ceil((y1 - self.y0) / self.pitch)))
        if c0 > c1 or r0 > r1:
            return
        X = self.X[r0:r1 + 1, c0:c1 + 1]
        Y = self.Y[r0:r1 + 1, c0:c1 + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        sq = dx * dx + dy * dy
        t = np.zeros_like(X) if sq == 0 else np.clip(((X - a[0]) * dx + (Y - a[1]) * dy) / sq, 0, 1)
        d = np.hypot(X - a[0] - t * dx, Y - a[1] - t * dy)
        mask[r0:r1 + 1, c0:c1 + 1] |= d <= half

    def cell(self, xy):
        c = int(round((xy[0] - self.x0) / self.pitch))
        r = int(round((xy[1] - self.y0) / self.pitch))
        return (r, c) if 0 <= r < self.ny and 0 <= c < self.nx else None


def _erode(mask):
    out = mask.copy()
    out[1:, :] &= mask[:-1, :]
    out[:-1, :] &= mask[1:, :]
    out[:, 1:] &= mask[:, :-1]
    out[:, :-1] &= mask[:, 1:]
    return out


def _pads(board, net, refs=None):
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net and (refs is None or (fp.GetReference(), p.GetNumber()) in refs):
                yield fp.GetReference(), p


def _pad_mask(grid, pad, layer):
    mask = np.zeros((grid.ny, grid.nx), dtype=bool)
    grid.poly(mask, pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE))
    return mask


def _geometry(board, net, window, pitch, corner):
    grid = Grid(window, pitch)
    rho = corner.rho
    copper = {}
    tracks = board.Tracks()
    items = [tracks[i].Cast() for i in range(len(tracks)) if tracks[i].GetNetname() == net]
    zones = board.Zones()
    zones = [zones[i] for i in range(len(zones)) if zones[i].GetNetname() == net
             and not zones[i].GetIsRuleArea() and zones[i].IsFilled()]
    barrels = []                        # (x, y, drill, layers)
    for layer in LAYERS:
        fill = np.zeros((grid.ny, grid.nx), dtype=bool)
        for z in zones:
            if z.IsOnLayer(layer):
                grid.poly(fill, z.GetFilledPolysList(layer))
        mask = _erode(fill)
        for t in items:
            if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == layer:
                a, b = t.GetStart(), t.GetEnd()
                grid.segment(mask, (_to(a.x), _to(a.y)), (_to(b.x), _to(b.y)),
                             corner.track_width_factor * _to(t.GetWidth()) / 2)
            elif t.Type() == pcbnew.PCB_VIA_T and t.IsOnLayer(layer):
                p = t.GetPosition()
                grid.segment(mask, (_to(p.x), _to(p.y)), (_to(p.x), _to(p.y)), _to(t.GetWidth()) / 2)
        for _, pad in _pads(board, net):
            if pad.IsOnLayer(layer) and (pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or layer in OUTER):
                mask |= _pad_mask(grid, pad, layer)
        copper[layer] = mask
    for t in items:
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            barrels.append(((_to(p.x), _to(p.y)), _to(t.GetDrillValue()),
                            [L for L in LAYERS if t.IsOnLayer(L)]))
    for _, pad in _pads(board, net):
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pad.GetDrillSize().x > 0:
            p = pad.GetPosition()
            barrels.append(((_to(p.x), _to(p.y)), _to(min(pad.GetDrillSize().x, pad.GetDrillSize().y)),
                            list(LAYERS)))

    # node numbering: copper cells of every layer, then one hub per barrel
    ids, offset = {}, 0
    for layer in LAYERS:
        idx = -np.ones((grid.ny, grid.nx), dtype=np.int64)
        n = int(copper[layer].sum())
        idx[copper[layer]] = offset + np.arange(n)
        ids[layer] = idx
        offset += n
    ea, eb, eg, ek = [], [], [], []           # ek: 0 along x, 1 along y, 2 barrel
    for layer in LAYERS:
        g = corner.thickness(layer) / rho               # siemens per square, ohm mm units
        idx = ids[layer]
        for kind, (sa, sb) in enumerate((((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
                                         ((slice(None, -1), slice(None)), (slice(1, None), slice(None))))):
            a, b = idx[sa], idx[sb]
            both = (a >= 0) & (b >= 0)
            ea.append(a[both]); eb.append(b[both]); eg.append(np.full(both.sum(), g))
            ek.append(np.full(both.sum(), kind))
    hubs = []
    for (xy, drill, layers) in barrels:
        area = math.pi * ((drill + 2 * corner.barrel_mm) ** 2 - drill ** 2) / 4
        r_half = rho * corner.board_mm / area / 2
        cell = grid.cell(xy)
        if cell is None:
            continue
        ends = [ids[L][cell] for L in layers if ids[L][cell] >= 0]
        if len(ends) < 2:
            continue
        hub = offset
        offset += 1
        hubs.append((xy, hub, ends, 1 / r_half))
        for e in ends:
            ea.append(np.array([hub])); eb.append(np.array([e])); eg.append(np.array([1 / r_half]))
            ek.append(np.array([2]))
    ea, eb, eg, ek = np.concatenate(ea), np.concatenate(eb), np.concatenate(eg), np.concatenate(ek)

    return grid, copper, ids, ea, eb, eg, ek, offset, hubs


def _progress(stage, **fields):
    """Opt-in numerical telemetry; does not change solver state or limits."""
    if os.environ.get('CUPC8_MESH_PROGRESS') != '1':
        return
    import json
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        rss = None
    print('mesh progress ' + json.dumps(dict(stage=stage, pid=os.getpid(),
          monotonic_seconds=time.monotonic(), max_rss_kib=rss, **fields)), flush=True)


def solve(board, net, sources, sinks, window, pitch=0.1, corner=Corner(), terminal_mm=1.0,
          tol=1e-9, max_iter=200000, solver='cg', geometry_cache=None, probes=(),
          voltage_reference='source'):
    """Resistance (mOhm) between two groups of pads [(ref, number)], each group
    tied to one ideal potential, through all of `net`'s copper in `window`.
    geometry_cache may be reused only while the supplied board is immutable."""
    if voltage_reference not in ('source', 'sink'):
        raise ValueError('voltage_reference must be source or sink')
    _progress('geometry_begin', net=net, sinks=sinks, pitch=pitch)
    key = (id(board), net, tuple(window), pitch, corner)
    if geometry_cache is not None and key in geometry_cache:
        geometry = geometry_cache[key]
    else:
        geometry = _geometry(board, net, window, pitch, corner)
        if geometry_cache is not None:
            geometry_cache[key] = geometry
    grid, copper, ids, ea, eb, eg, ek, offset, hubs = geometry
    _progress('geometry_complete', net=net, sinks=sinks, pitch=pitch, sites=grid.nx * grid.ny)

    def terminal(group):
        nodes = []
        for ref, num in group:
            hits = list(_pads(board, net, {(ref, num)}))
            if len(hits) != 1:
                raise ValueError('%s pad %s:%s missing or duplicated' % (net, ref, num))
            pad = hits[0][1]
            for layer in LAYERS:
                if pad.IsOnLayer(layer) and (pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or layer in OUTER):
                    m = _pad_mask(grid, pad, layer) & copper[layer]
                    nodes.extend(ids[layer][m].tolist())
        if not nodes:
            raise ValueError('%s: terminal %s has no copper in the window' % (net, group))
        return np.unique(nodes)

    src, snk = terminal(sources), terminal(sinks)
    if np.intersect1d(src, snk).size:
        raise ValueError('%s: source and sink terminals touch' % net)
    n = offset
    fixed = np.zeros(n, dtype=bool)
    fixed[src] = fixed[snk] = True
    v = np.zeros(n)
    # Source reference preserves the existing voltage gauge. Sink reference
    # solves w = 1 - v with exactly the same operator and electrodes, reading
    # tiny source-to-probe drops directly instead of subtracting near-one volts.
    v[src if voltage_reference == 'source' else snk] = 1.0

    # restrict to the component joining the source (floating islands make the
    # Laplacian singular) and require that it reaches the sink
    adj_a = np.concatenate([ea, eb])
    adj_b = np.concatenate([eb, ea])
    order = np.argsort(adj_a, kind='stable')
    adj_a, adj_b = adj_a[order], adj_b[order]
    start = np.searchsorted(adj_a, np.arange(n + 1))
    seen = np.zeros(n, dtype=bool)
    seen[src] = True
    frontier = src
    while frontier.size:
        lens = start[frontier + 1] - start[frontier]
        offs = np.repeat(start[frontier] - np.cumsum(lens) + lens, lens) + np.arange(lens.sum())
        nb = np.unique(adj_b[offs])
        nb = nb[~seen[nb]]
        seen[nb] = True
        frontier = nb[~fixed[nb]]
    if not seen[snk].any():
        raise ValueError('%s: open copper between %s and %s' % (net, sources, sinks))
    keep = seen[ea] & seen[eb]
    ea, eb, eg, ek = ea[keep], eb[keep], eg[keep], ek[keep]
    free = seen & ~fixed
    diag = np.bincount(ea, eg, n) + np.bincount(eb, eg, n)
    # right-hand side from the fixed source potential
    rhs = np.zeros(n)
    rhs += np.bincount(ea, eg * v[eb] * (fixed[eb] & free[ea]), n)
    rhs += np.bincount(eb, eg * v[ea] * (fixed[ea] & free[eb]), n)
    mf = (free[ea] & free[eb])
    fa, fb, fg = ea[mf], eb[mf], eg[mf]

    def matvec(x):
        y = diag * x
        y -= np.bincount(fa, fg * x[fb], n)
        y -= np.bincount(fb, fg * x[fa], n)
        y[~free] = 0
        return y

    inv = np.where(free, 1 / np.maximum(diag, 1e-30), 0)
    if solver in ('sparse', 'amg'):
        # The same Laplacian and Jacobi-preconditioned CG, with compiled CSR
        # matvecs. Drop only fixed/floating nodes, which the original CG zeros.
        from scipy.sparse import coo_matrix, diags
        from scipy.sparse.linalg import cg
        nodes = np.flatnonzero(free)
        ids_free = -np.ones(n, dtype=np.int64)
        ids_free[nodes] = np.arange(nodes.size)
        ia, ib = ids_free[fa], ids_free[fb]
        a = coo_matrix((np.concatenate((diag[nodes], -fg, -fg)),
                       (np.concatenate((np.arange(nodes.size), ia, ib)),
                        np.concatenate((np.arange(nodes.size), ib, ia)))),
                       shape=(nodes.size, nodes.size)).tocsr()
        iterations = [0]
        def counted(x):
            iterations[0] += 1
            if iterations[0] % 50 == 0 and os.environ.get('CUPC8_MESH_PROGRESS') == '1':
                _progress('cg_iteration', net=net, sinks=sinks, pitch=pitch,
                          iteration=iterations[0],
                          relative_residual=float(np.linalg.norm(rhs[nodes] - a @ x) /
                                                  np.linalg.norm(rhs[nodes])))
        preconditioner = diags(inv[nodes])
        if solver == 'amg':
            from pyamg import smoothed_aggregation_solver
            _progress('amg_begin', net=net, sinks=sinks, pitch=pitch, nodes=a.shape[0], nonzeros=a.nnz)
            preconditioner = smoothed_aggregation_solver(a, symmetry='symmetric').aspreconditioner()
            _progress('amg_complete', net=net, sinks=sinks, pitch=pitch)
        _progress('cg_begin', net=net, sinks=sinks, pitch=pitch, nodes=a.shape[0], rtol=tol, maxiter=max_iter)
        xf, status = cg(a, rhs[nodes], rtol=tol, atol=0, maxiter=max_iter,
                        M=preconditioner, callback=counted)
        _progress('cg_complete', net=net, sinks=sinks, pitch=pitch, iterations=iterations[0], status=int(status))
        if status != 0:
            raise ValueError('%s: mesh solve did not converge' % net)
        x = np.zeros(n)
        x[nodes] = xf
        it = iterations[0] - 1
    elif solver == 'cg':
        x = np.zeros(n)
        r = rhs * free
        z = inv * r
        p = z.copy()
        rz = r @ z
        norm0 = math.sqrt(r @ r) or 1.0
        for it in range(max_iter):
            ap = matvec(p)
            alpha = rz / (p @ ap)
            x += alpha * p
            r -= alpha * ap
            if math.sqrt(r @ r) <= tol * norm0:
                break
            z = inv * r
            rz_new = r @ z
            p = z + (rz_new / rz) * p
            rz = rz_new
        else:
            raise ValueError('%s: mesh solve did not converge' % net)
    else:
        raise ValueError('unknown copper mesh solver: %s' % solver)
    volts = np.where(free, x, v)
    current = eg * (volts[ea] - volts[eb])          # A per V, from a to b
    total = abs(np.bincount(ea, current, n)[src].sum() - np.bincount(eb, current, n)[src].sum())
    if total <= 0:
        raise ValueError('%s: no current flows' % net)
    transfers = {}
    for probe in probes:
        nodes = terminal([probe])
        if not (seen[nodes] | fixed[nodes]).all():
            raise ValueError('%s: open copper to qualified probe %s' % (net, probe))
        # Do not draw current at a qualified probe. Its worst finite-pad
        # cell gives a conservative drop rather than an averaged potential.
        drop = 1 - volts[nodes] if voltage_reference == 'source' else volts[nodes]
        transfers[probe] = 1000 * float(drop.max()) / total
    current /= total                                 # per ampere of terminal current

    # sheet current density per unit width at each cell, outside and inside
    # the terminal zones (within terminal_mm of a terminal pad)
    near = np.zeros(n, dtype=bool)
    rad = int(math.ceil(terminal_mm / pitch))
    for layer in LAYERS:
        idx = ids[layer]
        term = np.isin(idx, np.concatenate([src, snk])) & (idx >= 0)
        grown = term.copy()
        for _ in range(rad):
            grown = grown | np.roll(grown, 1, 0) | np.roll(grown, -1, 0) | np.roll(grown, 1, 1) | np.roll(grown, -1, 1)
        near[idx[grown & (idx >= 0)]] = True
    # the sheet current vector at a cell: the mean of its two x edges' and two
    # y edges' currents (a cell at a copper edge has one of each)
    jx = (np.bincount(ea, current * (ek == 0), n) + np.bincount(eb, current * (ek == 0), n)) / 2
    jy = (np.bincount(ea, current * (ek == 1), n) + np.bincount(eb, current * (ek == 1), n)) / 2
    flow = np.hypot(jx, jy)
    j_max, j_term, grids = {}, 0.0, {}
    for layer in LAYERS:
        idx = ids[layer]
        cells = idx[idx >= 0]
        if not cells.size:
            continue
        dens = flow[cells] / pitch                 # per unit width
        out = ~near[cells]
        grid = np.zeros(idx.shape)
        on = (idx >= 0) & seen[np.maximum(idx, 0)]
        grid[on] = flow[idx[on]] / pitch
        near_grid = np.zeros(idx.shape, dtype=bool)
        near_grid[idx >= 0] = near[idx[idx >= 0]]
        grids[pcbnew.LayerName(layer)] = (grid, near_grid)
        if out.any():
            j_max[pcbnew.LayerName(layer)] = float(dens[out].max())
        if (~out).any():
            j_term = max(j_term, float(dens[~out].max()))
    via_amps = []
    for xy, hub, ends, g in hubs:
        if seen[hub]:
            through = sum(abs(g * (volts[hub] - volts[e])) for e in ends) / 2 / total
            via_amps.append((xy, through))
    return Result(1000.0 / total, j_max, j_term, via_amps, int(seen.sum()), it + 1, grids, pitch, transfers)


def ipc_rise(amps, area_mm2, outer=True):
    """IPC-2221B trace temperature rise (C): I = k dT^0.44 A^0.725, A in mil^2.
    The derivation doc uses the external k for every layer (IPC-2152 finds
    inner traces about as cool); `outer=False` gives the internal-k upper bound."""
    k = 0.048 if outer else 0.024
    mil2 = area_mm2 / 0.0254 ** 2
    return (amps / (k * mil2 ** 0.725)) ** (1 / 0.44)


def fin_rise(amps, area_mm2, length_mm, rho):
    """Peak self-heating rise of a conductor of length L between two ends held
    at the adjoining copper's temperature, with no loss to the board (an
    upper bound): q' L^2 / (8 k A), q' = I^2 rho / A."""
    return amps ** 2 * rho / area_mm2 * length_mm ** 2 / (8 * K_COPPER * area_mm2)
