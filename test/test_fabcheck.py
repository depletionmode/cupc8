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

    def test_gpu_g85_slot_matches_pad_and_mutations_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            drill = fab / 'gpu.drl'
            header = 'M48\nFMAT,2\nMETRIC\nT3C0.900\n%\nG90\nG05\nT3\n'
            expected = Counter({fabcheck.slot_key((20.25, 40.06), (20.25, 40.86), .9): 1})
            with patch.object(fabcheck, 'board_holes', return_value=expected):
                drill.write_text(header + 'X20.25Y40.06G85X20.25Y40.86\nG05\nM30\n')
                self.assertEqual(fabcheck.check_drills(object(), fab), 1)
                drill.write_text(header + 'X20.25Y40.86G85X20.25Y40.06\nG05\nM30\n')
                self.assertEqual(fabcheck.check_drills(object(), fab), 1)
                for route in ('X20.35Y40.06G85X20.25Y40.86',
                              'X20.25Y40.06G85X20.25Y40.76'):
                    drill.write_text(header + route + '\nG05\nM30\n')
                    with self.assertRaisesRegex(ValueError, 'drill-to-pad/via mismatch'):
                        fabcheck.check_drills(object(), fab)

    def test_excellon_plating_attribute_matches_npth_board_hole(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            drill = fab / 'sample.drl'
            expected = Counter({(2., 2., 3.2): 1})
            header = ('M48\nFMAT,2\nMETRIC\n'
                      '; #@! TA.AperFunction,NonPlated,NPTH,ComponentDrill\n'
                      'T1C3.200\n%\nG90\nG05\nT1\nX2.0Y2.0\nM30\n')
            with patch.object(fabcheck, 'board_holes', return_value=(expected, expected.copy())):
                drill.write_text(header)
                self.assertEqual(fabcheck.check_drills(object(), fab, return_hits=True)[0], 1)
                drill.write_text(header.replace('NonPlated,NPTH', 'Plated,PTH'))
                with self.assertRaisesRegex(ValueError, 'plating class differs'):
                    fabcheck.check_drills(object(), fab, return_hits=True)

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
            for name in ('wifi-F_Cu.gtl', 'wifi-B_Cu.gbl',
                         'wifi-Edge_Cuts.gm1', 'wifi-F_Mask.gts', 'wifi-B_Mask.gbs',
                         'wifi-F_Paste.gtp', 'wifi-B_Paste.gbp',
                         'wifi-F_Silkscreen.gto', 'wifi-B_Silkscreen.gbo'):
                (out / 'fab' / name).write_text('stub')
            board = MagicMock()
            board.GetCopperLayerCount.return_value = 2
            settings = board.GetDesignSettings.return_value
            settings.m_MinClearance = 150000
            settings.m_TrackMinWidth = 100000
            settings.m_ViasMinAnnularWidth = 130000
            settings.m_CopperEdgeClearance = 300000
            settings.m_HoleClearance = 250000
            settings.m_SolderMaskMinWidth = 100000
            with patch.object(fabcheck, 'export_parity', return_value=(board, 9)), \
                 patch.object(fabcheck, 'check_drills', return_value=(218, Counter({(1., 1., .3): 1}), Counter())), \
                 patch.object(fabcheck, 'check_review'), \
                 patch.object(fabcheck.gerberdrc, 'check_clearance', return_value=123) as clearance, \
                 patch.object(fabcheck.gerberdrc, 'check_via_annular', return_value=12) as annular, \
                 patch.object(fabcheck.gerberdrc, 'check_pth_annular', return_value=4) as pth, \
                 patch.object(fabcheck.gerberdrc, 'check_edge') as edge, \
                 patch.object(fabcheck.gerberdrc, 'check_holes') as drilled, \
                 patch.object(fabcheck.gerberdrc, 'check_mask') as mask, \
                 patch.object(fabcheck.gerberdrc, 'check_mask_alignment', return_value=10) as align, \
                 patch.object(fabcheck.gerberdrc, 'check_paste_registration', return_value=5) as paste, \
                 patch.object(fabcheck.gerberdrc, 'check_silk_clearance', return_value=8) as silk:
                with self.assertRaisesRegex(ValueError, 'Gerber re-import DRC incomplete.*123 plotted copper objects'):
                    fabcheck.check(out)
                clearance.assert_called_once()
                annular.assert_called_once()
                pth.assert_called_once()
                edge.assert_called_once()
                drilled.assert_called_once()
                mask.assert_called_once()
                self.assertEqual(align.call_count, 2)
                self.assertEqual(paste.call_count, 2)
                self.assertEqual(silk.call_count, 2)

    def test_exported_copper_short_and_clearance_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            prefix = '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
            def gerber(second_x, second_net='/B'):
                return (prefix + '%TO.N,/A*%\nX1000000Y1000000D03*\n'
                        + '%TO.N,' + second_net + f'*%\nX{second_x}Y1000000D03*\nM02*\n')
            path.write_text(gerber(1351000))
            self.assertEqual(gerberdrc.check_clearance([path], .15), 2)
            path.write_text(gerber(1350000))  # exact rule, circular flashes are analytic
            self.assertEqual(gerberdrc.check_clearance([path], .15), 2)
            path.write_text(gerber(1200000))
            with self.assertRaisesRegex(ValueError, 'copper clearance below rule'):
                gerberdrc.check_clearance([path], .15)
            path.write_text(gerber(1349999))  # 0.149999 mm edge clearance
            with self.assertRaisesRegex(ValueError, 'copper clearance below rule'):
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

    def test_kicad_freepoly_flash_and_unsupported_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            macro = ('%AMFreePoly0*\n4,1,4,0,0,1,0,1,1,0,0,\n$1*%\n')
            body = ('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                    '%ADD10FreePoly0,0.000000*%\nD10*\n%TO.N,/A*%\n'
                    'X1000000Y1000000D03*\nM02*\n')
            path.write_text(macro + body)
            geometry = gerberdrc.Geometry()
            try:
                self.assertEqual(len(gerberdrc.plotted_copper(path, geometry)), 1)
                for mutant in (macro.replace('4,1,4', '4,0,4') + body,
                               macro + body.replace('FreePoly0,0.000000', 'FreePoly0,0.100000'),
                               macro.replace('1,1,0,0,', '1,1,0,1,') + body):
                    path.write_text(mutant)
                    with self.assertRaises(ValueError):
                        gerberdrc.plotted_copper(path, geometry)
            finally:
                geometry.close()

    def test_unsupported_gerber_geometry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample-F_Cu.gtl'
            base = ('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                    'D10*\n%TO.N,/A*%\nX1000000Y1000000D03*\nM02*\n')
            for mutant in (base.replace('%LPD*%', '%LPC*%'),
                           base.replace('%LPD*%', '%TF.FilePolarity,Negative*%\n%LPD*%'),
                           base.replace('%TO.N,/A*%', '%TD*%'),
                           base.replace('%LPD*%', '%TF.FileFunction,Paste,Top*%\n%LPD*%'),
                           base.replace('%ADD10C,0.200000*%',
                                        '%ADD10RoundRect,0.100000X0.200000X0.200000X-0.200000X0.200000X-0.200000X-0.200000X0.200000X-0.200000X0*%'),
                           base.replace('%ADD10C,0.200000*%', '%ADD10P,0.200000X6*%')):
                path.write_text(mutant)
                with self.assertRaises(ValueError):
                    gerberdrc.check_clearance([path], .15)

    def test_plotted_trace_width_and_edge_clearance_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            edge = fab / 'sample-Edge_Cuts.gm1'
            edge.write_text('%TF.FileFunction,Profile,NP*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.100000*%\n'
                            'D10*\nX2000000Y0D02*\nX2000000Y2000000D01*\nM02*\n')
            def flash(x):
                return ('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                        f'D10*\n%TO.N,/A*%\nX{x}Y1000000D03*\nM02*\n')
            copper.write_text(flash(1500000))
            self.assertEqual(gerberdrc.check_edge([copper], edge, .3), 1)
            copper.write_text(flash(1750000))
            with self.assertRaisesRegex(ValueError, 'copper-to-edge'):
                gerberdrc.check_edge([copper], edge, .3)
            copper.write_text('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.090000*%\n'
                              'D10*\n%TO.N,/A*%\nX1000000Y1000000D02*\n'
                              'X1500000Y1000000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'trace width'):
                gerberdrc.check_clearance([copper], .15, .1)
            copper.write_text('%TF.FileFunction,Copper,L1,Top*%\n%TF.FilePolarity,Positive*%\n'
                              '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.090000*%\n'
                              'D10*\n%TO.N,/A*%\nX1000000Y1000000D02*\nG02*\n'
                              'X2000000Y1000000I500000J0D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'trace width'):
                gerberdrc.check_clearance([copper], .15, .1)

    def test_plotted_mask_web_and_via_annular_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            mask = fab / 'sample-F_Mask.gts'
            prefix = ('%TF.FileFunction,Soldermask,Top*%\n%TF.FilePolarity,Negative*%\n'
                      '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n')
            mask.write_text(prefix + 'X1000000Y1000000D03*\nX1350000Y1000000D03*\nM02*\n')
            self.assertEqual(gerberdrc.check_mask([mask], .1), 2)
            mask.write_text(prefix + 'X1000000Y1000000D03*\nX1250000Y1000000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'solder-mask web'):
                gerberdrc.check_mask([mask], .1)

            board_file = fab / 'board.kicad_pcb'
            board_file.write_text('(kicad_pcb (via (at 1 -1) (size 0.6) (drill 0.3) '
                                  '(layers "F.Cu" "B.Cu")))')
            board = MagicMock()
            board.GetFileName.return_value = str(board_file)
            copper = fab / 'sample-F_Cu.gtl'
            def via(diameter):
                return ('%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                        '%TA.AperFunction,ViaPad*%\n'
                        f'%ADD10C,{diameter:.6f}*%\n%TD*%\n'
                        'D10*\n%TO.N,/A*%\nX1000000Y1000000D03*\nM02*\n')
            copper.write_text(via(.6))
            self.assertEqual(gerberdrc.check_via_annular(board, [copper], .13), 1)
            copper.write_text(via(.5))
            with self.assertRaisesRegex(ValueError, 'via annular ring'):
                gerberdrc.check_via_annular(board, [copper], .13)

    def test_pth_annular_and_mask_to_pad_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            pad = MagicMock()
            pad.GetAttribute.return_value = fabcheck.pcbnew.PAD_ATTRIB_PTH
            pad.GetDrillSize.return_value = fabcheck.pcbnew.VECTOR2I(
                fabcheck.pcbnew.FromMM(.9), fabcheck.pcbnew.FromMM(2.7))
            pad.GetPosition.return_value = fabcheck.pcbnew.VECTOR2I(
                fabcheck.pcbnew.FromMM(1), fabcheck.pcbnew.FromMM(-1))
            pad.GetOrientationDegrees.return_value = 0
            footprint = MagicMock()
            footprint.GetReference.return_value = 'J1'
            footprint.Pads.return_value = [pad]
            board = MagicMock()
            board.GetFootprints.return_value = [footprint]
            copper = fab / 'sample-F_Cu.gtl'
            def component(width, height):
                return ('%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                        '%TA.AperFunction,ComponentPad*%\n'
                        f'%ADD10O,{width:.6f}X{height:.6f}*%\n%TD*%\n'
                        'D10*\n%TO.N,/GND*%\nX1000000Y1000000D03*\nM02*\n')
            copper.write_text(component(1.5, 3.3))
            self.assertEqual(gerberdrc.check_pth_annular(board, [copper], .2), 1)
            # Exact nominal annulus at the threshold passes. A one-micron
            # reduction of the plotted pad is a real plotted-rule failure.
            copper.write_text(component(1.3, 3.1))
            self.assertEqual(gerberdrc.check_pth_annular(board, [copper], .2), 1)
            copper.write_text(component(1.299998, 3.1))
            with self.assertRaisesRegex(ValueError, 'PTH annular ring'):
                gerberdrc.check_pth_annular(board, [copper], .2)
            copper.write_text(component(1.1, 2.9))
            with self.assertRaisesRegex(ValueError, 'PTH annular ring'):
                gerberdrc.check_pth_annular(board, [copper], .2)

            copper.write_text(component(1.5, 3.3))
            mask = fab / 'sample-F_Mask.gts'
            def opening(width, height):
                return ('%TF.FileFunction,Soldermask,Top*%\n%TF.FilePolarity,Negative*%\n'
                        '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                        f'%ADD10O,{width:.6f}X{height:.6f}*%\nD10*\n'
                        'X1000000Y1000000D03*\nM02*\n')
            mask.write_text(opening(1.7, 3.5))
            self.assertEqual(gerberdrc.check_mask_alignment(copper, mask), 1)
            mask.write_text(opening(1.5, 3.3))
            self.assertEqual(gerberdrc.check_mask_alignment(copper, mask), 1)
            mask.write_text(opening(1.499998, 3.299998))
            with self.assertRaisesRegex(ValueError, 'mask-to-copper coverage indeterminate'):
                gerberdrc.check_mask_alignment(copper, mask)
            mask.write_text(opening(1.1, 2.9))
            with self.assertRaisesRegex(ValueError, 'mask opening does not cover'):
                gerberdrc.check_mask_alignment(copper, mask)

    def test_paste_registration_detects_oversized_deposit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper, mask, paste = (fab / ('sample-F_' + suffix) for suffix in
                                   ('Cu.gtl', 'Mask.gts', 'Paste.gtp'))
            copper.write_text('%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n%MOMM*%\n'
                              '%LPD*%\n%TA.AperFunction,SMDPad,CuDef*%\n'
                              '%ADD10C,0.600000*%\n%TD*%\nD10*\n%TO.N,/A*%\n'
                              'X1000000Y1000000D03*\nM02*\n')
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n%MOMM*%\n'
                            '%LPD*%\n%ADD10C,0.700000*%\nD10*\n'
                            'X1000000Y1000000D03*\nM02*\n')
            def deposit(width):
                return ('%TF.FileFunction,Paste,Top*%\n%TF.FilePolarity,Positive*%\n'
                        '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                        f'%ADD10C,{width:.6f}*%\nD10*\nX1000000Y1000000D03*\nM02*\n')
            paste.write_text(deposit(.55))
            self.assertEqual(gerberdrc.check_paste_registration(copper, mask, paste), 1)
            paste.write_text(deposit(.6))
            self.assertEqual(gerberdrc.check_paste_registration(copper, mask, paste), 1)
            paste.write_text(deposit(.8))
            with self.assertRaisesRegex(ValueError, 'paste deposit outside SMD copper'):
                gerberdrc.check_paste_registration(copper, mask, paste)

    def test_silkscreen_mask_clearance_and_arc(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            mask = fab / 'sample-F_Mask.gts'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n%MOMM*%\n'
                            '%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
                            'X1000000Y1000000D03*\nM02*\n')
            prefix = ('%TF.FileFunction,Legend,Top*%\n%TF.FilePolarity,Positive*%\n'
                      '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.150000*%\nD10*\n')
            silk.write_text(prefix + 'X1400000Y1000000D02*\nX2000000Y1000000D01*\nM02*\n')
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15), 1)
            silk.write_text(prefix.replace('0.150000', '0.120000') +
                            'X1400000Y1000000D02*\nX2000000Y1000000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'plotted trace width'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)
            silk.write_text(prefix + 'X1200000Y1000000D02*\nX2000000Y1000000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'silkscreen-to-mask clearance below rule'):
                gerberdrc.check_silk_clearance(silk, mask, .15)
            silk.write_text(prefix + 'X3000000Y1000000D02*\nG75*\nG02*\n'
                            'X3200000Y1000000I100000J0D01*\nG01*\nM02*\n')
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15), 1)

    def test_excellon_hole_to_copper_and_edge_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            edge = fab / 'sample-Edge_Cuts.gm1'
            prefix = ('%TF.FileFunction,Copper,L1,Top*%\n%TF.FilePolarity,Positive*%\n'
                      '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n'
                      '%TA.AperFunction,ComponentPad*%\n%ADD10C,0.600000*%\n%TD*%\n'
                      '%TA.AperFunction,Conductor*%\n%ADD11C,0.200000*%\n%TD*%\n'
                      'D10*\n%TO.N,/A*%\nX1000000Y1000000D03*\n')
            def plot(other_x):
                return (prefix + 'D11*\n%TO.N,/B*%\n'
                        f'X{other_x}Y1000000D03*\nM02*\n')
            def profile(x):
                return ('%TF.FileFunction,Profile,NP*%\n%FSLAX46Y46*%\n'
                        '%MOMM*%\n%LPD*%\n%ADD10C,0.100000*%\nD10*\n'
                        f'X{x}Y0D02*\nX{x}Y3000000D01*\nM02*\n')
            cuts = Counter({(1., 1., .3): 1, (2., 2., .3): 1})
            npth = Counter({(2., 2., .3): 1})
            copper.write_text(plot(1800000))
            edge.write_text(profile(3500000))
            self.assertEqual(gerberdrc.check_holes(cuts, npth, [copper], edge, .25, 1.), 2)
            copper.write_text(plot(1400000))
            with self.assertRaisesRegex(ValueError, 'hole-to-copper below rule'):
                gerberdrc.check_holes(cuts, npth, [copper], edge, .25, 1.)
            copper.write_text(plot(1800000))
            edge.write_text(profile(2800000))
            with self.assertRaisesRegex(ValueError, 'NPTH hole-to-edge below rule'):
                gerberdrc.check_holes(cuts, npth, [copper], edge, .25, 1.)
            edge.write_text(profile(3500000))
            copper.write_text(plot(1800000).replace('M02*',
                              'D10*\nX2000000Y2000000D03*\nM02*'))
            with self.assertRaisesRegex(ValueError, 'hole-to-copper below rule'):
                gerberdrc.check_holes(cuts, npth, [copper], edge, .25, 1.)
            copper.write_text(plot(1800000).replace('%TA.AperFunction,ComponentPad*%',
                                                     '%TA.AperFunction,Conductor*%'))
            with self.assertRaisesRegex(ValueError, 'lacks ComponentPad/ViaPad flash'):
                gerberdrc.check_holes(cuts, npth, [copper], edge, .25, 1.)
            copper.write_text(plot(1800000))
            slot = fabcheck.slot_key((1., .7), (1., 1.3), .2)
            self.assertEqual(gerberdrc.check_holes(Counter({slot: 1}), Counter(), [copper], edge, .25, 1.), 1)
            copper.write_text(plot(1300000))
            with self.assertRaisesRegex(ValueError, 'hole-to-copper below rule'):
                gerberdrc.check_holes(Counter({slot: 1}), Counter(), [copper], edge, .25, 1.)


if __name__ == '__main__':
    unittest.main()
