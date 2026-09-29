"""Value parsing in the power tools: SPICE scale suffixes and milliohm links."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
sys.path.insert(0, str(ROOT / 'hw/power/models'))
import board_thermal as bt
import fetch


class VswitchPort(unittest.TestCase):
    def test_millivolt_suffix_thresholds_port(self):
        # the OPAx376 / OPAx333 clamps: "VON=10MV" is 10 mV, not a parse error
        text = ".MODEL         _S1 VSWITCH ROFF=1E9 RON=10M VOFF=0.0V VON=10MV\n"
        out = fetch.port(text)
        self.assertIn("VT=0.005", out)
        self.assertIn("SW Ron=10M Roff=1E9", out)

    def test_plain_thresholds_port_as_before(self):
        out = fetch.port(".model S1 VSWITCH(RON=1 ROFF=1MEG VON=2.5 VOFF=0.5)\n")
        self.assertIn("VT=1.5", out)
        out = fetch.port(".MODEL OL_SW VSWITCH(RON=1E-3 ROFF=1E9 VON=900E-3 VOFF=800E-3)\n")
        self.assertIn("VT=0.85", out)


class LinkOhms(unittest.TestCase):
    def test_one_milliohm_link_is_not_one_megohm(self):
        self.assertAlmostEqual(bt.ohms('1m'), 0.001)
        self.assertLessEqual(bt.ohms('1m'), bt.LINK_MAX)

    def test_other_values_read_as_before(self):
        self.assertEqual(bt.ohms('0'), 0.0)
        self.assertEqual(bt.ohms('10k'), 10e3)
        self.assertEqual(bt.ohms('1M'), 1e6)
        self.assertEqual(bt.ohms('7.5k 0.1%'), 7.5e3)


if __name__ == '__main__':
    unittest.main()
