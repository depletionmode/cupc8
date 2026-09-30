"""Exact row-indexed counterpart of Matplotlib's zero-radius polygon test.

Uses the same binary64 crossing predicate; only skips edges whose endpoint
Y comparisons agree for the row. No polygon simplification or mesh changes.
Reference: matplotlib/matplotlib src/_path.h, point_in_path_impl.
"""
import numpy as np

def path_grid_mask(path, xs, ys):
    vertices = np.asarray(path.vertices, dtype=np.float64)
    xs, ys = np.asarray(xs), np.asarray(ys)
    if path.codes is not None or not np.isfinite(vertices).all():
        X, Y = np.meshgrid(xs, ys)
        return path.contains_points(np.column_stack((X.ravel(), Y.ravel()))).reshape(Y.shape)
    if (xs.ndim != 1 or ys.ndim != 1 or not np.isfinite(xs).all() or
            not np.isfinite(ys).all() or np.any(np.diff(xs) <= 0) or np.any(np.diff(ys) <= 0)):
        raise ValueError('raster coordinates must be finite and strictly increasing')
    result = np.zeros((len(ys), len(xs)), dtype=bool)
    if len(vertices) < 3 or not len(xs) or not len(ys):
        return result
    a, b = vertices, np.roll(vertices, -1, axis=0)
    # Matplotlib's >= endpoint predicate includes the high Y, excludes low Y.
    starts = np.searchsorted(ys, np.minimum(a[:, 1], b[:, 1]), side='right')
    ends = np.searchsorted(ys, np.maximum(a[:, 1], b[:, 1]), side='right')
    edges = np.flatnonzero(starts < ends)
    start_order = edges[np.argsort(starts[edges], kind='stable')]
    end_order = edges[np.argsort(ends[edges], kind='stable')]
    active = set(); add = drop = 0
    nx = len(xs)
    for row, y in enumerate(ys):
        while add < len(start_order) and starts[start_order[add]] <= row:
            active.add(int(start_order[add])); add += 1
        while drop < len(end_order) and ends[end_order[drop]] <= row:
            active.discard(int(end_order[drop])); drop += 1
        if not active:
            continue
        selected = np.fromiter(sorted(active), dtype=np.int64)
        x0, y0 = a[selected].T; x1, y1 = b[selected].T
        lhs = (y1 - y) * (x0 - x1)
        dy = y0 - y1
        yflag1 = y1 >= y
        # The crossing predicate is true on a prefix of the sorted X axis.
        # Binary search evaluates the original multiply/compare, avoiding
        # division-induced changes at exact contour/grid coincidences.
        low = np.zeros(len(selected), dtype=np.int64)
        high = np.full(len(selected), nx, dtype=np.int64)
        while np.any(low < high):
            work = np.flatnonzero(low < high)
            middle = (low[work] + high[work]) // 2
            hit = (lhs[work] >= (x1[work] - xs[middle]) * dy[work]) == yflag1[work]
            low[work[hit]] = middle[hit] + 1
            high[work[~hit]] = middle[~hit]
        counts = np.bincount(low, minlength=nx + 1)
        result[row] = (np.cumsum(counts[::-1])[::-1][1:] & 1).astype(bool)
    return result


def grid_poly(grid, mask, poly_set, shape_paths):
    xs, ys = grid.X[0], grid.Y[:, 0]
    for outline, holes in shape_paths(poly_set):
        (bx0, by0), (bx1, by1) = outline.vertices.min(0), outline.vertices.max(0)
        cols = np.flatnonzero((xs >= bx0) & (xs <= bx1))
        rows = np.flatnonzero((ys >= by0) & (ys <= by1))
        if not len(cols) or not len(rows):
            continue
        xx, yy = xs[cols], ys[rows]
        inside = path_grid_mask(outline, xx, yy)
        for hole in holes:
            inside &= ~path_grid_mask(hole, xx, yy)
        mask[np.ix_(rows, cols)] |= inside
