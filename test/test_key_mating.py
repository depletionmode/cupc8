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

    def test_umax_key_position_is_info_pointing_at_first_article_fit(self):
        # David, 2026-09-28: the 0.005 mm gap cannot beat JLC's +/-0.10 mm
        # edge tolerance on paper, so the position is qualified on real
        # boards (MECH-101); the static check reports it and does not fail.
        socket = fit.SOCKETS['C404113']
        note = fit.key_position_note(socket, fit.key_mating_margin(socket, *fit.CEM['key_w']))
        self.assertIn('0.005 mm', note)
        self.assertIn('+/-0.10 mm', note)
        self.assertEqual(fit.FIRST_ARTICLE_TEST, 'MECH-101')
        self.assertIn('first-article fit, MECH-101', note)
        self.assertFalse(hasattr(fit, 'key_position_check'))

    def test_socket_without_published_rib_tolerance_is_still_reported(self):
        socket = fit.SOCKETS['C19188869']        # SOFNG x4: nominal rib only
        self.assertNotIn('rib_plus', socket)
        note = fit.key_position_note(socket, 5.0)   # even a huge nominal gap
        self.assertIn('no published maximum key-rib width', note)
        self.assertIn('nominal only', note)
        self.assertNotIn('5.000 mm', note)          # a nominal margin is not quoted as if toleranced
        self.assertIn('MECH-101', note)

if __name__ == '__main__':
    unittest.main()
