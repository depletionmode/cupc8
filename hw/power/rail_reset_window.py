#!/usr/bin/env python3
"""MB-051 screening model for an autonomous two-rail reset redesign.

This is a threshold/timing and netlist diagnostic, not a circuit simulation
or a claim that the proposed hardware has been built or routed.
"""

from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cosim.netlist import read

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
        if not any(ref == 'U13' for ref, _ in circuit.nets[net]):
            raise ValueError(f'{net}: expected TCA9555 control absent')
        if not any(ref.startswith('R') and circuit.components[ref][0] == '10k'
                   for ref, _ in circuit.nets[net]):
            raise ValueError(f'{net}: expected pull-up absent')
    return circuit


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/hw/main/main.net')
    netlist_gap(path)
    print(f'BASELINE BIND: {path}: MAX811T U6 monitors +3V3 only; '
          'six slot resets have independent 10k pull-ups and TCA9555 controls')
    print('3V3 ±5%% floor %.3f V; MAX811T cold/hot falling threshold 3.00..3.15 V' % THREEV3_MIN)
    if 3.00 < THREEV3_MIN:
        print('FAIL: MAX811T can release below the 3V3 valid floor by %.0f mV' %
              (1000 * (THREEV3_MIN - 3.00)))
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
    print('MB-051 OPEN: no fitted dual-rail circuit, cold-off clamps, remote-rail '
          'bounds or routed DRC evidence')
    return 1


if __name__ == '__main__':
    sys.exit(main())
