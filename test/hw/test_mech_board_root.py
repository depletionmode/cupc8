#!/usr/bin/env python3
"""Actual completed eight-board mechanical roots reject partial/stale proofs.

No generators/routers are allowed on this explicit read-only path.
"""
import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mechanical_fit',ROOT/'hw/mech/fit.py')
fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
BOARD_ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'build/hw'
NAMES={'main','cpu','gpu','io','wifi','storage','eink','system'}
class BoardRoot(unittest.TestCase):
 def test_actual_eight_packages_ignore_partial_legacy_selector(self):
  with patch.dict(os.environ,{'CUPC8_MECH_BOARDS':'cpu'}),patch.object(fit.subprocess,'run',side_effect=AssertionError('generator forbidden')):
   result=fit.discover(BOARD_ROOT)
  self.assertEqual(set(result),NAMES)
  self.assertTrue(all(Path(p).is_relative_to(BOARD_ROOT) for p in result.values()))
 def fixture(self,base,main=False):
  for name in NAMES-{'main'}:(base/name).symlink_to(BOARD_ROOT/name,target_is_directory=True)
  if main:
   dst=base/'main';dst.mkdir()
   for p in (BOARD_ROOT/'main').iterdir():
    if p.name!='evidence.json':(dst/p.name).symlink_to(p,target_is_directory=p.is_dir())
   return dst
 def test_missing_board_never_falls_back_to_generator(self):
  with tempfile.TemporaryDirectory(prefix='cupc8-mech-missing-') as temp:
   base=Path(temp);self.fixture(base)
   with patch.object(fit.subprocess,'run',side_effect=AssertionError('generator forbidden')):
    with self.assertRaisesRegex(SystemExit,'main: explicit mechanical board root'):fit.discover(base)
 def test_stale_manufacturing_source_never_runs_fit_or_generator(self):
  with tempfile.TemporaryDirectory(prefix='cupc8-mech-stale-') as temp:
   base=Path(temp);dst=self.fixture(base,True);e=json.loads((BOARD_ROOT/'main/evidence.json').read_text());e['inputs']['hw/boards/main.py']='0'*64
   (dst/'evidence.json').write_text(json.dumps(e))
   with patch.object(fit.subprocess,'run',side_effect=AssertionError('generator forbidden')):
    with self.assertRaisesRegex(SystemExit,'stale board evidence'):fit.discover(base)
 def test_changed_actual_artifact_never_runs_fit_or_generator(self):
  with tempfile.TemporaryDirectory(prefix='cupc8-mech-artifact-') as temp:
   base=Path(temp);dst=self.fixture(base,True);e=json.loads((BOARD_ROOT/'main/evidence.json').read_text());e['artifacts']['main.kicad_pcb']='0'*64
   (dst/'evidence.json').write_text(json.dumps(e))
   with patch.object(fit.subprocess,'run',side_effect=AssertionError('generator forbidden')):
    with self.assertRaisesRegex(SystemExit,'changed or missing board artifacts'):fit.discover(base)
if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
