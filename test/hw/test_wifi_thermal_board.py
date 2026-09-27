"""Local Wi-Fi heat budget retains a required board-coupling measurement."""
from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
import boardevidence
import thermal
from thermal import wifi_coupling_budget, wifi_external_allowance, wifi_thermal_terms


class WifiThermalBoard(unittest.TestCase):
    def test_more_route_resistance_reduces_coupling_headroom(self):
        base = wifi_coupling_budget(0.04, 0.16, 0.12)
        narrow = wifi_coupling_budget(0.04, 0.40, 0.30)
        self.assertGreater(base[1], 0)
        self.assertGreater(base[2], 0)
        self.assertGreater(base[3], narrow[3])
        self.assertGreater(narrow[0], base[0])

    def test_contact_heat_and_external_transfer_reduce_esp_headroom(self):
        terms = wifi_thermal_terms(0.0380082176, 0.1346646075, 0.12344)
        internal_w, copper_w, esp_w, contact_w_per_ohm, rise_budget_c = terms
        self.assertGreater(internal_w, 0)
        self.assertGreater(copper_w, 0)
        self.assertAlmostEqual(esp_w, 1.26)
        self.assertAlmostEqual(rise_budget_c, 60)
        self.assertAlmostEqual(contact_w_per_ohm * 0.33, 0.04236, places=4)
        base = wifi_external_allowance(terms, 0, 188.2, 188.2, 188.2)
        with_contact = wifi_external_allowance(terms, 0.33, 188.2, 188.2, 188.2)
        self.assertAlmostEqual(base, 34.4291669, places=5)
        self.assertLess(with_contact, base)
        self.assertAlmostEqual((base - with_contact) * esp_w,
                               0.33 * contact_w_per_ohm * 188.2)

    def test_external_heat_requires_independent_transfer_coefficients(self):
        terms = wifi_thermal_terms(0.04, 0.16, 0.12)
        no_transfer = wifi_external_allowance(terms, 0.2, 0, 0, 0)
        coupled = wifi_external_allowance(terms, 0.2, 188.2, 188.2, 188.2)
        self.assertGreater(no_transfer, coupled)
        with self.assertRaises(ValueError):
            wifi_external_allowance(terms, -0.1, 188.2, 188.2, 188.2)

    def test_thermal_report_rejects_drc_finding_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / 'drc.json').write_text(json.dumps({
                'included_severities': ['error', 'warning', 'exclusion'],
                'violations': [{'description': 'open return'}],
                'unconnected_items': [], 'schematic_parity': [],
            }))
            with patch.object(boardevidence, 'validate'):
                with self.assertRaisesRegex(ValueError, 'drc has 1 findings'):
                    thermal.wifi_card(out)


if __name__ == '__main__':
    unittest.main()
