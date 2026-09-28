"""tools/jlc_dfm.py: the geometry it measures with, and its report on a built
card (skipped when build/hw/gpu is absent)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import jlc_dfm as dfm  # noqa: E402

SQUARE = [(0, 0), (1, 0), (1, 1), (0, 1)]


def moved(poly, dx, dy=0):
    return [(x + dx, y + dy) for x, y in poly]


class Geometry(unittest.TestCase):
    def test_gap_between_pads(self):
        self.assertAlmostEqual(dfm.poly_gap(SQUARE, moved(SQUARE, 1.2)), 0.2)
        self.assertAlmostEqual(dfm.poly_gap(SQUARE, moved(SQUARE, 2, 2)), 2 ** 0.5)

    def test_overlap_is_zero(self):
        self.assertEqual(dfm.poly_gap(SQUARE, moved(SQUARE, 0.5)), 0.0)
        self.assertEqual(dfm.poly_gap(SQUARE, [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6)]), 0.0)

    def test_inside_and_area(self):
        self.assertTrue(dfm.inside((0.5, 0.5), SQUARE))
        self.assertFalse(dfm.inside((1.5, 0.5), SQUARE))
        self.assertAlmostEqual(dfm.area(moved(SQUARE, 3, 4)), 1.0)

    def test_distance_to_edge(self):
        edge = [((-5, -1), (5, -1))]
        self.assertAlmostEqual(dfm.poly_to_lines(SQUARE, edge), 1.0)


@unittest.skipUnless((ROOT / 'build/hw/gpu/fab/cpl.csv').exists(), 'build/hw/gpu not built')
class BuiltCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = dfm.audit(ROOT / 'build/hw/gpu')

    def test_finger_area_is_clear(self):
        f = self.r['fingers']
        self.assertEqual(f['silk_within_keepout'], [])
        self.assertEqual(f['vias_within_keepout'], [])
        self.assertEqual(f['fingers_without_mask_opening'], 0)
        self.assertGreater(f['nearest_parts'][0]['mm'], dfm.FINGER_KEEPOUT_MM)

    def test_single_sided_and_under_jlc_standard_minimum(self):
        self.assertEqual(self.r['bottom'], [])
        self.assertLess(min(self.r['size_mm']), 50)   # JLC gold-finger and PCBA minimums

    def test_rp2040_exposed_pad_is_windowpaned(self):
        ep = [p for p in self.r['big_pad_paste'] if p['pad'] == 'U1.57'][0]
        self.assertTrue(50 <= ep['paste_pct'] <= 80, ep)
        self.assertEqual(self.r['via_in_pad']['U1.57']['open_holes'], 1)


if __name__ == '__main__':
    unittest.main()
