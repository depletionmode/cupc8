"""MB-051: the dual-rail reset qualifier's guaranteed windows, and its netlist binding."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import reset_supervisor as rs
import rail_reset_window as gate


def worst(rows):
    return min(min(r[6], r[7]) for r in rows)


class Windows(unittest.TestCase):
    def test_ladder_bias_corners_satisfy_independent_two_node_kcl(self):
        import numpy as np
        with patch.multiple(rs, REF_ERR=0, R_TOL=0, R_TOL_25=0, IB=1e-6):
            observed = {(round(a, 10), round(b, 10)) for a, b in rs.taps()}
            a, b, c = rs.R_L1, rs.R_L2, rs.R_L3
            matrix = np.array([[1/a + 1/b, -1/b], [-1/b, 1/b + 1/c]])
            expected = {tuple(round(v, 10) for v in np.linalg.solve(matrix, [rs.VREF/a - i33, -i12]))
                        for i33 in (-rs.IB, rs.IB) for i12 in (-rs.IB, rs.IB)}
        self.assertEqual(observed, expected)
        self.assertEqual(len(observed), 4)

    def test_positive_input_bias_expands_both_rail_threshold_intervals(self):
        tap = [(1.6, 1.15)]
        with patch.object(rs, 'IB', 0):
            original = [fn(tap=tap) for fn in (rs.thresholds_3v3, rs.thresholds_1v2)]
        with patch.object(rs, 'IB', 1e-6):
            biased = [fn(tap=tap) for fn in (rs.thresholds_3v3, rs.thresholds_1v2)]
        for before, after in zip(original, biased):
            self.assertLess(after[0], before[0])
            self.assertGreater(after[1], before[1])
            self.assertLess(after[2], before[2])
            self.assertGreater(after[3], before[3])

    def test_high_impedance_tap_is_charged_only_its_own_current(self):
        pin, tap = .0342, .3145
        effective = rs.effective_copper('/+1V2', pin, tap)
        self.assertGreater(effective, pin)
        self.assertLess(effective, rs.copper_limit_1v2())
        self.assertGreaterEqual(worst(rs.m1_margins(cu12=effective)), rs.MARGIN_MIN)
        self.assertGreaterEqual(rs.sense_current_bounds()['/+1V2'],
                                (rs.V33_OP[1] + .1) / (rs.R_S * (1 - rs.R_TOL_1PCT)))

    def test_passive_branch_transfer_and_superposition_bound(self):
        # Exact star: source -- common -- junction -- load; a second
        # junction branch ends at the sense tap. Unit load transfer to the
        # tap is common, even if the tap branch is arbitrarily resistive.
        common, load, sense = .01, .02, .40
        load_self, tap_self, transfer = common + load, common + sense, common
        self.assertLessEqual(transfer, load_self)
        iload, isense = .04, rs.sense_current_bounds()['/+1V2']
        actual_load_drop = iload * load_self + isense * transfer
        actual_tap_drop = iload * transfer + isense * tap_self
        bound = iload * rs.effective_copper('/+1V2', load_self, tap_self)
        self.assertLessEqual(actual_load_drop, bound)
        self.assertLessEqual(actual_tap_drop, bound)
        self.assertGreater(iload * tap_self, bound)

    def test_measured_route_passes_m1_and_keeps_future_failure_visible(self):
        measured = 0.024645342566990188
        self.assertGreaterEqual(worst(rs.m1_margins(measured)), rs.MARGIN_MIN)
        future = next(row for row in rs.margins(measured) if row[0] == '3V3 slots 5-6 full')
        self.assertLess(min(future[6], future[7]), rs.MARGIN_MIN)

    def test_m1_copper_limit_is_derived_from_the_same_five_mv_margins(self):
        limit = rs.copper_limit_3v3()
        self.assertAlmostEqual(worst(rs.m1_margins(limit)), rs.MARGIN_MIN, places=10)
        self.assertLess(worst(rs.m1_margins(limit + 0.001)), rs.MARGIN_MIN)
        self.assertGreaterEqual(worst(rs.m1_margins(limit - 0.001)), rs.MARGIN_MIN)

    def test_core_copper_limit_preserves_the_same_five_mv_margins(self):
        limit = rs.copper_limit_1v2()
        self.assertAlmostEqual(worst(rs.m1_margins(cu12=limit)), rs.MARGIN_MIN, places=10)
        self.assertLess(worst(rs.m1_margins(cu12=limit + 0.001)), rs.MARGIN_MIN)

    def test_every_window_clears_by_at_least_5_mv(self):
        rows = rs.margins()
        self.assertGreaterEqual(worst(rows), rs.MARGIN_MIN)
        names = [r[0] for r in rows]
        self.assertIn('1V2', names)
        self.assertIn('3V3 slots 5-6 full', names)

    def test_thresholds_sit_inside_the_valid_ranges(self):
        f3, f1 = rs.thresholds_3v3(), rs.thresholds_1v2()
        self.assertGreater(f3[0], rs.V33_MIN)
        self.assertLess(max(f3[1], f3[3]), rs.POW001_3V3_LOW)
        self.assertGreater(f1[0], rs.V12_MIN)
        self.assertLess(max(f1[1], f1[3]), rs.POW002_1V2_LOW)

    def test_a_0_ohm_jumper_link_breaks_the_3v3_window(self):
        # the fitted 1206 jumper is <= 50 mOhm: 61 mV at 1.22 A
        with patch.object(rs, 'R_LINK33', 0.050):
            rows = {r[0]: r for r in rs.margins()}
        self.assertLess(rows['3V3 slots 5-6 full'][7], 0)

    def test_a_1_percent_monitor_cannot_hold_the_1v2_window(self):
        # the TPS3890/TPS386000 class: +-1 % reference, as the earlier screens found
        with patch.object(rs, 'REF_ERR', 0.01):
            rows = {r[0]: r for r in rs.margins()}
        self.assertLess(min(rows['1V2'][6], rows['1V2'][7]), rs.MARGIN_MIN)

    def test_the_old_1v2_route_drop_is_outside_the_window(self):
        # salt 9 fed the chipset core through 0.2 mm tracks: 1.68 ohm to U7.92
        rows = {r[0]: r for r in rs.margins(cu12=1.68)}
        self.assertLess(rows['1V2'][6], 0)


class MeshRefinement(unittest.TestCase):
    def test_pll_branch_cannot_be_omitted_from_core_current_inventory(self):
        measurements = {'/+1V2': {('U7', '92'): {.1: 30, .07: 30},
                                  ('R49', '1'): {.1: 200, .07: 200},
                                  ('R50', '1'): {.1: 30, .07: 30},
                                  ('R116', '1'): {.1: 310, .07: 310}}}
        summary = gate.summarize(measurements)
        self.assertEqual(summary['/+1V2'][1], ('R49', '1'))
        self.assertGreater(rs.effective_copper('/+1V2', summary['/+1V2'][0],
                                              summary['/+1V2 tap'][0]), rs.copper_limit_1v2())

    def extract(self, solve):
        pad = SimpleNamespace(GetNumber=lambda: '131', GetNetname=lambda: '/+3V3')
        core = SimpleNamespace(GetNumber=lambda: '92', GetNetname=lambda: '/+1V2')
        board = SimpleNamespace(FindFootprintByReference=lambda _: SimpleNamespace(Pads=lambda: [pad, core]))
        output = StringIO()
        with patch('pcbnew.LoadBoard', return_value=board), patch.object(gate, '_extract_pin', side_effect=solve), redirect_stdout(output):
            result = gate.extract(Path('/unused.kicad_pcb'))
        return result, output.getvalue()

    def test_coarse_open_refines_only_affected_pin_and_keeps_other_results(self):
        calls = []
        def solve(job):
            _, net, _, sink, _, pitch, _ = job[:7]
            calls.append((sink, pitch))
            if sink == ('U7', '131') and pitch == .1:
                raise ValueError('open copper')
            return net, sink, pitch, (20 if pitch == .07 else 20.5) if sink[0] == 'U7' else 10
        result, output = self.extract(solve)
        self.assertEqual(result['/+3V3'][0], .0205)
        self.assertLess(result['/+3V3 pitch'], .1)
        self.assertEqual([sink for sink, pitch in calls if pitch == .05], [('U7', '131')])
        self.assertIn('R116.1 at 0.1 mm', output)
        self.assertIn('mesh refinement /+3V3 U7.131', output)

    def test_refined_disagreement_remains_a_gate_failure(self):
        def solve(job):
            _, net, _, sink, _, pitch, _ = job[:7]
            if sink == ('U7', '131') and pitch == .1:
                raise ValueError('open copper')
            return net, sink, pitch, (20 if pitch in (.07, .035) else 30) if sink == ('U7', '131') else 10
        result, _ = self.extract(solve)
        self.assertGreater(result['/+3V3 pitch'], .1)

    def test_actual_open_is_not_silently_discarded(self):
        def solve(job):
            _, net, _, sink, _, pitch, _ = job[:7]
            if sink[0] == 'U7':
                raise ValueError('open copper')
            return net, sink, pitch, 10
        with self.assertRaisesRegex(ValueError, 'open copper'):
            self.extract(solve)


class MeshReplay(unittest.TestCase):
    def setUp(self):
        import tempfile, hashlib, json
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pcb = self.root / 'main.kicad_pcb'
        self.log = self.root / 'mesh.log'
        self.audit = self.root / 'audit.json'
        self.digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        self.meta = {'completed_exit_code': 0, 'sha256': {}, 'original_sources': {}}
        for name in ('main.kicad_pcb', 'drc.json', 'main.net'):
            p = self.root / name
            p.write_text('immutable board input')
            self.meta['sha256'][str(p)] = self.digest(p)
        for name in ('copper_mesh.py', 'rail_reset_window.py', 'reset_supervisor.py'):
            p = gate.HERE / name
            copied = self.root / name
            copied.write_bytes(p.read_bytes())
            self.meta['sha256'][str(p.resolve())] = self.digest(p)
            self.meta['original_sources'][name] = str(copied)
        rows = [('/+3V3', ('U7', '6'), 25), ('/+3V3', ('R113', '1'), 20),
                ('/+1V2', ('U7', '92'), 30), ('/+1V2', ('R116', '1'), 310),
                ('/+1V2', ('R49', '1'), 20), ('/+1V2', ('R50', '1'), 20)]
        self.log.write_text(''.join('mesh %s %s.%s at %g mm: %.10f mOhm\n' % (net, *sink, pitch, value)
                                   for net, sink, value in rows for pitch in (.1, .07)))
        self.meta['log_sha256'] = self.digest(self.log)
        self.audit.write_text(json.dumps(self.meta))
        pads = [SimpleNamespace(GetNumber=lambda: '6', GetNetname=lambda: '/+3V3'),
                SimpleNamespace(GetNumber=lambda: '92', GetNetname=lambda: '/+1V2')]
        self.board = SimpleNamespace(FindFootprintByReference=lambda _: SimpleNamespace(Pads=lambda: pads))

    def replay(self):
        with patch('pcbnew.LoadBoard', return_value=self.board):
            return gate.replay_mesh(self.pcb, self.log, self.audit)[0]

    def test_completed_replay_keeps_tap_and_qualified_loads_separate(self):
        result = self.replay()
        self.assertAlmostEqual(result['/+1V2'][0], .030)
        self.assertAlmostEqual(result['/+1V2 tap'][0], .310)

    def test_changed_board_or_log_is_rejected(self):
        self.pcb.write_text('changed copper')
        with self.assertRaisesRegex(ValueError, 'changed board input'):
            self.replay()
        self.pcb.write_text('immutable board input')
        self.log.write_text(self.log.read_text() + 'changed result')
        with self.assertRaisesRegex(ValueError, 'altered extraction log'):
            self.replay()

    def test_changed_solver_requires_new_extraction(self):
        import json
        copied = Path(self.meta['original_sources']['copper_mesh.py'])
        copied.write_text(copied.read_text() + '\n# old solver revision\n')
        self.meta['sha256'][str((gate.HERE / 'copper_mesh.py').resolve())] = self.digest(copied)
        self.audit.write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ValueError, 'copper solver changed'):
            self.replay()


class Fake:
    """A netlist with the qualifier's connections; `drop` removes one pin."""

    def __init__(self, drop=None):
        self.pins = dict(gate.PINS)
        if drop:
            self.pins.pop(drop)
        self.components = {'U6': ('MAX811TEUS', ('jlc', 'x'))}
        self.resistors = [SimpleNamespace(ref=ref, ends=tuple('/' + n.lstrip('/') for n in sorted(ends)),
                                          value=('%g' % v if v >= 1 else '%gm' % (v * 1e3)))
                          for ref, (ends, v) in gate.RESISTORS.items()]

    def net(self, ref, pin):
        return self.pins.get((ref, pin))


class Binding(unittest.TestCase):
    def test_the_qualifier_netlist_binds(self):
        with patch.object(gate, 'read', return_value=Fake()):
            gate.netlist_bind('unused')

    def test_slot_clamp_missing_is_rejected(self):
        with patch.object(gate, 'read', return_value=Fake(drop=('U19', '2'))):
            with self.assertRaisesRegex(ValueError, 'U19.2'):
                gate.netlist_bind('unused')

    def test_1v2_monitor_missing_is_rejected(self):
        with patch.object(gate, 'read', return_value=Fake(drop=('D7', '2'))):
            with self.assertRaisesRegex(ValueError, 'D7.2'):
                gate.netlist_bind('unused')

    def test_wrong_threshold_resistor_is_rejected(self):
        fake = Fake()
        next(r for r in fake.resistors if r.ref == 'R113').value = '10k'
        with patch.object(gate, 'read', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'R113'):
                gate.netlist_bind('unused')

    def test_old_board_fails_the_gate(self):
        """The one-rail MAX811 board (no qualifier) cannot pass MB-051."""
        output = StringIO()
        with patch.object(sys, 'argv', ['rail_reset_window.py', 'unused']), \
             patch.object(gate.boardevidence, 'validate'), \
             patch.object(gate, 'check_report'), \
             patch.object(gate.Path, 'read_text', return_value='{}'), \
             patch.object(gate, 'read', return_value=Fake(drop=('U19', '1'))), redirect_stdout(output):
            status = gate.main()
        self.assertEqual(status, 1)
        self.assertIn('FAIL R0', output.getvalue())


class BoardSource(unittest.TestCase):
    """hw/boards/main.py carries the analysed circuit (no board build needed)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'hw/boards'))
        sys.path.insert(0, str(ROOT / 'hw/tools'))
        import main
        cls.parts = {p.ref: p for p in main.build_parts()}

    def test_every_slot_reset_is_clamped_from_npor_on_standby(self):
        u19 = self.parts['U19'].conns
        self.assertEqual(u19['VCC'], '3V3_STBY')
        for k in range(1, 7):
            self.assertEqual(u19['%dA' % k], 'nPOR')
            self.assertEqual(u19['%dY' % k], 'SLOT%d_RST_n' % k)
        self.assertEqual(set(self.parts['R118'].conns.values()), {'nPOR', 'GND'})

    def test_both_monitors_reach_manual_reset(self):
        self.assertEqual(self.parts['D7'].conns, {1: 'MON33_OK', 2: 'MON12_OK', 3: 'nMR'})
        self.assertEqual(self.parts['U18'].conns['OUT'], 'MON33_OK')
        self.assertEqual(self.parts['U20'].conns['IN+'], 'MON12_P')
        self.assertEqual(set(self.parts['R116'].conns.values()), {'+1V2', 'MON12_P'})

    def test_links_are_1_mohm_shunts(self):
        for ref in ('R7', 'R8'):
            self.assertEqual(self.parts[ref].value, '1m')
            self.assertEqual(self.parts[ref].lcsc, rs.PARTS[ref][1])


if __name__ == '__main__':
    unittest.main()
