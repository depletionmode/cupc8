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

    def test_gpu_tmds_sink_is_near_iovss_and_switching_is_open(self):
        c = circuit('gpu')
        _, sink, _, _ = rt.static_io(c, codes('gpu'))
        tmds = 4 * rt.TMDS_AVCC_MAX / (270 * 0.95 + rt.TMDS_RT_MIN)
        self.assertGreater(sink, tmds)
        self.assertGreater(tmds, 0.9 * rt.I_IOVSS_MAX)
        self.assertEqual(len(rt.tmds_lines(c)), 8)


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
