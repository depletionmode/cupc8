"""Native chiral footprint fixtures protect real top/bottom CPL projections."""
from pathlib import Path
import math
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import assembly_geometry as geometry
import kicadgen
import pcbnew


class NativeAssemblyGeometry(unittest.TestCase):
    def fixture(self, code, fpid, side, angle):
        record = yaml.safe_load((ROOT / 'hw/parts/easyeda' / (code + '.yaml')).read_text())
        turn = yaml.safe_load((ROOT / 'hw/parts/jlc_rotation.yaml').read_text())[fpid]
        board = pcbnew.BOARD()
        lib, name = fpid.split(':')
        fp = pcbnew.FootprintLoad(kicadgen.footprint_dir(lib), name)
        board.Add(fp)
        if side == 'Bottom':
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(25), pcbnew.FromMM(-17)))
        fp.SetOrientationDegrees(angle)
        actual = {p.GetNumber(): (pcbnew.ToMM(p.GetX()), pcbnew.ToMM(p.GetY()))
                  for p in fp.Pads() if p.GetNumber()}
        midpoint = geometry.midpoint(25, -17, angle, turn.get('offset'), side)
        rotation = geometry.rotation(angle, turn['rotation'], side)
        return board, actual, record, turn, midpoint, rotation

    def test_genuine_chiral_supplier_pads_match_native_on_both_sides(self):
        for code, fpid in [('C151890', 'jlc:SC-70-5_L2.1-W1.3-P0.65-LS2.1-BR'),
                           ('C7519', 'Package_TO_SOT_SMD:SOT-23-6')]:
            for side in ('Top', 'Bottom'):
                for angle in (0, 37, 90, 270):
                    with self.subTest(code=code, side=side, angle=angle):
                        board, actual, record, turn, midpoint, rotation = self.fixture(code, fpid, side, angle)
                        world = {n: (x, -y) for n, x, y in geometry.supplier_world(
                            record['pads'], rotation, *midpoint, side)}
                        self.assertEqual(set(actual), set(world))
                        self.assertLessEqual(max(math.dist(actual[n], world[n]) for n in actual), .2)

    def test_omitted_bottom_mirror_rejects_chiral_numbered_pads(self):
        board, actual, record, turn, midpoint, rotation = self.fixture(
            'C151890', 'jlc:SC-70-5_L2.1-W1.3-P0.65-LS2.1-BR', 'Bottom', 37)
        wrong = {n: (x, -y) for n, x, y in geometry.supplier_world(
            record['pads'], rotation, *midpoint, 'Top')}
        self.assertGreater(max(math.dist(actual[n], wrong[n]) for n in actual), .2)

    def test_added_bottom_correction_rejects_native_numbered_pads(self):
        board, actual, record, turn, midpoint, rotation = self.fixture(
            'C7519', 'Package_TO_SOT_SMD:SOT-23-6', 'Bottom', 37)
        self.assertEqual(turn['rotation'], 270)
        wrong = {n: (x, -y) for n, x, y in geometry.supplier_world(
            record['pads'], (37 + turn['rotation']) % 360, *midpoint, 'Bottom')}
        self.assertGreater(max(math.dist(actual[n], wrong[n]) for n in actual), .2)

    def test_invalid_side_and_nonfinite_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            geometry.rotation(0, 0, 'Front')
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                geometry.rotation(value, 0, 'Top')
            with self.assertRaises(ValueError):
                geometry.supplier_world([('1', value, 0)], 0, 0, 0, 'Top')


if __name__ == '__main__':
    unittest.main()
