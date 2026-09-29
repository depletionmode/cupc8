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
