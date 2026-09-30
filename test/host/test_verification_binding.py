"""Synthetic report/source/receipt fixtures: never a manufacturing pass."""
import importlib.util,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'))
spec=importlib.util.spec_from_file_location('verification_binding',ROOT/'tools/verification_binding.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
import boardevidence
class Reports(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.tests=[{'id':'X','cmd':'true','kind':'static'}]
  # Fabricated small artifacts exercise the REAL content-bound validator;
  # test statuses are explicit synthetic fixtures, not actual gate results.
  for b in gate.BOARDS:
   for rel in boardevidence.inputs(b,ROOT):
    p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic input\n')
   out=self.root/'build/hw'/b;(out/'fab').mkdir(parents=True)
   for name in [b+x for x in ('.kicad_sch','.kicad_pcb','.kicad_pro','.net')]+['erc.json','drc.json',b+'-top.png',b+'-bottom.png','fab/bom.csv','fab/cpl.csv','fab/order.json','fab/board-F_Cu.gtl','fab/board.drl']:
    (out/name).write_text('synthetic artifact\n')
   (out/'pipeline-scope.json').write_text(json.dumps({'pipeline_mode':'live-stock-checked','live_stock_check':{'status':'passed'}}))
   boardevidence.record(b,out,boardevidence.inputs(b,self.root),2,root=self.root)
  log=self.root/'build/test/X.log';log.parent.mkdir(parents=True);log.write_text('synthetic explicit test result\n');self.log=log
  self.snapshot=gate.capture(self.root);assert all(x['validated']for x in self.snapshot['boards'].values())
  self.report={'results':[{'id':'X','status':'pass','log':'build/test/X.log','log_sha256':gate.sha(log)}],'binding':{'version':1,'full_gate_run':True,'before':self.snapshot,'after':self.snapshot,'commands':{'X':'true'}}}
 def issues(self):return gate.release_problems(self.root,self.report,self.tests)
 def test_consistent_synthetic_full_run(self):self.assertEqual(self.issues(),[])
 def test_legacy_or_filtered_report_rejected(self):
  self.assertTrue(gate.release_problems(self.root,{'results':self.report['results']},self.tests));self.report['binding']['full_gate_run']=False;self.assertTrue(self.issues())
 def test_declared_generated_outputs_do_not_change_source_binding(self):
  p=self.root/'kernel/kernel.rom';p.parent.mkdir(exist_ok=True);p.write_bytes(b'actual generated ROM fixture')
  q=self.root/'tools/sim';q.parent.mkdir(exist_ok=True);q.write_bytes(b'actual generated simulator fixture')
  self.assertEqual(gate.sources(self.root),self.snapshot['sources'])
 def test_changed_source_despite_restored_timestamp(self):
  p=self.root/'hw/boards/main.py';stamp=p.stat();p.write_text('different actual source\n');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns));self.assertTrue(any('stale' in p for p in self.issues()))
 def test_changed_package_artifact(self):
  (self.root/'build/hw/io/fab/cpl.csv').write_text('changed placement');self.assertTrue(any('io: missing/stale' in p for p in self.issues()))
 def test_changed_test_log_rejected(self):
  self.log.write_text('tampered pass log');self.assertTrue(any('X: missing or changed' in p for p in self.issues()))
 def test_fresh_valid_offline_packages_never_ready(self):
  out=self.root/'build/hw/wifi';(out/'pipeline-scope.json').write_text(json.dumps({'pipeline_mode':'development-offline','live_stock_check':{'status':'skipped'}}));boardevidence.record('wifi',out,boardevidence.inputs('wifi',self.root),2,root=self.root)
  snap=gate.capture(self.root);self.report['binding']['before']=self.report['binding']['after']=snap
  self.assertTrue(any('wifi: development/offline' in p for p in self.issues()))
 def test_changed_quantity_not_hidden_by_new_valid_receipt(self):
  out=self.root/'build/hw/main';boardevidence.record('main',out,boardevidence.inputs('main',self.root),3,root=self.root);snap=gate.capture(self.root);self.report['binding']['before']=self.report['binding']['after']=snap;self.assertTrue(any('main: required assembly quantity' in p for p in self.issues()))
 def test_midrun_change_or_new_catalogue_command_rejected(self):
  self.report['binding']['before']={};self.assertTrue(any('during verification' in p for p in self.issues()));self.report['binding']['before']=self.snapshot;self.tests[0]['cmd']='new-required-command';self.assertTrue(any('catalogue' in p for p in self.issues()))
 def test_required_failure_without_verification_row_rejected(self):
  self.tests[0]['vrow']='unlisted'
  for status in ('FAIL','pending','not run'):
   self.report['results'][0]['status']=status
   self.assertTrue(any('required non-hardware test is not passing' in p for p in self.issues()))
 def test_missing_required_command_rejected(self):
  self.tests[0].pop('cmd');self.report['binding']['commands']={'X':None}
  self.assertTrue(any('no implemented command' in p for p in self.issues()))
 def test_duplicate_catalogue_or_result_ids_rejected(self):
  self.tests.append(dict(self.tests[0],cmd='different command'))
  self.assertTrue(any('catalogue has duplicate' in p for p in self.issues()))
  self.tests.pop();self.report['results'].append(dict(self.report['results'][0],status='FAIL'))
  self.assertTrue(any('report has duplicate' in p for p in self.issues()))
 def test_changed_stable_order_policy_or_first_article_condition_rejected(self):
  for name in ('jlc-order-checklist.md','parts.md','first-article-plan.md'):
   p=self.root/'doc/hardware'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original acceptance/order policy')
   snap=gate.capture(self.root);self.report['binding']['before']=self.report['binding']['after']=snap
   stat=p.stat();p.write_text('changed acceptance/order policy');os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns))
   self.assertTrue(any('stale' in issue for issue in self.issues()))
 def test_make_verify_propagates_readiness_failure(self):
  fake=self.root/'fake-bin';fake.mkdir();py=fake/'python3';py.write_text('#!/bin/sh\ncase "$1" in tools/fabready.py) exit 1;; *) exit 0;; esac\n');py.chmod(0o755)
  result=subprocess.run(['make','-f',str(ROOT/'Makefile'),'verify','JOBS=1'],cwd=self.root,env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH']),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);self.assertNotEqual(result.returncode,0)
if __name__=='__main__':unittest.main()
