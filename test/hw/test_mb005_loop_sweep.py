"""The MB-005 loop sweep finds each check's edge without moving the assumption."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import design as d
import mb005_loop_sweep as sweep


class LoopSweep(unittest.TestCase):
    def test_current_assumption_passes_and_is_restored(self):
        before = d.R_RECEPTACLE
        got = sweep.fast(before)
        self.assertEqual(d.R_RECEPTACLE, before)
        self.assertTrue(all(row[0] for row in got.values()), [k for k, v in got.items() if not v[0]])

    def test_edges_bracket_pass_and_fail(self):
        found, _ = sweep.limits(sweep.fast)
        finite = {k: r for k, r in found.items() if r not in (None, float('inf'))}
        binding = min(finite, key=finite.get)
        self.assertEqual(binding, 'POW-006 B5')
        edge = finite[binding]
        self.assertGreater(edge, d.R_RECEPTACLE)
        self.assertTrue(sweep.fast(edge - 1e-4)[binding][0])
        self.assertFalse(sweep.fast(edge + 1e-4)[binding][0])

    def test_ipc2221_fit(self):
        # IPC-2221B outer: a 10 mil, 1 oz trace carries ~0.88 A at a 10 C rise
        self.assertAlmostEqual(sweep.ipc2221_rise(0.885, 0.254, 34.8), 10.0, delta=0.2)
        self.assertGreater(sweep.ipc2221_rise(1.0, 0.254, 34.8, internal=True),
                           sweep.ipc2221_rise(1.0, 0.254, 34.8))


if __name__ == '__main__':
    unittest.main()
