"""RP2040 package heat bound (GC/IC/SC/EC/YC-006) and its netlist binding."""
from pathlib import Path
from unittest.mock import patch
import dataclasses
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
sys.path.insert(0, str(ROOT / 'hw'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
import rp2040_thermal as rt
sys.path.insert(0, str(ROOT / 'hw/boards'))
import gpu  # noqa: E402  (the declared TMDS resistors)
from cosim.netlist import read

BUILD = ROOT / 'build/hw'


def circuit(board):
    return read(BUILD / board / f'{board}.net')


def codes(board):
    return rt.bom_codes(BUILD / board / 'fab/bom.csv')


class PackageBound(unittest.TestCase):
    def test_terms_are_the_rated_limits(self):
        self.assertAlmostEqual(rt.vreg_path_w(), 3.63 * 0.100)
        self.assertAlmostEqual(rt.ldo_loss_w(), (3.63 - 0.8 * 0.97) * 0.100)
        self.assertAlmostEqual(rt.io_w(), 3.63 * 0.05 + 4.13 * 0.05)
        # the LDO loss is inside the regulator-path term, never added to it
        self.assertLess(rt.ldo_loss_w(), rt.vreg_path_w())
        self.assertLess(rt.tj(rt.package_w()), 85.0)

    def test_regulator_over_its_rating_fails(self):
        # mutation: a 150 mA core load (over Table 192 IMAX) breaks 85 C
        with patch.object(rt, 'I_VREG_MAX', 0.150):
            self.assertGreater(rt.tj(rt.package_w()), 85.0)

    def test_resistor_values(self):
        for text, ohms in (('10k', 1e4), ('4k7', 4700), ('100R', 100), ('270', 270),
                           ('33R', 33), ('1k', 1000), ('750k', 750e3)):
            self.assertAlmostEqual(rt.ohms(text), ohms)


class StaticIo(unittest.TestCase):
    def test_storage_leds_within_iovdd(self):
        source, sink, _, unknown = rt.static_io(circuit('storage'), codes('storage'))
        self.assertLess(source, rt.I_IOVDD_MAX)
        self.assertLess(sink, rt.I_IOVSS_MAX)
        self.assertEqual(unknown, [])

    def test_led_resistor_mutation_fails(self):
        # mutation: the storage LED resistors cut to 33 ohm source too much
        base = circuit('storage')
        resistors = tuple(dataclasses.replace(r, value='33R') if r.ref in ('R5', 'R6') else r
                          for r in base.resistors)
        mutated = dataclasses.replace(base, resistors=resistors)
        source, _, _, _ = rt.static_io(mutated, codes('storage'))
        self.assertGreater(source, rt.I_IOVDD_MAX)

    def test_unknown_led_part_uses_zero_forward_voltage(self):
        c = codes('storage')
        base, _, _, _ = rt.static_io(circuit('storage'), c)
        c = {ref: ('C0' if code == 'C12624' else code) for ref, code in c.items()}
        worse, _, _, _ = rt.static_io(circuit('storage'), c)
        self.assertGreater(worse, base)

    def gpu_with_tmds(self, value):
        """The built GPU netlist with RN1/RN2 set to `value` ohms."""
        base = circuit('gpu')
        resistors = tuple(dataclasses.replace(r, value=value) if r.ref.startswith('RN') else r
                          for r in base.resistors)
        return dataclasses.replace(base, resistors=resistors)

    def test_gpu_tmds_sink_within_iovss_with_margin(self):
        # the declared TMDS resistors (hw/boards/gpu.py) keep the steady sink
        # current at least 10 % under IIOVSS_MAX; switching (R4) stays open
        c = self.gpu_with_tmds(gpu.TMDS_R)
        _, sink, _, _ = rt.static_io(c, codes('gpu'))
        tmds = 4 * rt.TMDS_AVCC_MAX / (rt.ohms(gpu.TMDS_R) * 0.95 + rt.TMDS_RT_MIN)
        self.assertGreater(sink, tmds)
        self.assertLess(sink, 0.9 * rt.I_IOVSS_MAX)
        self.assertEqual(len(rt.tmds_lines(c)), 8)

    def test_picodvi_270_ohm_exceeds_iovss(self):
        # mutation: PicoDVI's own 270 ohm sinks 46.0 mA on the TMDS lines alone
        _, sink, _, _ = rt.static_io(self.gpu_with_tmds('270'), codes('gpu'))
        self.assertGreater(sink, rt.I_IOVSS_MAX)

    def test_gpu_build_has_the_declared_tmds_resistors(self):
        self.assertEqual(rt.tmds_resistors(circuit('gpu')), [rt.ohms(gpu.TMDS_R)])


class TmdsSwing(unittest.TestCase):
    RAIL = (rt.d.V3V3_MIN, rt.d.buck_vout_range()[1])

    def test_declared_resistors_within_dvi_swing(self):
        lo, hi = rt.tmds_swing(rt.ohms(gpu.TMDS_R), *self.RAIL)
        self.assertGreaterEqual(lo, rt.DVI_SWING_MIN)
        self.assertLessEqual(2 * hi, rt.DVI_SWING_MAX)

    def test_swing_mutations_fail(self):
        # 1 kohm starves the sink under 150 mV; 150 ohm drives it past 1200 mV
        self.assertLess(rt.tmds_swing(1000, *self.RAIL)[0], rt.DVI_SWING_MIN)
        self.assertGreater(2 * rt.tmds_swing(150, *self.RAIL)[1], rt.DVI_SWING_MAX)

    def test_swing_hand_value(self):
        # weakest corner: AVcc 3.465 V, RT 45 ohm, 378 ohm, 200 ohm pad; the
        # high pin at IOVDD 3.135 V still sinks (3.465 - 3.135) / 423 ohm
        lo, _ = rt.tmds_swing(360, 3.135, 3.135)
        self.assertAlmostEqual(lo, 45 * (3.465 / (200 + 378 + 45) - 0.33 / (378 + 45)), places=6)


class Binding(unittest.TestCase):
    def test_changed_regulator_output_net_fails(self):
        import thermal_bind
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch)
            for name in ('storage.net', 'storage.kicad_pcb'):
                shutil.copy(BUILD / 'storage' / name, out / name)
            thermal_bind.bind('storage', out)
            net = out / 'storage.net'
            text = net.read_text()
            # mutation: rename the 1V1 net, as if VREG_VOUT fed another rail
            self.assertIn('"/1V1"', text)
            net.write_text(text.replace('"/1V1"', '"/1V1_ALT"'))
            with self.assertRaises(ValueError):
                thermal_bind.bind('storage', out)


if __name__ == '__main__':
    unittest.main()
