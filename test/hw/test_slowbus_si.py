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


class SlotSpiQualification(unittest.TestCase):
    """M1's required rate and unsupported hardware maximum stay distinct."""

    def results(self, miso_settled_ns=20):
        def receiver(group, label, rise, fall):
            return {'group': group, 'receivers': {label: {'edges': [
                {'edge': 'rise', 'first_band_ns': 1, 'settled_ns': rise},
                {'edge': 'fall', 'first_band_ns': 1, 'settled_ns': fall}]}}}
        return [receiver('MB spi SCK', 'J16:storage:U1.4', 2, 30),
                receiver('MB spi MOSI', 'J16:storage:U1.5', 4, 4),
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

    def test_waveform_period_uses_qualified_rate(self):
        self.assertEqual(si.SPI_HZ, si.QUALIFIED_SPI_HZ)
        self.assertEqual(si.QUALIFIED_SPI_HZ, 3e6)
        self.assertEqual(si.SPI_HARDWARE_MAX_HZ, 6e6)
        edges, _ = si.clock_edges(si.SPI_HZ)
        self.assertAlmostEqual((edges[1][0] - edges[0][0]) * 1e9, 166.6666667)


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
            failures = si.simulate(case, work)['failures']
        self.assertTrue(any('non-monotonic' in f or 'rings back' in f for f in failures), failures)


def main():
    global BOARD_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-dir', type=Path, default=BOARD_DIR)
    args, rest = parser.parse_known_args()
    BOARD_DIR = args.board_dir.resolve()
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)


if __name__ == '__main__':
    main()
