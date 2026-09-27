#!/usr/bin/env python3
"""Provenance and report regressions without KiCad/network dependencies."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/tools'))
import boardevidence as evidence
import boardcheck


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('hw/boards/cpu.py', 'hw/boards/rp2040card.py', 'hw/pins.yaml', 'hw/tools/check.py'):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture')
        self.out = self.root / 'build/hw/cpu'
        (self.out / 'fab').mkdir(parents=True)
        for name in ('cpu.kicad_sch', 'cpu.kicad_pcb', 'cpu.kicad_pro', 'cpu.net', 'erc.json',
                     'drc.json', 'fab/bom.csv', 'fab/cpl.csv', 'fab/order.json',
                     'fab/cpu-F_Cu.gbr', 'fab/cpu.drl', 'cpu-top.png', 'cpu-bottom.png'):
            (self.out / name).write_text('fixture')
        self.before = evidence.inputs('cpu', self.root)
        evidence.record('cpu', self.out, self.before, 3, self.root)

    def test_valid_and_relocated_build(self):
        self.assertEqual(evidence.validate('cpu', self.out, self.root)['boards'], 3)

    def test_missing_receipt(self):
        (self.out / 'evidence.json').unlink()
        with self.assertRaises(FileNotFoundError):
            evidence.validate('cpu', self.out, self.root)

    def test_stale_source(self):
        (self.root / 'hw/boards/cpu.py').write_text('swapped pins')
        with self.assertRaisesRegex(ValueError, 'stale board evidence'):
            evidence.validate('cpu', self.out, self.root)

    def test_changed_board(self):
        (self.out / 'cpu.kicad_pcb').write_text('unrouted replacement')
        with self.assertRaisesRegex(ValueError, 'changed or missing board artifacts'):
            evidence.validate('cpu', self.out, self.root)

    def test_deleted_artifact(self):
        (self.out / 'fab/bom.csv').unlink()
        with self.assertRaisesRegex(ValueError, 'changed or missing board artifacts'):
            evidence.validate('cpu', self.out, self.root)

    def test_changed_during_pipeline(self):
        (self.root / 'hw/pins.yaml').write_text('new pin mapping')
        with self.assertRaisesRegex(ValueError, 'changed during pipeline'):
            evidence.record('cpu', self.out, self.before, 3, self.root)

    def test_missing_required_artifact_even_with_matching_manifest(self):
        (self.out / 'cpu.net').unlink()
        evidence.record('cpu', self.out, self.before, 3, self.root)
        with self.assertRaisesRegex(ValueError, 'missing or empty artifact'):
            evidence.validate('cpu', self.out, self.root)

    def test_missing_fab_export_even_with_matching_manifest(self):
        (self.out / 'fab/cpu-F_Cu.gbr').unlink()
        evidence.record('cpu', self.out, self.before, 3, self.root)
        with self.assertRaisesRegex(ValueError, 'missing or empty fab artifact'):
            evidence.validate('cpu', self.out, self.root)

    def test_changed_render(self):
        (self.out / 'cpu-top.png').write_text('wrong render')
        with self.assertRaisesRegex(ValueError, 'changed or missing board artifacts'):
            evidence.validate('cpu', self.out, self.root)

    def test_wrong_board(self):
        with self.assertRaisesRegex(ValueError, 'wrong board'):
            evidence.validate('gpu', self.out, self.root)


class ReportTests(unittest.TestCase):
    SEVERITIES = {'included_severities': ['error', 'warning', 'exclusion']}

    def test_clean_reports(self):
        boardcheck.check_report({**self.SEVERITIES, 'sheets': [{'violations': []}]}, 'erc')
        boardcheck.check_report(dict(self.SEVERITIES, violations=[], unconnected_items=[], schematic_parity=[]), 'drc')

    def test_omitted_severity_is_not_clean(self):
        with self.assertRaisesRegex(ValueError, 'omitted a severity class'):
            boardcheck.check_report({'included_severities': ['error'], 'sheets': [{'violations': []}]}, 'erc')

    def test_missing_erc_sheet_findings(self):
        with self.assertRaisesRegex(ValueError, 'missing sheet violations'):
            boardcheck.check_report({**self.SEVERITIES, 'sheets': [{}]}, 'erc')

    def test_missing_report_fields(self):
        for check in ('erc', 'drc'):
            with self.subTest(check=check), self.assertRaises(ValueError):
                boardcheck.check_report({}, check)

    def test_each_drc_failure_class(self):
        for key in ('violations', 'unconnected_items', 'schematic_parity'):
            report = dict(self.SEVERITIES, violations=[], unconnected_items=[], schematic_parity=[])
            report[key] = [{'severity': 'error'}]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'has 1 findings'):
                boardcheck.check_report(report, 'drc')

    def test_erc_warning_is_not_implicitly_waived(self):
        with self.assertRaisesRegex(ValueError, 'has 1 findings'):
            boardcheck.check_report({**self.SEVERITIES, 'sheets': [{'violations': [{'severity': 'warning'}]}]}, 'erc')


if __name__ == '__main__':
    unittest.main()
