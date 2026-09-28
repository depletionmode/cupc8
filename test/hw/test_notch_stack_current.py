"""Synthetic geometry regressions for the receipt-bound card notch audit."""

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[2] / 'tools/notch_stack_current.py'
SPEC = importlib.util.spec_from_file_location('notch_stack_current', MODULE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class NotchStackGeometry(unittest.TestCase):
    def test_current_symmetric_stack_fails_rule(self):
        gaps = AUDIT.clearance(10, 13, .7, .7, 10.55, 12.45)
        self.assertAlmostEqual(gaps[0], .2)
        self.assertAlmostEqual(gaps[1], .2)
        self.assertLess(min(gaps), AUDIT.RULE_MM)

    def test_shifted_notch_cannot_improve_both_clearances(self):
        centered = AUDIT.clearance(10, 13, .7, .7, 10.55, 12.45)
        shifted = AUDIT.clearance(10, 13, .7, .7, 10.60, 12.50)
        self.assertAlmostEqual(sum(centered), sum(shifted))
        self.assertLess(min(shifted), min(centered))

    def test_fixed_pitch_cannot_meet_rule_at_cem_minima(self):
        gap = AUDIT.required_gap(AUDIT.CEM_NOTCH_MIN_MM,
                                 AUDIT.CEM_FINGER_MIN_MM,
                                 AUDIT.CEM_FINGER_MIN_MM)
        self.assertAlmostEqual(gap, 3.09)
        self.assertGreater(gap, AUDIT.CURRENT_PITCH_MAX_MM)
        best = (AUDIT.CURRENT_PITCH_MAX_MM-AUDIT.CEM_NOTCH_MIN_MM
                -AUDIT.CEM_FINGER_MIN_MM)/2
        self.assertAlmostEqual(best, .26)


if __name__ == '__main__':
    unittest.main()
