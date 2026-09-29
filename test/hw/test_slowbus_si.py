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
* a passing CPU-bus net fails once its series resistor pack is shorted
  (netlist mutation) and once a long stub is added to its routed copper
  (board mutation);
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


def cpu_case(net='CPU_A0'):
    bench = si.Bench(BOARD_DIR)
    cases = [c for c in si.cc_bus_cases(bench) if c.name.startswith(net + ' ')]
    # the fast corner: strongest driver, lowest impedance, light loads
    for case in cases:
        cfg = case.config
        if (cfg.corner, cfg.package, cfg.zscale, cfg.rx_c, cfg.connector) == ('max', 0, 1.1, 0, 0):
            return case
    raise AssertionError('fast-corner CPU_A0 case missing')


class Mutations(unittest.TestCase):
    def test_baseline_passes(self):
        result = si.simulate(cpu_case(), BOARD_DIR)
        self.assertEqual(result['failures'], [])

    def test_shorted_series_pack_fails(self):
        case = cpu_case()
        rn = next(r for r in si.Bench(BOARD_DIR).circuit('cpu').resistors
                  if r.ref.startswith('RN') and '/CPU_A0' in ''.join(r.ends) or
                  (r.ref.startswith('RN') and any(e.endswith('A0') for e in r.ends)))
        pack = rn.ref.split('.')[0]
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('main', 'cpu'))
            source = (BOARD_DIR / 'cpu/cpu.net').read_text()
            changed, count = re.subn(rf'(\(ref "{pack}"\)\s*\(value ")33("\))', r'\g<1>0.01\2', source)
            self.assertEqual(count, 1)
            replace_file(work / 'cpu/cpu.net', changed)
            result = si.simulate(case, work)
        self.assertTrue(any('overshoot' in f or 'undershoot' in f or 'rings back' in f
                            for f in result['failures']), result['failures'])

    def test_long_stub_fails(self):
        case = cpu_case()
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            mirror(BOARD_DIR, work, ('main', 'cpu'))
            text = (BOARD_DIR / 'main/main.kicad_pcb').read_text()
            # a 150 mm unterminated F.Cu stub from the U7 receiver pad
            import pcbnew
            board = pcbnew.LoadBoard(str(BOARD_DIR / 'main/main.kicad_pcb'))
            u7 = board.FindFootprintByReference('U7')
            pad = next(p for p in u7.Pads() if p.GetNetname() == '/CPU_A0')
            x, y = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            stub = ''.join(f'\n\t(segment (start {x:.4f} {y + 25 * k:.4f}) '
                           f'(end {x:.4f} {y + 25 * (k + 1):.4f}) (width 0.2) (layer "F.Cu") '
                           f'(net "/CPU_A0") (uuid "00000000-0000-0000-0000-00000000000{k}"))'
                           for k in range(6))
            changed = text.rstrip()[:-1] + stub + '\n)\n'
            replace_file(work / 'main/main.kicad_pcb', changed)
            result = si.simulate(case, work)
        self.assertGreater(result['nets']['main:/CPU_A0']['copper_mm'], 150)
        self.assertTrue(result['failures'], 'a 150 mm stub still passed')

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


def main():
    global BOARD_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-dir', type=Path, default=BOARD_DIR)
    args, rest = parser.parse_known_args()
    BOARD_DIR = args.board_dir.resolve()
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)


if __name__ == '__main__':
    main()
