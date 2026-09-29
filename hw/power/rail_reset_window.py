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
}
LCSC = dict([(ref, lcsc) for ref, (_, lcsc) in rs.PARTS.items()] +
            [('R110', rs.R_PREC[rs.R_L1]), ('R111', rs.R_PREC[rs.R_L2]), ('R112', rs.R_PREC[rs.R_L3]),
             ('R113', rs.R_PREC[rs.R_T]), ('R114', rs.R_PREC[rs.R_BT]),
             ('R115', rs.R_1PCT[rs.R_F33]), ('R116', rs.R_1PCT[rs.R_S]), ('R117', rs.R_1PCT[rs.R_F12])])
RESET_PATHS = [('nPOR', ('U6', '2'), [('U7', '61')] + [('U19', a) for a in ('1', '3', '5', '9', '11', '13')]),
               ('nMR', ('U6', '3'), [('D7', '3'), ('SW1', '1')])] + \
    [('SLOT%d_RST_n' % (k + 1), ('U19', y), [('J%d' % (11 + k), 'B9')])
     for k, y in enumerate(('2', '4', '6', '8', '10', '12'))]
PITCHES = (0.25, 0.18)


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


def extract(pcb):
    """Worst driving-point resistances (ohm) from each link to the chipset's
    supply pins and to the monitor tap, all layers and zones, two pitches."""
    import pcbnew
    import copper_mesh as cm
    board = pcbnew.LoadBoard(str(pcb))
    u7 = board.FindFootprintByReference('U7')
    worst = {}
    for net, link, tap, window in (('/+3V3', ('R7', '2'), ('R113', '1'), (40.0, 20.0, 128.0, 160.0)),
                                   ('/+1V2', ('R8', '2'), ('R116', '1'), (85.0, 30.0, 131.0, 110.0))):
        sinks = [('U7', p.GetNumber()) for p in u7.Pads() if p.GetNetname() == net] + [tap]
        vals = []
        for sink in sinks:
            r = [cm.solve(board, net, [link], [sink], window, pitch).milliohms for pitch in PITCHES]
            vals.append((max(r) / 1000, sink, abs(r[0] - r[1]) / max(r)))
        worst[net] = max(vals)
        worst[net + ' pitch'] = max(v[2] for v in vals)
    return worst


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', nargs='?', type=Path, default=ROOT / 'build/hw/main')
    parser.add_argument('--spice', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    c = Checks('MB-051 reset qualifier bound to the routed main board (hw/power/rail_reset_window.py)')
    try:
        boardevidence.validate('main', out)
        check_report(json.loads((out / 'drc.json').read_text()), 'drc')
        netlist_bind(out / 'main.net')
        bom_bind(out)
        lengths = routed_paths(out / 'main.kicad_pcb')
        cu = extract(out / 'main.kicad_pcb')
    except (OSError, ValueError, KeyError) as error:
        c.info('receipt/topology', str(error))
        c.check('R0', 'receipt, netlist, BOM and routed reset copper match the analysed circuit', 0, 1, '>=', '',
                fmt='%d')
        return c.done()
    c.info('bound', '%s: U6 + REF3425 + 2 x OPA376 + D7 + U19 and every value/LCSC as reset_supervisor.py' % out)
    c.info('reset copper (mm)', ', '.join('%s %.1f' % (k, v) for k, v in sorted(lengths.items())))
    r33, sink33, _ = cu['/+3V3']
    r12, sink12, _ = cu['/+1V2']
    c.info('extracted', '+3V3 R7:2 -> %s.%s %.2f mOhm; +1V2 R8:2 -> %s.%s %.2f mOhm (worst of the chipset '
           'pins and the monitor tap, %g/%g mm pitches)' % (*sink33, 1e3 * r33, *sink12, 1e3 * r12, *PITCHES))
    c.check('R1', '+3V3 copper, link to any chipset pin or the tap, vs the analysis allowance', 1e3 * r33,
            1e3 * rs.CU33_MAX, '<=', 'mOhm')
    c.check('R2', '+1V2 copper, link to any chipset pin or the tap, vs the analysis allowance', 1e3 * r12,
            1e3 * rs.CU12_MAX, '<=', 'mOhm')
    c.check('R3', 'mesh pitch convergence', 100 * max(cu['/+3V3 pitch'], cu['/+1V2 pitch']), 10.0, '<=', '%')
    for k, (name, lo, hi, fmin, rmax, fmax, mlo, mhi) in enumerate(rs.margins(r33, r12)):
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
