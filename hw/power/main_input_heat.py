#!/usr/bin/env python3
"""MB-005: the main board's input loop, extracted from the routed receipt.

Requirement (David, 2026-09-28; doc/hardware/mb005-loop-requirement-derivation.md,
hw/power/design.py R_RECEPTACLE):

  - the board-side input loop -- positive copper J1 -> F1 -> U2, the GND
    return from the eFuse and its 5V_SYS input capacitors to J1, and the
    receptacle terminations, solder joints and layer transitions -- is at
    most 60 mOhm at the hottest corner. The mated VBUS/GND contacts are not
    in it: USB Type-C R2.0 4.4.1 counts them in the cable's IR-drop budget;
  - every full-current conductor rises at most 20 C at the eFuse's worst-case current limit
    maximum current limit, which it can carry indefinitely.

Resistance: copper_mesh.solve over every layer, zone fill, track, pad and
barrel of each net, at the derivation's corner (115 C; tracks at 80 % of
their drawn width; 24.9 / 11.4 um outer / inner copper; 15 um via wall;
1.76 mm board). Each J1 pad is taken alone as the source (the worst split
of the two contact groups), at two mesh pitches; the larger result counts.
Solder joints and the receptacle's tails are allowances (TRANSITIONS).

Temperature: each mandatory mesh pitch is evaluated at the worst-case current
limit. Connected hot regions no larger than NECK_MAX_MM are bounded by
copper-only conduction above the body's temperature; every other copper
cell, including the neck boundary, contributes to the IPC-2221B body bound.
The classification cutoff uses each actual layer thickness. The external k
policy remains unchanged on every layer; the internal-k bound is printed.
Via barrels use their extracted current fractions. Only genuine load-power
conductors receive the full current; control-pin routes remain reference
resistance/topology diagnostics.
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
    ('C3', '1'): '/5V_SYS', ('C5', '1'): '/5V_SYS', ('C3', '2'): '/GND', ('C5', '2'): '/GND', ('U3', '2'): '/GND',
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
REFINEMENT_PITCHES = (0.05, 0.035)
CONVERGENCE_LIMIT = 0.10

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
# U2:8 is the eFuse's control-circuit ground reference (TPS25947 §5,
# IQ max 610 uA, §6.5), not the load-current return. Keep its conservative
# resistance/reference extraction for I1/I2, but never force the full load
# through that stub for thermal qualification. C3/C5 shorted-capacitor
# returns and U3 power ground genuinely can carry the full eFuse limit.
# An external bench load at R4 returns at C3:2, as MB-109's local power
# connection does; remote slot branches retain their separate current limits.
THERMAL_RETURN_NAMES = frozenset(name for name, _, src, _, _ in RETURN
                                 if src != [('U2', '8')])

OUTPUT = [       # Power branches draw the full limit; U3 EN is a reference diagnostic
    ('U2 OUT -> R4:1', '/5V_SYS', [('U2', '6')], [('R4', '1')], (4, 146, 46, 168)),
    ('U2 OUT -> U3:1', '/5V_SYS', [('U2', '6')], [('U3', '1')], (4, 146, 46, 168)),
    ('U2 OUT -> U3:4', '/5V_SYS', [('U2', '6')], [('U3', '4')], (4, 146, 46, 168)),
    ('U2 OUT -> C3:1', '/5V_SYS', [('U2', '6')], [('C3', '1')], (4, 146, 46, 168)),
    ('U2 OUT -> C5:1', '/5V_SYS', [('U2', '6')], [('C5', '1')], (4, 146, 46, 168)),
]
# TLV62569PDDCR pins: 1=EN, 2=GND, 3=SW, 4=VIN (actual fitted C398365).
# EN tied to 5V_SYS remains checked for identity/resistance, but is not VIN.
THERMAL_OUTPUT_NAMES = frozenset(name for name, _, _, sinks, _ in OUTPUT
                                 if sinks != [('U3', '1')])



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


def extract(board, cases, solver='cg'):
    """Retain every mandatory/refined grid and its conservative resistance.

    Refine only to establish numerical confidence; never discard a coarse
    resistance or thermal overbound. Cache geometry only inside this call,
    during which the board is immutable; terminal currents are solved anew.
    """
    out, cache = {}, {}
    for name, net, src, snk, window in cases:
        runs = []
        for pitch in PITCHES + REFINEMENT_PITCHES:
            if len(runs) >= 2:
                last = [x.milliohms for x in runs[-2:]]
                if abs(last[0] - last[1]) / max(last) <= CONVERGENCE_LIMIT:
                    break
            runs.append(cm.solve(board, net, src, snk, window, pitch, CORNER,
                                 solver=solver, geometry_cache=cache))
        resistances = [x.milliohms for x in runs]
        last = resistances[-2:]
        out[name] = (max(resistances), abs(last[0] - last[1]) / max(last), runs)
    return out


def model_sources():
    paths = [Path(__file__), ROOT / 'hw/power/copper_mesh.py',
             ROOT / 'hw/power/polygon_raster.py', ROOT / 'hw/power/design.py']
    return {str(p.resolve()): boardevidence.digest(p) for p in paths}


def dump_results(path, receipt_dir, groups, status, model_hashes, solver='cg'):
    """Source/receipt-bound density arrays, every observed pitch, no release claim."""
    path = path.resolve()
    if path.is_relative_to(receipt_dir.resolve()):
        raise ValueError('thermal result dump must be outside the completed receipt directory')
    if model_sources() != model_hashes:
        raise ValueError('thermal model sources changed during qualification')
    boardevidence.validate('main', receipt_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays, cases = {}, []
    for group in groups:
        for name, (maximum, disagreement, runs) in group.items():
            meshes = []
            for r in runs:
                layers = {}
                for layer, (density, near) in r.grids.items():
                    key = 'grid_%d' % len(arrays)
                    arrays[key] = density
                    arrays[key + '_terminal'] = near
                    layers[layer] = {'density': key, 'terminal': key + '_terminal'}
                meshes.append({'pitch_mm': r.pitch, 'milliohms': r.milliohms,
                               'cells': r.cells, 'iterations': r.iterations,
                               'layers': layers, 'via_amps': r.via_amps})
            cases.append({'name': name, 'maximum_milliohms': maximum,
                          'last_pair_disagreement': disagreement, 'meshes': meshes})
    density_path = path.with_suffix('.npz')
    np.savez_compressed(density_path, **arrays)
    report = {'schema': 1, 'kind': 'receipt-bound-thermal-qualification-results',
              'manufacturing_release': False, 'gate_exit_status': status,
              'receipt': str(receipt_dir.resolve()),
              'receipt_sha256': boardevidence.digest(receipt_dir / 'evidence.json'),
              'pcb_sha256': boardevidence.digest(receipt_dir / 'main.kicad_pcb'),
              'model_sources': model_hashes,
              'density_file': str(density_path), 'density_sha256': boardevidence.digest(density_path),
              'solver': solver, 'python_version': sys.version, 'numpy_version': np.__version__,
              'current_a': d.insw_ilim()[2], 'rise_limit_c': RISE_LIMIT_C,
              'convergence_limit': CONVERGENCE_LIMIT, 'cases': cases}
    path.write_text(json.dumps(report, indent=2, default=lambda v: v.item() if isinstance(v, np.generic) else str(v)) + '\n')


NECK_MAX_MM = 3.0      # a hot region longer than this counts as the body


def cut_density(amps, thickness=None):
    """Per-ampere sheet density at which the whole current, spread at that
    density, reaches RISE_LIMIT_C - 5 C at the actual layer thickness (IPC-2221B
    external-k policy unchanged): above
    it a region is either a short neck (bounded as a fin) or the body."""
    thickness = CORNER.outer_mm if thickness is None else thickness
    lo, hi = 0.01, 100.0                       # equivalent width, mm
    for _ in range(60):
        w = (lo * hi) ** 0.5
        if cm.ipc_rise(amps, w * thickness) > RISE_LIMIT_C - 5:
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
    body_j = {}
    necks = []
    for layer, (grid, near) in (result.grids or {}).items():
        outer = layer in ('F.Cu', 'B.Cu')
        t = CORNER.outer_mm if outer else CORNER.inner_mm
        cut = cut_density(amps, t)
        free = grid > 0
        hot = free & (grid > cut)
        # Every non-neck cell, including the neck boundary, contributes to
        # the body bound. Removing a halo would understate its temperature.
        neck_mask = np.zeros_like(hot)
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
                    neck_mask[r, c] = True
        rest = free & ~neck_mask
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
    parser.add_argument('--solver', choices=('cg', 'sparse', 'amg'), default='cg')
    parser.add_argument('--dump-results', type=Path, help='JSON/NPZ result path outside the receipt directory')
    args = parser.parse_args()
    model_hashes = model_sources()
    c = Checks('MB-005 main input loop and fault-current copper rise (hw/power/main_input_heat.py)')
    try:
        board = inspect(args.out.resolve())
        pos = extract(board, POSITIVE, args.solver)
        ret = extract(board, RETURN, args.solver)
        outp = extract(board, OUTPUT, args.solver)
    except (OSError, ValueError) as error:
        c.info('receipt/topology', str(error))
        c.check('I0', 'content-valid routed main board, input pin topology and closed copper', 0, 1, '>=', '',
                fmt='%d')
        return c.done()
    amps = d.insw_ilim()[2]
    for group in (pos, ret, outp):
        for name, (m, dis, runs) in group.items():
            c.info(name, '%.3f mOhm (pitches %s mm; last pair disagree %.1f %%; %d cells)' %
                   (m, '/'.join('%g' % r.pitch for r in runs), 100 * dis, runs[-1].cells))
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
    c.check('I2', 'mesh convergence (last two observed pitches; all coarse overbounds retained)',
            100 * worst_dis, 100 * CONVERGENCE_LIMIT, '<=', '%')
    body_all = neck_all = barrel_all = inner_all = 0.0
    for group in (pos, ret, outp):
        for name, (_, _, runs) in group.items():
            if ((group is ret and name not in THERMAL_RETURN_NAMES) or
                    (group is outp and name not in THERMAL_OUTPUT_NAMES)):
                c.info(name + ' thermal scope', 'control-pin resistance diagnostic; not a full-current path')
                continue
            for r in runs:
                body, inner, neck, barrel = rises(r, amps)
                c.info(name + ' rise at %g mm' % r.pitch,
                       'body %.1f C (internal-k bound %.1f), terminal neck +%.1f, barrel %.2f C' %
                       (body, inner, neck, barrel))
                body_all, inner_all = max(body_all, body), max(inner_all, inner)
                neck_all, barrel_all = max(neck_all, body + neck), max(barrel_all, body + barrel)
    c.check('I3', 'full-current copper rise at %.3f A: body (IPC-2221B, the whole current at the peak '
            'density)' % amps, body_all, RISE_LIMIT_C, '<=', 'C')
    c.check('I4', 'full-current copper rise: terminal necks (body + neck bound)', neck_all, RISE_LIMIT_C,
            '<=', 'C')
    c.check('I5', 'full-current copper rise: via barrels (body + barrel bound)', barrel_all, RISE_LIMIT_C,
            '<=', 'C')
    status = c.done()
    if args.dump_results:
        dump_results(args.dump_results, args.out.resolve(), (pos, ret, outp), status, model_hashes, args.solver)
    return status


if __name__ == '__main__':
    sys.exit(main())
