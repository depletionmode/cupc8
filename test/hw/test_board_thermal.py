"""Main board / CPU card thermal rows (MB-006, CC-006): iCE40 1V2 and HT7533."""
from pathlib import Path
from unittest.mock import patch
import contextlib
import copy
import dataclasses
import io
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
import board_thermal as bt
import design as d
from cosim.netlist import read

BUILD = ROOT / 'build/hw'


def circuit(board):
    return read(BUILD / board / f'{board}.net')


def with_resistor(base, ref, value):
    resistors = tuple(dataclasses.replace(r, value=value) if r.ref == ref else r
                      for r in base.resistors)
    return dataclasses.replace(base, resistors=resistors)


class Standby(unittest.TestCase):
    def test_loads_fit_at_the_rated_input(self):
        loads = bt.stby_loads(circuit('main'))
        total = sum(i for _, i in loads)
        self.assertLess(total, bt.ht7533_allowed())
        self.assertLess(bt.tj(bt.ht7533_w(total), bt.HT_THETA_JA), d.TJ_LIMIT_C)

    def test_heavy_enable_pulldown_fails(self):
        # mutation: R44 (PWR_EN pull-down) cut to 470 ohm, 7 mA from 3V3_STBY
        loads = bt.stby_loads(with_resistor(circuit('main'), 'R44', '470'))
        total = sum(i for _, i in loads)
        self.assertGreater(total, bt.ht7533_allowed())
        self.assertGreater(bt.tj(bt.ht7533_w(total), bt.HT_THETA_JA), d.TJ_LIMIT_C)

    def test_new_standby_part_is_unmodelled(self):
        # a reset-qualifier part on 3V3_STBY must be modelled before it passes
        c = copy.deepcopy(circuit('main'))
        c.components['U17'] = ('REF3425IDBVR', ('jlc', 'REF3425IDBVR'))
        c.pins[('U17', '3')] = bt.STBY_NET
        c.nets[bt.STBY_NET] = list(c.nets[bt.STBY_NET]) + [('U17', '3')]
        with self.assertRaises(ValueError):
            bt.stby_loads(c)

    def test_reset_buffer_on_standby_is_charged_and_fits(self):
        # U19 (SN74LVC07A, MB-051) on 3V3_STBY with all six inputs on nPOR: each input is
        # charged its dICC, and the total must still fit the HT7533 (headroom ~5.76 mA)
        c = copy.deepcopy(circuit('main'))
        c.components['U19'] = ('SN74LVC07A', ('jlc', 'SN74LVC07A'))
        for pin, net in [('14', bt.STBY_NET), ('7', '/GND')] + [(str(k), '/nPOR') for k in (1, 3, 5, 9, 11, 13)]:
            c.pins[('U19', pin)] = net
            c.nets[net] = list(c.nets.get(net, [])) + [('U19', pin)]
        loads = dict(bt.stby_loads(c))
        lvc = [i for name, i in loads.items() if name.startswith('U19')]
        self.assertEqual(lvc, [bt.LVC07_ICC_MAX + 6 * bt.LVC07_DICC_MAX])
        self.assertLess(sum(loads.values()), bt.ht7533_allowed())

    def test_datasheet_theta_is_used(self):
        self.assertEqual(bt.HT_THETA_JA, 500.0)
        with patch.object(bt, 'HT_THETA_JA', 50000.0):
            self.assertLess(bt.ht7533_allowed(), sum(i for _, i in bt.stby_loads(circuit('main'))))


class CoreRail(unittest.TestCase):
    def test_ceiling_matches_thm001_formula(self):
        i = bt.rt9013_ceiling()
        self.assertAlmostEqual(bt.tj(bt.rt9013_w(i), d.RT9013_THETA_JA), d.TJ_LIMIT_C)
        self.assertGreater(i, bt.ICE40_ICCPEAK_MAX + bt.ICE40_ICCPLLPEAK_MAX)

    def test_branches(self):
        for board in ('main', 'cpu'):
            branches, pll = bt.rail_1v2(board, circuit(board))
            self.assertEqual(len(pll), 2)
            self.assertLess(sum(i for _, i in branches), 2e-3)

    def test_heavy_sense_branch_breaks_the_ceiling(self):
        # mutation: the main 1V2 sense resistor R100 cut from 1k to 10 ohm
        branches, _ = bt.rail_1v2('main', with_resistor(circuit('main'), 'R100', '10'))
        self.assertGreater(sum(i for _, i in branches), bt.rt9013_ceiling())

    def test_fpga_resources_fit_hx4k(self):
        res = bt.fpga_resources(ROOT / 'build/fpga/chipset/chipset.asc')
        self.assertGreater(res['LUTs'], 0)
        self.assertLessEqual(res['LUTs'] + res['CARRYs'], 2 * 3520)
        self.assertEqual(bt.fpga_clocks(ROOT / 'build/fpga/cpucard/cpucard.json'), {'CPU_CLK'})


class Row(unittest.TestCase):
    def run_row(self, board):
        with contextlib.redirect_stdout(io.StringIO()) as text:
            rc = bt.check_board(board, BUILD / board, validate=False)
        return rc, text.getvalue()

    def test_operating_core_current_is_open(self):
        rc, text = self.run_row('cpu')
        self.assertEqual(rc, 1)
        self.assertIn('FAIL F2', text)
        self.assertIn('pass F1', text)

    def test_supplied_core_bound_gates(self):
        with patch.object(bt, 'ICE40_CORE_MAX', 0.040):
            rc, text = self.run_row('main')
        self.assertEqual(rc, 0, text)
        self.assertIn('pass H2', text)
        # mutation: a core maximum over the RT9013 ceiling fails
        with patch.object(bt, 'ICE40_CORE_MAX', 0.120):
            rc, text = self.run_row('main')
        self.assertEqual(rc, 1)
        self.assertIn('FAIL F2', text)


if __name__ == '__main__':
    unittest.main()
