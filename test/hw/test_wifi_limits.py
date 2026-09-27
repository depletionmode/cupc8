"""The WC-005 sensitivity scenarios must alter the actual transient deck."""
from pathlib import Path
import hashlib
import sys
import tarfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import buck
import design as d
import wifi_limits


class WifiLimits(unittest.TestCase):
    def test_routed_fixture_matches_recorded_inputs(self):
        archive = ROOT / 'test/hw/fixtures/wifi-power-route-20260927.tar.xz'
        expected = {
            'wifi.kicad_pcb': 'a03625fc088ddcedb99c7498ee02de18b73485eee8f73a291996f84700a3c0df',
            'wifi.net': '98648d1e9355414f08e8b784da948d4657126436c25e6c0a77a85fa702fb6979',
            'fab/order.json': '5f535efc038f922cb4e6fac27c0d23dc49f1f6bdc426011192ebd7803a814b59',
        }
        with tarfile.open(archive, 'r:xz') as bundle:
            self.assertEqual(set(bundle.getnames()), set(expected))
            for name, digest in expected.items():
                with bundle.extractfile(name) as member:
                    self.assertEqual(hashlib.sha256(member.read()).hexdigest(), digest)

    def test_esr_and_contact_reach_the_spice_elements(self):
        deck = buck.wifi_deck('worst', 0.038, 0.135, 0.123, esr=0.5, r_contact=0.4)
        for name in ('Rcesr1', 'Rcesr2', 'Rcesr3'):
            self.assertIn(name + ' ', deck)
            self.assertRegex(deck, r'(?m)^' + name + r' .* 0\.5$')
        self.assertRegex(deck, r'(?m)^Rground return 0 0\.523$')

    def test_rail_extrema_use_burst_low_and_startup_high_corners(self):
        time = [0, buck.T_STEP, (buck.T_STEP + buck.T_REL) / 2, buck.T_REL, buck.T_END]
        volts = [0, 3.2, 3.1, 3.2, 0]
        wave = (time, volts, [], [])
        nominal = d.buck_vout(d.WIFI_BUCK_R1, d.WIFI_BUCK_R2)
        minimum, maximum = wifi_limits.rail_extrema(wave)
        self.assertAlmostEqual(minimum, 3.1 * d.wifi_vout_range()[0] / nominal)
        self.assertAlmostEqual(maximum, 3.2 * d.wifi_vout_range()[1] / nominal)

    def test_overvoltage_fails_even_when_burst_minimum_passes(self):
        self.assertFalse(wifi_limits.within_limits((3.097, 3.665)))
        self.assertTrue(wifi_limits.within_limits((3.113, 3.560)))


if __name__ == '__main__':
    unittest.main()
