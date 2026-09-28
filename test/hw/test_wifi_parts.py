"""The Wi-Fi power gates use cited, netlist-bound part data and a correctly
grounded TI model (POW-003 / WC-005)."""
from pathlib import Path
import io
import re
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/power'))
import buck
import spice
import wifi_parts as wp


def fixture_netlist(directory):
    with tarfile.open(ROOT / 'test/hw/fixtures/wifi-power-route-20260927.tar.xz', 'r:xz') as bundle:
        data = bundle.extractfile('wifi.net').read()
    path = Path(directory) / 'wifi.net'
    path.write_bytes(data)
    return path


class WifiParts(unittest.TestCase):
    def test_fixture_netlist_fits_the_sourced_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(wp.binding_errors(fixture_netlist(tmp)), [])

    def test_changed_lcsc_part_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = fixture_netlist(tmp)
            text = path.read_text()
            # C2 swapped for another 22 uF part: its data no longer applies
            swapped = re.sub(r'(\(ref "C2"\)(?:(?!\(comp).)*?\(name "LCSC"\) ")C45783"',
                             r'\1C602037"', text, count=1, flags=re.S)
            self.assertNotEqual(swapped, text)
            path.write_text(swapped)
            self.assertEqual(wp.binding_errors(path), [('C2', 'C45783', 'C602037')])

    def test_every_part_cites_a_source(self):
        for part in list(wp.CAPACITORS.values()) + [wp.TLV62569, wp.ESP32_C3]:
            self.assertIn(part['source'], wp.SOURCES)
        for title, url in wp.SOURCES.values():
            self.assertTrue(url.startswith('https://'), url)

    def test_missing_manufacturer_guarantees_keep_gates_red(self):
        # Samsung, YAGEO and Espressif publish only typical ESR, DC-bias and
        # current data; F5/F7/F8 (and thermal T4p) must not pass on them.
        self.assertFalse(wp.guaranteed('esr_max'))
        self.assertFalse(wp.guaranteed('min_effective_c'))
        self.assertFalse(wp.load_envelope_bounded())

    def test_vout_range_includes_tolerance_tcr_and_vfb_temperature(self):
        lo, hi = wp.vout_range()
        t = 0.01 + 100e-6 * 75                      # 1 %, 100 ppm/C, 25 -> 100 C
        self.assertAlmostEqual(lo, 0.588 * 0.997 * (1 + 4.53 * (1 - t) / (1 + t)))
        self.assertAlmostEqual(hi, 0.612 * 1.003 * (1 + 4.53 * (1 + t) / (1 - t)))
        plo, phi = wp.vout_range('C861412', 'C122538')
        self.assertGreater(plo, lo)
        self.assertLess(phi, hi)

    def test_stress_capacitance_uses_the_next_tabulated_bias(self):
        c = wp.stress_capacitance('C45783', 3.45)   # -> the 3.6 V point
        self.assertAlmostEqual(c, 22e-6 * 0.8 * (1 - 0.3625) * 0.85 * 0.875)
        self.assertLess(wp.stress_capacitance('C45783', 5.5), c)


class TiModelGround(unittest.TestCase):
    def test_ti_subcircuit_uses_global_node_zero(self):
        text = Path(spice.lib('TLV62569_TRANS.lib')).read_text()
        body = text[text.index('.SUBCKT TLV62569_TRANS'):text.index('.ENDS TLV62569_TRANS')]
        self.assertRegex(body, r'(?m)^V_U3_V70\s+\S+\s+0\s')   # an internal supply to node 0

    def test_wifi_deck_puts_u2_gnd_on_node_zero(self):
        deck = buck.wifi_deck('worst', 0.038, 0.135, 0.123, r_board_return=0.07)
        self.assertRegex(deck, r'(?m)^X1 vin fb sw vin 0 TLV62569_TRANS$')
        self.assertRegex(deck, r'(?m)^R10 fb 0 ')
        self.assertRegex(deck, r'(?m)^Rboardreturn 0 slot_gnd 0\.07$')
        for line in deck.splitlines():
            if re.match(r'(Vs|Cbulk|Iother) ', line):
                self.assertIn(' slot_gnd ', line)
        self.assertNotIn('buck_gnd', deck)

    def test_caps_override_reaches_the_deck(self):
        deck = buck.wifi_deck('worst', 0.038, 0.135, 0.123, caps=(5e-6, 8e-6, 7e-8))
        self.assertRegex(deck, r'(?m)^C1 c1term 0 5e-06$')
        self.assertRegex(deck, r'(?m)^C2 c2term 0 8e-06$')
        self.assertRegex(deck, r'(?m)^C3 c3term return 7e-08$')

    def test_divider_and_load_overrides_reach_the_deck(self):
        deck = buck.wifi_deck('worst', 0.038, 0.135, 0.123, divider=(459e3, 100e3), i_load=0.5083)
        self.assertRegex(deck, r'(?m)^R9 buck fb 459000(\.0)?$')
        self.assertRegex(deck, r'(?m)^R10 fb 0 100000(\.0)?$')
        self.assertRegex(deck, r'(?m)^Iesp out return PWL\(.* 0\.5083 .*\)$')


if __name__ == '__main__':
    unittest.main()
