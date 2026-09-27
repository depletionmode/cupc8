"""The WC-005 sensitivity scenarios must alter the actual transient deck."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import buck
import design as d
import wifi_limits


class WifiLimits(unittest.TestCase):
    def test_esr_and_contact_reach_the_spice_elements(self):
        deck = buck.wifi_deck('worst', 0.038, 0.135, 0.123, esr=0.5, r_contact=0.4)
        for name in ('Rcesr1', 'Rcesr2', 'Rcesr3'):
            self.assertIn(name + ' ', deck)
            self.assertRegex(deck, r'(?m)^' + name + r' .* 0\.5$')
        self.assertRegex(deck, r'(?m)^Rground return 0 0\.523$')

    def test_minimum_supply_uses_burst_and_dc_low_corner(self):
        time = [0, buck.T_STEP, (buck.T_STEP + buck.T_REL) / 2, buck.T_REL, buck.T_END]
        volts = [0, 3.2, 3.1, 3.2, 0]
        wave = (time, volts, [], [])
        nominal = d.buck_vout(d.WIFI_BUCK_R1, d.WIFI_BUCK_R2)
        want = 3.1 * d.wifi_vout_range()[0] / nominal
        self.assertAlmostEqual(wifi_limits.minimum_supply(wave), want)


if __name__ == '__main__':
    unittest.main()
