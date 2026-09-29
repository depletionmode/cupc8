#!/usr/bin/env python3
"""Quasi-static 2-D cross-section solver for PCB transmission lines.

The Laplace equation div(eps grad phi) = 0 is discretised on a tensor-product
grid whose lines include every conductor and dielectric edge.  The five-point
stencil used here is exactly the linear finite-element (P1) stiffness matrix
on the right triangles that split each rectangle, so it is a conforming
Galerkin method.  By the Dirichlet principle its capacitance matrix is never
smaller than the exact one (C_h >= C in the Loewner order) for the modelled
geometry.  The outer box is a grounded wall, which can only add capacitance.

Consequently every impedance returned here,
    Z_se   = 1 / (c * sqrt(C * C_air))             (one signal conductor)
    Z_diff = sqrt(p * p_air) / c,  p = u' C^-1 u,  u = (1, -1)
is a rigorous LOWER bound on the modelled line's quasi-TEM impedance, on any
grid.  Refining the grid raises it monotonically towards the exact value; the
difference between two nested grids estimates the remaining error.

Only numpy is required (matrix-free Jacobi-preconditioned conjugate gradient).
"""
import math

import numpy as np

EPS0 = 8.8541878128e-12
C_LIGHT = 299792458.0


def _graded(breaks, fine, coarse, ratio, focus, refine=1):
    """Grid lines through every break, `fine` spacing near `focus` points,
    growing geometrically by `ratio` up to `coarse` away from them.

    `refine` = 2, 4, ... splits every cell of the refine = 1 grid into equal
    parts, so the grids are nested: each finer finite-element space contains
    the coarser one and the impedance bound can only rise."""
    breaks = sorted(set(round(b, 9) for b in breaks))
    focus = np.array(sorted(set(focus)))

    def spacing(x):
        d = np.min(np.abs(focus - x)) if len(focus) else math.inf
        # size(d) = fine + (ratio - 1) * d keeps neighbouring cells within
        # `ratio` of each other.
        return min(coarse, fine + (ratio - 1) * d)

    lines = [breaks[0]]
    for a, b in zip(breaks, breaks[1:]):
        x = a
        while True:
            step = spacing(x)
            if b - x <= step * 1.0001:
                break
            # never leave a sliver smaller than a third of a cell before b
            if b - x - step < step / 3:
                step = (b - x) / 2
            x += step
            lines.append(x)
        lines.append(b)
    base = np.array(lines)
    parts = [base[:-1] + (base[1:] - base[:-1]) * k / refine for k in range(refine)]
    return np.append(np.stack(parts, axis=1).ravel(), base[-1])


class Section:
    """A cross-section: horizontal x (mm), vertical y (mm, up positive).

    conductors: list of (x0, x1, y0, y1, cid) rectangles; cid 0 is ground,
                1..n are signal conductors.
    dielectrics: list of (x0, x1, y0, y1, eps_r) rectangles; later entries
                 override earlier ones; the background is air.
    box: (x0, x1, y0, y1) grounded outer wall.
    """

    def __init__(self, conductors, dielectrics, box, fine=.005, coarse=.1,
                 ratio=1.25, refine=1):
        self.conductors = conductors
        self.dielectrics = dielectrics
        self.box = box
        x0, x1, y0, y1 = box
        xb = [x0, x1] + [v for c in conductors for v in c[:2] if x0 < v < x1]
        yb = [y0, y1] + [v for c in conductors for v in c[2:4] if y0 < v < y1]
        xb += [v for d in dielectrics for v in d[:2] if x0 < v < x1]
        yb += [v for d in dielectrics for v in d[2:4] if y0 < v < y1]
        signals = [c for c in conductors if c[4] > 0]
        xf = [v for c in signals for v in c[:2]]
        yf = [v for c in signals for v in c[2:4]]
        # The fine region also covers each signal's nearest reference edges.
        xf += [v for c in conductors if c[4] == 0 for v in c[:2]
               if any(abs(v - s) < .5 for s in xf)]
        self.x = _graded(xb, fine, coarse, ratio, xf, refine)
        self.y = _graded(yb, fine, coarse, ratio, yf, refine)
        nx, ny = len(self.x), len(self.y)
        xc = (self.x[:-1] + self.x[1:]) / 2
        yc = (self.y[:-1] + self.y[1:]) / 2
        eps = np.ones((nx - 1, ny - 1))
        for a, b, c, d, er in dielectrics:
            eps[np.ix_((xc > a) & (xc < b), (yc > c) & (yc < d))] = er
        self.eps = eps
        cid = np.full((nx, ny), -1, dtype=int)
        tol = 1e-9
        for a, b, c, d, k in conductors:
            ix = (self.x >= a - tol) & (self.x <= b + tol)
            iy = (self.y >= c - tol) & (self.y <= d + tol)
            region = np.ix_(ix, iy)
            clash = (cid[region] >= 0) & (cid[region] != k)
            if np.any(clash & (k > 0)) or np.any(clash & (cid[region] > 0)):
                raise ValueError('two different conductors touch in the section')
            cid[region] = k
        wall = np.concatenate((cid[0, :], cid[-1, :], cid[:, 0], cid[:, -1]))
        if np.any(wall > 0):
            raise ValueError('a signal conductor touches the grounded outer wall')
        cid[0, :] = cid[-1, :] = 0
        cid[:, 0] = cid[:, -1] = 0
        self.cid = cid
        self.nsig = max((c[4] for c in conductors), default=0)
        if self.nsig < 1:
            raise ValueError('section has no signal conductor')

    def _weights(self, eps):
        hx = np.diff(self.x)[:, None]
        hy = np.diff(self.y)[None, :]
        cx = eps * (hy / 2) / hx           # per cell, on its two x-edges
        cy = eps * (hx / 2) / hy           # per cell, on its two y-edges
        nx, ny = len(self.x), len(self.y)
        wx = np.zeros((nx - 1, ny))
        wx[:, :-1] += cx
        wx[:, 1:] += cx
        wy = np.zeros((nx, ny - 1))
        wy[:-1, :] += cy
        wy[1:, :] += cy
        return wx, wy

    @staticmethod
    def _apply(phi, wx, wy):
        out = np.zeros_like(phi)
        fx = wx * (phi[1:, :] - phi[:-1, :])
        out[:-1, :] -= fx
        out[1:, :] += fx
        fy = wy * (phi[:, 1:] - phi[:, :-1])
        out[:, :-1] -= fy
        out[:, 1:] += fy
        return -out

    def _solve(self, wx, wy, k, start=None, tol=1e-9, maxiter=40000):
        # Any iterate is an admissible potential, so the energy -- and each
        # self capacitance -- stays an upper bound however early CG stops.
        free = self.cid < 0
        fixed = np.where(self.cid == k, 1.0, 0.0)
        diag = np.zeros_like(fixed)
        diag[:-1, :] += wx
        diag[1:, :] += wx
        diag[:, :-1] += wy
        diag[:, 1:] += wy
        b = -self._apply(fixed, wx, wy) * free
        x = np.zeros_like(fixed) if start is None else np.where(free, start, 0.0)
        r = b - self._apply(x, wx, wy) * free
        z = np.where(free, r / np.where(diag > 0, diag, 1), 0)
        p = z.copy()
        rz = np.sum(r * z)
        norm = math.sqrt(np.sum(b * b)) or 1.0
        for _ in range(maxiter):
            ap = self._apply(p, wx, wy) * free
            alpha = rz / np.sum(p * ap)
            x += alpha * p
            r -= alpha * ap
            if math.sqrt(np.sum(r * r)) < tol * norm:
                return x + fixed
            z = np.where(free, r / np.where(diag > 0, diag, 1), 0)
            rz_new = np.sum(r * z)
            p = z + (rz_new / rz) * p
            rz = rz_new
        raise RuntimeError('cross-section CG did not converge')

    def capacitance(self, air=False, starts=None):
        """Maxwell capacitance matrix per metre (F/m), signals 1..n.

        `starts` are initial potentials (e.g. from the other dielectric
        case); they only speed the solve up."""
        eps = np.ones_like(self.eps) if air else self.eps
        wx, wy = self._weights(eps)
        phis = [self._solve(wx, wy, k, starts[k - 1] if starts else None)
                for k in range(1, self.nsig + 1)]
        self.last_potentials = phis
        n = self.nsig
        cmat = np.zeros((n, n))
        for i in range(n):
            for j in range(i, n):
                dx_i = np.diff(phis[i], axis=0)
                dx_j = np.diff(phis[j], axis=0)
                dy_i = np.diff(phis[i], axis=1)
                dy_j = np.diff(phis[j], axis=1)
                e = np.sum(wx * dx_i * dx_j) + np.sum(wy * dy_i * dy_j)
                cmat[i, j] = cmat[j, i] = EPS0 * e
        return cmat


def line_parameters(section):
    """Impedance (ohm) and delay (s/m) lower-bound figures for a section."""
    c = section.capacitance()
    c0 = section.capacitance(air=True, starts=section.last_potentials)
    out = {'nodes': int(section.cid.size), 'c_self': [float(v) for v in np.diag(c)]}
    if section.nsig == 1:
        out['z_se'] = 1 / (C_LIGHT * math.sqrt(c[0, 0] * c0[0, 0]))
        out['delay'] = math.sqrt(c[0, 0] / c0[0, 0]) / C_LIGHT
        out['c_per_m'] = c[0, 0]
        return out
    u = np.array([1.0, -1.0])
    p = u @ np.linalg.solve(c, u)
    p0 = u @ np.linalg.solve(c0, u)
    out['z_diff'] = math.sqrt(p * p0) / C_LIGHT
    out['delay'] = math.sqrt(p0 / p) / C_LIGHT
    out['c_diff_per_m'] = 1 / p
    # Each line alone (the other held at ground): its own even/odd mix.
    out['z_se'] = [1 / (C_LIGHT * math.sqrt(c[i, i] * c0[i, i])) for i in range(2)]
    return out


def stripline_exact(w, b, er):
    """Cohn's exact zero-thickness centred stripline impedance (ohm)."""
    k = 1 / math.cosh(math.pi * w / (2 * b))
    kp = math.sqrt(1 - k * k)
    return 30 * math.pi / math.sqrt(er) * _ellipk(k) / _ellipk(kp)


def _ellipk(k):
    """Complete elliptic integral K(k) by the arithmetic-geometric mean."""
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(40):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)
