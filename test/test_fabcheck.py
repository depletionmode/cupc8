"""Mutation checks for the fabrication evidence gate."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hw' / 'tools'))
import fabcheck
import boardevidence
import gerberdrc


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

    def test_fab_gate_requires_copper_geometry_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'wifi'
            (out / 'fab').mkdir(parents=True)
            for name in ('wifi-F_Cu.gtl', 'wifi-B_Cu.gbl'):
                (out / 'fab' / name).write_text('stub')
            board = MagicMock()
            board.GetCopperLayerCount.return_value = 2
            board.GetDesignSettings.return_value.m_MinClearance = 150000
            with patch.object(fabcheck, 'export_parity', return_value=(board, 9)), \
                 patch.object(fabcheck, 'check_drills', return_value=218), \
                 patch.object(fabcheck, 'check_review'), \
                 patch.object(fabcheck.gerberdrc, 'check_clearance', return_value=123) as clearance:
                with self.assertRaisesRegex(ValueError, 'Gerber re-import DRC incomplete.*123 plotted copper objects'):
                    fabcheck.check(out)
                clearance.assert_called_once()

    def test_exported_copper_short_and_clearance_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            prefix = '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
            def gerber(second_x, second_net='/B'):
                return (prefix + '%TO.N,/A*%\nX1000000Y1000000D03*\n'
                        + '%TO.N,' + second_net + f'*%\nX{second_x}Y1000000D03*\nM02*\n')
            path.write_text(gerber(1351000))
            self.assertEqual(gerberdrc.check_clearance([path], .15), 2)
            path.write_text(gerber(1200000))
            with self.assertRaisesRegex(ValueError, 'copper clearance'):
                gerberdrc.check_clearance([path], .15)
            path.write_text(gerber(1349999))  # 0.149999 mm edge clearance
            with self.assertRaisesRegex(ValueError, 'copper clearance'):
                gerberdrc.check_clearance([path], .15)
            # A 2 mm circle at this angle falls halfway between buffer chords.
            # An inscribed polygon alone would overstate the 0.14999 mm gap.
            path.write_text(prefix.replace('0.200000', '2.000000')
                            + '%TO.N,/A*%\nX1000000Y1000000D03*\n'
                            + '%TO.N,/B*%\nX3149828Y1026384D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'copper clearance'):
                gerberdrc.check_clearance([path], .15)
            path.write_text(gerber(1000000))
            with self.assertRaisesRegex(ValueError, 'copper clearance'):
                gerberdrc.check_clearance([path], .15)
            path.write_text(gerber(1351000, '/A'))
            self.assertEqual(gerberdrc.check_clearance([path], .15), 2)

    def test_unsupported_gerber_geometry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            base = ('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                    'D10*\n%TO.N,/A*%\nX1000000Y1000000D03*\nM02*\n')
            for mutant in (base.replace('%LPD*%', '%LPC*%'),
                           base.replace('%LPD*%', '%TF.FilePolarity,Negative*%\n%LPD*%'),
                           base.replace('%TO.N,/A*%', '%TD*%'),
                           base.replace('%ADD10C,0.200000*%',
                                        '%ADD10RoundRect,0.100000X0.200000X0.200000X-0.200000X0.200000X-0.200000X-0.200000X0.200000X-0.200000X0*%'),
                           base.replace('%ADD10C,0.200000*%', '%ADD10P,0.200000X6*%')):
                path.write_text(mutant)
                with self.assertRaises(ValueError):
                    gerberdrc.check_clearance([path], .15)


if __name__ == '__main__':
    unittest.main()
