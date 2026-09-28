"""Mutation checks for the fabrication evidence gate."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hw' / 'tools'))
import fabcheck
import boardevidence
import gerberdrc
import silktextaudit


class FabCheckTests(unittest.TestCase):
    def test_source_silk_text_inventory_and_receipt_binding(self):
        pcbnew = fabcheck.pcbnew
        mm = pcbnew.FromMM
        board = pcbnew.BOARD()
        board.GetDesignSettings().m_MinSilkTextHeight = mm(.8)
        word = pcbnew.PCB_TEXT(board)
        word.SetText('REV')
        word.SetLayer(pcbnew.F_SilkS)
        word.SetTextSize(pcbnew.VECTOR2I(mm(.8), mm(.8)))
        board.Add(word)
        hidden = pcbnew.PCB_TEXT(board)
        hidden.SetText('HIDDEN')
        hidden.SetLayer(pcbnew.F_SilkS)
        hidden.SetTextSize(pcbnew.VECTOR2I(mm(.4), mm(.4)))
        hidden.SetVisible(False)
        board.Add(hidden)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('U1')
        fp.Reference().SetLayer(pcbnew.F_SilkS)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(.8), mm(.8)))
        fp.Value().SetText('PART')
        fp.Value().SetLayer(pcbnew.B_SilkS)
        fp.Value().SetVisible(True)
        fp.Value().SetTextSize(pcbnew.VECTOR2I(mm(1), mm(1)))
        extra = pcbnew.PCB_TEXT(fp)
        extra.SetText('MARK')
        extra.SetLayer(pcbnew.B_SilkS)
        extra.SetTextSize(pcbnew.VECTOR2I(mm(.8), mm(.8)))
        fp.Add(extra)
        board.Add(fp)
        minimum, entries = silktextaudit.inventory(board)
        self.assertEqual(minimum, .8)
        self.assertEqual({item['literal'] for item in entries}, {'REV', 'U1', 'PART', 'MARK'})
        self.assertEqual({item['kind'] for item in entries},
                         {'board_text', 'reference', 'value', 'footprint_text'})
        self.assertEqual({item['layer'] for item in entries}, {'F.Silkscreen', 'B.Silkscreen'})
        self.assertEqual(len({item['uuid'] for item in entries}), 4)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'card'
            fab = out / 'fab'
            fab.mkdir(parents=True)
            for name in ('evidence.json', 'card.kicad_pcb'):
                (out / name).write_text(name)
            for name in ('card-F_Silkscreen.gto', 'card-B_Silkscreen.gbo'):
                (fab / name).write_text(name)
            report = Path(tmp) / 'text-review.json'
            with patch.object(silktextaudit.boardevidence, 'validate', return_value={'version': 1}), \
                 patch.object(silktextaudit.fabcheck, 'export_parity', return_value=(board, 9)):
                payload = silktextaudit.audit(out, report)
            self.assertEqual(payload['count'], 4)
            self.assertEqual(payload['review_status'], 'pending')
            self.assertEqual(payload['binding']['receipt_sha256'],
                             boardevidence.digest(out / 'evidence.json'))
            self.assertEqual(payload['binding']['parity_layer_count'], 9)
            with self.assertRaisesRegex(ValueError, 'outside receipt-owned'):
                silktextaudit.audit(out, fab / 'text-review.json')
            report.unlink()
            fp.Value().SetTextSize(pcbnew.VECTOR2I(mm(.799999), mm(.799999)))
            with patch.object(silktextaudit.boardevidence, 'validate', return_value={'version': 1}), \
                 patch.object(silktextaudit.fabcheck, 'export_parity', return_value=(board, 9)):
                with self.assertRaisesRegex(ValueError, 'nominal silk text height'):
                    silktextaudit.audit(out, report)
            self.assertFalse(report.exists())
            fp.Value().SetTextSize(pcbnew.VECTOR2I(mm(1), mm(1)))
            with patch.object(silktextaudit.boardevidence, 'validate',
                              side_effect=ValueError('stale board evidence')):
                with self.assertRaisesRegex(ValueError, 'stale board evidence'):
                    silktextaudit.audit(out, report)
            with patch.object(silktextaudit.boardevidence, 'validate', return_value={'version': 1}), \
                 patch.object(silktextaudit.fabcheck, 'export_parity',
                              side_effect=ValueError('Gerber geometry differs')):
                with self.assertRaisesRegex(ValueError, 'Gerber geometry differs'):
                    silktextaudit.audit(out, report)
            self.assertFalse(report.exists())
            board.GetDesignSettings().m_MinSilkTextHeight = mm(.7)
            with self.assertRaisesRegex(ValueError, 'below 0.800 mm fab rule'):
                silktextaudit.inventory(board)

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
                drill.write_text(drill.read_text().replace('X1.0Y2.0', 'X1.0001Y2.0'))
                with self.assertRaisesRegex(ValueError, 'unsupported Excellon command'):
                    fabcheck.check_drills(object(), fab)
                drill.write_text(drill.read_text().replace('X1.0001Y2.0', 'X1.0Y2.0')
                                 .replace('T1C0.300', 'T1C0.3001'))
                with self.assertRaisesRegex(ValueError, 'unsupported Excellon command'):
                    fabcheck.check_drills(object(), fab)
                drill.write_text(drill.read_text().replace('T1C0.3001', 'T1C0.300'))
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
            settings.m_HoleToHoleMin = 500000
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
                with self.assertRaisesRegex(ValueError, 'Gerber re-import DRC incomplete.*filled copper regions'):
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

    def test_plotted_drc_coverage_stays_closed_with_or_without_mask_rule(self):
        for width in (0, .1):
            with self.subTest(mask_width=width):
                with self.assertRaisesRegex(ValueError, 'minimum neck width in filled copper') as caught:
                    fabcheck.require_complete_plotted_drc(width)
                message = str(caught.exception)
                self.assertIn('filled silkscreen regions', message)
                self.assertIn('silkscreen text height', message)
                self.assertEqual('positive solder-mask web rule is not configured' in message,
                                 width == 0)

    @unittest.skipUnless(shutil.which('kicad-cli'), 'KiCad Gerber exporter unavailable')
    def test_silk_text_and_graphic_can_have_identical_plot_commands(self):
        """A Gerber-only checker cannot identify every source text object."""
        pcbnew = fabcheck.pcbnew
        mm = pcbnew.FromMM
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def plot(name, board):
                source = directory / (name + '.kicad_pcb')
                pcbnew.SaveBoard(str(source), board)
                out = directory / name
                subprocess.run(('kicad-cli', 'pcb', 'export', 'gerbers',
                                '-l', 'F.Silkscreen', '-o', str(out), str(source)),
                               check=True, capture_output=True, text=True)
                return (out / (name + '-F_Silkscreen.gto')).read_text()

            text_board = pcbnew.BOARD()
            dash = pcbnew.PCB_TEXT(text_board)
            dash.SetText('-')
            dash.SetLayer(pcbnew.F_SilkS)
            dash.SetTextSize(pcbnew.VECTOR2I(mm(.8), mm(.8)))
            dash.SetTextThickness(mm(.15))
            dash.SetPosition(pcbnew.VECTOR2I(mm(10), mm(10)))
            text_board.Add(dash)
            text_plot = plot('text', text_board)
            segments = re.findall(r'X(-?\d+)Y(-?\d+)D0[12]\*', text_plot)
            self.assertEqual(len(segments), 2)
            self.assertNotIn('FlashText', text_plot)

            graphic_board = pcbnew.BOARD()
            line = pcbnew.PCB_SHAPE(graphic_board)
            line.SetShape(pcbnew.SHAPE_T_SEGMENT)
            # KiCad's internal unit is 1 nm, so convert the Gerber's
            # six-decimal-millimetre coordinates through FromMM explicitly.
            line.SetStart(pcbnew.VECTOR2I(mm(int(segments[0][0])/1000000),
                                           mm(-int(segments[0][1])/1000000)))
            line.SetEnd(pcbnew.VECTOR2I(mm(int(segments[1][0])/1000000),
                                         mm(-int(segments[1][1])/1000000)))
            line.SetWidth(mm(.15))
            line.SetLayer(pcbnew.F_SilkS)
            graphic_board.Add(line)
            graphic_plot = plot('graphic', graphic_board)
            self.assertEqual(text_plot[text_plot.index('G04 APERTURE LIST*'):],
                             graphic_plot[graphic_plot.index('G04 APERTURE LIST*'):])

    def test_excellon_drill_spacing_exact_boundary_and_slot(self):
        circle = (1.0, 1.0, .3)
        at_limit = (1.8, 1.0, .3)  # 0.5 mm clearance between 0.3 mm cuts
        self.assertEqual(fabcheck.check_drill_spacing(Counter({circle: 1, at_limit: 1}), .5), 2)
        with self.assertRaisesRegex(ValueError, 'drill-to-drill clearance'):
            fabcheck.check_drill_spacing(Counter({circle: 1, (1.799, 1.0, .3): 1}), .5)
        slot = fabcheck.slot_key((1.8, 1.0), (1.8, 2.0), .3)
        self.assertEqual(fabcheck.check_drill_spacing(Counter({circle: 1, slot: 1}), .5), 2)
        crossing = fabcheck.slot_key((1.0, 1.0), (2.0, 1.0), .3)
        with self.assertRaisesRegex(ValueError, 'drill-to-drill clearance'):
            fabcheck.check_drill_spacing(Counter({slot: 1, crossing: 1}), .5)

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

    def test_isolated_filled_copper_width_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            copper = Path(tmp) / 'sample-F_Cu.gtl'
            prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                      '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                      '%MOMM*%\n%LPD*%\n%ADD10C,0.100000*%\n'
                      'D10*\n%TO.N,/GND*%\n')
            def region(width):
                return ('G36*\nX1000000Y1000000D02*\n'
                        'X2000000Y1000000D01*\n'
                        f'X2000000Y{1000000+width}D01*\n'
                        f'X1000000Y{1000000+width}D01*\n'
                        'X1000000Y1000000D01*\nG37*\n')
            copper.write_text(prefix + region(100000) + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 1)
            copper.write_text(prefix + region(99999) + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated filled region width 0.099999 mm'):
                gerberdrc.check_clearance([copper], .15, .1)
            # A perpendicular same-net stroke cannot rescue the thin parts
            # outside its outward bounding box.
            copper.write_text(prefix + region(99999) +
                              'X1500000Y900000D02*\nX1500000Y1200000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.099999 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            # A different-net crossing is already a clearance violation; it
            # cannot excuse the isolated /GND region's own width failure.
            copper.write_text(prefix + region(99999) + '%TO.N,/VCC*%\n'
                              'X1500000Y900000D02*\nX1500000Y1200000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated filled region width'):
                gerberdrc.check_clearance([copper], .15, .1)
            # A region with a separate interior contour cannot be treated as
            # a simple island. The parser rejects it rather than guessing at
            # the annular copper width around the hole.
            copper.write_text(prefix + region(1000000).replace(
                'G37*\n', 'X1300000Y1300000D02*\nX1700000Y1300000D01*\n'
                         'X1700000Y1700000D01*\nX1300000Y1700000D01*\n'
                         'X1300000Y1300000D01*\nG37*\n') + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'multiple region contours unsupported'):
                gerberdrc.check_clearance([copper], .15, .1)

    def test_isolated_filled_neck_mutations(self):
        def dumbbell(bridge):
            low = 1500000 - bridge // 2
            high = low + bridge
            points = [(1000000,1000000), (1500000,1000000),
                      (1500000,low), (2000000,low), (2000000,1000000),
                      (2500000,1000000), (2500000,2000000),
                      (2000000,2000000), (2000000,high),
                      (1500000,high), (1500000,2000000),
                      (1000000,2000000), (1000000,1000000)]
            return 'G36*\n' + ''.join(f'X{x}Y{y}D{"02" if i == 0 else "01"}*\n'
                                     for i, (x,y) in enumerate(points)) + 'G37*\n'
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask = fab / 'sample-F_Mask.gts'
            prefix = '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
            copper_prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                             '%TF.FilePolarity,Positive*%\n' + prefix + '%TO.N,/GND*%\n')
            silk_prefix = ('%TF.FileFunction,Legend,Top*%\n'
                           '%TF.FilePolarity,Positive*%\n' + prefix)
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n' + prefix +
                            'X9000000Y9000000D03*\nM02*\n')
            copper.write_text(copper_prefix + dumbbell(100000) + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 1)
            copper.write_text(copper_prefix + dumbbell(80000) + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated filled region has a 0.080000 mm span below 0.100000 mm'):
                gerberdrc.check_clearance([copper], .15, .1)
            # The bounding-box superset of one touching stroke still leaves
            # a provably narrow portion of the bridge.
            copper.write_text(copper_prefix + dumbbell(80000) +
                              'X1750000Y1300000D02*\nX1750000Y1700000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            silk.write_text(silk_prefix + dumbbell(150000) + 'M02*\n')
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15, .15), 1)
            silk.write_text(silk_prefix + dumbbell(100000) + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated filled region has a 0.100000 mm span below 0.150000 mm'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

    def test_connected_filled_region_union_mutations(self):
        def rectangle(x0, y0, x1, y1):
            return (f'G36*\nX{x0}Y{y0}D02*\nX{x1}Y{y0}D01*\n'
                    f'X{x1}Y{y1}D01*\nX{x0}Y{y1}D01*\n'
                    f'X{x0}Y{y0}D01*\nG37*\n')
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask = fab / 'sample-F_Mask.gts'
            prefix = '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
            copper_prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                             '%TF.FilePolarity,Positive*%\n' + prefix + '%TO.N,/GND*%\n')
            silk_prefix = ('%TF.FileFunction,Legend,Top*%\n'
                           '%TF.FilePolarity,Positive*%\n' + prefix)
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n' + prefix +
                            'X9000000Y9000000D03*\nM02*\n')
            narrow = (rectangle(1000000,1000000,1500000,1080000) +
                      rectangle(1500000,1000000,2000000,1080000))
            copper.write_text(copper_prefix + narrow + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span below 0.100000 mm'):
                gerberdrc.check_clearance([copper], .15, .1)
            widened = (rectangle(1000000,1000000,2000000,1090000) +
                       rectangle(1000000,1090000,2000000,1180000))
            copper.write_text(copper_prefix + widened + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            # One stroke's outward box cannot widen the full region union.
            copper.write_text(copper_prefix + narrow +
                              'X1250000Y900000D02*\nX1250000Y1200000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            silk_narrow = (rectangle(1000000,1000000,1500000,1100000) +
                           rectangle(1500000,1000000,2000000,1100000))
            silk.write_text(silk_prefix + silk_narrow + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.100000 mm span below 0.150000 mm'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)
            silk_widened = (rectangle(1000000,1000000,2000000,1100000) +
                            rectangle(1000000,1100000,2000000,1200000))
            silk.write_text(silk_prefix + silk_widened + 'M02*\n')
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15, .15), 2)

    def test_rectangular_flash_widens_filled_region_on_half_micron_grid(self):
        def region(y1):
            return ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                    f'X2000000Y{y1}D01*\nX1000000Y{y1}D01*\n'
                    'X1000000Y1000000D01*\nG37*\n')
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask = fab / 'sample-F_Mask.gts'
            prefix = '%FSLAX46Y46*%\n%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
            copper_prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                             '%TF.FilePolarity,Positive*%\n' + prefix + '%TO.N,/GND*%\n')
            silk_prefix = ('%TF.FileFunction,Legend,Top*%\n'
                           '%TF.FilePolarity,Positive*%\n' + prefix)
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n' + prefix +
                            'D10*\nX9000000Y9000000D03*\nM02*\n')
            def plotted(base, flash_height):
                return (base + f'%ADD11R,1.000000X{flash_height:.6f}*%\nD10*\n' +
                        region(1080000) + 'D11*\nX1500000Y1040000D03*\nM02*\n')
            copper.write_text(plotted(copper_prefix, .101))
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            copper.write_text(plotted(copper_prefix, .099))
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.099000 mm span below 0.100000 mm'):
                gerberdrc.check_clearance([copper], .15, .1)
            # Two touching flashes cover opposite halves; both must enter
            # the transitive connected union before a width is measured.
            copper.write_text(copper_prefix + '%ADD11R,0.500000X0.121000*%\nD10*\n' +
                              region(1080000) + 'D11*\nX1250000Y1040000D03*\n'
                              'X1750000Y1040000D03*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 3)
            # The narrow flash tongue beyond a wide region is a pad, not a
            # narrow filled-region span.
            copper.write_text(copper_prefix + '%ADD11R,0.500000X0.050000*%\nD10*\n' +
                              region(1200000) + 'D11*\nX2250000Y1100000D03*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            silk.write_text(plotted(silk_prefix, .151))
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15, .15), 2)
            silk.write_text(plotted(silk_prefix, .149))
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.149000 mm span below 0.150000 mm'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

    def test_bounded_stroke_and_nonrectangular_flash_witnesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            copper = Path(tmp) / 'sample-F_Cu.gtl'
            prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                      '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                      '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                      '%ADD11O,0.400000X0.200000*%\nD10*\n%TO.N,/GND*%\n')
            region = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                      'X2000000Y1080000D01*\nX1000000Y1080000D01*\n'
                      'X1000000Y1000000D01*\nG37*\n')
            copper.write_text(prefix + region + 'X1500000Y1040000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            copper.write_text(prefix + region + 'D11*\nX1500000Y1040000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            # This centerline's 0.20 mm aperture spans the full region; a
            # bounding-box witness must allow that widening.
            copper.write_text(prefix + region +
                              'X1000000Y1040000D02*\nX2000000Y1040000D01*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            # Two unknown flashes widen only local pieces of the region.
            # Their outward boxes cannot cover its thin center span.
            copper.write_text(prefix + region +
                              'X1100000Y1040000D03*\nX1900000Y1040000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            # A third flash touches the first flash but not the region. The
            # bounded proof must defer because its ink might widen the union.
            copper.write_text(prefix + region +
                              'X1100000Y1040000D03*\nX1900000Y1040000D03*\n'
                              'X1100000Y1230000D03*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 4)
            # Five direct operations exceed the bounded proof, even though
            # the central span still appears thin in this particular plot.
            copper.write_text(prefix + region + ''.join(
                'X%dY1040000D03*\n' % x for x in
                (1050000, 1080000, 1110000, 1140000, 1170000)) + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 6)
            # Two strokes fully widen the region; their boxes must not
            # invent a failure where no sub-rule span remains.
            copper.write_text(prefix + region +
                              'X1000000Y1040000D02*\nX1500000Y1040000D01*\n'
                              'X1500000Y1040000D02*\nX2000000Y1040000D01*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 3)

    def test_nonorthogonal_filled_scanline_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            copper = Path(tmp) / 'sample-F_Cu.gtl'
            prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                      '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                      '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n%TO.N,/GND*%\n')
            # Diagonal shoulders surround a 0.080 mm neck. The two adjacent
            # y-slabs are wider than the rule at exact rational midpoints.
            narrow = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                      'X2000000Y1200000D01*\nX1540000Y1300000D01*\n'
                      'X1540000Y1400000D01*\nX2000000Y1500000D01*\n'
                      'X2000000Y1700000D01*\nX1000000Y1700000D01*\n'
                      'X1000000Y1500000D01*\nX1460000Y1400000D01*\n'
                      'X1460000Y1300000D01*\nX1000000Y1200000D01*\n'
                      'X1000000Y1000000D01*\nG37*\n')
            copper.write_text(prefix + narrow + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated nonorthogonal filled region has a 0.080000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            # Exactly 0.100 mm at the neck is accepted.
            at_limit = narrow.replace('X1540000', 'X1550000').replace('X1460000', 'X1450000')
            copper.write_text(prefix + at_limit + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 1)
            # A taper ending at a narrow rounded tip has no two-sided neck.
            taper = ('G36*\nX1000000Y1000000D02*\nX2000000Y1000000D01*\n'
                     'X1559000Y1180000D01*\nX1510000Y1200000D01*\n'
                     'X1490000Y1200000D01*\nX1441000Y1180000D01*\n'
                     'X1000000Y1000000D01*\nG37*\n')
            copper.write_text(prefix + taper + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 1)
            # A touching same-net stroke may widen the sampled union.
            copper.write_text(prefix + narrow +
                              'X1500000Y1250000D02*\nX1500000Y1450000D01*\nM02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            mask = Path(tmp) / 'sample-F_Mask.gts'
            silk = Path(tmp) / 'sample-F_Silkscreen.gto'
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                            'D10*\nX9000000Y9000000D03*\nM02*\n')
            silk.write_text(prefix.replace('Copper,L1,Top', 'Legend,Top')
                            .replace('0.200000', '0.150000') + narrow + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated nonorthogonal filled region has a 0.080000 mm span'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

    def test_near_vertex_nonorthogonal_neck_without_midpoint_failure(self):
        # The 1.20-1.30 mm slab is 0.140 mm wide at its midpoint and
        # 0.080 mm wide at the top vertex. A rational interior slice is
        # 0.090 mm; midpoint-only witnesses miss this real plotted neck.
        points = [(1, 1), (2, 1), (2, 1.2), (1.6, 1.2),
                  (1.54, 1.3), (2, 1.4), (2, 1.6), (1, 1.6),
                  (1, 1.4), (1.46, 1.3), (1.4, 1.2), (1, 1.2)]
        def region(vertices):
            commands = ['G36*']
            for index, (x, y) in enumerate([*vertices, vertices[0]]):
                commands.append('X%dY%dD0%d*' %
                                (round(x*1000000), round(y*1000000),
                                 2 if index == 0 else 1))
            return '\n'.join([*commands, 'G37*']) + '\n'
        prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                  '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                  '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n%TO.N,/GND*%\n')
        with tempfile.TemporaryDirectory() as tmp:
            copper = Path(tmp) / 'sample-F_Cu.gtl'
            copper.write_text(prefix + region(points) + 'M02*\n')
            with self.assertRaisesRegex(ValueError,
                                        'isolated nonorthogonal filled region has a 0.090000 mm span'):
                gerberdrc.check_clearance([copper], .15, .1)
            # The exact 0.100 mm limiting vertex has no sub-rule slice.
            at_limit = [(1.55 if x == 1.54 else 1.45 if x == 1.46 else x, y)
                        for x, y in points]
            copper.write_text(prefix + region(at_limit) + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 1)
            # The same non-midpoint witness applies to plotted legend ink.
            silk_points = [(1.65 if x == 1.6 else 1.56 if x == 1.54 else
                            1.44 if x == 1.46 else 1.35 if x == 1.4 else x, y)
                           for x, y in points]
            silk = Path(tmp) / 'sample-F_Silkscreen.gto'
            mask = Path(tmp) / 'sample-F_Mask.gts'
            silk.write_text(prefix.replace('Copper,L1,Top', 'Legend,Top')
                            .replace('0.200000', '0.150000') + region(silk_points) + 'M02*\n')
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                            'D10*\nX9000000Y9000000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError,
                                        'isolated nonorthogonal filled region has a 0.135000 mm span'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

    def test_connected_nonorthogonal_neck_witness_on_copper_and_silk(self):
        # A second filled region touches a wide lobe. The isolated witness
        # must defer, while the connected union still has an 80 um neck.
        narrow = [(1, 1), (2, 1), (2, 1.2), (1.54, 1.3),
                  (1.54, 1.4), (2, 1.5), (2, 1.7), (1, 1.7),
                  (1, 1.5), (1.46, 1.4), (1.46, 1.3), (1, 1.2)]
        attached = [(.8, 1), (1.2, 1), (1.2, 1.2), (.8, 1.2)]

        def region(points):
            commands = ['G36*']
            for index, (x, y) in enumerate([*points, points[0]]):
                commands.append('X%dY%dD0%d*' %
                                (round(x * 1000000), round(y * 1000000),
                                 2 if index == 0 else 1))
            return '\n'.join([*commands, 'G37*']) + '\n'

        header = ('%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                  '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n')
        wide_flash = ('%ADD11R,0.200000X0.300000*%\nD11*\n'
                      'X1500000Y1350000D03*\n')
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            copper = fab / 'sample-F_Cu.gtl'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask = fab / 'sample-F_Mask.gts'
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n'
                            'X9000000Y9000000D03*\nM02*\n')
            copper_header = '%TF.FileFunction,Copper,L1,Top*%\n' + header + '%TO.N,/GND*%\n'
            silk_header = '%TF.FileFunction,Legend,Top*%\n' + header.replace(
                '0.200000', '0.150000')
            for path, prefix, check, limit in (
                    (copper, copper_header,
                     lambda: gerberdrc.check_clearance([copper], .15, .1), .1),
                    (silk, silk_header,
                     lambda: gerberdrc.check_silk_clearance(silk, mask, .15, .15), .15)):
                path.write_text(prefix + region(narrow) + region(attached) + 'M02*\n')
                with self.assertRaisesRegex(ValueError,
                                            'connected nonorthogonal filled region union has a 0.080000 mm'):
                    check()
                # A rectangular flash broadens the entire interior neck.
                path.write_text(prefix + region(narrow) + region(attached) + wide_flash + 'M02*\n')
                self.assertEqual(check(), 3)
                # Exact-width necks pass; the proof is strictly below rule.
                half = limit / 2
                at_limit = [(1.5 + half if x == 1.54 else
                             1.5 - half if x == 1.46 else x, y) for x, y in narrow]
                path.write_text(prefix + region(at_limit) + region(attached) + 'M02*\n')
                self.assertEqual(check(), 2)

    def test_connected_nonorthogonal_near_vertex_union_mutations(self):
        # The region is 0.140 mm wide at the slab midpoint and 0.080 mm
        # at its vertex. A second region touches a wide lobe, so the
        # isolated witness defers and the connected union must find it.
        narrow = [(1, 1), (2, 1), (2, 1.2), (1.6, 1.2),
                  (1.54, 1.3), (2, 1.4), (2, 1.6), (1, 1.6),
                  (1, 1.4), (1.46, 1.3), (1.4, 1.2), (1, 1.2)]
        attached = [(.8, 1), (1.2, 1), (1.2, 1.2), (.8, 1.2)]
        def region(points):
            lines = ['G36*']
            for index, (x, y) in enumerate([*points, points[0]]):
                lines.append('X%dY%dD0%d*' %
                             (round(x*1000000), round(y*1000000),
                              2 if index == 0 else 1))
            return '\n'.join([*lines, 'G37*']) + '\n'
        prefix = ('%TF.FileFunction,Copper,L1,Top*%\n'
                  '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                  '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\nD10*\n%TO.N,/GND*%\n')
        with tempfile.TemporaryDirectory() as tmp:
            copper = Path(tmp) / 'sample-F_Cu.gtl'
            copper.write_text(prefix + region(narrow) + region(attached) + 'M02*\n')
            with self.assertRaisesRegex(ValueError,
                                        'connected nonorthogonal filled region union has a 0.090000 mm'):
                gerberdrc.check_clearance([copper], .15, .1)
            widened = ('%ADD11R,0.200000X0.200000*%\nD11*\n'
                       'X1500000Y1300000D03*\n')
            copper.write_text(prefix + region(narrow) + region(attached) + widened + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 3)
            at_limit = [(1.55 if x == 1.54 else 1.45 if x == 1.46 else x, y)
                        for x, y in narrow]
            copper.write_text(prefix + region(at_limit) + region(attached) + 'M02*\n')
            self.assertEqual(gerberdrc.check_clearance([copper], .15, .1), 2)
            silk_narrow = [(1.65 if x == 1.6 else 1.56 if x == 1.54 else
                            1.44 if x == 1.46 else 1.35 if x == 1.4 else x, y)
                           for x, y in narrow]
            silk = Path(tmp) / 'sample-F_Silkscreen.gto'
            mask = Path(tmp) / 'sample-F_Mask.gts'
            silk.write_text(prefix.replace('Copper,L1,Top', 'Legend,Top')
                            .replace('0.200000', '0.150000') +
                            region(silk_narrow) + region(attached) + 'M02*\n')
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                            'D10*\nX9000000Y9000000D03*\nM02*\n')
            with self.assertRaisesRegex(ValueError,
                                        'connected nonorthogonal filled region union has a 0.135000 mm'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

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

    def test_isolated_filled_silk_width_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            fab = Path(tmp)
            mask = fab / 'sample-F_Mask.gts'
            silk = fab / 'sample-F_Silkscreen.gto'
            mask.write_text('%TF.FileFunction,Soldermask,Top*%\n'
                            '%TF.FilePolarity,Negative*%\n%FSLAX46Y46*%\n'
                            '%MOMM*%\n%LPD*%\n%ADD10C,0.200000*%\n'
                            'D10*\nX9000000Y9000000D03*\nM02*\n')
            prefix = ('%TF.FileFunction,Legend,Top*%\n'
                      '%TF.FilePolarity,Positive*%\n%FSLAX46Y46*%\n'
                      '%MOMM*%\n%LPD*%\n%ADD10C,0.150000*%\nD10*\n')
            def region(width):
                return ('G36*\nX1000000Y1000000D02*\n'
                        'X2000000Y1000000D01*\n'
                        f'X2000000Y{1000000+width}D01*\n'
                        f'X1000000Y{1000000+width}D01*\n'
                        'X1000000Y1000000D01*\nG37*\n')
            silk.write_text(prefix + region(150000) + 'M02*\n')
            self.assertEqual(gerberdrc.check_silk_clearance(silk, mask, .15, .15), 1)
            silk.write_text(prefix + region(149999) + 'M02*\n')
            with self.assertRaisesRegex(ValueError, 'isolated filled region width 0.149999 mm'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)
            # The bounding-box superset still leaves thin ink outside this
            # perpendicular stroke, so the partial check proves a failure.
            silk.write_text(prefix + region(149999) +
                            'X1500000Y900000D02*\nX1500000Y1200000D01*\nM02*\n')
            with self.assertRaisesRegex(ValueError, 'connected filled region union has a 0.149999 mm span'):
                gerberdrc.check_silk_clearance(silk, mask, .15, .15)

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
