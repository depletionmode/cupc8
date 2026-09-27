#!/usr/bin/env python3
"""Memory timing budgets fail when a routed path exceeds the available clocks."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hw.timing.memory_budget import margins, routed_lengths
from unittest.mock import patch


def lengths(mm):
    return ({f'MEM_A{i}': mm for i in range(19)} |
            {f'MEM_D{i}': mm for i in range(8)} |
            {name: mm for name in ('MEM_nOE', 'MEM_nWE', 'MEM_nCE_RAM', 'MEM_nCE_ROM')})


class MemoryBudgetTests(unittest.TestCase):
    def test_nominal_and_overlong_route(self):
        good = dict(margins(lengths(50), (10, 10)))
        self.assertTrue(all(v >= .2 for v in good.values()), good)
        bad = dict(margins(lengths(10000), (10, 10)))
        self.assertLess(bad['ROM read setup (two clocks)'], .2)

    def test_every_memory_net_must_be_routed(self):
        with patch('hw.timing.memory_budget.copper_lengths', return_value=lengths(50)):
            self.assertEqual(routed_lengths(Path('fixture'))['MEM_A0'], 50)
        incomplete = lengths(50)
        del incomplete['MEM_D7']
        with patch('hw.timing.memory_budget.copper_lengths', return_value=incomplete):
            with self.assertRaisesRegex(ValueError, 'MEM_D7'):
                routed_lengths(Path('fixture'))


if __name__ == '__main__':
    unittest.main()
