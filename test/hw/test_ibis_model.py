#!/usr/bin/env python3
"""The exact vendor IBIS source is required before any ngspice claim."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/si'))
from fetch_ice40_ibis import verify

MODEL = Path(__file__).resolve().parents[2] / 'build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs'


class VendorModelTests(unittest.TestCase):
    def test_exact_vendor_model_and_corrupt_counterexample(self):
        source = MODEL.read_bytes()
        self.assertEqual(len(verify(source)), 64)
        changed = bytearray(source)
        changed[100] ^= 1
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            verify(changed)


if __name__ == '__main__':
    unittest.main()
