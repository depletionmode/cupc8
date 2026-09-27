#!/usr/bin/env python3
"""Route mutations that must invalidate the HDMI D0 field-solver input."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/si'))
from openems_gpu_d0 import PAIR_GEOMETRY, completion_decay, routed_pair


def segment(name, a, b, width=.2, layer='F.Cu'):
    return '(segment (start %s %s) (end %s %s) (width %s) (layer "%s") (net "%s"))' % (
        *a, *b, width, layer, name)


def fixture():
    p = segment('/HD_D0P', (26.3, -27.9), (26.3, -30)) + segment(
        '/HD_D0P', (26.3, -30), (26.0, -33.74))
    n = segment('/HD_D0N', (27.1, -27.9), (27.1, -30)) + segment(
        '/HD_D0N', (27.1, -30), (27.0, -33.74))
    return '(kicad_pcb ' + p + n + ')'


class RouteInputTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gpu.kicad_pcb'
            path.write_text(text)
            return routed_pair(path)

    def test_accepts_both_connected_top_layer_routes(self):
        routes = self.load(fixture())
        self.assertEqual({name: len(parts) for name, parts in routes.items()},
                         {'/HD_D0P': 2, '/HD_D0N': 2})

    def test_each_tmds_pair_has_independent_connected_launches(self):
        for pair, (nets, _, ends) in PAIR_GEOMETRY.items():
            text = '(kicad_pcb ' + ' '.join(segment(net, *ends[net]) for net in nets) + ')'
            with self.subTest(pair=pair), tempfile.TemporaryDirectory() as directory:
                board = Path(directory) / 'gpu.kicad_pcb'
                board.write_text(text)
                self.assertEqual(set(routed_pair(board, pair)), set(nets))
                board.write_text(text.replace(f'(net "{nets[0]}")', '(net "/BROKEN")', 1))
                with self.assertRaises(ValueError):
                    routed_pair(board, pair)
                board.write_text(text.replace('(layer "F.Cu")', '(layer "B.Cu")', 1))
                with self.assertRaises(ValueError):
                    routed_pair(board, pair)
                board.write_text(text.replace('(kicad_pcb ',
                                             f'(kicad_pcb (via (at {ends[nets[0]][0][0]} -30) (net "{nets[0]}")) ', 1))
                with self.assertRaises(ValueError):
                    routed_pair(board, pair)
                first_end = ends[nets[0]][1]
                board.write_text(text.replace(f'(end {first_end[0]} {first_end[1]})',
                                              f'(end {first_end[0] + .1} {first_end[1]})', 1))
                with self.assertRaises(ValueError):
                    routed_pair(board, pair)

    def test_swapped_wire_and_via_are_rejected(self):
        source = fixture()
        for altered in (source.replace('(end 26.0 -33.74)', '(end 26.1 -33.74)'),
                        source.replace('(start 26.3 -30)', '(start 26.4 -30)'),
                        source.replace('(layer "F.Cu")', '(layer "B.Cu")', 1),
                        source.replace('(kicad_pcb ',
                                       '(kicad_pcb (via (at 26.3 -30) (net "/HD_D0P")) ', 1)):
            with self.subTest(altered=altered):
                with self.assertRaises(ValueError):
                    self.load(altered)

    def test_solver_completion_must_be_explicit(self):
        self.assertEqual(completion_decay('RunFDTD: end-criteria of -40.00dB reached after '
                                          '95484 timesteps (-40.01dB)'), -40.01)
        self.assertIsNone(completion_decay('RunFDTD: Warning: Max. number of timesteps '
                                           'was reached before the end-criteria of -40dB was reached'))
        self.assertIsNone(completion_decay('RunFDTD: end-criteria of -30.00dB reached after '
                                           '40000 timesteps (-30.01dB)'))


if __name__ == '__main__':
    unittest.main()
