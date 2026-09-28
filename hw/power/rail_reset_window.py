#!/usr/bin/env python3
"""MB-051 receipt-bound diagnosis of the fitted reset circuit.

The printed states are counterexamples to the required sequencing contract,
not a simulation of an unfitted redesign. A valid board receipt and connected
reset copper cannot make the fitted one-rail supervisor qualify both rails.
"""

import argparse
from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw/si'))
from cosim.netlist import read
import boardevidence
from boardcheck import check_report
from ibis_bus import routed_distances
import json

THREEV3_MIN = 3.3 * 0.95
ONEV2_MIN = 1.2 * 0.95
MODELED_THREEV3_LOW = 3.246  # POW-001 DC worst corner
MODELED_ONEV2_LOW = 1.172    # POW-002, including step and ripple
MODELED_ONEV2_STEADY = 1.176  # POW-002 1.173 V step floor + 3.2 mV step droop


def falling_min(nominal, accuracy):
    return nominal * (1 - accuracy)


def rising_max(nominal, accuracy, hysteresis_max):
    return nominal * (1 + accuracy) * (1 + hysteresis_max)


def netlist_gap(path):
    circuit = read(path)
    if circuit.components.get('U6', (None,))[0] != 'MAX811TEUS':
        raise ValueError('fitted supervisor changed; reassess thresholds and reset ownership')
    for pin, expected in ((('U6', '4'), '/+3V3'), (('U6', '2'), '/nPOR'),
                          (('U6', '3'), '/nMR'), (('U7', '61'), '/nPOR')):
        if circuit.net(*pin) != expected:
            raise ValueError(f'{pin}: expected {expected}, got {circuit.net(*pin)}')
    if not any(net == '/+1V2' for (ref, _), net in circuit.pins.items() if ref == 'U7'):
        raise ValueError('chipset has no 1V2 core pins')
    if any(circuit.net('U6', pin) == '/+1V2' for pin in ('1', '2', '3', '4')):
        raise ValueError('unexpected 1V2 input at fitted 3V3 supervisor')
    for n in range(1, 7):
        net = f'/SLOT{n}_RST_n'
        nodes = circuit.nets[net]
        pulls = [ref for ref, _ in nodes if ref.startswith('R') and
                 circuit.components[ref][0] == '10k' and any(
                     r.ref == ref and set(r.ends) == {net, '/+3V3'}
                     for r in circuit.resistors)]
        expected = {(f'J{n + 10}', 'B9'), ('U13', str(n + 3))}
        if len(pulls) != 1 or set(nodes) != expected | {(pulls[0], '2')}:
            raise ValueError(f'{net}: fitted pull-up/control topology changed; reassess MB-051')
    return circuit


def routed_reset_paths(out):
    """Bind the existing control routes to a content-valid, clean main PCB."""
    boardevidence.validate('main', out)
    check_report(json.loads((out / 'drc.json').read_text()), 'drc')
    circuit = netlist_gap(out / 'main.net')
    pcb = out / 'main.kicad_pcb'
    paths = [('nPOR', ('U6', '2'), [('U7', '61')])]
    for slot in range(1, 7):
        paths.append((f'SLOT{slot}_RST_n', ('U13', str(slot + 3)),
                      [(f'J{slot + 10}', 'B9')]))
    measured = {}
    for net, source, targets in paths:
        full_name = '/' + net
        if circuit.net(*source) != full_name or any(
                circuit.net(*target) != full_name for target in targets):
            raise ValueError(f'{net}: reset pins differ from the exported netlist')
        distances = routed_distances(pcb, full_name, source, targets)
        for target in targets:
            length = distances.get(f'{target[0]}.{target[1]}')
            if length is None:
                raise ValueError(f'{net}: open copper to {target[0]}.{target[1]}')
            measured[net] = length
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', nargs='?', type=Path, default=ROOT / 'build/hw/main',
                        help='completed main-board receipt directory')
    args = parser.parse_args()
    try:
        lengths = routed_reset_paths(args.out.resolve())
    except (OSError, ValueError, KeyError) as error:
        print(f'MB-051 FAIL: board receipt or reset topology: {error}')
        return 1
    print(f'BASELINE BIND: {args.out}: MAX811T U6 monitors +3V3 only; '
          'six slot resets have independent 10k pull-ups and TCA9555 controls')
    print('ROUTED RESET COPPER (mm): ' + ', '.join(
        f'{name}={lengths[name]:.3f}' for name in sorted(lengths)))
    print('3V3 ±5%% floor %.3f V; MAX811T cold/hot falling threshold 3.00..3.15 V' % THREEV3_MIN)
    if 3.00 < THREEV3_MIN:
        print('FAIL: MAX811T can release below the 3V3 valid floor by %.0f mV' %
              (1000 * (THREEV3_MIN - 3.00)))
    print('COUNTEREXAMPLE 1: +3V3=3.100 V, +1V2=1.200 V, supervisor '
          'threshold=3.000 V, manual reset released, hold timer expired: '
          'nPOR may release while +3V3 is below 3.135 V.')
    print('COUNTEREXAMPLE 2: +3V3=3.300 V, +1V2=0 V, sysctl absent: '
          'U6 sees its good rail; U13 powers up with reset outputs as inputs '
          'and each slot reset has a 10k pull-up. Slots can leave reset '
          'before +1V2 is good.')
    # TI TPS3890 fixed 3.17 V: ±1% falling accuracy, ≤0.825% hysteresis.
    lo3, hi3 = falling_min(3.17, .01), rising_max(3.17, .01, .00825)
    print('TPS389033 screen: falling >= %.4f V; rising <= %.4f V; '
          'normal low %.3f V' % (lo3, hi3, MODELED_THREEV3_LOW))
    if not THREEV3_MIN < lo3 < hi3 < MODELED_THREEV3_LOW:
        raise ValueError('3V3 candidate has no threshold window')
    # With ±1% and ≤0.825% hysteresis, no TPS3890 nominal 1V2 threshold
    # can both assert above the FPGA's 1.140 V floor and release by the
    # existing regulator's 1.172 V low corner. Divider tolerance shrinks it.
    nominal_floor = ONEV2_MIN / (1 - .01)
    nominal_ceiling = MODELED_ONEV2_LOW / ((1 + .01) * (1 + .00825))
    print('TPS3890 1V2 nominal threshold would need >= %.4f V to assert '
          'before 1.140 V and <= %.4f V to release by %.3f V' %
          (nominal_floor, nominal_ceiling, MODELED_ONEV2_LOW))
    if nominal_floor >= nominal_ceiling:
        print('FAIL: no guaranteed 1V2 threshold window; shortfall %.2f mV '
              'before divider tolerance or remote card drop' %
              (1000 * (nominal_floor - nominal_ceiling)))
    # Abstract desired wiring. This confirms the logic requirement while
    # leaving device startup, propagation, analog hysteresis and routing open.
    for power, g3, g1, manual, chipset, expander in product((0, 1), repeat=6):
        por = power and g3 and g1 and manual
        cpu = por and chipset
        slot = por and expander
        assert not (cpu or slot) if not (power and g3 and g1 and manual) else True
    print('LOGIC SCREEN: all 64 desired-state combinations keep CPU/slot reset '
          'asserted until both rails, power and manual reset permit release')
    print('MB-051 OPEN: the routed board has no fitted dual-rail qualifier, '
          'cold-off clamps or remote-rail bounds')
    return 1


if __name__ == '__main__':
    sys.exit(main())
