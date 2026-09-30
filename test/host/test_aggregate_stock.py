#!/usr/bin/env python3
"""Shared scarce-part stock can pass eight separate checks and fail the order."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aggregate_stock', ROOT/'tools/aggregate_stock.py')
gate = importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

class Aggregate(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name)
  for board in gate.BOARDS:
   path=self.base/board; (path/'fab').mkdir(parents=True)
   (path/'evidence.json').write_text(json.dumps({'boards':2}))
   (path/'fab/bom.csv').write_text('Designator,LCSC Part #\nR1,C123\n')
  # Synthetic tests exercise aggregation; real CLI always uses the actual validator.
  validator=patch.object(gate.boardevidence,'validate',side_effect=lambda b,p:json.loads((p/'evidence.json').read_text()))
  validator.start();self.addCleanup(validator.stop)
  environment=patch.dict(os.environ,{'CUPC8_OFFLINE':'','JLCPARTS_RECORDED':''})
  environment.start();self.addCleanup(environment.stop)
 def query(self,stock):return patch.object(gate.jlcparts,'query',return_value=[{'componentCode':'C123','stockCount':stock}])
 def test_separate_board_checks_pass_shared_order_fails(self):
  stock=4
  self.assertTrue(all(stock>=2*2 for b in gate.BOARDS))
  report={}
  with self.query(stock):
   with self.assertRaisesRegex(ValueError,'combined demand 16'):gate.check(self.base,report)
  self.assertEqual(report['parts']['C123']['required_stock'],32)
  self.assertEqual(report['status'],'failed')
 def test_sum_margin_boundary_and_before_after_binding(self):
  report={}
  with self.query(32) as query:gate.check(self.base,report)
  self.assertEqual(query.call_count,1)
  self.assertEqual(report['status'],'passed')
  self.assertEqual(report['input_validation_after_queries'],'passed')
 def test_offline_and_recorded_cannot_query_or_pass(self):
  for variable in ('CUPC8_OFFLINE','JLCPARTS_RECORDED'):
   with self.subTest(variable=variable),patch.dict(os.environ,{variable:'fixture'}),patch.object(gate.jlcparts,'query',side_effect=AssertionError('live query forbidden')):
    with self.assertRaisesRegex(ValueError,'rejects offline'):gate.check(self.base,{})
 def test_missing_board_or_wrong_quantity_rejected(self):
  receipt=self.base/'main/evidence.json';receipt.write_text('{"boards":3}')
  with self.assertRaisesRegex(ValueError,'exactly 2'):gate.demand(self.base)
  receipt.unlink()
  with self.assertRaises(OSError):gate.demand(self.base)
 def test_duplicate_designator_rejected(self):
  (self.base/'io/fab/bom.csv').write_text('Designator,LCSC Part #\nR1,C123\nR1,C456\n')
  with self.assertRaisesRegex(ValueError,'repeated BOM'):gate.demand(self.base)
 def test_query_mutation_invalidates_proof(self):
  def mutate(*args):
   (self.base/'main/fab/bom.csv').write_text('Designator,LCSC Part #\n"R1,R2",C123\n')
   return [{'componentCode':'C123','stockCount':100}]
  report={}
  with patch.object(gate.jlcparts,'query',side_effect=mutate):
   with self.assertRaisesRegex(ValueError,'changed during'):gate.check(self.base,report)
  self.assertNotEqual(report['status'],'passed')
 def test_wrong_supplier_identity_does_not_pass(self):
  with patch.object(gate.jlcparts,'query',return_value=[{'componentCode':'C124','stockCount':100}]):
   with self.assertRaisesRegex(ValueError,'missing or ambiguous'):gate.check(self.base,{})
 def test_network_failure_is_blocked_without_cached_answer(self):
  report={}
  with patch.object(gate.jlcparts,'query',side_effect=OSError('DNS unavailable')):
   with self.assertRaises(OSError):gate.check(self.base,report)
  self.assertEqual(report['status'],'blocked');self.assertEqual(report['parts'],{})
if __name__=='__main__':unittest.main()
