#!/usr/bin/env python3
"""MB-051: the dual-rail reset qualifier, bound to the routed main-board receipt.

hw/power/reset_supervisor.py holds the circuit (REF3425, two OPA376
comparators, D7 into U6's ~MR, U19 clamping the six slot resets) and proves
its threshold windows from datasheet limits, with copper allowances between
each regulator and the loads. This script checks that the receipt's netlist
is that circuit, part for part and value for value; that the reset copper
is connected on the routed board; and it extracts the copper those
allowances stand for (+3V3: R7 to every chipset +3V3 pin and to the monitor's
tap; +1V2: R8 to every chipset +1V2 pin and to the monitor's tap), then
re-runs the windows with the extracted values.

    python3 hw/power/rail_reset_window.py [build/hw/main]
    python3 hw/power/rail_reset_window.py --spice [build/hw/main]   # + the ngspice sequences
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/si'))
sys.path.insert(0, str(HERE))
from cosim.netlist import read  # noqa: E402
import boardevidence  # noqa: E402
from boardcheck import check_report  # noqa: E402
import reset_supervisor as rs  # noqa: E402
from spice import Checks  # noqa: E402

# (ref, pin): net, from reset_supervisor's circuit
PINS = {
    ('U6', '4'): '/+3V3', ('U6', '1'): '/GND', ('U6', '2'): '/nPOR', ('U6', '3'): '/nMR',
    ('U7', '61'): '/nPOR',
    ('U17', '4'): '/+3V3', ('U17', '3'): '/+3V3', ('U17', '1'): '/GND', ('U17', '2'): '/GND',
    ('U17', '5'): '/VREF25', ('U17', '6'): '/VREF25',
    ('U18', '5'): '/+3V3', ('U18', '2'): '/GND', ('U18', '3'): '/MON33_P', ('U18', '4'): '/MON_T33',
    ('U18', '1'): '/MON33_OK',
    ('U20', '5'): '/+3V3', ('U20', '2'): '/GND', ('U20', '3'): '/MON12_P', ('U20', '4'): '/MON_T12',
    ('U20', '1'): '/MON12_OK',
    ('D7', '3'): '/nMR', ('D7', '1'): '/MON33_OK', ('D7', '2'): '/MON12_OK',
    ('U19', '14'): '/3V3_STBY', ('U19', '7'): '/GND',
    ('SW1', '1'): '/nMR',
}
for k, (a, y) in enumerate(((1, 2), (3, 4), (5, 6), (9, 8), (11, 10), (13, 12))):
    PINS[('U19', str(a))] = '/nPOR'
    PINS[('U19', str(y))] = '/SLOT%d_RST_n' % (k + 1)
    PINS[('J%d' % (11 + k), 'B9')] = '/SLOT%d_RST_n' % (k + 1)
    PINS[('U13', str(k + 4))] = '/SLOT%d_RST_n' % (k + 1)
# resistor: (ends, ohms)
RESISTORS = {
    'R110': ({'/VREF25', '/MON_T33'}, rs.R_L1), 'R111': ({'/MON_T33', '/MON_T12'}, rs.R_L2),
    'R112': ({'/MON_T12', '/GND'}, rs.R_L3), 'R113': ({'/+3V3', '/MON33_P'}, rs.R_T),
    'R114': ({'/MON33_P', '/GND'}, rs.R_BT), 'R115': ({'/MON33_OK', '/MON33_P'}, rs.R_F33),
    'R116': ({'/+1V2', '/MON12_P'}, rs.R_S), 'R117': ({'/MON12_OK', '/MON12_P'}, rs.R_F12),
    'R118': ({'/nPOR', '/GND'}, rs.R_NPOR_PD),
    'R7': ({'/3V3_BUCK', '/+3V3'}, 0.001), 'R8': ({'/1V2_LDO', '/+1V2'}, 0.001),
    'R49': ({'/+1V2', '/VCCPLL1'}, 100), 'R50': ({'/+1V2', '/VCCPLL0'}, 100),
    'R11': ({'/+1V2', '/Q1_B'}, 10e3), 'R100': ({'/+1V2', '/V1V2_SENSE'}, 1e3),
}
LCSC = dict([(ref, lcsc) for ref, (_, lcsc) in rs.PARTS.items()] +
            [('R110', rs.R_PREC[rs.R_L1]), ('R111', rs.R_PREC[rs.R_L2]), ('R112', rs.R_PREC[rs.R_L3]),
             ('R113', rs.R_PREC[rs.R_T]), ('R114', rs.R_PREC[rs.R_BT]),
             ('R115', rs.R_1PCT[rs.R_F33]), ('R116', rs.R_1PCT[rs.R_S]), ('R117', rs.R_1PCT[rs.R_F12])])
RESET_PATHS = [('nPOR', ('U6', '2'), [('U7', '61')] + [('U19', a) for a in ('1', '3', '5', '9', '11', '13')]),
               ('nMR', ('U6', '3'), [('D7', '3'), ('SW1', '1')])] + \
    [('SLOT%d_RST_n' % (k + 1), ('U19', y), [('J%d' % (11 + k), 'B9')])
     for k, y in enumerate(('2', '4', '6', '8', '10', '12'))]
PITCHES = (0.1, 0.07)       # resolve 0.15 mm escapes at the 80% width corner


def ohms(value):
    text = value.split()[0]
    if text.endswith('m'):
        return float(text[:-1]) * 1e-3
    scale = {'k': 1e3, 'K': 1e3, 'M': 1e6}.get(text[-1], 1.0)
    return float(text[:-1] if scale != 1.0 else text) * scale


def netlist_bind(path):
    circuit = read(path)
    if circuit.components.get('U6', (None,))[0] != 'MAX811TEUS':
        raise ValueError('U6 is not the MAX811T the qualifier drives')
    for pin, net in PINS.items():
        if circuit.net(*pin) != net:
            raise ValueError('%s.%s: expected %s, got %s' % (pin[0], pin[1], net, circuit.net(*pin)))
    for ref, (ends, value) in RESISTORS.items():
        res = next((r for r in circuit.resistors if r.ref == ref), None)
        if res is None or set(res.ends) != ends:
            raise ValueError('%s: expected between %s' % (ref, sorted(ends)))
        if abs(ohms(res.value) - value) > 1e-6 * value:
            raise ValueError('%s: value %s, the analysis has %g ohm' % (ref, res.value, value))
    return circuit


def bom_bind(out):
    import csv
    have = {}
    with (out / 'fab/bom.csv').open() as f:
        for row in csv.DictReader(f):
            for ref in row['Designator'].split(','):
                have[ref.strip()] = row['LCSC Part #']
    for ref, lcsc in LCSC.items():
        if have.get(ref) != lcsc:
            raise ValueError('%s: BOM has %s, the analysis has %s' % (ref, have.get(ref), lcsc))


def routed_paths(pcb):
    from ibis_bus import routed_distances
    measured = {}
    for net, source, targets in RESET_PATHS:
        distances = routed_distances(pcb, '/' + net, source, targets)
        for target in targets:
            length = distances.get('%s.%s' % target)
            if length is None:
                raise ValueError('%s: open copper %s.%s to %s.%s' % (net, *source, *target))
            measured['%s %s.%s' % (net, *target)] = length
    return measured


_BOARDS = {}
_GEOMETRY = {}


def _extract_pin(job):
    import pcbnew
    import copper_mesh as cm
    pcb, net, link, sink, window, pitch, solver = job[:7]
    probes = job[7] if len(job) > 7 else ()
    # A worker uses one immutable completed receipt; reuse its rasterized
    # copper between terminal pairs, without reusing a solved voltage field.
    if str(pcb) not in _BOARDS:
        _BOARDS[str(pcb)] = pcbnew.LoadBoard(str(pcb))
    board = _BOARDS[str(pcb)]
    result = cm.solve(board, net, [link], [sink], window, pitch, solver=solver,
                      geometry_cache=_GEOMETRY, probes=probes)
    if probes:
        print('PLL drive %s.%s at %g mm: %.10f mOhm; qualified transfers %s' %
              (*sink, pitch, result.milliohms, result.transfer_milliohms), flush=True)
    return net, sink, pitch, max(result.transfer_milliohms.values()) if probes else result.milliohms


def extract(pcb, workers=1, solver='cg'):
    """Worst driving-point resistances (ohm) from each link to the chipset's
    supply pins and to the monitor tap, all layers and zones, two pitches."""
    import pcbnew
    import copper_mesh as cm
    # Each invocation binds a fresh receipt, even if a caller rebuilt the
    # same path since the previous extraction in this Python process.
    _BOARDS.clear()
    _GEOMETRY.clear()
    board = pcbnew.LoadBoard(str(pcb))
    u7 = board.FindFootprintByReference('U7')
    from concurrent.futures import ProcessPoolExecutor, as_completed
    jobs = []
    for net, link, tap, window in (('/+3V3', ('R7', '2'), ('R113', '1'), (40.0, 20.0, 128.0, 160.0)),
                                   ('/+1V2', ('R8', '2'), ('R116', '1'), (85.0, 20.0, 131.0, 110.0))):
        sinks = [('U7', p.GetNumber()) for p in u7.Pads() if p.GetNetname() == net] + [tap]
        if net == '/+1V2':
            sinks += [('R49', '1'), ('R50', '1')]
        for sink in sinks:
            probes = tuple(s for s in sinks if s[0] == 'U7') + (tap,) if sink[0] in ('R49', 'R50') else ()
            jobs.extend((pcb, net, link, sink, window, pitch, solver, probes) for pitch in PITCHES)
    measured = {}
    failed = {}
    def record(job, result=None, error=None):
        _, net, _, sink, _, pitch, _ = job[:7]
        if error is not None:
            failed[(net, sink, pitch)] = str(error)
            print('mesh %s %s.%s at %g mm: unresolved: %s' % (net, *sink, pitch, error), flush=True)
        else:
            _, _, _, value = result
            print('mesh %s %s.%s at %g mm: %.10f mOhm' % (net, *sink, pitch, value), flush=True)
            measured.setdefault(net, {}).setdefault(sink, {})[pitch] = value
    if workers == 1:
        for job in jobs:
            try:
                record(job, _extract_pin(job))
            except ValueError as error:
                record(job, error=error)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_extract_pin, job): job for job in jobs}
            for future in as_completed(futures):
                try:
                    record(futures[future], future.result())
                except ValueError as error:
                    record(futures[future], error=error)
    # A narrow diagonal can disappear on one raster despite continuous
    # physical copper. Refine only affected terminals, sequentially to bound
    # memory; a real open or unconverged result still fails the same gate.
    pin_jobs = {(job[1], job[3]): job for job in jobs}
    for (net, sink), job in pin_jobs.items():
        pitches = measured.get(net, {}).get(sink, {})
        if all(p in pitches for p in PITCHES):
            r = [pitches[p] for p in PITCHES]
            if abs(r[0] - r[1]) / max(r) <= .10:
                continue
        if any('open copper' not in msg for (n, s, _), msg in failed.items() if (n, s) == (net, sink)):
            raise ValueError('mesh solver failed for %s %s.%s: %s' %
                             (net, *sink, [msg for (n, s, _), msg in failed.items() if (n, s) == (net, sink)]))
        fine = (.07, .05, .035, .025)
        pair = None
        for k, pitch in enumerate(fine):
            if pitch not in pitches:
                refined = (*job[:5], pitch, solver, *job[7:])
                record(refined, _extract_pin(refined))
                pitches = measured[net][sink]
            if k:
                pair = fine[k-1:k+1]
                r = [pitches[p] for p in pair]
                if abs(r[0] - r[1]) / max(r) <= .10:
                    break
        measured[net][sink] = {p: pitches[p] for p in pair}
        print('mesh refinement %s %s.%s: using %g/%g mm; strict 10%% convergence unchanged' %
              (net, *sink, *pair), flush=True)
    return summarize(measured)


def summarize(measured):
    """Keep physical load-pad and monitor driving-point resistances separate."""
    worst = {}
    for net, pins in measured.items():
        vals = []
        for sink, pitches in pins.items():
            r = list(pitches.values())
            vals.append((max(r) / 1000, sink, abs(r[0] - r[1]) / max(r)))
        worst[net] = max(v for v in vals if v[1][0] not in ('R113', 'R116'))
        worst[net + ' tap'] = max(v for v in vals if v[1][0] in ('R113', 'R116'))
        worst[net + ' pitch'] = max(v[2] for v in vals)
    return worst


def replay_mesh(pcb, log, audit):
    """Re-evaluate a completed numerical extraction without changing its graph.

    Audit records the original solver/model sources and immutable board inputs;
    this is an analysis cache, never a fabrication receipt. The normal receipt,
    netlist, BOM and DRC checks still run before this function is called.
    """
    import hashlib
    import re
    import pcbnew
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    meta = json.loads(audit.read_text())
    if meta['completed_exit_code'] != 0 or digest(log) != meta['log_sha256']:
        raise ValueError('mesh replay: incomplete or altered extraction log')
    for name in ('main.kicad_pcb', 'drc.json', 'main.net'):
        path = pcb.parent / name
        if digest(path) != meta['sha256'][str(path.resolve())]:
            raise ValueError('mesh replay: changed board input %s' % name)
    for name, path in meta['original_sources'].items():
        original = str((HERE / name).resolve())
        if digest(path) != meta['sha256'][original]:
            raise ValueError('mesh replay: original source audit mismatch %s' % name)
    if digest(HERE / 'copper_mesh.py') != meta['sha256'][str((HERE / 'copper_mesh.py').resolve())]:
        raise ValueError('mesh replay: copper solver changed; re-extract')
    measured, pairs = {}, {}
    for line in log.read_text().splitlines():
        match = re.fullmatch(r'mesh (\S+) (\S+)\.(\S+) at ([\d.]+) mm: ([\d.]+) mOhm', line)
        if match:
            net, ref, pin, pitch, value = match.groups()
            # Printed values have 10 decimal places in mOhm. Round upward
            # by half the final printed unit to preserve the upper bound.
            measured.setdefault(net, {}).setdefault((ref, pin), {})[float(pitch)] = float(value) + 5e-11
        match = re.fullmatch(r'mesh refinement (\S+) (\S+)\.(\S+): using ([\d.]+)/([\d.]+) mm; strict 10% convergence unchanged', line)
        if match:
            net, ref, pin, a, b = match.groups()
            pair = float(a), float(b)
            if pair not in ((.07, .05), (.05, .035), (.035, .025)):
                raise ValueError('mesh replay: unsupported refinement pair')
            pairs[(net, (ref, pin))] = pair
    board = pcbnew.LoadBoard(str(pcb))
    pads = board.FindFootprintByReference('U7').Pads()
    expected = {net: {('U7', p.GetNumber()) for p in pads if p.GetNetname() == net}
                for net in ('/+3V3', '/+1V2')}
    expected['/+3V3'].add(('R113', '1'))
    expected['/+1V2'].update((('R116', '1'), ('R49', '1'), ('R50', '1')))
    if set(measured) != set(expected) or any(set(measured[n]) != sinks for n, sinks in expected.items()):
        raise ValueError('mesh replay: supply/tap/PLL inventory changed or incomplete')
    for net, pins in measured.items():
        for sink, pitches in pins.items():
            pair = pairs.get((net, sink), PITCHES)
            pins[sink] = {p: pitches[p] for p in pair}
    return summarize(measured), meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', nargs='?', type=Path, default=ROOT / 'build/hw/main')
    parser.add_argument('--spice', action='store_true')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--solver', choices=('cg', 'sparse', 'amg'), default='cg')
    parser.add_argument('--mesh-log-replay', type=Path, help='reuse an audited completed extraction with the same board and solver')
    parser.add_argument('--mesh-audit', type=Path, help='input hashes and original sources for --mesh-log-replay')
    parser.add_argument('--future-slots', action='store_true', help='also require the future two-card load')
    args = parser.parse_args()
    out = args.out.resolve()
    c = Checks('MB-051 reset qualifier bound to the routed main board (hw/power/rail_reset_window.py)')
    try:
        boardevidence.validate('main', out)
        check_report(json.loads((out / 'drc.json').read_text()), 'drc')
        netlist_bind(out / 'main.net')
        bom_bind(out)
        lengths = routed_paths(out / 'main.kicad_pcb')
        if args.mesh_log_replay:
            if args.mesh_audit is None:
                raise ValueError('--mesh-log-replay requires --mesh-audit')
            cu, audit = replay_mesh(out / 'main.kicad_pcb', args.mesh_log_replay, args.mesh_audit)
            import hashlib
            old = audit['sha256'][str((HERE / 'reset_supervisor.py').resolve())]
            new = hashlib.sha256((HERE / 'reset_supervisor.py').read_bytes()).hexdigest()
            c.info('numerical replay audit', 'same board/solver; original model %s, current model %s; '
                   'original log %s' % (old, new, audit['log_sha256']))
        else:
            cu = extract(out / 'main.kicad_pcb', args.workers, args.solver)
    except (OSError, ValueError, KeyError) as error:
        c.info('receipt/topology', str(error))
        c.check('R0', 'receipt, netlist, BOM and routed reset copper match the analysed circuit', 0, 1, '>=', '',
                fmt='%d')
        return c.done()
    c.info('bound', '%s: U6 + REF3425 + 2 x OPA376 + D7 + U19 and every value/LCSC as reset_supervisor.py' % out)
    c.info('reset copper (mm)', ', '.join('%s %.1f' % (k, v) for k, v in sorted(lengths.items())))
    pin33, sink33, _ = cu['/+3V3']
    pin12, sink12, _ = cu['/+1V2']
    tap33 = cu['/+3V3 tap'][0]
    tap12 = cu['/+1V2 tap'][0]
    r33 = rs.effective_copper('/+3V3', pin33, tap33,
                             'slots 5-6 full' if args.future_slots else 'M1')
    r12 = rs.effective_copper('/+1V2', pin12, tap12)
    c.info('sense current', '+3V3 <= %.3f uA through %.3f mOhm; +1V2 <= %.3f uA through %.3f mOhm; '
           'sense branches carry their own current, not the FPGA load' %
           (1e6 * rs.sense_current_bounds()['/+3V3'], 1e3 * tap33,
            1e6 * rs.sense_current_bounds()['/+1V2'], 1e3 * tap12))
    c.info('extracted', '+3V3 R7:2 -> %s.%s %.2f mOhm; +1V2 R8:2 -> %s.%s %.2f mOhm (worst of the chipset '
           'qualified load targets, %g/%g mm pitches with affected paths refined through 0.025 mm)' %
           (*sink33, 1e3 * pin33, *sink12, 1e3 * pin12, *PITCHES))
    c.check('R1', '+3V3 copper, link to any chipset pin or the tap, vs the analysis allowance', 1e3 * r33,
            1e3 * rs.copper_limit_3v3('slots 5-6 full' if args.future_slots else 'M1'), '<=', 'mOhm')
    c.check('R2', '+1V2 copper, link to any chipset pin or the tap, vs the analysis allowance', 1e3 * r12,
            1e3 * rs.copper_limit_1v2(), '<=', 'mOhm')
    c.check('R3', 'mesh pitch convergence', 100 * max(cu['/+3V3 pitch'], cu['/+1V2 pitch']), 10.0, '<=', '%')
    rows = rs.margins(r33, r12)
    if not args.future_slots:
        future = next(row for row in rows if row[0] == '3V3 slots 5-6 full')
        c.info('future slots 5-6 (advisory)', 'low/high margins %.2f/%.2f mV; outside M1 load' %
               (1000 * future[6], 1000 * future[7]))
        rows = rs.m1_margins(r33, r12)
    for k, (name, lo, hi, fmin, rmax, fmax, mlo, mhi) in enumerate(rows):
        c.check('R%da' % (4 + k), '%s (extracted copper): asserts before any load leaves its range' % name,
                1000 * mlo, 1000 * rs.MARGIN_MIN, '>=', 'mV')
        c.check('R%db' % (4 + k), '%s (extracted copper): releases and never trips at the regulator low' % name,
                1000 * mhi, 1000 * rs.MARGIN_MIN, '>=', 'mV')
    if args.spice:
        import reset_sequence
        reset_sequence.run(c)
    return c.done()


if __name__ == '__main__':
    sys.exit(main())
