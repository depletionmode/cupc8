"""Socket-key tolerance checks that do not require a board build."""
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    'cupc8_mechanical_fit', Path(__file__).resolve().parents[1] / 'hw/mech/fit.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)


class KeyMatingTests(unittest.TestCase):
    def test_umax_drawing_key_barely_fits_cem_min_notch_when_centered(self):
        socket = fit.SOCKETS['C404113']
        margin = fit.key_mating_margin(socket, *fit.CEM['key_w'])
        self.assertAlmostEqual(margin, .005)
        self.assertGreater(margin, 0)
        self.assertLess(margin, fit.JLC_HIGH_PRECISION_EDGE_TOLERANCE)

    def test_mutated_key_or_notch_requires_positive_worst_case_margin(self):
        socket = dict(fit.SOCKETS['C404113'])
        socket['rib_plus'] = 0
        self.assertGreater(fit.key_mating_margin(socket, 1.90, .06), 0)
        socket['rib_plus'] = .07
        self.assertLess(fit.key_mating_margin(socket, 1.90, .06), 0)
        self.assertLess(fit.key_mating_margin(socket, 1.84, .06), 0)


if __name__ == '__main__':
    unittest.main()
