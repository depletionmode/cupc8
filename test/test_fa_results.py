"""First-article record parsing and gate status (tools/fa_results.py)."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fa_results as fa

GOOD_CAP = {'c_5v5_uf': 9.0, 'c_3v6_uf': 12.5, 'esr_max_mohm': 6.0}


def record(test='WC-103', board='wifi', unit='u1', measurements=None, **extra):
    rec = dict(schema=fa.SCHEMA, test=test, board=board, unit=unit, date='2026-10-10',
               measurements=dict(GOOD_CAP if measurements is None else measurements))
    if test == 'WC-103':
        rec.update(part_lcsc='C602037', lot='fitted-lot-A')
    rec.update(extra)
    return rec


class FaResultsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rec, folder=None, name=None):
        path = self.dir / (folder or rec['test']) / (name or '%s-%s.json' % (rec['unit'], rec['date']))
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(rec))
        return path

    def test_green_needs_enough_passing_units(self):
        for i in range(9):
            self.write(record(unit='s%d' % i))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'pending')
        self.write(record(unit='s9'))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'green')

    def test_wc103_rejects_wrong_or_missing_part_and_lot(self):
        for field, bad in (('part_lcsc', 'C45783'), ('part_lcsc', None),
                           ('lot', ''), ('lot', None), ('lot', 123)):
            with self.subTest(field=field, bad=bad):
                rec = record(**{field: bad})
                self.assertEqual(fa.verdict(rec)[0], 'fail')
                with self.assertRaisesRegex(ValueError, field):
                    fa.load(self.write(rec))

    def test_wc103_mixed_lots_do_not_close_ten_part_gate(self):
        for i in range(10):
            self.write(record(unit='s%d' % i, lot='A' if i < 5 else 'B'))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'pending')
        for i in range(10, 15):
            self.write(record(unit='s%d' % i, lot='A'))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'green')

    def test_repeat_records_of_one_unit_count_once(self):
        for day in range(10):
            self.write(record(unit='same', date='2026-10-%02d' % (day + 1)))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'pending')

    def test_one_failure_is_red_until_voided(self):
        for i in range(10):
            self.write(record(unit='s%d' % i))
        bad = record(unit='s10', measurements=dict(GOOD_CAP, esr_max_mohm=151))
        path = self.write(bad)
        state, lines = fa.status('WC-103', fa.records(self.dir))
        self.assertEqual(state, 'red')
        self.assertIn('esr_max_mohm', '\n'.join(lines))
        path.write_text(json.dumps(dict(bad, void='probe fixture open, remeasured as s11')))
        self.assertEqual(fa.status('WC-103', fa.records(self.dir))[0], 'green')

    def test_missing_measurement_is_incomplete_not_pass(self):
        rec = record(measurements={'c_5v5_uf': 9.0, 'c_3v6_uf': 12.5})
        self.assertEqual(fa.verdict(rec)[0], 'incomplete')

    def test_limits_at_the_edge(self):
        self.assertEqual(fa.verdict(record(measurements=dict(GOOD_CAP, esr_max_mohm=150)))[0], 'pass')
        self.assertEqual(fa.verdict(record(measurements=dict(GOOD_CAP, c_5v5_uf=7.79)))[0], 'fail')
        rails = {'v_3v3_v': 3.391, 'v_1v2_v': 1.2, 'ripple_3v3_mvpp': 5}
        self.assertEqual(fa.verdict(record('MB-101', 'main', measurements=rails))[0], 'fail')

    def test_copper_scaled_to_hot_corner(self):
        # 44 mOhm at 20 C is 44 x (1 + 0.00393 x 95) = 60.4 mOhm at 115 C: fails MB-108
        rec = record('MB-108', 'main', measurements={'r_loop_mohm': 44.0, 'board_temp_c': 20.0})
        self.assertAlmostEqual(fa.value(rec, 'r_loop_mohm'), 44.0 * (1 + 0.00393 * 95))
        self.assertEqual(fa.verdict(rec)[0], 'fail')
        rec['measurements']['r_loop_mohm'] = 43.0
        self.assertEqual(fa.verdict(rec)[0], 'pass')

    def test_heating_scaled_to_rated_current(self):
        # Normalize to the guaranteed limit, including external RILM tolerance/TCR.
        rec = record('MB-109', 'main', measurements={'i_load_a': 2.8, 'minutes_at_load': 20,
                                                     'dt_input_copper_c': 12.0})
        self.assertAlmostEqual(fa.value(rec, 'dt_input_copper_c'), 12.0 * (fa.insw_ilim()[2] / 2.8) ** 2)
        self.assertEqual(fa.verdict(rec)[0], 'pass')
        rec['measurements']['dt_input_copper_c'] = 16.0
        self.assertEqual(fa.verdict(rec)[0], 'fail')

    def test_gpu_hdmi_hpd_and_edid_gate(self):
        # GC-105: a real monitor's hot-plug detect and EDID through the GPU card's DDC path
        good = {'hpd_off_v': 0.02, 'hpd_on_v': 2.95, 'ddc_idle_5v_side_v': 4.9, 'ddc_idle_3v3_side_v': 3.3,
                'edid_bytes_read': 128, 'edid_header_ok': 1, 'edid_checksum_ok': 1}
        self.assertEqual(fa.verdict(record('GC-105', 'gpu', measurements=good))[0], 'pass')
        for key, value in (('hpd_on_v', 1.44),         # a 2.4 V sink HPD through the 22k/33k divider
                           ('hpd_off_v', 0.6), ('ddc_idle_3v3_side_v', 2.6), ('edid_bytes_read', 127),
                           ('edid_header_ok', 0), ('edid_checksum_ok', 0)):
            self.assertEqual(fa.verdict(record('GC-105', 'gpu', measurements=dict(good, **{key: value})))[0],
                             'fail', key)
        missing = {k: v for k, v in good.items() if k != 'edid_checksum_ok'}
        self.assertEqual(fa.verdict(record('GC-105', 'gpu', measurements=missing))[0], 'incomplete')
        for unit in ('a', 'b'):
            self.write(record('GC-105', 'gpu', unit, good))
        self.assertEqual(fa.status('GC-105', fa.records(self.dir))[0], 'green')

    def test_reset_thresholds_require_room_and_soaked_hot_measurements(self):
        good = {'ambient_room_c': 25, 'ambient_hot_c': 40, 'minutes_hot': 30,
                'v_3v3_fall_trip_v': 3.19, 'v_1v2_fall_trip_v': 1.155,
                'v_3v3_fall_trip_hot_v': 3.19, 'v_1v2_fall_trip_hot_v': 1.155,
                'slot_rst_held': 1}
        self.assertEqual(fa.verdict(record('MB-113', 'main', measurements=good))[0], 'pass')
        for key in ('ambient_hot_c', 'minutes_hot', 'v_3v3_fall_trip_hot_v',
                    'v_1v2_fall_trip_hot_v'):
            with self.subTest(missing=key):
                missing = {k: v for k, v in good.items() if k != key}
                result, lines = fa.verdict(record('MB-113', 'main', measurements=missing))
                self.assertEqual(result, 'incomplete')
                self.assertIn(key, '\n'.join(lines))
        for key, value in (('ambient_hot_c', 37.9), ('minutes_hot', 29.9),
                           ('v_3v3_fall_trip_hot_v', 3.1697),
                           ('v_3v3_fall_trip_hot_v', 3.2036),
                           ('v_1v2_fall_trip_hot_v', 1.1506),
                           ('v_1v2_fall_trip_hot_v', 1.1605)):
            with self.subTest(field=key, value=value):
                result, lines = fa.verdict(record('MB-113', 'main', measurements=dict(good, **{key: value})))
                self.assertEqual(result, 'fail')
                self.assertIn(key, '\n'.join(lines))
        for unit in ('a', 'b'):
            self.write(record('MB-113', 'main', unit, good))
            expected = 'pending' if unit == 'a' else 'green'
            self.assertEqual(fa.status('MB-113', fa.records(self.dir))[0], expected)

    def test_malformed_records_are_rejected(self):
        cases = [(dict(record(), schema='cupc8-fa/0'), 'schema'),
                 (dict(record(), test='XX-999'), 'unknown test'),
                 (dict(record(), board='gpu'), 'not covered'),
                 (record(measurements=dict(GOOD_CAP, esr_max_mohm='6')), 'not a number'),
                 (record(measurements=dict(GOOD_CAP, esr_max_mohm=True)), 'not a number')]
        for rec, message in cases:
            path = self.write(rec, folder=rec['test'] if rec['test'] in fa.GATES else 'WC-103')
            with self.assertRaisesRegex(ValueError, message):
                fa.load(path)
            path.unlink()
        with self.assertRaisesRegex(ValueError, 'filed under'):
            fa.load(self.write(record(), folder='WC-104'))

    def test_multi_board_gate_needs_every_board(self):
        mech = {'notch_width_mm': 1.90, 'notch_gap_min_mm': 0.15, 'fingers_trimmed': 0,
                'inserts_by_hand': 1, 'reverse_blocked': 1, 'continuity_max_ohm': 0.1,
                'continuity_10_cycles_max_ohm': 0.1, 'adjacent_shorts': 0}
        for board in fa.GATES['MECH-101']['boards'][:-1]:
            for unit in ('a', 'b'):
                self.write(record('MECH-101', board, board + unit, mech))
        self.assertEqual(fa.status('MECH-101', fa.records(self.dir))[0], 'pending')
        for unit in ('a', 'b'):
            self.write(record('MECH-101', 'system', 'system' + unit, mech))
        self.assertEqual(fa.status('MECH-101', fa.records(self.dir))[0], 'green')

    def test_cli_exit_code(self):
        def run():
            with contextlib.redirect_stdout(io.StringIO()):
                return fa.main(['--dir', str(self.dir), 'WC-103'])
        self.assertEqual(run(), 1)
        for i in range(10):
            self.write(record(unit='s%d' % i))
        self.assertEqual(run(), 0)

    def test_every_gate_is_well_formed(self):
        for test, gate in fa.GATES.items():
            self.assertTrue(set(gate['boards']) <= set(fa.BOARDS), test)
            self.assertGreaterEqual(gate['units'], 1, test)
            for mid, rule in gate.get('scale', {}).items():
                self.assertIn(mid, gate['m'], test)
                self.assertIn(rule[0], ('cu', 'i2'), test)
                self.assertIn('board_temp_c' if rule[0] == 'cu' else rule[1], gate['m'], test)
            for lim in gate['m'].values():
                self.assertIn(lim[0], ('<=', '>=', 'range'), test)
                self.assertEqual(len(lim), 3 if lim[0] == 'range' else 2, test)


if __name__ == '__main__':
    unittest.main()
