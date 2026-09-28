"""Mutations of KiCad GND fills and stitching-via return paths."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
from wifi_ground import compare, compare_card_edge, estimate


def zone(layer, lo, hi):
    return (f'(zone (net "/GND") (layer "{layer}") '
            f'(filled_polygon (layer "{layer}") (pts '
            f'(xy {lo} 0) (xy {hi} 0) (xy {hi} 4) (xy {lo} 4))))')


def fixture(path, second_via=True, fill=True):
    parts = ['(kicad_pcb']
    for ref, x, y in [('U1', 1, 1), ('C2', 8, 1), ('C3', 8, 3), ('U2', 9, 3)]:
        pin = '2' if ref != 'U1' else '1'
        parts.append(f'(footprint "X" (at {x} {y}) (property "Reference" "{ref}") '
                     f'(pad "{pin}" smd rect (at 0 0) (size 0.8 0.8) '
                     '(layers "F.Cu") (net "/GND")))')
    parts.append('(footprint "X" (at 9 1) (property "Reference" "J1") '
                 '(pad "A3" smd rect (at 0 0) (size 0.8 0.8) '
                 '(layers "B.Cu") (net "/GND")) '
                 '(pad "B3" smd rect (at 0 0) (size 0.8 0.8) '
                 '(layers "F.Cu") (net "/GND")))')
    if fill:
        parts.extend((zone('F.Cu', 0, 3), zone('F.Cu', 7, 10), zone('B.Cu', 0, 10)))
    else:
        parts.extend((zone('F.Cu', 0, 3), zone('B.Cu', 0, 10).replace('filled_polygon', 'polygon')))
    parts.append('(via (at 2 2) (size 0.8) (layers "F.Cu" "B.Cu") (net "/GND"))')
    if second_via:
        parts.append('(via (at 8 2) (size 0.8) (layers "F.Cu" "B.Cu") (net "/GND"))')
    parts.append(')')
    path.write_text(' '.join(parts))


class WifiGround(unittest.TestCase):
    def test_two_layer_fill_and_vias(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / 'wifi.kicad_pcb'
            fixture(board)
            resistance, count, cells = estimate(board)
            self.assertGreater(resistance, 0)
            self.assertEqual(count, 2)
            self.assertTrue(all(cells))
            scenario, coarse, fine, discrepancy = compare(board)
            self.assertEqual(scenario, max(coarse[0], fine[0]))
            self.assertLess(discrepancy, 0.1)  # fixed physical corridor width
            fixture(board, second_via=False)
            with self.assertRaisesRegex(ValueError, 'does not connect'):
                estimate(board)
            fixture(board, fill=False)
            with self.assertRaisesRegex(ValueError, 'no saved fill'):
                estimate(board)

    def test_j1_return_requires_routed_fill_and_cross_layer_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / 'wifi.kicad_pcb'
            fixture(board)
            # The production extractor requires all fitted finger contacts.
            # Patch only the pin list in this four-pad synthetic fixture.
            from unittest.mock import patch
            with patch('wifi_ground.CARD_EDGE_GND', {'A': ('A3',), 'B': ('B3',)}):
                paths, _, _, errors = compare_card_edge(board)
                self.assertGreater(paths['esp_to_J1_A'], 0)
                self.assertGreater(paths['esp_to_J1_B'], 0)
                self.assertLess(max(errors.values()), 0.1)
                fixture(board, second_via=False)
                with self.assertRaisesRegex(ValueError, 'does not connect'):
                    compare_card_edge(board)


if __name__ == '__main__':
    unittest.main()
