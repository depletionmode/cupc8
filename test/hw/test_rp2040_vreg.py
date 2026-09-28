"""Mutation evidence for hw/power/rp2040_vreg.py (RP2040 VREG/DVDD point)."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import rp2040_vreg  # noqa: E402
from spice import Checks  # noqa: E402

GPU_MAIN = (ROOT / 'fw/rp2040/gpu/main.c').read_text()


def run(card, main_c=None, net=None):
    """Failed check ids for `card`, optionally with main.c text or netlist replaced."""
    out = ROOT / 'build/hw' / card
    with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
        if main_c is not None:
            directory = rp2040_vreg.CARDS[card][0]
            (Path(tmp) / 'fw/rp2040' / directory).mkdir(parents=True)
            (Path(tmp) / 'fw/rp2040' / directory / 'main.c').write_text(main_c)
        if net is not None:
            (Path(tmp) / (card + '.net')).write_text(net)
            out = Path(tmp)
        with patch.object(rp2040_vreg, 'ROOT', Path(tmp) if main_c is not None else ROOT):
            c = Checks('test')
            rp2040_vreg.check(card, out, c)
    return c.failed


@unittest.skipUnless((ROOT / 'build/hw/gpu/gpu.net').exists(), 'needs build/hw/gpu')
class Rp2040Vreg(unittest.TestCase):
    def test_gpu_overclock_fails_by_data_sheet(self):
        self.assertEqual(run('gpu'), ['V3', 'V5'])

    def test_gpu_at_default_vreg_and_clock_passes(self):
        text = GPU_MAIN.replace('vreg_set_voltage(VREG_VOLTAGE_1_20);', '')
        text = text.replace('set_sys_clock_khz(DVI_TIMING.bit_clk_khz, true);', '')
        self.assertEqual(run('gpu', text), [])

    def test_raising_vsel_on_a_default_card_fails(self):
        text = GPU_MAIN.replace('set_sys_clock_khz(DVI_TIMING.bit_clk_khz, true);', '')
        self.assertEqual(run('gpu', text), ['V3'])

    def test_unknown_timing_is_an_error(self):
        text = GPU_MAIN.replace('dvi_timing_640x480p_60hz', 'dvi_timing_800x600p_60hz', 1)
        with self.assertRaisesRegex(ValueError, 'not understood'):
            run('gpu', text)

    def test_netlist_mutations_fail(self):
        net = (ROOT / 'build/hw/gpu/gpu.net').read_text()
        # C14 (the 1 uF on VREG_VOUT) dropped to 100 nF: V0 fails
        c14 = net.index('(ref "C14")')
        mutated = net[:c14] + net[c14:].replace('(value "1u")', '(value "100n")', 1)
        self.assertEqual(run('gpu', GPU_MAIN.replace('VREG_VOLTAGE_1_20', 'VREG_VOLTAGE_1_10')
                             .replace('set_sys_clock_khz(DVI_TIMING.bit_clk_khz, true);', ''),
                             mutated), ['V0'])


if __name__ == '__main__':
    unittest.main()
