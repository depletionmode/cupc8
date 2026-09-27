"""Mutation checks for the fabrication evidence gate."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hw' / 'tools'))
import fabcheck
import boardevidence


class FabCheckTests(unittest.TestCase):
    def test_gerber_geometry_detects_mutated_coordinate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            path.write_text('%FSLAX46Y46*%\n%MOMM*%\nX1000000Y2000000D02*\nM02*\n')
            original = fabcheck.gerber_geometry(path)
            path.write_text(path.read_text().replace('Y2000000', 'Y3000000'))
            self.assertNotEqual(original, fabcheck.gerber_geometry(path))
            path.write_text(path.read_text().replace('M02*', ''))
            with self.assertRaisesRegex(ValueError, 'end marker'):
                fabcheck.gerber_geometry(path)

    def test_drill_shift_and_missing_hit_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            drill = fab / 'board.drl'
            drill.write_text('M48\nMETRIC\nT1C0.300\n%\nG90\nG05\nT1\nX1.0Y2.0\nM30\n')
            with patch.object(fabcheck, 'board_holes', return_value=Counter({(1.0, 2.0, .3): 1})):
                self.assertEqual(fabcheck.check_drills(object(), fab), 1)
                drill.write_text(drill.read_text().replace('X1.0Y2.0', 'X1.2Y2.0'))
                with self.assertRaisesRegex(ValueError, 'drill-to-pad/via mismatch'):
                    fabcheck.check_drills(object(), fab)
                drill.write_text(drill.read_text().replace('X1.2Y2.0\n', ''))
                with self.assertRaisesRegex(ValueError, 'empty or incomplete'):
                    fabcheck.check_drills(object(), fab)

    def test_review_binds_to_exact_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'wifi'
            (out / 'fab').mkdir(parents=True)
            names = ('fab/bom.csv', 'fab/cpl.csv', 'wifi.kicad_pcb', 'wifi-top.png')
            for name in names:
                (out / name).write_bytes(name.encode())
            review = dict(board='wifi', reviewer='Example Reviewer', reviewed_at='2026-09-27',
                          result='approved', notes='All markers align; pin-one and polarities reviewed.',
                          sha256={name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                                  for name in names})
            path = out / 'fab/cpl-review.json'
            with self.assertRaisesRegex(ValueError, 'missing'):
                fabcheck.check_review(out)
            path.write_text(json.dumps(review))
            fabcheck.check_review(out)
            (out / 'fab/cpl.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'stale'):
                fabcheck.check_review(out)

    def test_provenance_hashes_real_gerber_extensions_but_not_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'fab').mkdir()
            (out / 'fab/board-F_Cu.gtl').write_text('Gerber commands')
            (out / 'fab/cpl-review.json').write_text('{}')
            artifacts = boardevidence.artifacts(out)
            self.assertIn('fab/board-F_Cu.gtl', artifacts)
            self.assertNotIn('fab/cpl-review.json', artifacts)

    def test_export_parity_and_review_do_not_replace_reimport_drc(self):
        with patch.object(fabcheck, 'export_parity', return_value=(object(), 9)), \
             patch.object(fabcheck, 'check_drills', return_value=218), \
             patch.object(fabcheck, 'check_review'):
            with self.assertRaisesRegex(ValueError, 'Gerber re-import DRC is still missing'):
                fabcheck.check(Path('/tmp/wifi'))


if __name__ == '__main__':
    unittest.main()
