"""MB-005: the input-loop and fault-rise report, and the copper mesh it uses."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import copper_mesh as cm
import design as d
import main_input_heat as gate


def result(milliohms, j=0.4, j_term=1.0, vias=()):
    """A mesh result: j = peak sheet density per ampere (1/j = equivalent width, mm)."""
    return cm.Result(milliohms, {'F.Cu': j}, j_term, list(vias), 1000, 10)


class MainInputHeat(unittest.TestCase):
    def report(self, pos, ret, out):
        def extract(board, cases):
            table = {id(gate.POSITIVE): pos, id(gate.RETURN): ret, id(gate.OUTPUT): out}[id(cases)]
            return {name: (table, 0.01, result(table, **KW[0])) for name, *_ in cases}
        output = StringIO()
        with patch.object(sys, 'argv', ['main_input_heat.py', 'unused']), \
             patch.object(gate, 'inspect', return_value=None), \
             patch.object(gate, 'extract', side_effect=extract), redirect_stdout(output):
            status = gate.main()
        return status, output.getvalue()

    def setUp(self):
        KW[0] = {}

    def test_requirement_is_the_decided_60_mohm_and_20_c(self):
        self.assertAlmostEqual(gate.LOOP_LIMIT_MOHM, 60.0)
        self.assertAlmostEqual(d.R_RECEPTACLE, 0.060)
        self.assertEqual(gate.RISE_LIMIT_C, 20.0)
        self.assertAlmostEqual(gate.CORNER.temperature_c, 115.0)

    def test_wide_short_loop_passes(self):
        status, text = self.report(5.0, 3.0, 5.0)
        self.assertIn('pass I1', text)
        self.assertIn('pass I3', text)
        self.assertEqual(status, 0, text)

    def test_loop_over_60_mohm_fails(self):
        # 2 x 25 positive + 6 return + 5 allowance = 61 mOhm
        status, text = self.report(25.0, 6.0, 5.0)
        self.assertEqual(status, 1)
        self.assertIn('FAIL I1', text)

    def test_narrow_conductor_fails_the_20_c_rule(self):
        KW[0] = {'j': 1 / 0.4}              # 0.4 mm of outer copper carrying 3.213 A
        status, text = self.report(5.0, 3.0, 5.0)
        self.assertEqual(status, 1)
        self.assertIn('FAIL I3', text)

    def test_the_old_route_width_fails_heating(self):
        # the salt-9 J1-F1 track: 0.5 mm drawn, 80 % etched, 24.9 um
        rise = cm.ipc_rise(d.insw_ilim()[2], 0.4 * 0.0249)
        self.assertGreater(rise, 100)
        # 1.75 mm drawn is the derivation's 20 C width
        self.assertLess(cm.ipc_rise(d.insw_ilim()[2], 1.75 * 0.8 * 0.0249), 20.5)

    def test_invalid_receipt_fails_before_route_report(self):
        output = StringIO()
        with patch.object(sys, 'argv', ['main_input_heat.py', 'unused']), \
             patch.object(gate, 'inspect', side_effect=ValueError('stale receipt')), \
             redirect_stdout(output):
            status = gate.main()
        self.assertEqual(status, 1)
        self.assertIn('FAIL I0', output.getvalue())
        self.assertNotIn('fault corner', output.getvalue())

    def test_receipted_board_with_drc_finding_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'drc.json').write_text(json.dumps({
                'included_severities': ['error', 'warning', 'exclusion'],
                'violations': [{'description': 'shorted rail'}],
                'unconnected_items': [], 'schematic_parity': [],
            }))
            with patch.object(gate.boardevidence, 'validate'):
                with self.assertRaisesRegex(ValueError, 'drc has 1 findings'):
                    gate.inspect(path)


KW = [{}]


class CopperMesh(unittest.TestCase):
    """The mesh on a real pcbnew board: one straight track between two pads."""

    def board(self, width_mm, length_mm, layer_name='F.Cu', via=False):
        import pcbnew
        mm = pcbnew.FromMM
        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, '/T')
        board.Add(net)
        for ref, x in (('A', 0.0), ('B', length_mm)):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            pad = pcbnew.PAD(fp)
            pad.SetNumber('1')
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            ls = pcbnew.LSET()
            ls.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(ls)
            pad.SetSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
            fp.Add(pad)
            fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(10.0)))
            board.Add(fp)
            pad.SetNet(net)
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(0.0), mm(10.0)))
        t.SetEnd(pcbnew.VECTOR2I(mm(length_mm), mm(10.0)))
        t.SetWidth(mm(width_mm))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net)
        board.Add(t)
        return board

    def test_straight_track_matches_its_sheet_resistance(self):
        corner = cm.Corner()
        board = self.board(2.0, 20.0)
        r = cm.solve(board, '/T', [('A', '1')], [('B', '1')], (-2, 7, 22, 13), 0.05, corner)
        # pad edges at 0.5 and 19.5 mm: 19 mm of 1.6 mm effective width
        expect = 1000 * corner.rho * 19.0 / (0.8 * 2.0 * corner.outer_mm)
        self.assertAlmostEqual(r.milliohms, expect, delta=0.08 * expect)
        # the whole ampere crosses 1.6 mm: 0.625 A/mm
        self.assertAlmostEqual(r.j_max_a_per_mm['F.Cu'], 1 / 1.6, delta=0.15 / 1.6)

    def test_open_copper_is_an_error(self):
        board = self.board(2.0, 20.0)
        with self.assertRaisesRegex(ValueError, 'open copper|no copper'):
            cm.solve(board, '/T', [('A', '1')], [('B', '1')], (-2, 7, 10, 13), 0.1)


if __name__ == '__main__':
    unittest.main()
