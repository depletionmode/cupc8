#!/usr/bin/env python3
"""WC-006 rejects changed strap wiring and checks both ESP32-C3 boot modes."""

import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hw.cosim.netlist import Circuit
from hw.tools import strapcheck


def circuit():
    components = {ref: (value, ('Device', kind)) for ref, value, kind in (
        ('R1', '10k', 'R'), ('R2', '10k', 'R'), ('R3', '10k', 'R'),
        ('R4', '10k', 'R'), ('C5', '1u', 'C'))}
    pins = {}
    for ref, a, b in (
        ('R1', '/3V3', '/EN'), ('R2', '/3V3', '/BOOT'),
        ('R3', '/3V3', '/STRAP8'), ('R4', '/3V3', '/STRAP2'),
        ('C5', '/EN', '/GND')):
        pins[ref, '1'], pins[ref, '2'] = a, b
    pins.update({
        ('U1', '3'): '/3V3', ('U1', '8'): '/EN', ('U1', '5'): '/STRAP2',
        ('U1', '22'): '/STRAP8', ('U1', '23'): '/BOOT',
        ('J1', 'B9'): '/EN', ('J1', 'A18'): '/BOOT',
    })
    nets = {}
    for pin, net in pins.items():
        nets.setdefault(net, []).append(pin)
    return Circuit(components, nets, pins, ())


class Strapping(unittest.TestCase):
    def test_expected_wiring(self):
        self.assertEqual(strapcheck.topology(circuit()), (10000.0, 1e-6))

    def test_en_capacitor_removed_is_rejected(self):
        c = circuit()
        c.pins['C5', '1'] = '/3V3'
        with self.assertRaisesRegex(ValueError, 'C5 expected'):
            strapcheck.topology(c)

    def test_unexpected_driver_on_gpio8_is_rejected(self):
        c = circuit()
        c.nets['/STRAP8'].append(('J1', 'B16'))
        with self.assertRaisesRegex(ValueError, 'STRAP8 contains'):
            strapcheck.topology(c)

    def test_boot_pullup_removed_is_rejected(self):
        c = circuit()
        c.components['R2'] = ('100k', ('Device', 'R'))
        with self.assertRaisesRegex(ValueError, 'R2 expected'):
            strapcheck.topology(c)

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice unavailable')
    def test_reset_transient_both_boot_modes(self):
        for download in (False, True):
            crossing, sample = strapcheck.simulate(10000, 1e-6, download)
            self.assertGreater(crossing, 0.001)
            self.assertGreater(sample[0] - crossing, 0.003)
            self.assertGreater(sample[3], strapcheck.VIH)
            self.assertGreater(sample[4], strapcheck.VIH)
            self.assertLess(sample[2], strapcheck.VIL) if download else self.assertGreater(sample[2], strapcheck.VIH)


if __name__ == '__main__':
    unittest.main()
