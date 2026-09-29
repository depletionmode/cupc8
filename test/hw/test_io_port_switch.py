"""IC-005 (hw/power/io_port_switch.py): the TPS2553DBVR-1's guaranteed
current-limit window, its FAULT levels, and the transient decks. Mutations of
the limit resistor or pull-up must fail the checks."""
import contextlib
import io
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import io_port_switch as ps  # noqa: E402
from spice import Checks  # noqa: E402


def failed(**kw):
    with contextlib.redirect_stdout(io.StringIO()):
        c = Checks('test')
        ps.analytic_checks(c, **kw)
    return c.failed


class PortSwitch(unittest.TestCase):
    def test_proposed_window_covers_the_keyboard(self):
        lo, hi = ps.ios_window()
        self.assertGreaterEqual(lo, 0.500)
        self.assertAlmostEqual(lo, 0.5142, places=3)
        self.assertAlmostEqual(hi, 0.6474, places=3)
        self.assertEqual(failed(), [])

    def test_window_encloses_every_tested_datasheet_row(self):
        lo_env, hi_env = ps.envelope()
        for r, lo, hi in ps.IOS_TABLE:
            self.assertLessEqual(ps.ios_eq(r * 1e3, 'min') * lo_env, lo / 1e3 + 1e-9)
            self.assertGreaterEqual(ps.ios_eq(r * 1e3, 'max') * hi_env, hi / 1e3 - 1e-9)

    def test_mutation_higher_rilim_fails_minimum(self):
        self.assertIn('S1', failed(rilim=47.5e3))       # 491 mA min

    def test_mutation_loose_resistor_fails_minimum(self):
        self.assertIn('S1', failed(tol=0.05))

    def test_mutation_stiff_pullup_fails_fault_low(self):
        self.assertIn('S7', failed(r_pullup=1e3))       # 3.5 mA: VOL not specified

    def test_short_deck_latches_after_the_deglitch(self):
        deck = ps.deck('short', 5.4, 0.647, t_resp=2e-6, t_deg=10e-3)
        t_off = ps.T_SHORT + 2e-6 + 10e-3
        ven = next(line for line in deck.splitlines() if line.startswith('Ven '))
        points = [float(x) for x in ven[ven.index('(') + 1:-1].split()]
        self.assertAlmostEqual(points[2], t_off, delta=1e-9)       # on until the latch
        self.assertEqual(points[-1], 0.0)                           # then off
        self.assertIn('Vilim ilim 0 PWL(0 0.647 %g 0.647' % ps.T_SHORT, deck)
        self.assertRegex(ps.deck('short', 5.4, 0.647, latch=False), r'(?m)^Ven en 0 DC 1$')

    def test_ti_deck_replaces_the_sy6280_with_the_switch(self):
        deck = ps.ti_deck('high', 0.647, 2e-6, 1e-12)
        self.assertIn('TPS61023_schematic', deck)
        self.assertNotRegex(deck, r'(?m)^Rsw ')
        self.assertNotRegex(deck, r'(?m)^Iload ')
        self.assertIn('Bsw vin vs I = V(g) * 0.5 * (1 + tanh((V(vin) - 2.35) / 0.02)) * V(ilim) '
                      '* tanh(V(vin, vs) / (0.06 * V(ilim)))', deck)

    @unittest.skipUnless(shutil.which('ngspice'), 'needs ngspice')
    def test_mutation_100n_at_in_fails_the_in_overshoot(self):
        # TI's 0.1 uF minimum at IN, 10 nH of track, a short at the receptacle:
        # IN rings over its 7 V absolute max; the 1 uF keeps it under
        kw = dict(corner='high', ios=0.647, t_resp=ps.T_RESP_TYP, l_short=50e-9, t_fall=1e-7)
        up = ps.VBOOST_MAX
        bad = ps.ti_short(('test_100n', dict(kw, c_in=100e-9)))
        good = ps.ti_short(('test_1u', dict(kw, c_in=1e-6)))
        self.assertGreater(bad['vinmax'] + up - bad['vbpre'], ps.VIN_ABS)
        self.assertLess(good['vinmax'] + up - good['vbpre'], ps.VIN_ABS)


if __name__ == '__main__':
    unittest.main()
