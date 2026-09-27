#!/usr/bin/env python3
"""Geometric counterexamples for the routed parallel-run screen."""
import sys
import unittest
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/tools'))
from crosstalk import Segment, parallel_runs, read_board


def seg(net, a, b, width=.1, layer='F.Cu'):
    return Segment(net, layer, a, b, width)


class CrosstalkTests(unittest.TestCase):
    def test_board_formats_and_missing_routes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'test.kicad_pcb'
            for net_table, net in [('(net 1 "a")', '1'), ('', '"a"')]:
                path.write_text('(kicad_pcb %s (segment (start 0 0) (end 12 0) '
                                '(width 0.1) (layer "F.Cu") (net %s)))' % (net_table, net))
                self.assertEqual(read_board(path), [seg('a', (0, 0), (12, 0))])
            for invalid in ['(kicad_pcb)', '(kicad_pcb (arc))']:
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    read_board(path)
            with self.assertRaises(ValueError):
                read_board(Path(d) / 'missing.kicad_pcb')

    def test_long_close_run(self):
        runs = parallel_runs([seg('a', (0, 0), (12, 0)), seg('b', (12, .25), (0, .25))])
        self.assertEqual(len(runs), 1)
        self.assertAlmostEqual(runs[0]['gap_mm'], .15)
        self.assertAlmostEqual(runs[0]['length_mm'], 12)

    def test_split_tracks_still_detected(self):
        self.assertEqual(len(parallel_runs([
            seg('a', (0, 0), (6, 0)), seg('a', (6, 0), (12, 0)),
            seg('b', (0, .25), (7, .25)), seg('b', (7, .25), (12, .25))])), 1)

    def test_safe_cases(self):
        base = seg('a', (0, 0), (12, 0))
        for other in [seg('a', (0, .25), (12, .25)),
                      seg('b', (0, .25), (12, .25), layer='B.Cu'),
                      seg('b', (0, .3), (12, .3)),
                      seg('b', (2, .25), (12, .25)),
                      seg('b', (0, -1), (12, 1))]:
            with self.subTest(other=other):
                self.assertEqual(parallel_runs([base, other]), [])

    def test_diagonal(self):
        self.assertEqual(len(parallel_runs([
            seg('a', (0, 0), (10, 10)), seg('b', (0, .3), (10, 10.3))])), 1)

    def test_disjoint_sections_do_not_sum(self):
        self.assertEqual(parallel_runs([
            seg('a', (0, 0), (20, 0)), seg('b', (0, .25), (6, .25)),
            seg('b', (8, .25), (14, .25))]), [])


if __name__ == '__main__':
    unittest.main()
