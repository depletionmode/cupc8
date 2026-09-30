"""MB-005: the input-loop and fault-rise report, and the copper mesh it uses."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import copper_mesh as cm
import design as d
import main_input_heat as gate


def result(milliohms, j=0.4, j_term=1.0, vias=()):
    """A mesh result: j = peak sheet density per ampere (1/j = equivalent width, mm)."""
    grid = np.full((5, 100), j)                  # a 10 mm strip at 0.1 mm pitch
    return cm.Result(milliohms, {'F.Cu': j}, j_term, list(vias), 1000, 10,
                     {'F.Cu': (grid, np.zeros(grid.shape, bool))}, 0.1)


class MainInputHeat(unittest.TestCase):
    def report(self, pos, ret, out, heat_by_name=None):
        def extract(board, cases, solver='cg'):
            table = {id(gate.POSITIVE): pos, id(gate.RETURN): ret, id(gate.OUTPUT): out}[id(cases)]
            return {name: (table, 0.01, [result(table, **((heat_by_name or {}).get(name, KW[0]))),
                                       result(table, **((heat_by_name or {}).get(name, KW[0])))])
                    for name, *_ in cases}
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

    def test_result_without_grids_cannot_pass_the_rise_rule(self):
        # the rule once read nothing from a result with no density grids and passed
        with self.assertRaisesRegex(ValueError, 'no current-density grids'):
            gate.rises(cm.Result(5.0, {'F.Cu': 0.4}, 1.0, [], 1000, 10), 3.213)

    def test_the_old_route_width_fails_heating(self):
        # the salt-9 J1-F1 track: 0.5 mm drawn, 80 % etched, 24.9 um
        rise = cm.ipc_rise(d.insw_ilim()[2], 0.4 * 0.0249)
        self.assertGreater(rise, 100)
        # The earlier 1.75 mm estimate no longer meets 20 C at the current
        # full temperature/tolerance 3.288102 A limit; 1.80 mm does.
        self.assertGreater(cm.ipc_rise(d.insw_ilim()[2], 1.75 * 0.8 * 0.0249), 20.0)
        self.assertLess(cm.ipc_rise(d.insw_ilim()[2], 1.80 * 0.8 * 0.0249), 20.0)

    def test_actual_layer_thickness_sets_the_same_15_c_cut(self):
        amps = d.insw_ilim()[2]
        for thickness in (gate.CORNER.outer_mm, gate.CORNER.inner_mm):
            cut = gate.cut_density(amps, thickness)
            self.assertAlmostEqual(cm.ipc_rise(amps, thickness / cut), 15.0, places=8)
        self.assertLess(gate.cut_density(amps, gate.CORNER.inner_mm),
                        gate.cut_density(amps, gate.CORNER.outer_mm))

    def test_neck_boundary_heat_is_counted_in_body(self):
        amps = d.insw_ilim()[2]
        cut = gate.cut_density(amps)
        grid = np.full((7, 7), cut * .99)
        grid[3, 3] = cut * 2
        r = result(1)
        r.grids = {'F.Cu': (grid, np.zeros(grid.shape, bool))}
        body, _, neck, _ = gate.rises(r, amps)
        self.assertAlmostEqual(body, cm.ipc_rise(amps, gate.CORNER.outer_mm / (cut * .99)))
        self.assertGreater(neck, 0)

    def test_control_ground_excluded_only_from_full_current_thermal(self):
        self.assertTrue(any(src == [('U2', '8')] for _, _, src, _, _ in gate.RETURN))
        self.assertFalse(any(name.startswith('U2:8') for name in gate.THERMAL_RETURN_NAMES))
        expected = {name for name, _, src, _, _ in gate.RETURN
                    if src[0][0] in ('C3', 'C5', 'U3')}
        self.assertEqual(gate.THERMAL_RETURN_NAMES, expected)
        self.assertEqual(len(expected), 6)

    def test_control_stub_heat_cannot_fail_but_each_power_ground_can(self):
        control = {name: {'j': 2.5} for name, *_ in gate.RETURN if name.startswith('U2:8')}
        status, text = self.report(5.0, 3.0, 5.0, control)
        self.assertEqual(status, 0, text)
        for ref in ('C3', 'C5', 'U3'):
            with self.subTest(power_ground=ref):
                heat = {name: {'j': 2.5} for name, *_ in gate.RETURN if name.startswith(ref + ':')}
                status, text = self.report(5.0, 3.0, 5.0, heat)
                self.assertEqual(status, 1)
                self.assertIn('FAIL I3', text)

    def test_enable_pin_is_not_the_buck_power_input(self):
        self.assertEqual(gate.INPUT_PINS[('U3', '1')], '/5V_SYS')
        self.assertEqual(gate.THERMAL_OUTPUT_NAMES, {'U2 OUT -> R4:1', 'U2 OUT -> U3:4',
                                                   'U2 OUT -> C3:1', 'U2 OUT -> C5:1'})
        status, text = self.report(5.0, 3.0, 5.0, {'U2 OUT -> U3:1': {'j': 2.5}})
        self.assertEqual(status, 0, text)
        status, text = self.report(5.0, 3.0, 5.0, {'U2 OUT -> U3:4': {'j': 2.5}})
        self.assertEqual(status, 1)
        self.assertIn('FAIL I3', text)

    def test_each_capacitor_positive_escape_is_mandatory(self):
        for name in ('U2 OUT -> C3:1', 'U2 OUT -> C5:1'):
            with self.subTest(shorted_capacitor=name):
                status, text = self.report(5.0, 3.0, 5.0, {name: {'j': 2.5}})
                self.assertEqual(status, 1)
                self.assertIn('FAIL I3', text)

    def test_coarse_pitch_failure_cannot_hide_behind_fine_pass(self):
        calls = 0
        def bound(r, amps):
            nonlocal calls
            calls += 1
            return (21.0 if calls == 1 else 1.0, 1.0, 0.0, 0.0)
        with patch.object(gate, 'rises', side_effect=bound):
            status, text = self.report(5.0, 3.0, 5.0)
        self.assertEqual(status, 1)
        self.assertIn('FAIL I3', text)
        self.assertEqual(calls, 2 * (len(gate.POSITIVE) + len(gate.THERMAL_RETURN_NAMES) + len(gate.THERMAL_OUTPUT_NAMES)))

    def test_adaptive_convergence_retains_all_coarse_bounds(self):
        case = [gate.OUTPUT[0]]
        with patch.object(cm, 'solve', side_effect=[result(100), result(80), result(75)]) as solve:
            maximum, disagreement, runs = gate.extract(None, case, solver='amg')[case[0][0]]
        self.assertEqual(maximum, 100)
        self.assertAlmostEqual(disagreement, 5 / 80)
        self.assertEqual(len(runs), 3)
        self.assertEqual([call.args[5] for call in solve.call_args_list], [.1, .07, .05])
        caches = [call.kwargs['geometry_cache'] for call in solve.call_args_list]
        self.assertTrue(all(cache is caches[0] for cache in caches))
        self.assertTrue(all(call.kwargs['solver'] == 'amg' for call in solve.call_args_list))

    def test_nonconverged_refinement_remains_a_failure(self):
        case = [gate.OUTPUT[0]]
        with patch.object(cm, 'solve', side_effect=[result(100), result(80), result(60), result(40)]):
            maximum, disagreement, runs = gate.extract(None, case)[case[0][0]]
        self.assertEqual(maximum, 100)
        self.assertGreater(disagreement, gate.CONVERGENCE_LIMIT)
        self.assertEqual(len(runs), 4)

    def test_dump_binds_receipt_model_and_every_grid_without_mutating_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / 'board'
            receipt.mkdir()
            (receipt / 'main.kicad_pcb').write_text('real PCB placeholder for digest regression')
            (receipt / 'evidence.json').write_text('{}')
            path = root / 'report.json'
            hashes = gate.model_sources()
            grids = [result(10), result(8)]
            grids[1].pitch = .07
            cases = {'case': (10, .2, grids)}
            with patch.object(gate.boardevidence, 'validate') as validate:
                gate.dump_results(path, receipt, (cases,), 1, hashes)
            validate.assert_called_once_with('main', receipt)
            report = json.loads(path.read_text())
            self.assertEqual(report['gate_exit_status'], 1)
            self.assertFalse(report['manufacturing_release'])
            self.assertEqual(report['pcb_sha256'], gate.boardevidence.digest(receipt / 'main.kicad_pcb'))
            self.assertEqual(report['model_sources'], hashes)
            self.assertEqual([r['pitch_mm'] for r in report['cases'][0]['meshes']], [.1, .07])
            with np.load(path.with_suffix('.npz')) as arrays:
                for mesh in report['cases'][0]['meshes']:
                    np.testing.assert_equal(arrays[mesh['layers']['F.Cu']['density']], grids[0].grids['F.Cu'][0])
            self.assertEqual(sorted(p.name for p in receipt.iterdir()), ['evidence.json', 'main.kicad_pcb'])
            with patch.object(gate, 'model_sources', return_value={}):
                with self.assertRaisesRegex(ValueError, 'changed during qualification'):
                    gate.dump_results(path, receipt, (cases,), 1, hashes)
            with self.assertRaisesRegex(ValueError, 'outside'):
                gate.dump_results(receipt / 'report.json', receipt, (cases,), 1, hashes)

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

    def test_compiled_solvers_preserve_resistance_and_current_density(self):
        import importlib.util
        if importlib.util.find_spec('scipy') is None:
            self.skipTest('optional SciPy sparse solver is not installed')
        board = self.board(2.0, 20.0)
        args = (board, '/T', [('A', '1')], [('B', '1')], (-2, 7, 22, 13), 0.1)
        original = cm.solve(*args)
        solvers = ['sparse'] + (['amg'] if importlib.util.find_spec('pyamg') else [])
        for solver in solvers:
            with self.subTest(solver=solver):
                compiled = cm.solve(*args, solver=solver)
                self.assertAlmostEqual(compiled.milliohms, original.milliohms, places=6)
                self.assertAlmostEqual(compiled.j_max_a_per_mm['F.Cu'], original.j_max_a_per_mm['F.Cu'], places=6)
                np.testing.assert_allclose(compiled.grids['F.Cu'][0], original.grids['F.Cu'][0], atol=1e-6)
                with self.assertRaisesRegex(ValueError, 'open copper|no copper'):
                    cm.solve(board, '/T', [('A', '1')], [('B', '1')], (-2, 7, 10, 13), 0.1, solver=solver)

    def test_cached_geometry_solves_each_terminal_pair_again(self):
        import pcbnew
        board = self.board(2.0, 20.0)
        middle = pcbnew.FOOTPRINT(board.FindFootprintByReference('A'))
        middle.SetReference('C')
        middle.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(10)))
        board.Add(middle)
        for pad in middle.Pads():
            pad.SetNet(board.FindNet('/T'))
        cache = {}
        args = (board, '/T', [('A', '1')])
        window = (-2, 7, 22, 13)
        full = cm.solve(*args, [('B', '1')], window, 0.1, geometry_cache=cache)
        half = cm.solve(*args, [('C', '1')], window, 0.1, geometry_cache=cache)
        fresh = cm.solve(*args, [('C', '1')], window, 0.1)
        self.assertLess(half.milliohms, 0.6 * full.milliohms)
        self.assertAlmostEqual(half.milliohms, fresh.milliohms, places=8)
        np.testing.assert_allclose(half.grids['F.Cu'][0], fresh.grids['F.Cu'][0], atol=1e-8)

    def test_unloaded_probe_reports_transfer_without_drawing_load(self):
        import pcbnew
        board = self.board(2.0, 20.0)
        middle = pcbnew.FOOTPRINT(board.FindFootprintByReference('A'))
        middle.SetReference('C')
        middle.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10), pcbnew.FromMM(10)))
        board.Add(middle)
        for pad in middle.Pads():
            pad.SetNet(board.FindNet('/T'))
        args = (board, '/T', [('A', '1')], [('B', '1')], (-2, 7, 22, 13), .1)
        original = cm.solve(*args)
        probed = cm.solve(*args, probes=(('C', '1'), ('B', '1')))
        self.assertAlmostEqual(original.milliohms, probed.milliohms, places=8)
        self.assertAlmostEqual(probed.transfer_milliohms[('B', '1')], probed.milliohms, places=8)
        self.assertGreater(probed.transfer_milliohms[('C', '1')], .45 * probed.milliohms)
        self.assertLess(probed.transfer_milliohms[('C', '1')], .60 * probed.milliohms)


if __name__ == '__main__':
    unittest.main()
