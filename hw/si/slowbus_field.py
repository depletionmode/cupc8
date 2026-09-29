#!/usr/bin/env python3
"""2D electrostatic cross-section solver for PCB transmission lines.

Finite-volume Laplace solve on a non-uniform tensor grid inside a grounded
box: the conductors (signal traces at fixed potential, reference planes and
coplanar pour at 0 V) are cells with fixed potential; each dielectric layer
has its own permittivity, air elsewhere. The Maxwell capacitance matrix
with the dielectrics (C) and in vacuum (C0) gives, for quasi-TEM lines,

    L = inv(C0) / c^2,   Z0 = 1 / (c sqrt(C C0)),   t_d = sqrt(C / C0) / c.

Validated against the exact zero-thickness stripline (Cohn) and the
Hammerstad-Jensen microstrip in test/hw/test_slowbus_si.py.
"""
import math

import numpy as np

EPS0 = 8.8541878128e-12
C_LIGHT = 299792458.0


def _axis(fixed, lo, hi, fine, coarse, grow=1.3):
    """Grid lines through every `fixed` coordinate, fine near them."""
    pts = sorted({round(v, 7) for v in fixed if lo <= v <= hi} | {lo, hi})
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        span = b - a
        if span <= fine * 1.01:
            out.append(b)
            continue
        # grow from both ends towards the middle
        left, right, step = [a], [b], fine
        while left[-1] + step < right[-1] - step:
            left.append(left[-1] + step)
            if left[-1] + step < right[-1] - step:
                right.append(right[-1] - step)
            step = min(step * grow, coarse)
        out += left[1:] + right[::-1]
    return np.array(sorted(set(round(v, 9) for v in out)))


def solve(layers, conductors, width, top_air, fine=None, iterations=20000, tol=1e-7, bottom_air=0.0):
    """Capacitance matrices per metre.

    layers: [(z0, z1, eps_r)] dielectric slabs (z upwards, mm).
    conductors: [(x0, x1, z0, z1, index)], index -1 = ground (0 V), 0..n-1
    signal conductors. width: half-width of the box (mm).
    Returns (C, C0) as n x n arrays in F/m."""
    zs = [z for l in layers for z in l[:2]] + [z for c in conductors for z in c[2:4]]
    xs = [x for c in conductors for x in c[:2]]
    zmin, zmax = min(zs) - bottom_air, max(zs) + top_air
    thin = min(c[3] - c[2] for c in conductors)
    fine = fine or max(min(thin / 2, .01), .004)
    x = _axis(xs + [0.0], -width, width, fine, width / 20)
    z = _axis(zs, zmin, zmax, fine, (zmax - zmin) / 20)
    nx, nz = len(x), len(z)
    xc, zc = (x[:-1] + x[1:]) / 2, (z[:-1] + z[1:]) / 2      # cell centres
    eps_cell = np.ones((nx - 1, nz - 1))
    for z0, z1, er in layers:
        mask = (zc >= z0) & (zc < z1)
        eps_cell[:, mask] = er
    signals = sorted({c[4] for c in conductors if c[4] >= 0})
    n = len(signals)
    fixed = np.zeros((nx, nz), bool)
    owner = np.full((nx, nz), -2)
    X, Z = np.meshgrid(x, z, indexing='ij')
    for x0, x1, z0, z1, idx in conductors:
        m = (X >= x0 - 1e-9) & (X <= x1 + 1e-9) & (Z >= z0 - 1e-9) & (Z <= z1 + 1e-9)
        fixed |= m
        owner[m] = idx
    # the box itself is ground
    fixed[0, :] = fixed[-1, :] = fixed[:, 0] = fixed[:, -1] = True
    edge = np.zeros_like(fixed)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    owner[edge & (owner == -2)] = -1

    def matrices(eps):
        # node coefficients: flux through the four half-cell faces
        dx, dz = np.diff(x), np.diff(z)
        ce = np.zeros((nx, nz))
        cw, cn, cs = ce.copy(), ce.copy(), ce.copy()
        # east face of node (i,j): between i and i+1, spans z half-cells above/below
        e_up = np.zeros((nx - 1, nz))
        e_up[:, :-1] += eps[:, :] * dz[None, :] / 2
        e_up[:, 1:] += eps[:, :] * dz[None, :] / 2
        ce[:-1, :] = e_up / dx[:, None]
        cw[1:, :] = e_up / dx[:, None]
        n_up = np.zeros((nx, nz - 1))
        n_up[:-1, :] += eps[:, :] * dx[:, None] / 2
        n_up[1:, :] += eps[:, :] * dx[:, None] / 2
        cn[:, :-1] = n_up / dz[None, :]
        cs[:, 1:] = n_up / dz[None, :]
        return ce, cw, cn, cs

    def capacitance(eps):
        ce, cw, cn, cs = matrices(eps)
        diag = ce + cw + cn + cs
        diag[diag == 0] = 1
        out = np.zeros((n, n))
        red = ((np.arange(nx)[:, None] + np.arange(nz)[None, :]) % 2 == 0)
        free = ~fixed
        omega = 2 / (1 + math.sin(math.pi / max(nx, nz)))
        for col, sig in enumerate(signals):
            phi = np.zeros((nx, nz))
            phi[owner == sig] = 1.0
            for it in range(iterations):
                delta = 0.0
                for colour in (red, ~red):
                    upd = np.zeros_like(phi)
                    upd[1:-1, 1:-1] = (ce[1:-1, 1:-1] * phi[2:, 1:-1] + cw[1:-1, 1:-1] * phi[:-2, 1:-1] +
                                       cn[1:-1, 1:-1] * phi[1:-1, 2:] + cs[1:-1, 1:-1] * phi[1:-1, :-2]) / diag[1:-1, 1:-1]
                    m = colour & free
                    change = omega * (upd[m] - phi[m])
                    phi[m] += change
                    if change.size:
                        delta = max(delta, float(np.max(np.abs(change))))
                if delta < tol:
                    break
            else:
                raise RuntimeError('field solver did not converge')
            # charge on each conductor = net flux out of its nodes
            resid = diag * phi - (np.pad(ce[:-1] * phi[1:], ((0, 1), (0, 0))) +
                                  np.pad(cw[1:] * phi[:-1], ((1, 0), (0, 0))) +
                                  np.pad(cn[:, :-1] * phi[:, 1:], ((0, 0), (0, 1))) +
                                  np.pad(cs[:, 1:] * phi[:, :-1], ((0, 0), (1, 0))))
            for row, other in enumerate(signals):
                out[row, col] = float(np.sum(resid[owner == other]))
        return out * EPS0

    return capacitance(eps_cell), capacitance(np.ones_like(eps_cell))


def line(layers, conductors, width, top_air, bottom_air=0.0):
    """Single line: (Z0 ohm, delay s/m)."""
    c, c0 = solve(layers, conductors, width, top_air, bottom_air=bottom_air)
    c, c0 = c[0, 0], c0[0, 0]
    return 1 / (C_LIGHT * math.sqrt(c * c0)), math.sqrt(c / c0) / C_LIGHT


def coupled(layers, conductors, width, top_air, bottom_air=0.0):
    """Two lines: (Z0 of line 0, delay, Kb, Kf) for line 1 aggressing line 0.

    Kb = (Cm/C + Lm/L)/4 (saturated NEXT); Kf = (Cm/C - Lm/L)/2 (FEXT per
    unit of coupled delay / rise time)."""
    c, c0 = solve(layers, conductors, width, top_air, bottom_air=bottom_air)
    lmat = np.linalg.inv(c0) / C_LIGHT ** 2
    kc = -c[0, 1] / c[0, 0]
    kl = lmat[0, 1] / lmat[0, 0]
    z0 = 1 / (C_LIGHT * math.sqrt(c[0, 0] * c0[0, 0]))
    td = math.sqrt(c[0, 0] / c0[0, 0]) / C_LIGHT
    return z0, td, (kc + kl) / 4, (kc - kl) / 2


def ellipk(k):
    """Complete elliptic integral of the first kind K(k) by the AGM."""
    a, b = 1.0, math.sqrt(1 - k * k)
    while abs(a - b) > 1e-15:
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)
