import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('spi_cascade', Path(__file__).parents[2] / 'hw/si/spi_cascade.py')
cascade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cascade)


class CascadeTiming(unittest.TestCase):
    def test_slow_legal_input_does_not_inherit_fast_fixture(self):
        t = [i * 1e-9 for i in range(31)]
        v = [i / 10 for i in range(31)]
        r = cascade.input_observation(t, v, 0., 30e-9, 'rise')
        self.assertTrue(r['recommended_rate_ok'])
        self.assertFalse(r['published_fast_fixture_observed'])

    def test_reentry_uses_last_crossing(self):
        t = [i * 1e-9 for i in range(7)]
        v = [0., 1., 2.2, 1.2, 2.3, 2.8, 3.]
        r = cascade.input_observation(t, v, 0., 6e-9, 'rise')
        self.assertEqual(r['input_vm_crossings'], 2)
        self.assertGreater(r['input_vm_last_ns'], 3.)

    def test_early_crossing_without_final_valid_level_fails(self):
        t = [i * 1e-9 for i in range(5)]
        r = cascade.input_observation(t, [0., 1., 2.2, 1.5, 1.5], 0., 4e-9, 'rise')
        self.assertFalse(r['complete'])
        self.assertFalse(r['recommended_rate_ok'])

    def test_actual_network_delay_cannot_disappear(self):
        self.assertAlmostEqual(cascade.anchored_upper(8., 11., 2.), 21.7)
        self.assertAlmostEqual(cascade.anchored_upper(8., 1., 2.), 12.7)

    def test_auto_cs_half_period_is_not_strict_pass(self):
        paths = {key: (0., 0.) for key in ('SCK', 'MOSI', 'CS')}
        r = cascade.timing_envelope(paths, held_lead_ns=1e9 / 6e6)
        self.assertFalse(r['published_cs_requirement_ok'])

    def test_opposed_path_alignment_and_unknown_esp(self):
        r = cascade.timing_envelope({'SCK': (0., 20.), 'MOSI': (0., 30.), 'CS': (0., 25.)})
        self.assertTrue(r['published_cs_requirement_ok'])
        self.assertAlmostEqual(r['received_cs_lead_lower_ns'], 1000 / 3 - 25)
        self.assertFalse(r['numeric_esp_setup_hold_response_qualified'])
        self.assertFalse(r['datasheet_only_guarantee'])

    def test_missing_or_invalid_path_fails_closed(self):
        with self.assertRaises(ValueError):
            cascade.timing_envelope({'SCK': (0., 1.)})
        with self.assertRaises(ValueError):
            cascade.anchored_upper(float('nan'), 1., 1.)


if __name__ == '__main__':
    unittest.main()
