#!/usr/bin/env python3
"""MB-005: the main board's input loop, extracted from the routed receipt.

Requirement (David, 2026-09-28; doc/hardware/mb005-loop-requirement-derivation.md,
hw/power/design.py R_RECEPTACLE):

  - the board-side input loop -- positive copper J1 -> F1 -> U2, the GND
    return from the eFuse and its 5V_SYS input capacitors to J1, and the
    receptacle terminations, solder joints and layer transitions -- is at
    most 60 mOhm at the hottest corner. The mated VBUS/GND contacts are not
    in it: USB Type-C R2.0 4.4.1 counts them in the cable's IR-drop budget;
  - every full-current conductor rises at most 20 C at the eFuse's 3.213 A
    maximum current limit, which it can carry indefinitely.

Resistance: copper_mesh.solve over every layer, zone fill, track, pad and
barrel of each net, at the derivation's corner (115 C; tracks at 80 % of
their drawn width; 24.9 / 11.4 um outer / inner copper; 15 um via wall;
1.76 mm board). Each J1 pad is taken alone as the source (the worst split
of the two contact groups), at two mesh pitches; the larger result counts.
Solder joints and the receptacle's tails are allowances (TRANSITIONS).

Temperature: at 3.213 A each conductor's peak sheet current density (outside
1 mm of a terminal pad) is turned into an equivalent trace carrying the
whole current at that density, and IPC-2221B gives its rise (the external k
for every layer, as the derivation does; the internal-k bound is printed).
The copper within 1 mm of a terminal pad (the pad's escape neck) is bounded
as a conductor between two ends held at the body's temperature (no loss to
the board), and each via barrel likewise with its extracted current.
"""

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import boardevidence
from boardcheck import check_report
from cosim.netlist import read
import copper_mesh as cm
import design as d
from spice import Checks


INPUT_PINS = {
    ('J1', 'A4B9'): '/VBUS', ('J1', 'B4A9'): '/VBUS', ('J1', 'A1B12'): '/GND', ('J1', 'B1A12'): '/GND',
    ('F1', '1'): '/VBUS', ('F1', '2'): '/VBUS_F',
    ('U2', '5'): '/VBUS_F', ('U2', '6'): '/5V_SYS', ('U2', '8'): '/GND',
    ('C3', '1'): '/5V_SYS', ('C3', '2'): '/GND', ('C5', '2'): '/GND', ('U3', '2'): '/GND',
    ('R4', '1'): '/5V_SYS', ('U3', '1'): '/5V_SYS', ('U3', '4'): '/5V_SYS',
}
CORNER = cm.Corner()
LOOP_LIMIT_MOHM = 1000 * d.R_RECEPTACLE
RISE_LIMIT_C = 20.0
# allowances, mOhm: each solder joint in the loop (J1 VBUS and GND, F1 x 2,
# U2 IN, and the return's source pad), and each of J1's two terminal tails
SOLDER_JOINT_MOHM, SOLDER_JOINTS = 0.5, 6
J1_TAIL_MOHM, J1_TAILS = 1.0, 2
TRANSITIONS = SOLDER_JOINT_MOHM * SOLDER_JOINTS + J1_TAIL_MOHM * J1_TAILS
PITCHES = (0.1, 0.07)

# (name, net, sources, sinks, window mm, what the current is)
POSITIVE = [
    ('J1 A4B9 -> F1:1', '/VBUS', [('J1', 'A4B9')], [('F1', '1')], (10, 164, 40, 186)),
    ('J1 B4A9 -> F1:1', '/VBUS', [('J1', 'B4A9')], [('F1', '1')], (10, 164, 40, 186)),
    ('F1:2 -> U2 IN', '/VBUS_F', [('F1', '2')], [('U2', '5')], (8, 154, 30, 172)),
]
RETURN = [
    ('%s -> J1 %s' % (s, j), '/GND', [tuple(s.split(':'))], [('J1', j)], (0, 140, 52, 188))
    for s in ('U2:8', 'C3:2', 'C5:2', 'U3:2') for j in ('A1B12', 'B1A12')
]
OUTPUT = [       # 5V_SYS from U2's OUT: a fault beyond either branch draws the full limit
    ('U2 OUT -> R4:1', '/5V_SYS', [('U2', '6')], [('R4', '1')], (4, 146, 46, 168)),
    ('U2 OUT -> U3:1', '/5V_SYS', [('U2', '6')], [('U3', '1')], (4, 146, 46, 168)),
    ('U2 OUT -> U3:4', '/5V_SYS', [('U2', '6')], [('U3', '4')], (4, 146, 46, 168)),
]


def inspect(out):
    boardevidence.validate('main', out)
    check_report(json.loads((out / 'drc.json').read_text()), 'drc')
    order = json.loads((out / 'fab/order.json').read_text())
    required = {'layers': 6, 'thickness_mm': 1.6, 'finished_outer_copper_oz': 1,
                'finished_inner_copper_oz': 0.5, 'stackup': 'JLC06161H-3313'}
    for key, value in required.items():
        if order.get(key) != value:
            raise ValueError('input loss model requires %s=%s, got %s' % (key, value, order.get(key)))
    netlist = read(out / 'main.net')
    board = pcbnew.LoadBoard(str(out / 'main.kicad_pcb'))
    for pin, net in INPUT_PINS.items():
        if netlist.net(*pin) != net:
            raise ValueError('%s netlist: expected %s, got %s' % (pin, net, netlist.net(*pin)))
        fp = board.FindFootprintByReference(pin[0])
        if fp is None:
            raise ValueError('%s: missing PCB footprint' % (pin,))
        contacts = [pad for pad in fp.Pads() if pad.GetNumber() == pin[1]]
        if len(contacts) != 1 or contacts[0].GetNetname() != net:
            raise ValueError('%s: PCB pad/net differs from exported netlist' % (pin,))
    return board


def extract(board, cases):
    """{name: (mOhm, disagreement, Result at the finer pitch)}"""
    out = {}
    for name, net, src, snk, window in cases:
        runs = [cm.solve(board, net, src, snk, window, pitch, CORNER) for pitch in PITCHES]
        r = [x.milliohms for x in runs]
        out[name] = (max(r), abs(r[0] - r[1]) / max(r), runs[-1])
    return out


NECK_MAX_MM = 3.0      # a hot region longer than this counts as the body


def cut_density(amps):
    """Per-ampere sheet density at which the whole current, spread at that
    density, reaches RISE_LIMIT_C - 5 C on outer copper (IPC-2221B): above
    it a region is either a short neck (bounded as a fin) or the body."""
    lo, hi = 0.01, 100.0                       # equivalent width, mm
    for _ in range(60):
        w = (lo * hi) ** 0.5
        if cm.ipc_rise(amps, w * CORNER.outer_mm) > RISE_LIMIT_C - 5:
            lo = w
        else:
            hi = w
    return 1 / hi


def _components(mask):
    """4-connected components of a boolean grid: [(cells, (rows, cols))]."""
    import numpy as np
    seen = np.zeros_like(mask)
    out = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        stack, cells = [(r0, c0)], []
        seen[r0, c0] = True
        while stack:
            r, c = stack.pop()
            cells.append((r, c))
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < mask.shape[0] and 0 <= nc < mask.shape[1] and mask[nr, nc] and not seen[nr, nc]:
                    seen[nr, nc] = True
                    stack.append((nr, nc))
        out.append(cells)
    return out


def neck_rise(grid, cells, amps, t, pitch):
    """Peak self-heating (C) of a hot copper region above its surroundings:
    steady conduction in the copper sheet alone (k t per square), Joule heat
    J^2 rho / t per area from the extracted current density, every edge to
    other copper held at the surroundings' temperature, no loss to the board
    (an upper bound for the region)."""
    import numpy as np
    index = {rc: i for i, rc in enumerate(cells)}
    n = len(cells)
    g = cm.K_COPPER * t                               # W/K between neighbouring cells
    a = np.zeros((n, n))
    q = np.zeros(n)
    for i, (r, c) in enumerate(cells):
        j = grid[r, c] * amps                         # A per mm width
        q[i] = j * j * CORNER.rho / t * pitch * pitch  # W in the cell
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            k = index.get((nr, nc))
            if k is not None:
                a[i, i] += g
                a[i, k] -= g
            elif 0 <= nr < grid.shape[0] and 0 <= nc < grid.shape[1] and grid[nr, nc] > 0:
                a[i, i] += g                          # to the surrounding copper
    if not (a.diagonal() > 0).all():
        return float('inf')
    return float(np.linalg.solve(a, q).max())


def rises(result, amps):
    """(body rise, internal-k bound, worst neck rise above the body, worst barrel rise), C.

    Body: IPC-2221B for an equivalent trace carrying the whole current at
    the conductor's peak density, outside short necks. A neck is a connected
    region above cut_density() no longer than NECK_MAX_MM (a pad escape, the
    crowding round a via): its rise above the body is neck_rise()."""
    if not result.grids:
        raise ValueError('mesh result carries no current-density grids: the rise cannot be bounded')
    cut = cut_density(amps)
    body_j = {}
    necks = []
    for layer, (grid, near) in (result.grids or {}).items():
        outer = layer in ('F.Cu', 'B.Cu')
        t = CORNER.outer_mm if outer else CORNER.inner_mm
        free = grid > 0
        hot = free & (grid > cut)
        # the body is the copper away from the necks: a neck's own rise is
        # solved above its surroundings, which are within 0.5 mm of it
        halo = np.zeros_like(hot)
        jb = 0.0
        for cells in _components(hot):
            rows = [r for r, _ in cells]
            cols = [c for _, c in cells]
            length = (max(max(rows) - min(rows), max(cols) - min(cols)) + 1) * result.pitch
            if length > NECK_MAX_MM:
                jb = max(jb, float(max(grid[r, c] for r, c in cells)))
            else:
                necks.append(neck_rise(grid, cells, amps, t, result.pitch))
                for r, c in cells:
                    halo[r, c] = True
        for _ in range(int(math.ceil(0.5 / result.pitch))):
            halo = halo | np.roll(halo, 1, 0) | np.roll(halo, -1, 0) | np.roll(halo, 1, 1) | np.roll(halo, -1, 1)
        rest = free & ~hot & ~halo
        if rest.any():
            jb = max(jb, float(grid[rest].max()))
        body_j[layer] = (jb, outer, t)
    body = inner = 0.0
    for jb, outer, t in body_j.values():
        if jb > 1e-6:
            body = max(body, cm.ipc_rise(amps, t / jb, outer=True))
            inner = max(inner, cm.ipc_rise(amps, t / jb, outer=outer))
    barrel = 0.0
    for _, frac in result.via_amps:
        area = math.pi * ((0.3 + 2 * CORNER.barrel_mm) ** 2 - 0.3 ** 2) / 4
        barrel = max(barrel, cm.fin_rise(amps * frac, area, CORNER.board_mm, CORNER.rho))
    return body, inner, max(necks, default=0.0), barrel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, help='completed main-board receipt')
    args = parser.parse_args()
    c = Checks('MB-005 main input loop and fault-current copper rise (hw/power/main_input_heat.py)')
    try:
        board = inspect(args.out.resolve())
        pos = extract(board, POSITIVE)
        ret = extract(board, RETURN)
        outp = extract(board, OUTPUT)
    except (OSError, ValueError) as error:
        c.info('receipt/topology', str(error))
        c.check('I0', 'content-valid routed main board, input pin topology and closed copper', 0, 1, '>=', '',
                fmt='%d')
        return c.done()
    amps = d.insw_ilim()[2]
    for group in (pos, ret, outp):
        for name, (m, dis, r) in group.items():
            c.info(name, '%.3f mOhm (pitches %s mm disagree %.1f %%; %d cells)' %
                   (m, '/'.join('%g' % p for p in PITCHES), 100 * dis, r.cells))
    j1_f1 = max(pos['J1 A4B9 -> F1:1'][0], pos['J1 B4A9 -> F1:1'][0])
    f1_u2 = pos['F1:2 -> U2 IN'][0]
    ret_worst = max(m for m, _, _ in ret.values())
    loop = j1_f1 + f1_u2 + ret_worst + TRANSITIONS
    c.info('loop', 'positive %.3f + %.3f, return %.3f, solder/tails %.1f (allowance: %d joints x %.1f, '
           '%d tails x %.1f) = %.3f mOhm at %.0f C' % (j1_f1, f1_u2, ret_worst, TRANSITIONS, SOLDER_JOINTS,
                                                      SOLDER_JOINT_MOHM, J1_TAILS, J1_TAIL_MOHM, loop,
                                                      CORNER.temperature_c))
    c.info('fault corner', '%.3f A: %.1f mV across the board-side loop, %.0f mW in it' %
           (amps, amps * loop, amps ** 2 * loop))
    c.check('I1', 'board-side input loop at the hottest corner (the mated contacts are the cable\'s, '
            'USB Type-C R2.0 4.4.1)', loop, LOOP_LIMIT_MOHM, '<=', 'mOhm')
    worst_dis = max(dis for g in (pos, ret, outp) for _, dis, _ in g.values())
    c.check('I2', 'mesh pitch convergence (largest disagreement between %g and %g mm)' % PITCHES,
            100 * worst_dis, 10.0, '<=', '%')
    body_all = neck_all = barrel_all = inner_all = 0.0
    for group in (pos, ret, outp):
        for name, (_, _, r) in group.items():
            body, inner, neck, barrel = rises(r, amps)
            c.info(name + ' rise', 'body %.1f C (internal-k bound %.1f), terminal neck +%.1f, barrel %.2f C' %
                   (body, inner, neck, barrel))
            body_all, inner_all = max(body_all, body), max(inner_all, inner)
            neck_all, barrel_all = max(neck_all, body + neck), max(barrel_all, body + barrel)
    c.check('I3', 'full-current copper rise at %.3f A: body (IPC-2221B, the whole current at the peak '
            'density)' % amps, body_all, RISE_LIMIT_C, '<=', 'C')
    c.check('I4', 'full-current copper rise: terminal necks (body + neck bound)', neck_all, RISE_LIMIT_C,
            '<=', 'C')
    c.check('I5', 'full-current copper rise: via barrels (body + barrel bound)', barrel_all, RISE_LIMIT_C,
            '<=', 'C')
    return c.done()


if __name__ == '__main__':
    sys.exit(main())
