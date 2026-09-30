#!/usr/bin/env python3
"""Regressions and must-fail mutations for hw/si/slowbus_si.py (row 4.6).

    python3 test/hw/test_slowbus_si.py [--board-dir build/hw]

* the lumped RLGC ladder reproduces an ideal ngspice T line, and the field
  solver the exact stripline and the Hammerstad-Jensen microstrip;
* every converted IBIS driver replays its vendor fixture;
* the waveform checks flag a non-monotonic edge, ring-back, and an
  overshoot beyond the AC allowance, and pass a clean edge;
* the routed six-slot SCK extraction matches SI-005's planar lengths, and an
  opened J16 launch is an open, not a silently shorter bus;
* the /CPU_A0 overshoot with the superseded 33 ohm arrays is real: the routed peak matches one ideal
  line driven by the same IBIS model, and only the series value moves it;
* the same net with its arrays at 68 ohm passes at the min corner, fails
  once the series resistor is removed (netlist mutation) and once a stub
  is doubled from 30 mm to 60 mm (board mutation);
* a changed board byte breaks the evidence binding.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
sys.path.insert(0, str(ROOT / 'test/hw'))
import slowbus_models as models  # noqa: E402
import slowbus_route as route  # noqa: E402
import slowbus_si as si  # noqa: E402

BOARD_DIR = ROOT / 'build/hw'


def mirror(board_dir, target, kinds):
    """A board directory whose builds link to the originals (files copied
    later are the mutated ones)."""
    for kind in kinds:
        (target / kind).mkdir(parents=True)
        for item in (board_dir / kind).iterdir():
            (target / kind / item.name).symlink_to(item)


def replace_file(path, text):
    path.unlink()
    path.write_text(text)


class TiInputCurrent(unittest.TestCase):
    def qualify(self, voltage, current, part=si.TI_LVC125):
        v = np.array(voltage)
        t = np.arange(len(v)) * 1e-9
        metrics, failures = si.evaluate(t, v, part, (), t[-1], 3.3)
        return si.qualify_ti_input_current(metrics, failures, part, v,
                                          None if current is None else np.array(current))

    def test_negative_input_with_bounded_full_pin_current(self):
        metrics, failures = self.qualify([0, -.94, 0], [0, -.0144, .01])
        self.assertEqual(failures, [])
        self.assertEqual(metrics['input_pin_current_peak_a'], .0144)

    def test_overcurrent_remains_failure(self):
        _, failures = self.qualify([0, -.94, 0], [0, -.0501, 0])
        self.assertTrue(any('exceeds 50 mA' in f for f in failures))
        self.assertTrue(any('undershoot' in f for f in failures))

    def test_missing_incomplete_nonfinite_current_fails(self):
        for current in (None, [0], [0, float('nan'), 0]):
            _, failures = self.qualify([0, -.94, 0], current)
            self.assertTrue(any('complete pin-current' in f for f in failures))

    def test_positive_voltage_and_other_manufacturers_unchanged(self):
        _, failures = self.qualify([0, -.94, 6.6], [0, -.01, .01])
        self.assertTrue(any('overshoot' in f for f in failures))
        _, failures = self.qualify([0, -.94, 0], [0, -.01, .01], si.AHC125)
        self.assertTrue(any('undershoot' in f for f in failures))


class TiInputTransition(unittest.TestCase):
    def qualify(self, points, edge='rise'):
        t = np.arange(0, 41) * 1e-9
        x, y = zip(*points)
        v = np.interp(t, np.array(x) * 1e-9, y)
        return si.qualify_ti_input_transition({}, [], si.TI_LVC125, t, v,
                                             ((0, edge),), 41e-9)

    def test_fast_both_edges_pass(self):
        self.assertEqual(self.qualify(((0, 0), (4, 3.3), (40, 3.3)))[1], [])
        self.assertEqual(self.qualify(((0, 3.3), (4, 0), (40, 0)), 'fall')[1], [])

    def test_brief_slow_point_is_diagnostic_not_invented_rating(self):
        metrics, failures = self.qualify(((0, 0), (2, 1), (4, 1.05), (6, 3.3), (40, 3.3)))
        self.assertEqual(failures, [])
        self.assertLess(metrics['input_transition']['edges'][0]['diagnostic_minimum_v_per_ns_in_band'], .1)

    def test_long_plateau_consumes_whole_band_budget(self):
        _, failures = self.qualify(((0, 0), (2, 1), (20, 1.05), (22, 3.3), (40, 3.3)))
        self.assertTrue(any('whole-band transit' in f for f in failures))

    def test_current_rating_exception_does_not_remove_slew_failure(self):
        metrics, failures = self.qualify(((0, -.9), (2, 1), (20, 1.05), (22, 3.3), (40, 3.3)))
        _, failures = si.qualify_ti_input_current(metrics, failures, si.TI_LVC125,
                                                np.array([-.9, 1, 3.3]), np.array([-.01, 0, 0]))
        self.assertTrue(any('whole-band transit' in f for f in failures))


class Waveform(unittest.TestCase):
    def check(self, v, edges=((1e-9, 'rise'),), part='RP2040'):
        t = np.linspace(0, 40e-9, len(v))
        return si.evaluate(t, np.array(v, float), part, edges, 40e-9, 3.3)[1]

    def ramp(self, *points, n=401):
        t = np.linspace(0, 40e-9, n)
        xs, ys = zip(*points)
        return np.interp(t, np.array(xs) * 1e-9, ys)

    def test_clean_edge_passes(self):
        self.assertEqual(self.check(self.ramp((0, 0), (1, 0), (3, 3.3), (40, 3.3))), [])

    def test_non_monotonic_band(self):
        fails = self.check(self.ramp((0, 0), (1, 0), (2, 1.5), (2.5, 1.0), (4, 3.3), (40, 3.3)))
        self.assertTrue(any('non-monotonic' in f for f in fails), fails)

    def test_ringback(self):
        fails = self.check(self.ramp((0, 0), (1, 0), (2, 3.3), (3, 1.8), (4, 3.3), (40, 3.3)))
        self.assertTrue(any('rings back' in f for f in fails), fails)

    def test_overshoot_and_ac_allowance(self):
        over = self.ramp((0, 0), (1, 0), (2, 3.9), (3, 3.3), (40, 3.3))
        self.assertTrue(any('overshoot' in f for f in self.check(over)))
        # iCE40: 3.63 V for < 1.6 ns is inside the maker's AC allowance ...
        brief = self.ramp((0, 0), (1, 0), (2, 3.63), (2.5, 3.3), (40, 3.3))
        self.assertEqual(self.check(brief, part='ICE40HX4K-TQ144'), [])
        # ... but not for 3 ns
        long = self.ramp((0, 0), (1, 0), (2, 3.63), (5, 3.63), (6, 3.3), (40, 3.3))
        self.assertTrue(any('AC allowance' in f for f in self.check(long, part='ICE40HX4K-TQ144')))


class SampledMiso(unittest.TestCase):
    def check(self, points):
        t = np.linspace(0, 40e-9, 4001)
        x, y = zip(*points)
        v = np.interp(t, np.array(x) * 1e-9, y)
        return si.evaluate_sampled(t, v, 'ICE40HX4K-TQ144', ((1e-9, 'rise'),),
                                   40e-9, 3.3, {'rise': 12.0})

    def test_early_data_ring_is_safe_before_sample(self):
        metrics, fails = self.check(((0, 0), (1, 0), (2, 1.5), (3, 1.0),
                                     (4, 3.3), (6, 1.8), (8, 3.3), (40, 3.3)))
        self.assertEqual(fails, [])
        self.assertTrue(metrics['sampling']['ok'])
        self.assertTrue(metrics['sampling']['uniform_edge_failures'])

    def test_late_data_ring_fails_sample_window(self):
        metrics, fails = self.check(((0, 0), (1, 0), (3, 3.3), (24, 3.3),
                                     (25, 1.8), (30, 3.3), (40, 3.3)))
        self.assertTrue(any('after setup deadline' in f for f in fails), fails)
        self.assertFalse(metrics['sampling']['ok'])

    def test_early_overvoltage_remains_hard_failure(self):
        _, fails = self.check(((0, 0), (1, 0), (2, 4.0), (3, 3.3), (40, 3.3)))
        self.assertTrue(any('overshoot' in f for f in fails), fails)

    def test_never_valid_level_fails(self):
        _, fails = self.check(((0, 0), (1, 0), (4, 1.9), (40, 1.9)))
        self.assertTrue(any('missing valid threshold crossing' in f for f in fails), fails)

    def test_missing_edges_cannot_pass(self):
        fails, _ = si.sampled_data_failures({'edges': []}, [], {'rise': 12.0})
        self.assertIn('sampled data: missing edge coverage', fails)

    def test_numpy_timing_scalar_serializes_without_coercion(self):
        import json
        _, sampling = si.sampled_data_failures(
            {'edges': [{'edge': 'rise', 'settled_ns': 2.0}]}, [],
            {'rise': np.float64(12)})
        self.assertIs(type(sampling['sample_windows'][0]['ok']), bool)
        self.assertEqual(json.loads(json.dumps(sampling)), sampling)


class SampledMosi(unittest.TestCase):
    def rows(self, settled=20, stress=False):
        def metrics(part, pin):
            return {'part': part, 'edges': [{'edge': 'rise', 'settled_ns': settled},
                                           {'edge': 'fall', 'settled_ns': settled}]}
        labels = ('J11:gpu:U1.5', 'J13:wifi:U1.5')
        failures = [label + ': rise non-monotonic in threshold band (15 mV)' for label in labels]
        if stress:
            failures.append(labels[0] + ': overshoot 4.2 V beyond abs max 3.8 V')
        return [{'group': 'MB spi SCK', 'receivers': {'J11:gpu:U1.4': {
                    'edges': [{'edge': 'rise', 'first_band_ns': 5, 'settled_ns': 12}]}}},
                {'group': 'MB spi MOSI', 'failures': failures,
                 'receivers': {labels[0]: metrics('RP2040', 5),
                               labels[1]: metrics('ESP32-C3-MINI-1', 5)}}]

    def test_early_ripple_separated_only_for_sampled_rp_data(self):
        rows = self.rows();si.qualify_sampled_mosi(rows)
        self.assertFalse(any('gpu' in f for f in rows[1]['failures']))
        self.assertTrue(any('wifi' in f for f in rows[1]['failures']))
        self.assertTrue(rows[1]['receivers']['J11:gpu:U1.5']['sampling']['ok'])
        self.assertTrue(rows[1]['uniform_edge_failures'])

    def test_late_recross_or_stress_still_fails(self):
        for rows in (self.rows(settled=180), self.rows(stress=True)):
            si.qualify_sampled_mosi(rows)
            self.assertTrue(any('gpu' in f for f in rows[1]['failures']))
            self.assertFalse(rows[1]['receivers']['J11:gpu:U1.5']['sampling']['ok'])

    def test_missing_clock_retains_original_failure(self):
        rows = self.rows()[1:];before = list(rows[0]['failures'])
        si.qualify_sampled_mosi(rows)
        self.assertEqual(rows[0]['failures'], before)
        self.assertNotIn('mosi_sampling_basis', rows[0])


class SchmittDiagnostic(unittest.TestCase):
    def check(self, points):
        t = np.linspace(0, 40e-9, 4001)
        x, y = zip(*points)
        v = np.interp(t, np.array(x) * 1e-9, y)
        return si.hysteresis_edge_diagnostics(t, v, ((1e-9, 'rise'),), 40e-9, .8, 2, .2)

    def test_small_reversal_and_band_reentry_below_hysteresis(self):
        r = self.check(((0, 0), (1, 0), (3, 1.5), (4, 1.45),
                        (5, 2.1), (6, 1.95), (8, 3.3), (40, 3.3)))
        self.assertTrue(r['ok'], r)
        self.assertAlmostEqual(r['edges'][0]['whole_band_adverse_mv'], 50, places=4)

    def test_multiple_small_downsteps_must_be_measured_together(self):
        r = self.check(((0, 0), (1, 0), (3, 1.6), (4, 1.51),
                        (5, 1.42), (6, 1.33), (8, 3.3), (40, 3.3)))
        self.assertFalse(r['ok'], r)
        self.assertAlmostEqual(r['edges'][0]['whole_band_adverse_mv'], 270, places=4)

    def test_late_full_valid_band_recross_fails(self):
        r = self.check(((0, 0), (1, 0), (3, 3.3), (22, 3.3),
                        (24, .7), (30, 3.3), (40, 3.3)))
        self.assertFalse(r['ok'], r)
        self.assertTrue(r['edges'][0]['full_valid_band_recross'])

    def test_missing_final_level_or_edges_cannot_pass(self):
        self.assertFalse(self.check(((0, 0), (1, 0), (4, 1.9), (40, 1.9)))['ok'])
        self.assertFalse(si.hysteresis_edge_diagnostics(np.array([0]), np.array([0]),
                                                       (), 1, .8, 2, .2)['ok'])

    def test_falling_edge_opposite_excursion_fails(self):
        t = np.linspace(0, 40e-9, 4001)
        v = np.interp(t, np.array([0, 1, 3, 4, 6, 40]) * 1e-9,
                      [3.3, 3.3, 1.3, 1.6, 0, 0])
        r = si.hysteresis_edge_diagnostics(t, v, ((1e-9, 'fall'),), 40e-9, .8, 2, .2)
        self.assertFalse(r['ok'], r)
        self.assertAlmostEqual(r['edges'][0]['whole_band_adverse_mv'], 300, places=4)

    def test_hysteresis_diagnostic_does_not_replace_voltage_stress(self):
        t = np.linspace(0, 40e-9, 4001)
        v = np.interp(t, np.array([0, 1, 3, 6, 40]) * 1e-9, [0, 0, 4.2, 3.3, 3.3])
        self.assertTrue(si.hysteresis_edge_diagnostics(t, v, ((1e-9, 'rise'),),
                                                     40e-9, .8, 2, .2)['ok'])
        _, failures = si.evaluate(t, v, 'RP2040', ((1e-9, 'rise'),), 40e-9, 3.3)
        self.assertTrue(any('overshoot' in f for f in failures), failures)


class GenuineAhc(unittest.TestCase):
    def test_input_voltage_limits_are_distinct_from_output_limits(self):
        t = np.linspace(0, 40e-9, 401)
        v = np.interp(t, np.array([0, 1, 3, 40]) * 1e-9, [0, 0, 4.2, 4.2])
        _, input_fails = si.evaluate(t, v, si.AHC125, ((1e-9, 'rise'),), 40e-9, 3.3)
        _, output_fails = si.evaluate(t, v, si.AHC125_OUTPUT, ((1e-9, 'rise'),), 40e-9, 3.3)
        self.assertFalse(any('overshoot' in f for f in input_fails), input_fails)
        self.assertTrue(any('overshoot' in f for f in output_fails), output_fails)
        _, negative = si.evaluate(t, np.full_like(t, -.6), si.AHC125, (), 40e-9, 3.3)
        self.assertTrue(any('undershoot' in f for f in negative), negative)

    def test_esp_published_input_range_remains_enforced(self):
        t = np.linspace(0, 40e-9, 401)
        _, fails = si.evaluate(t, np.full_like(t, 3.61), 'ESP32-C3-MINI-1', (), 40e-9, 3.3)
        self.assertTrue(any('published DC input range' in f for f in fails), fails)
        self.assertFalse(any('abs max' in f for f in fails), fails)

    def test_card_input_reads_voltage_relative_to_local_ground(self):
        asm = si.Assembler(None, si.Config(si.EMPTY, extra=(('card_ground_offset', .04),)), 3.3)
        asm.device('J11:gpu', 'gpu', 'U1', '4', 'RP2040', 'pad')
        asm.deck.lines.append('Vdrive pad 0 3.3')
        with tempfile.TemporaryDirectory() as work:
            _, waves = si.run_deck(asm.deck, 3.3, 10e-9, 10e-12, work)
        self.assertAlmostEqual(float(waves[-1, 0]), 3.26, places=5)

    def test_distinct_buffer_receiver_and_cap_ground_references(self):
        cfg = si.Config(si.EMPTY, extra=(('card_ground_offset', .04),
            ('ground_delta_wifi_U4', .04), ('ground_delta_wifi_U1', -.01),
            ('ground_delta_wifi_C61', .02)))
        asm = si.Assembler(None, cfg, 3.3)
        local = asm.buffer_package('pad', 'wifi', 'U4')
        asm.deck.probes.append(si.Probe('buffer-local', local, 'diagnostic', 'tx'))
        asm.device('wifi', 'wifi', 'U1', '16', 'ESP32-C3-MINI-1', 'pad')
        asm.signal_capacitor('wifi', 'C61', '10p', 'pad', '/GND')
        asm.deck.lines.append('Vdrive pad 0 3.3')
        with tempfile.TemporaryDirectory() as work:
            _, waves = si.run_deck(asm.deck, 3.3, 10e-9, 10e-12, work)
        self.assertAlmostEqual(float(waves[-1, 0]), 3.22, places=5)
        self.assertAlmostEqual(float(waves[-1, 1]), 3.27, places=5)
        self.assertIn('Vcard_ground_wifi_C61 card_ground_wifi_C61 0 0.06', asm.deck.lines)
        self.assertAlmostEqual(asm.local_ground_offset('main', 'U7'), 0.)
        for invalid in (float('nan'), float('inf')):
            asm = si.Assembler(None, si.Config(si.EMPTY, extra=(
                ('ground_delta_wifi_U4', invalid),)), 3.3)
            with self.assertRaises(ValueError):
                asm.buffer_package('pad', 'wifi', 'U4')

    def test_physical_passive_tolerance_and_ground_reference(self):
        cfg = si.Config(si.EMPTY, extra=(('miso_series_scale', 1.03),
                                        ('miso_shunt_scale', .97),
                                        ('miso_pullup_scale', 1.03),
                                        ('card_ground_offset', .04)))
        asm = si.Assembler(None, cfg, 3.6)
        self.assertAlmostEqual(asm.resistance('gpu', 'R60', '270'), 278.1)
        self.assertAlmostEqual(asm.resistance('wifi', 'R61', '10k'), 9700)
        self.assertAlmostEqual(asm.resistance('main', 'R107', '47k'), 48410)
        self.assertEqual(asm.resistance('gpu', 'R10', '270'), 270)
        local = asm.buffer_package('pad')
        self.assertIn('Vcard_ground card_ground 0 0.04', asm.deck.lines)
        self.assertTrue(any('pad card_ground' in line and line.startswith('C')
                            for line in asm.deck.lines))
        self.assertTrue(any(f' {local} 0.04' in line and 'ground_gauge' in line
                            for line in asm.deck.lines))

    def test_native_cap_branch_resistor_independent_tolerance(self):
        cfg = si.Config(si.EMPTY, extra=(('resistor_scale_wifi_R69', .96),
                                        ('resistor_scale_wifi_R70', 1.04),
                                        ('signal_cap_esr', 30.)))
        asm = si.Assembler(None, cfg, 3.6)
        self.assertAlmostEqual(asm.resistance('wifi', 'R69', '10'), 9.6)
        self.assertAlmostEqual(asm.resistance('wifi', 'R70', '10'), 10.4)
        self.assertEqual(asm.resistance('wifi', 'R63', '220'), 220)
        for invalid in (0., -1., float('nan'), float('inf')):
            asm = si.Assembler(None, si.Config(si.EMPTY, extra=(
                ('resistor_scale_wifi_R69', invalid),)), 3.6)
            with self.assertRaises(ValueError):
                asm.resistance('wifi', 'R69', '10')

    def test_cap_branch_resistor_body_is_separate_from_cap_esl(self):
        asm = si.Assembler(None, si.Config(si.EMPTY, extra=(
            ('resistor_esl_wifi_R69', 2e-9), ('signal_cap_esl', 1e-9))), 3.3)
        asm.resistor_body('wifi', 'R69', 'bus', 'cap_pad', 10.)
        self.assertEqual(len(asm.deck.lines), 2)
        self.assertTrue(asm.deck.lines[0].endswith(' 10'))
        self.assertTrue(asm.deck.lines[1].endswith(' cap_pad 2e-09'))
        for invalid in (-1., float('nan'), float('inf')):
            asm = si.Assembler(None, si.Config(si.EMPTY, extra=(
                ('resistor_esl_wifi_R69', invalid),)), 3.3)
            with self.assertRaises(ValueError):
                asm.resistor_body('wifi', 'R69', 'bus', 'cap_pad', 10.)

    def test_actual_buffer_discovery_and_independent_package_coverage(self):
        bench = si.Bench(BOARD_DIR)
        card = bench.circuit('gpu')
        ref, pin = si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW')
        card.components[ref] = (si.AHC125, card.components[ref][1])
        card.pins[ref, pin] = '/MISO_SRC'
        cases = [c for c in si.mb_spi_cases(bench, kinds=('gpu',)) if c.group == 'MB spi MISO']
        self.assertEqual(len(cases), 768)
        self.assertEqual({(c.config.package, c.config.get('buffer_package')) for c in cases},
                         {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.assertTrue(all(c.drives[0].start[-2:] == (ref, pin) for c in cases))

    def test_miso_driver_and_two_shunt_references_are_independent(self):
        cfg = si.Config(si.EMPTY, extra=(('card_ground_offset', .15),
                                        ('miso_shunt_ground_delta', -.035),
                                        ('main_miso_shunt_ground_offset', .015)))
        asm = si.Assembler(None, cfg, 3.6)
        driver = asm.card_ground()
        card_shunt = asm.card_ground(shunt=True)
        main_shunt = asm.main_miso_shunt_ground()
        asm.deck.probes.extend(si.Probe(n, n, si.TI_LVC125) for n in
                               (driver, card_shunt, main_shunt))
        with tempfile.TemporaryDirectory() as work:
            _, waves = si.run_deck(asm.deck, 3.6, 5e-9, 10e-12, work)
        self.assertAlmostEqual(float(waves[-1, 0]), .15)
        self.assertAlmostEqual(float(waves[-1, 1]), .115)
        self.assertAlmostEqual(float(waves[-1, 2]), .015)

    def test_unspecified_shunt_references_preserve_common_ground(self):
        asm = si.Assembler(None, si.Config(si.EMPTY), 3.3)
        self.assertEqual(asm.card_ground(), asm.card_ground(shunt=True))
        self.assertEqual(asm.main_miso_shunt_ground(), '0')

    def test_all_vendor_corner_fixtures_replay(self):
        ahc = models.load_ahc125(si.OUT_DIR / 'cache/sclm008.ibs')
        self.assertEqual(ahc['out'].vcc, {'typ': 3.3, 'min': 3.0, 'max': 3.6})
        self.assertEqual(ahc['out'].params['temperature_range'],
                         {'typ': 40, 'min': 100, 'max': -40})
        for corner in models.CORNERS:
            for edge in ('rise', 'fall'):
                self.assertTrue(models.fixture_check(ahc['out'], corner, edge)['ok'], (corner, edge))

    def test_fitted_network_rejects_candidate_series_insertion(self):
        class Dummy:
            cfg = si.Config(si.EMPTY, extra=(('tx_series', 270.0),))
        with self.assertRaisesRegex(ValueError, 'double count'):
            si.ibis_driver([], 1e-9)(Dummy(), 'node', 'gpu', 'U4', '4', si.AHC125)


class SlotSpiQualification(unittest.TestCase):
    """M1's required rate and unsupported hardware maximum stay distinct."""

    def test_miso_response_source_is_not_other_card_name(self):
        self.assertEqual(si.miso_controller_kind({'case':
            'MISO J11 gpu all gpu actualbranch mixed mapwifi'}), 'gpu')
        self.assertEqual(si.miso_controller_kind({'case':
            'M1mix MISO J14 storage with wifi'}), 'storage')
        self.assertEqual(si.miso_controller_kind({'driver_kind': 'wifi',
                                                 'case': 'GPU with storage'}), 'wifi')
        self.assertIsNone(si.miso_controller_kind({'case': 'unidentified native buffer'}))

    def test_unreviewed_bracket_supply_is_rejected_before_assembly(self):
        for voltage in (2.9, 3.7):
            config = si.Config(si.EMPTY, extra=(('bracket_vdd', voltage),))
            case = si.Case('local input', 'unreviewed rail',
                           (si.Drive(('gpu', 'gpu', 'U1', '6'), 'RP2040', ()),),
                           config, 10e-9)
            with self.assertRaisesRegex(ValueError, 'bracket source rail'):
                si.simulate(case, BOARD_DIR)

    def results(self, miso_settled_ns=20):
        def receiver(group, label, rise, fall):
            return {'group': group, 'receivers': {label: {'edges': [
                {'edge': 'rise', 'first_band_ns': 1, 'settled_ns': rise},
                {'edge': 'fall', 'first_band_ns': 1, 'settled_ns': fall}]}}}
        return [receiver('MB spi SCK', 'J16:storage:U1.4', 2, 30),
                receiver('MB spi MOSI', 'J16:storage:U1.5', 4, 4),
                receiver('MB spi MISO input', 'storage:U4.2', 5, 5),
                receiver('MB spi MISO', 'main:U7.48', miso_settled_ns, miso_settled_ns)]

    def test_qualified_rate_pass_does_not_qualify_hardware_maximum(self):
        report = si.timing_checks('CC-007', self.results())
        checks = [c for c in report['checks'] if 'slot MISO turnaround' in c['check']]
        required, diagnostic = checks
        self.assertTrue(required['required'])
        self.assertTrue(required['ok'])
        self.assertIn('3 MHz', required['check'])
        self.assertFalse(diagnostic['required'])
        self.assertFalse(diagnostic['ok'])
        self.assertIn('6 MHz', diagnostic['check'])
        self.assertIn('unsupported', diagnostic['check'])
        self.assertTrue(report['ok'])
        self.assertFalse(report['slot_spi_qualification']['hardware_max_analog_qualified'])

    def test_missing_qualified_sample_budget_fails(self):
        report = si.timing_checks('CC-007', self.results(miso_settled_ns=100))
        self.assertFalse(report['ok'])
        self.assertIn('3 MHz', report['summary'])

    def test_missing_local_buffer_input_route_cannot_qualify(self):
        rows = [r for r in self.results() if r['group'] != 'MB spi MISO input']
        report = si.timing_checks('CC-007', rows)
        self.assertFalse(report['ok'])
        self.assertIn('pad-to-buffer input route', report['summary'])

    def test_local_buffer_input_route_consumes_sample_budget(self):
        rows = self.results(miso_settled_ns=60)
        short = si.timing_checks('CC-007', rows)
        for metrics in rows[2]['receivers'].values():
            for edge in metrics['edges']:
                edge['settled_ns'] = 100
        long = si.timing_checks('CC-007', rows)
        self.assertTrue(short['ok'])
        self.assertFalse(long['ok'])

    def test_waveform_period_uses_qualified_rate(self):
        self.assertEqual(si.SPI_HZ, si.QUALIFIED_SPI_HZ)
        self.assertEqual(si.QUALIFIED_SPI_HZ, 3e6)
        self.assertEqual(si.SPI_HARDWARE_MAX_HZ, 6e6)
        edges, _ = si.clock_edges(si.SPI_HZ)
        self.assertAlmostEqual((edges[1][0] - edges[0][0]) * 1e9, 166.6666667)


class RpSchmittClock(unittest.TestCase):
    SCOPE = dict(schmitt_enabled=True, voltage_select=0, nominal_iovdd=3.3,
                 case_temperature_min=-40., case_temperature_max=85.)

    def qualify(self, points, scope=None, **kwargs):
        t = np.linspace(0, 30e-9, 3001)
        v = np.interp(t * 1e9, [x for x, _ in points], [y for _, y in points])
        metrics, fails = si.evaluate(t, v, 'RP2040', ((0., 'rise'),), 30e-9, 3.3)
        args = dict(scope=self.SCOPE if scope is None else scope, reference='U1',
                    pin='4', gpio=2, iovdd=3.3)
        args.update(kwargs)
        return si.qualify_rp_schmitt_clock(metrics, fails, t, v, ((0., 'rise'),),
                                           30e-9, **args)

    def test_small_early_reverse_is_safe_with_verified_state(self):
        m, fails = self.qualify([(0, 0), (3, 1.7), (4, 1.6), (8, 3.3), (30, 3.3)])
        self.assertTrue(m['uniform_edge_failures'])
        self.assertTrue(m['schmitt_qualification']['ok'])
        self.assertFalse(fails)

    def test_accumulated_reverse_and_late_full_recross_fail(self):
        for points in ([(0, 0), (3, 1.7), (4, 1.65), (5, 1.6), (6, 1.55),
                        (7, 1.5), (8, 1.45), (12, 3.3), (30, 3.3)],
                       [(0, 0), (3, 3.3), (20, 3.3), (21, .7), (22, 3.3), (30, 3.3)],
                       [(0, 0), (3, 1.7), (4, 1.5), (8, 3.3), (30, 3.3)]):
            _, fails = self.qualify(points)
            self.assertTrue(any('whole-period' in f for f in fails))

    def test_state_pin_rail_temperature_scope_must_be_valid(self):
        wave = [(0, 0), (8, 3.3), (30, 3.3)]
        variants = [dict(scope={}), dict(scope=dict(self.SCOPE, schmitt_enabled=False)),
                    dict(scope=dict(self.SCOPE, voltage_select=1)),
                    dict(scope=dict(self.SCOPE, case_temperature_max=86)),
                    dict(scope=dict(self.SCOPE, nominal_iovdd=1.8)),
                    dict(reference='U2'), dict(pin='5', gpio=3), dict(pin='4', gpio=5),
                    dict(iovdd=2.49), dict(iovdd=3.64)]
        for args in variants:
            with self.subTest(args=args):
                _, fails = self.qualify(wave, **args)
                self.assertTrue(any('scope absent or invalid' in f for f in fails))

    def test_firmware_state_binding_rejects_disabled_or_missing_assertion(self):
        from unittest.mock import patch
        source = (si.ROOT / 'fw/rp2040/common/slotspi.c').read_text()
        self.assertIsNotNone(si.rp_schmitt_firmware_scope())
        for broken in (source.replace('PIN_SLOT_SCK, true', 'PIN_SLOT_SCK, false'),
                       source.replace('hard_assert(pads_bank0_hw->voltage_select == 0);', ''),
                       source + '\nvoid disable_spi(void) { gpio_set_input_hysteresis_enabled(2, false); }\n'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root / 'fw/rp2040/common/slotspi.c'
                path.parent.mkdir(parents=True); path.write_text(broken)
                with patch.object(si, 'ROOT', root):
                    self.assertIsNone(si.rp_schmitt_firmware_scope())

    def test_early_overvoltage_is_never_excused(self):
        _, fails = self.qualify([(0, 0), (3, 5), (4, 3.3), (30, 3.3)])
        self.assertTrue(any('overshoot' in f for f in fails))


class EspLocalThresholds(unittest.TestCase):
    def test_high_level_obeys_receiver_rail_not_nominal(self):
        t = np.array([0., 1e-9])
        wave = np.array([2.5, 2.5])
        self.assertEqual([], si.quiet(t, wave, 'ESP32-C3-MINI-1', 1, 3.0)[1])
        failures = si.quiet(t, wave, 'ESP32-C3-MINI-1', 1, 3.6)[1]
        self.assertTrue(any('VIH 2.700' in f for f in failures), failures)

    def test_low_level_and_fixed_ttl_are_distinct(self):
        t = np.array([0., 1e-9])
        wave = np.array([.85, .85])
        self.assertEqual([], si.quiet(t, wave, 'ESP32-C3-MINI-1', 0, 3.6)[1])
        self.assertTrue(si.quiet(t, wave, 'ESP32-C3-MINI-1', 0, 3.0)[1])
        self.assertEqual((2., .8), si.PARTS[si.TI_LVC125].thresholds(3.6))

    def test_edge_must_reach_actual_high_and_stress_remains(self):
        t = np.linspace(0., 10e-9, 101)
        wave = np.minimum(t / 4e-9, 1.) * 2.5
        _, failures = si.evaluate(t, wave, 'ESP32-C3-MINI-1',
                                  [(0., 'rise')], 10e-9, 3.6)
        self.assertTrue(any('never crosses VIH' in f for f in failures), failures)
        _, failures = si.evaluate(t, np.full(t.shape, 3.91),
                                  'ESP32-C3-MINI-1', (), 10e-9, 3.6)
        self.assertTrue(any('overshoot' in f for f in failures), failures)
        with self.assertRaises(ValueError):
            si.PARTS['ESP32-C3-MINI-1'].thresholds(float('nan'))


class LocalIbisReference(unittest.TestCase):
    def test_active_local_driver_uses_its_genuine_corner(self):
        asm = si.Assembler(None, si.Config(si.EMPTY, corner='min',
                           extra=(('buffer_corner_wifi_U5', 'max'),)), 3.135)
        asm.lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
        si.ibis_driver([], 8e-9, 1.)(asm, 'pad', 'wifi', 'U5', '4', si.TI_LVC125)
        asm.deck.lines += ['Rload pad 0 100k', 'Cload pad 0 10p']
        with tempfile.TemporaryDirectory() as work:
            _, waves = si.run_deck(asm.deck, 3.135, 8e-9, 10e-12, work)
        self.assertEqual(asm.deck.probes[-1].vdd, 3.6)
        self.assertGreater(float(waves[-1, -1]), 3.55)
        self.assertTrue(asm.deck.notes[-1].endswith('max'))

    def test_active_local_driver_rejects_unsupported_corner(self):
        asm = si.Assembler(None, si.Config(si.EMPTY,
                           extra=(('buffer_corner_wifi_U5', 'unsupported'),)), 3.3)
        asm.lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
        with self.assertRaises(ValueError):
            si.ibis_driver([], 8e-9, 1.)(asm, 'pad', 'wifi', 'U5', '4', si.TI_LVC125)

    def input_dc(self, offset, physical, main_vdd):
        cfg = si.Config(si.EMPTY, corner='min', extra=(('card_ground_offset', offset),
                           ('buffer_corner_wifi', 'max')))
        asm = si.Assembler(None, cfg, main_vdd)
        asm.lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
        asm.device('J11:wifi', 'wifi', 'U5', '2', si.TI_LVC125, 'pad')
        asm.deck.lines.append(f'Vphysical pad 0 {physical:g}')
        with tempfile.TemporaryDirectory() as work:
            _, waves = si.run_deck(asm.deck, main_vdd, 4e-9, 20e-12, work)
        return asm, waves[-1]

    def test_genuine_input_common_mode_and_single_ground_gauge(self):
        a, av = self.input_dc(.15, -.7, 3.135)
        b, bv = self.input_dc(0., -.85, 3.465)
        # Identical local voltage must give identical genuine clamp current,
        # despite different absolute pad voltage and unrelated main supply.
        np.testing.assert_allclose(av, bv, rtol=1e-5, atol=1e-8)
        self.assertGreater(abs(float(av[0])), 1e-5)
        self.assertAlmostEqual(float(av[1]), -.85, delta=.002)
        self.assertEqual(sum('ground_gauge' in x for x in a.deck.lines), 1)
        self.assertEqual(a.deck.probes[-1].vdd, 3.6)

    def test_independent_main_rail_does_not_change_local_input(self):
        a, av = self.input_dc(.15, 3.4, 3.135)
        b, bv = self.input_dc(.15, 3.4, 3.465)
        np.testing.assert_allclose(av, bv, atol=1e-9)
        self.assertAlmostEqual(float(av[1]), 3.25, delta=.002)
        self.assertEqual(a.deck.probes[-1].vdd, b.deck.probes[-1].vdd)

    def test_source_ground_moves_physical_output_once_and_keeps_stress(self):
        values = []
        for offset in (0., .15):
            asm = si.Assembler(None, si.Config(si.EMPTY, corner='max',
                                extra=(('card_ground_offset', offset),)), 3.465)
            asm.lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
            si.ibis_driver([], 8e-9, 1.)(asm, 'pad', 'wifi', 'U3', '4', si.TI_LVC125)
            asm.deck.lines += ['Rload pad 0 100k', 'Cload pad 0 10p']
            asm.deck.probes.append(si.Probe('physical FPGA input', 'pad', 'ICE40HX4K-TQ144'))
            with tempfile.TemporaryDirectory() as work:
                t, w = si.run_deck(asm.deck, 3.465, 8e-9, 10e-12, work)
            values.append(float(w[-1, -1]))
            self.assertEqual(sum('ground_gauge' in x for x in asm.deck.lines), 1)
            if offset:
                _, failures = si.evaluate(t, w[:, -1], 'ICE40HX4K-TQ144', (), 8e-9, 3.465)
                self.assertTrue(any('overshoot' in f for f in failures), failures)
        self.assertAlmostEqual(values[1] - values[0], .15, delta=.001)

    def test_main_receiver_bank_and_pullup_use_main_fixed_corner(self):
        class Bench:
            def ice40_model(self, pin): return 'lvc330io'
        asm = si.Assembler(Bench(), si.Config(si.EMPTY, corner='max',
                           extra=(('ice40_receiver_corner', 'min'),)), 3.6)
        asm.ice40 = models.load_ice40()
        asm.device('main', 'main', 'U7', '48', 'ICE40HX4K-TQ144', 'pad')
        expected = asm.ice40['lvc330io'].vcc['min']
        self.assertEqual(asm.deck.probes[-1].vdd, expected)
        node = asm.rail('/+3V3', 'main')
        self.assertIn(f'V{node} {node} 0 {expected:g}', asm.deck.lines)
        self.assertNotEqual(expected, 3.6)

    def test_invalid_local_reference_fails_closed(self):
        model = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')['in']
        asm = si.Assembler(None, si.Config(si.EMPTY, extra=(('card_ground_offset', float('nan')),)), 3.3)
        with self.assertRaises(ValueError): asm.buffer_reference('die', 'wifi', 'U5', model, 'max')
        asm = si.Assembler(None, si.Config(si.EMPTY), 3.3)
        with self.assertRaises(ValueError): asm.buffer_reference('die', 'wifi', 'U5', model, 'unsupported')


class PhysicalSignalCap(unittest.TestCase):
    def test_actual_cap_tolerance_and_local_reference_in_transient(self):
        cfg = si.Config(si.EMPTY, extra=(('card_ground_offset', .15),
                                         ('signal_cap_scale', .9),
                                         ('signal_cap_scale_C60', 1.1),
                                         ('signal_cap_esr', 2.),
                                         ('signal_cap_esl', 2e-9)))
        asm = si.Assembler(None, cfg, 3.3)
        asm.signal_capacitor('wifi', 'C60', '10p', 'pad', '/GND')
        asm.deck.lines += ['Vsource source card_ground PWL(0 0 1n 0 1.001n 1 80n 1)',
                           'Rsource source pad 1000']
        asm.deck.probes.append(si.Probe('filtered pad', 'pad', 'RP2040'))
        with tempfile.TemporaryDirectory() as work:
            t, waves = si.run_deck(asm.deck, 3.3, 80e-9, 10e-12, work)
        at = int(np.argmin(np.abs(t - 21e-9)))
        expected = .15 + 1 - np.exp(-20 / 11.022)
        self.assertAlmostEqual(float(waves[at, 0]), expected, delta=.002)
        self.assertTrue(any(line.startswith('L') for line in asm.deck.lines))

    def test_return_resistance_measures_actual_ac_drop(self):
        cfg = si.Config(si.EMPTY, extra=(('card_ground_offset', .15),
                                         ('signal_cap_return_r', 3.),
                                         ('signal_cap_return_r_gpu_C60', 10.)))
        asm = si.Assembler(None, cfg, 3.3)
        asm.signal_capacitor('gpu', 'C60', '10p', 'pad', '/GND')
        asm.deck.lines += ['Vsource source card_ground PWL(0 0 1n 0 1.001n 1 80n 1)',
                           'Rsource source pad 1000']
        asm.deck.probes.append(si.Probe('filtered pad', 'pad', 'RP2040'))
        with tempfile.TemporaryDirectory() as work:
            t, waves = si.run_deck(asm.deck, 3.3, 80e-9, 10e-12, work)
        current = waves[:, 0]; ground_drop = waves[:, 1]
        self.assertGreater(float(np.max(current)), .0009)
        np.testing.assert_allclose(ground_drop, 10 * current, atol=1e-8)
        at = int(np.argmin(np.abs(t - 21e-9)))
        expected_current = np.exp(-20 / 10.1) / 1010
        self.assertAlmostEqual(float(current[at]), expected_current, delta=2e-6)
        self.assertLess(abs(float(ground_drop[-1])), 1e-5)

    def test_return_inductance_adds_to_body_esl(self):
        cfg = si.Config(si.EMPTY, extra=(('signal_cap_esl', 2e-9),
                                         ('signal_cap_return_l', 2e-9)))
        asm = si.Assembler(None, cfg, 3.3)
        asm.signal_capacitor('gpu', 'C60', '10p', 'pad', '/GND')
        asm.deck.lines += ['Vsource source card_ground PWL(0 0 1n 0 1.01n 1 80n 1)',
                           'Rsource source pad 100']
        with tempfile.TemporaryDirectory() as work:
            t, waves = si.run_deck(asm.deck, 3.3, 80e-9, 1e-12, work)
        self.assertGreater(float(np.max(np.abs(waves[:, 1]))), .01)
        self.assertLess(abs(float(waves[-1, 1])), 1e-5)

    def test_invalid_rf_envelope_fails_closed(self):
        for setting, value in (('signal_cap_scale', 0), ('signal_cap_esr', -1),
                               ('signal_cap_esl', float('nan')), ('signal_cap_return_r', -1),
                               ('signal_cap_return_l', float('nan'))):
            asm = si.Assembler(None, si.Config(si.EMPTY, extra=((setting, value),)), 3.3)
            with self.assertRaisesRegex(ValueError, 'invalid capacitor sensitivity'):
                asm.signal_capacitor('gpu', 'C60', '10p', 'pad', '/GND')


class GenuineTiLvc(unittest.TestCase):
    def test_disabled_y_rating_does_not_change_driven_y_rating(self):
        t = np.linspace(0, 20e-9, 201)
        v = np.full_like(t, 4.2)
        _, disabled = si.evaluate(t, v, si.TI_LVC125_HIZ_OUTPUT, (), 20e-9, 3.)
        _, driven = si.evaluate(t, v, si.TI_LVC125_OUTPUT, (), 20e-9, 3.)
        self.assertFalse(disabled, disabled)
        self.assertTrue(driven, driven)
        _, excessive = si.evaluate(t, np.full_like(t, 6.6), si.TI_LVC125_HIZ_OUTPUT,
                                  (), 20e-9, 3.)
        self.assertTrue(excessive, excessive)

    def test_miso_source_is_distinct_from_local_level_buffers(self):
        bench = si.Bench(BOARD_DIR)
        card = bench.circuit('gpu')
        ref, pin = si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW')
        card.components[ref] = (si.TI_LVC125, card.components[ref][1])
        card.pins[ref, pin] = '/MISO_SRC'
        for name, net in (('U_LEVEL_SCK', '/SCK_LEVEL'), ('U_LEVEL_MOSI', '/MOSI_LEVEL')):
            card.components[name] = (si.TI_LVC125, card.components[ref][1])
            card.pins[name, '4'] = net
        self.assertEqual(si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW'), (ref, pin))
        card.pins['U_LEVEL_MOSI', '4'] = '/MISO_SRC'
        with self.assertRaisesRegex(ValueError, '/MISO_SRC'):
            si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW')

    def test_real_ti_input_and_output_limits_are_distinct(self):
        t = np.linspace(0, 40e-9, 401)
        v = np.interp(t, np.array([0, 1, 3, 40]) * 1e-9, [0, 0, 4.2, 4.2])
        _, input_fails = si.evaluate(t, v, si.TI_LVC125, ((1e-9, 'rise'),), 40e-9, 3.3)
        _, output_fails = si.evaluate(t, v, si.TI_LVC125_OUTPUT, ((1e-9, 'rise'),), 40e-9, 3.3)
        self.assertFalse(any('overshoot' in f for f in input_fails), input_fails)
        self.assertTrue(any('overshoot' in f for f in output_fails), output_fails)

    def test_real_ti_requires_miso_src_and_independent_dck_bounds(self):
        bench = si.Bench(BOARD_DIR)
        card = bench.circuit('gpu')
        ref, pin = si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW')
        card.components[ref] = (si.TI_LVC125, card.components[ref][1])
        with self.assertRaisesRegex(ValueError, '/MISO_SRC'):
            si.driver_pin(bench, 'gpu', '/MISO', '74LVC1G125GW')
        card.pins[ref, pin] = '/MISO_SRC'
        cases = [c for c in si.mb_spi_cases(bench, kinds=('gpu',)) if c.group == 'MB spi MISO']
        self.assertEqual(len(cases), 768)
        self.assertEqual({(c.config.package, c.config.get('buffer_package')) for c in cases},
                         {(0, 0), (0, 1), (1, 0), (1, 1)})

    def test_real_ti_rejects_double_hypothetical_network(self):
        asm = si.Assembler(None, si.Config(si.EMPTY, extra=(('tx_series', 220),)), 3.3)
        asm.lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
        with self.assertRaisesRegex(ValueError, 'double count'):
            asm.device('J11:gpu', 'gpu', 'U4', '4', si.TI_LVC125, 'pad')

    def test_genuine_lvc_fixture_has_characterized_slow_anchor(self):
        model = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')['out']
        self.assertEqual(model.vcc, {'typ': 3.3, 'min': 3.0, 'max': 3.6})
        self.assertEqual(si.TI_LVC125_TPD50_MAX, 4.7e-9)
        for corner in models.CORNERS:
            for package in (0, 1):
                for edge in ('rise', 'fall'):
                    crossing = si.ti_lvc_fixture50_crossing(corner, package, edge)
                    self.assertGreater(crossing, 0)
                    self.assertLess(crossing, 30)


class Models(unittest.TestCase):
    def test_ladder_matches_ideal_line(self):
        g = route.Graph('x', 'n', 'JLC04161H-7628', {'In1.Cu': '/GND'})
        a, b = ((0, 0), 'F.Cu'), ((1000000, 0), 'F.Cu')
        g.tracks, g.pads = [[a, b, 'F.Cu', .35, 100.0]], {'A': a, 'B': b}
        ladder = route.Ladder(g, 'x', section_mm=1.0)
        lines = ladder.emit()
        z0, ps, _, _ = ladder.constants[('F.Cu', .35)]
        self.assertAlmostEqual(z0, 51.7, delta=1.0)   # JLC's 50 ohm width is ~0.35 mm
        td = 100 * ps * 1e-12
        deck = ['t', 'Vs s 0 PWL(0 0 1n 0 1.5n 1)', f'Rs s {ladder.pad("A")} {z0}', *lines,
                'Vi si 0 PWL(0 0 1n 0 1.5n 1)', f'Ri si t1 {z0}', f'T1 t1 0 t2 0 Z0={z0} TD={td}',
                'Ct t2 0 1f', '.options method=gear', '.control', 'set noaskquit',
                'tran 2p 5n 0 2p', f'wrdata o.dat v({ladder.pad("B")}) v(t2)', 'quit', '.endc', '.end']
        with tempfile.TemporaryDirectory() as work:
            Path(work, 'l.cir').write_text('\n'.join(deck) + '\n')
            subprocess.run(['ngspice', '-b', 'l.cir'], cwd=work, capture_output=True, check=True)
            data = np.loadtxt(Path(work, 'o.dat'))
        self.assertLess(np.max(np.abs(data[:, 1] - data[:, 3])), .03)

    def test_field_solver(self):
        import math
        import slowbus_field as field
        # zero-thickness stripline, exact (Cohn): b 1.0 mm, w 0.2 mm, Dk 4.4
        b, w = 1.0, .2
        z, td = field.line([(0, b, 4.4)], [(-w / 2, w / 2, b / 2 - .002, b / 2 + .002, 0),
                                           (-10, 10, -.001, 0, -1), (-10, 10, b, b + .001, -1)],
                           6.0, 0.0)
        k = 1 / math.cosh(math.pi * w / (2 * b))
        exact = 30 * math.pi / math.sqrt(4.4) * field.ellipk(k) / field.ellipk(math.sqrt(1 - k * k))
        self.assertLess(abs(z - exact) / exact, .04)
        self.assertAlmostEqual(td * 1e9, math.sqrt(4.4) / 299.792458 * 1e3, delta=.05)
        # JLC04161H-7628 microstrip vs Hammerstad-Jensen
        h, w, t = .2104, .35, .035
        z, _ = field.line([(0, h, 4.4)], [(-w / 2, w / 2, h, h + t, 0), (-10, 10, -.01, 0, -1)],
                          5.0, 3.0)
        self.assertLess(abs(z - route._z_microstrip(w, h, t, 4.4)[0]) / z, .03)

    def test_ibis_fixture_replay(self):
        ice40 = models.load_ice40()
        lvc = models.load_lvc125(si.OUT_DIR / 'cache/scem270.zip')
        ok, report = si.fixture_report(ice40, lvc)
        self.assertTrue(ok, {k: v for k, v in report.items() if not v['ok']})


class Routed(unittest.TestCase):
    def test_sck_topology_matches_si005(self):
        pins = ['R36.2'] + [f'J{n}.B13' for n in range(11, 17)]
        g = route.extract(BOARD_DIR / 'main/main.kicad_pcb', 'main', '/SPI_SCK',
                          pins + ['J4.3', 'TP54.1'])
        self.assertEqual(g.vias, 5)
        self.assertAlmostEqual(route.summary(g)['copper_mm'], 280.477, delta=.01)

    def test_opened_launch_is_an_open(self):
        from test_cosim_main_cpu_data import open_pad_tracks
        with tempfile.TemporaryDirectory() as work:
            changed = Path(work) / 'open.kicad_pcb'
            open_pad_tracks(BOARD_DIR / 'main/main.kicad_pcb', changed, 'J16', 'B13', '/SPI_SCK', 1)
            with self.assertRaisesRegex(ValueError, r"copper open from .* \['J16.B13'\]"):
                route.extract(changed, 'main', '/SPI_SCK',
                              ['R36.2'] + [f'J{n}.B13' for n in range(11, 17)] + ['J4.3', 'TP54.1'])


FAST_CORNER = ('max', 0, 1.1, 0, 0)     # corner, package, zscale, rx_c, connector
MIN_CORNER = ('min', 0, 1.1, 0, 0)
FIX_OHMS = 68                           # best single series value found (cpubus_options.py)


def cpu_case(bench, net='CPU_A0', corner=FAST_CORNER):
    for case in si.cc_bus_cases(bench):
        cfg = case.config
        if case.name.startswith(net + ' ') and \
                (cfg.corner, cfg.package, cfg.zscale, cfg.rx_c, cfg.connector) == corner:
            return case
    raise AssertionError(f'{corner} {net} case missing')


def ideal_line_peak(series_ohms, z0=98.0, td=.9e-9):
    """Peak at an iCE40 receiver die for the same IBIS driver (max corner) into
    one ideal lossless line: no routed copper, vias, socket or z-steps."""
    ice40 = models.load_ice40()
    model, corner = ice40['lvc330_b3io'], 'max'
    ku, kd = models.ku_schedule(model, corner, [(2e-9, 'rise')], 30e-9)
    deck = ['* ideal line', f'Vvcc_ibis vcc_ibis 0 {model.vcc[corner]:g}',
            models.pwl_source('ku', 'nku', ku), models.pwl_source('kd', 'nkd', kd),
            *models.ibis_device_lines('d', model, corner, 'die', 'vcc_ibis', 'nku', 'nkd'),
            'Lp die pin 1n', f'Rs pin a {series_ohms:g}', f'T1 a 0 b 0 Z0={z0:g} TD={td:g}',
            'Cb b 0 1.1p', 'Lr b rd 7n', 'Rr rd rx 0.6',
            *models.ibis_device_lines('r', model, corner, 'rx', 'vcc_ibis'),
            '.options method=gear reltol=1e-4 abstol=1e-10 vntol=1e-5 itl4=200',
            '.control', 'set noaskquit', 'tran 10p 30n 0 10p', 'wrdata w.dat v(rx)', 'quit', '.endc',
            '.end']
    with tempfile.TemporaryDirectory() as work:
        Path(work, 'i.cir').write_text('\n'.join(deck) + '\n')
        subprocess.run(['ngspice', '-b', 'i.cir'], cwd=work, capture_output=True, check=True)
        return float(np.loadtxt(Path(work, 'w.dat'))[:, 1].max())


def fixed_boards(work, ohms=FIX_OHMS):
    """main + cpu with the CPU card's 33 ohm RN arrays changed to `ohms`."""
    import cpubus_options as options
    return options.mutated_boards(BOARD_DIR, work, card_ohms=ohms)


def add_stub(work, mm, net='/CPU_A0', ref='U7'):
    """An unterminated F.Cu stub of `mm` off the receiver pad, in work/main."""
    import pcbnew
    board = pcbnew.LoadBoard(str(BOARD_DIR / 'main/main.kicad_pcb'))
    pad = next(p for p in board.FindFootprintByReference(ref).Pads() if p.GetNetname() == net)
    x, y = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
    pieces, left, k = '', float(mm), 0
    while left > 1e-9:
        piece = min(25.0, left)
        pieces += (f'\n\t(segment (start {x:.4f} {y + 25 * k:.4f}) (end {x:.4f} {y + 25 * k + piece:.4f}) '
                   f'(width 0.2) (layer "F.Cu") (net "{net}") (uuid "00000000-0000-0000-0000-0000000000{k:02d}"))')
        left, k = left - piece, k + 1
    text = (BOARD_DIR / 'main/main.kicad_pcb').read_text()
    replace_file(work / 'main/main.kicad_pcb', text.rstrip()[:-1] + pieces + '\n)\n')


class OldCpuBus33(unittest.TestCase):
    """/CPU_A0 (CPU-card U1.1 -> RN1 -> J1 -> J2 -> 110 mm In2/In3 -> U7.25) with the
    superseded 33 ohm arrays (the board now has 68 ohm, FIX_OHMS) is a real
    overshoot, not a model artefact: the same IBIS driver into one ideal lossless
    line reproduces the routed peak, and only the series value moves it."""

    def routed_33(self):
        with tempfile.TemporaryDirectory() as work:
            fixed_boards(Path(work), ohms=33)
            return si.simulate(cpu_case(si.Bench(Path(work))), Path(work))

    def test_overshoot_is_reported(self):
        result = self.routed_33()
        self.assertTrue(any('main:U7.25: overshoot' in f and 'beyond abs max 3.600 V' in f
                            for f in result['failures']), result['failures'])
        self.assertGreater(result['receivers']['main:U7.25']['vmax'], 4.0)

    def test_ideal_line_reproduces_the_peak(self):
        routed = self.routed_33()['receivers']['main:U7.25']['vmax']
        ideal = ideal_line_peak(33)
        self.assertLess(abs(routed - ideal), .15, (routed, ideal))
        self.assertGreater(ideal, 4.0)
        self.assertLess(ideal_line_peak(100), 3.5)        # matched: no overshoot, Zs ~ Z0

    def test_schottky_clamps_alone_do_not_meet_the_limit(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as work:
            fixed_boards(Path(work), ohms=33)          # the superseded arrays
            case = cpu_case(si.Bench(Path(work)))
            clamped = replace(case, config=replace(case.config, extra=(('rx_diode', 1),)))
            peak = si.simulate(clamped, Path(work))['receivers']['main:U7.25']['vmax']
        self.assertGreater(peak, 3.9)      # Vcc 3.47 V + Schottky drop at tens of mA


class Mutations(unittest.TestCase):
    """Must-fail mutations of a passing design: the CPU card's arrays at FIX_OHMS,
    checked at the min corner where that value passes."""

    def simulate(self, work, corner=MIN_CORNER):
        return si.simulate(cpu_case(si.Bench(work), corner=corner), work)

    def test_fixed_baseline_passes(self):
        with tempfile.TemporaryDirectory() as work:
            fixed_boards(Path(work))
            self.assertEqual(self.simulate(Path(work))['failures'], [])

    def test_removed_series_resistor_fails(self):
        with tempfile.TemporaryDirectory() as work:
            fixed_boards(Path(work), ohms=.01)          # the pack shorted out
            result = self.simulate(Path(work))
        self.assertTrue(any('overshoot' in f or 'undershoot' in f for f in result['failures']),
                        result['failures'])

    def test_stub_length_is_the_lever(self):
        for mm, fails in ((30, False), (60, True), (150, True)):
            with self.subTest(stub_mm=mm), tempfile.TemporaryDirectory() as work:
                work = Path(work)
                fixed_boards(work)
                add_stub(work, mm)
                result = self.simulate(work)
                self.assertGreater(result['nets']['main:/CPU_A0']['copper_mm'], 110 + mm - 1)
                self.assertEqual(bool(result['failures']), fails, result['failures'])

    def test_changed_board_breaks_evidence(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            shutil.copytree(BOARD_DIR / 'storage', work / 'storage', symlinks=True)
            path = work / 'storage/storage.kicad_pcb'
            data = bytearray(path.read_bytes())
            data[-2] ^= 1
            path.write_bytes(bytes(data))
            with self.assertRaises(ValueError):
                si.load_evidence(work, ('storage',), artifacts_only=True)


def net_value(work, kind, refs, old, new):
    """work/<kind>/<kind>.net with the value of each ref in `refs` changed old -> new."""
    text = (BOARD_DIR / kind / f'{kind}.net').read_text()
    for ref in refs:
        text, count = re.subn(rf'(\(ref "{ref}"\)\s*\(value ")({re.escape(old)})("\))',
                              rf'\g<1>{new}\3', text)
        if count != 1:
            raise AssertionError(f'{kind} {ref}: value {old} found {count} times')
    replace_file(work / kind / f'{kind}.net', text)


def pick(cases, name, **wanted):
    found = [c for c in cases if c.name.startswith(name + ' ') and all(
        (getattr(c.config, k) if hasattr(c.config, k) else c.config.get(k)) == v
        for k, v in wanted.items())]
    if len(found) != 1:
        raise AssertionError(f'{name} {wanted}: {len(found)} cases')
    return found[0]


class StorageCard(unittest.TestCase):
    """RP2040 -> microSD. The RP2040 publishes no IBIS or edge rate, so the row
    is judged at both driver bounds: the weak bound (170 ohm, 5 ns) must pass; the
    fast bound (20 ohm, 0.5 ns, unsourced) fails and stays red until measured."""

    def case(self, work, bracket, net='SD_MOSI'):
        return pick(si.sc_cases(si.Bench(work)), net, bracket=bracket, zscale=1.1, rx_c=0)

    def test_weak_bound_passes_and_fast_bound_is_red(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('storage',))
            self.assertEqual(si.simulate(self.case(work, 1), work)['failures'], [])
            fast = si.simulate(self.case(work, 0), work)['failures']
        self.assertTrue(any('overshoot' in f for f in fast), fast)

    def test_wrong_pullup_fails(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('storage',))
            net_value(work, 'storage', ('RN1',), '10k', '100')      # a 100 ohm "pull-up"
            failures = si.simulate(self.case(work, 1), work)['failures']
        self.assertTrue(any('never crosses VIL' in f for f in failures), failures)


class EinkCard(unittest.TestCase):
    """RP2040 -> 33 ohm -> panel cable -> HAT (TXB0108). Judged at the fast driver
    bound over the 300 ohm loose-cable bound: the as-built 33 ohm fails; 150 ohm
    passes at 0.15 m, and fails again for a removed resistor and a doubled cable."""

    def simulate(self, ohms, cable_m=.15, net='EPD_CLK'):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('eink',))
            if ohms != 33:
                net_value(work, 'eink', ('R10', 'R11', 'R12'), '33R', f'{ohms:g}')
            case = pick(si.ec_cases(si.Bench(work)), net, bracket=0, zscale=1.1, rx_c=0,
                        cable_z=300.0, cable_m=cable_m)
            return si.simulate(case, work)['failures']

    def test_as_built_is_red_at_the_fast_bound(self):
        self.assertTrue(any('undershoot' in f for f in self.simulate(33)))

    def test_fixed_baseline_passes(self):
        self.assertEqual(self.simulate(150), [])

    def test_removed_series_resistor_fails(self):
        self.assertTrue(self.simulate(.01))

    def test_doubled_cable_fails(self):
        self.assertTrue(self.simulate(150, cable_m=.3))


class MainSpi(unittest.TestCase):
    """iCE40 U7.43 -> R36 33 ohm -> six-slot SCK tree -> RP2040 card. Only a
    lightly loaded corner passes as built (one storage card in J16, max IBIS,
    10 pF RP2040 input); the populated-slot cases are red and are reported by
    the row. Removing R36 must fail even in that corner."""

    def simulate(self, ohms):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('main', 'storage'))
            if ohms != 33:
                net_value(work, 'main', ('R36',), '33', f'{ohms:g}')
            case = pick(si.mb_spi_cases(si.Bench(work), kinds=('storage',), singles=('storage',)),
                        'SCK storage in J16 only', corner='max', package=1, zscale=.9, rx_c=1,
                        connector=0)
            return si.simulate(case, work)['failures']

    def test_lightly_loaded_baseline_passes(self):
        self.assertEqual(self.simulate(33), [])

    def test_removed_series_resistor_fails(self):
        failures = self.simulate(.01)
        self.assertTrue(any('overshoot' in f for f in failures), failures)

    def test_full_slots_are_red_as_built(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('main', 'storage'))
            case = pick(si.mb_spi_cases(si.Bench(work), kinds=('storage',), singles=()),
                        'SCK all storage', corner='min', package=0, zscale=.9, rx_c=0, connector=0)
            result = si.simulate(case, work)
        self.assertTrue(result['failures'], result)
        # This real populated clock must violate a physical Schmitt margin,
        # rather than merely retain the obsolete uniform-edge wording.
        rejected = [m['schmitt_qualification'] for label, m in result['receivers'].items()
                    if label.endswith(':storage:U1.4')
                    and not m.get('schmitt_qualification', {}).get('ok', True)]
        self.assertTrue(rejected, result)
        self.assertTrue(any(e['whole_band_adverse_mv'] >= 200
                            or e['full_valid_band_recross']
                            for m in rejected for e in m['edges']), rejected)


def main():
    global BOARD_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-dir', type=Path, default=BOARD_DIR)
    args, rest = parser.parse_known_args()
    BOARD_DIR = args.board_dir.resolve()
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)


if __name__ == '__main__':
    main()
