#!/usr/bin/env python3
"""STEP cache rejects changed copper, exporter, models and foreign ownership."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/mech'))
import step_cache as cache
import fit
class Cache(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name);self.pcb=self.base/'board.kicad_pcb'
  self.model=self.base/'part.wrl';self.model.write_text('vrml')
  self.actual=self.model.with_suffix('.step');self.actual.write_text('modelSTEP')
  self.pcb.write_text('(kicad_pcb (model '+json.dumps(str(self.model))+'))')
  (self.base/'evidence.json').write_text(json.dumps({'inputs':{}}))
  self.exporter=self.base/'kicad-cli';self.exporter.write_text('exporter')
  self.cmd=[str(self.exporter),'pcb','export','step','--subst-models']
  self.step=self.base/'board.step';self.step.write_text('exportedSTEP')
  self.which=patch.object(cache.shutil,'which',return_value=str(self.exporter));self.which.start();self.addCleanup(self.which.stop)
 def ident(self):return cache.identity(self.pcb,self.cmd)
 def own(self):
  identity=self.ident();cache.record(self.step,identity,identity);return identity
 def test_unowned_existing_step_is_never_adopted(self):
  self.assertFalse(cache.reusable(self.step,self.ident()))
  self.assertFalse(cache.sidecar(self.step).exists())
 def test_real_export_record_roundtrip_and_tampered_step(self):
  identity=self.own();self.assertTrue(cache.reusable(self.step,identity))
  self.step.write_text('changedSTEP');self.assertFalse(cache.reusable(self.step,identity))
 def test_changed_board_with_preserved_mtime(self):
  self.own();stamp=self.pcb.stat().st_mtime_ns
  self.pcb.write_text(self.pcb.read_text()+' copper changed')
  os.utime(self.pcb,ns=(stamp,stamp));self.assertFalse(cache.reusable(self.step,self.ident()))
 def test_same_bytes_wrong_root_rejected(self):
  self.own();other=self.base/'foreign';other.mkdir();foreign=other/self.pcb.name
  foreign.write_bytes(self.pcb.read_bytes());(other/'evidence.json').write_bytes((self.base/'evidence.json').read_bytes())
  identity=cache.identity(foreign,self.cmd)
  self.assertFalse(cache.reusable(self.step,identity))
 def test_actual_step_substitution_change_rejected(self):
  self.own();self.actual.write_text('differentSTEPmodel')
  self.assertFalse(cache.reusable(self.step,self.ident()))
 def test_exporter_and_options_changes_rejected(self):
  self.own();self.exporter.write_text('newexporter')
  self.assertFalse(cache.reusable(self.step,self.ident()))
  self.own();self.cmd.append('--no-components')
  self.assertFalse(cache.reusable(self.step,self.ident()))
 def test_missing_model_becomes_present_invalidates(self):
  self.actual.unlink();self.own();self.actual.write_text('newmodel')
  self.assertFalse(cache.reusable(self.step,self.ident()))
 def test_changes_during_export_cannot_record(self):
  before=self.ident();self.pcb.write_text(self.pcb.read_text()+' mutation')
  with self.assertRaisesRegex(ValueError,'changed during export'):cache.record(self.step,before,self.ident())
  self.assertFalse(cache.sidecar(self.step).exists())
 def test_unresolved_model_variable_rejected(self):
  self.pcb.write_text('(kicad_pcb (model "${UNKNOWN_MECH_VAR}/part.step"))')
  with self.assertRaisesRegex(ValueError,'unresolved'):self.ident()
 def test_full_fit_key_also_binds_step_and_model(self):
  board={'pcb':str(self.pcb),'name':'board','kind':'io','source_bound_step':True}
  with patch.object(fit,'OUT',str(self.base)):
   step,cmd=fit.step_command(board)
   identity=cache.identity(self.pcb,cmd+[str(self.pcb)])
   cache.record(step,identity,identity)
   key=fit.inputs_key({'board':board})
   self.assertEqual(key,fit.inputs_key({'board':board}))
   self.actual.write_text('modifiedglobalmodel')
   self.assertNotEqual(key,fit.inputs_key({'board':board}))
   self.actual.write_text('modelSTEP')
   self.assertEqual(key,fit.inputs_key({'board':board}))
   self.step.write_text('tamperedexport')
   self.assertNotEqual(key,fit.inputs_key({'board':board}))
 def test_empty_export_rejected(self):
  identity=self.ident();self.step.write_bytes(b'')
  with self.assertRaisesRegex(ValueError,'missing/empty'):cache.record(self.step,identity,identity)
if __name__=='__main__':unittest.main()
