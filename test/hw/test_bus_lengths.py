#!/usr/bin/env python3
"""BUS-005 cannot use a nominal board size as routed timing evidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hw.timing import cpubus_budget as bus


class LengthEvidence(unittest.TestCase):
    def test_missing_layout_is_red(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus, 'ROOT', tmp):
            with self.assertRaisesRegex(ValueError, 'routed trace lengths missing'):
                bus.lengths()

    def test_per_net_lengths_are_required(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus, 'ROOT', tmp):
            path = Path(tmp) / 'build/hw/cpubus_lengths.json'
            path.parent.mkdir(parents=True)
            for data in ({}, {'bus_mm': {}, 'clk_diff_mm': 1},
                         {'bus_mm': {'CPU_A0': 0}, 'clk_diff_mm': 1},
                         {'bus_mm': {'CPU_A0': 12}}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    bus.lengths()
            path.write_text(json.dumps({'bus_mm': {'CPU_A0': 12, 'CPU_D0': 16},
                                        'clk_diff_mm': 2}))
            self.assertEqual(bus.lengths()[:2], (16, 2))


if __name__ == '__main__':
    unittest.main()
