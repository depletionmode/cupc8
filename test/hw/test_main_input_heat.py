"""The MB-005 input loss report rejects incomplete physical evidence."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import design as d
import main_input_heat as gate


class MainInputHeat(unittest.TestCase):
    def report(self, route):
        output = StringIO()
        with patch.object(sys, 'argv', ['main_input_heat.py', 'unused']), \
             patch.object(gate, 'inspect', return_value=route), redirect_stdout(output):
            status = gate.main()
        return status, output.getvalue()

    def test_route_loss_uses_eFuse_maximum_current(self):
        amps = d.insw_ilim()[2]
        millivolts, milliwatts = gate.losses(73.060, amps)
        self.assertAlmostEqual(millivolts, amps * 73.060)
        self.assertAlmostEqual(milliwatts, amps ** 2 * 73.060)
        self.assertGreater(milliwatts, 700)

    def test_over_budget_route_and_missing_physical_bounds_fail(self):
        status, report = self.report((37.129, 35.931))
        self.assertEqual(status, 1)
        self.assertIn('FAIL I1', report)
        for ident in ('I2', 'I3', 'I4'):
            self.assertIn('FAIL ' + ident, report)

    def test_optimistic_route_still_cannot_clear_evidence_gates(self):
        status, report = self.report((3.0, 4.0))
        self.assertEqual(status, 1)
        self.assertIn('pass I1', report)
        for ident in ('I2', 'I3', 'I4'):
            self.assertIn('FAIL ' + ident, report)

    def test_invalid_receipt_fails_before_route_report(self):
        output = StringIO()
        with patch.object(sys, 'argv', ['main_input_heat.py', 'unused']), \
             patch.object(gate, 'inspect', side_effect=ValueError('stale receipt')), \
             redirect_stdout(output):
            status = gate.main()
        self.assertEqual(status, 1)
        self.assertIn('FAIL I0', output.getvalue())
        self.assertNotIn('fault corner', output.getvalue())


if __name__ == '__main__':
    unittest.main()
