#!/usr/bin/env python3
"""BUS-005 cannot use a nominal board size as routed timing evidence."""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hw.timing import cpubus_budget as bus


class LengthEvidence(unittest.TestCase):
    def test_copper_length_counts_branches_and_vias(self):
        from hw.timing.extract_lengths import copper_lengths
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / 'fixture.kicad_pcb'
            board.write_text('(kicad_pcb (general (thickness 1.6)) (net 1 "/CPU_A0") '
                             '(segment (start 0 0) (end 6 0) (net 1)) '
                             '(segment (start 6 0) (end 10 0) (net 1)) '
                             '(via (at 6 0) (net 1)))')
            self.assertAlmostEqual(copper_lengths(board)['CPU_A0'], 11.6)

    def test_missing_layout_is_red(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus, 'ROOT', tmp):
            with self.assertRaisesRegex(ValueError, 'routed trace lengths missing'):
                bus.lengths()

    def test_per_net_lengths_are_required(self):
        from hw.timing.extract_lengths import bus_nets
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus, 'ROOT', tmp):
            root = Path(tmp)
            path = root / 'build/hw/cpubus_lengths.json'
            path.parent.mkdir(parents=True)
            boards = [root / 'build/hw/main/main.kicad_pcb',
                      root / 'build/hw/cpu/cpu.kicad_pcb']
            for board in boards:
                board.parent.mkdir(parents=True)
                board.write_text('routed board fixture')
            sources = {str(board.relative_to(root)): hashlib.sha256(board.read_bytes()).hexdigest()
                       for board in boards}
            good = {'version': 1, 'bus_mm': {name: 16 for name in bus_nets()},
                    'clk_diff_mm': 2, 'sources': sources}
            for bad in ({}, dict(good, bus_mm={}),
                        dict(good, bus_mm={**good['bus_mm'], 'extra': 5}),
                        dict(good, clk_diff_mm=-1), dict(good, sources={})):
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    bus.lengths()
            path.write_text(json.dumps(good))
            self.assertEqual(bus.lengths()[:2], (16, 2))
            boards[0].write_text('changed after extraction')
            with self.assertRaisesRegex(ValueError, 'stale routed length evidence'):
                bus.lengths()


if __name__ == '__main__':
    unittest.main()
