"""Local Wi-Fi heat budget retains a required board-coupling measurement."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
from thermal import wifi_coupling_budget


class WifiThermalBoard(unittest.TestCase):
    def test_more_route_resistance_reduces_coupling_headroom(self):
        base = wifi_coupling_budget(0.04, 0.16, 0.12)
        narrow = wifi_coupling_budget(0.04, 0.40, 0.30)
        self.assertGreater(base[1], 0)
        self.assertGreater(base[2], 0)
        self.assertGreater(base[3], narrow[3])
        self.assertGreater(narrow[0], base[0])


if __name__ == '__main__':
    unittest.main()
