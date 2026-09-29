"""External RILM corners must be included in eFuse current guarantees."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/power'))
import design as d


class InputCurrentLimit(unittest.TestCase):
    def test_room_temperature_accounts_for_resistor_tolerance(self):
        lo, nominal, hi = d.insw_ilim(resistor_temp_c=25)
        self.assertAlmostEqual(nominal, 3340 / 1130)
        self.assertAlmostEqual(lo, (3340 / (1130 * 1.01)) * 0.888)
        self.assertAlmostEqual(hi, (3340 / (1130 * 0.99)) * 1.087)
        self.assertGreater(hi, 3.245)

    def test_full_rated_temperature_range_bounds_room_and_cold(self):
        lo, _, hi = d.insw_ilim()
        self.assertAlmostEqual(lo, 3340 * 0.888 / (1130 * 1.01 * 1.013))
        self.assertAlmostEqual(hi, 3340 * 1.087 / (1130 * 0.99 * 0.987))
        self.assertGreater(hi, 3.288)
        self.assertLess(hi, 3.3)
        for temperature in (-55, -40, 25, 115, 125, 155):
            corners = d.insw_ilim(resistor_temp_c=temperature)
            self.assertLessEqual(lo, corners[0])
            self.assertGreaterEqual(hi, corners[2])
        with self.assertRaises(ValueError):
            d.insw_ilim(resistor_temp_c=156)


if __name__ == '__main__':
    unittest.main()
