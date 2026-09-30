from pathlib import Path
import sys,tempfile,unittest,json,importlib.util
ROOT=Path(__file__).resolve().parents[2]
if not (ROOT/'hw/tools').is_dir():ROOT=Path('/home/depmod/code/cupc8')
sys.path.insert(0,str(ROOT/'hw/tools'));sys.path.insert(0,str(ROOT/'hw/boards'))
import pcbnew,kicadgen as kg,route_seed as seed
spec=importlib.util.spec_from_file_location('fixture',ROOT/'test/hw/test_main_seeded.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
def back_layers():
 layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);return layers
class SeedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'test-routed.kicad_pcb';self.seed=Path(self.tmp.name)/'seed.json'
  self.board=fixture.board([('A','N',10,10),('B','N',20,10)],tracks=[('N',pcbnew.F_Cu,10,10,20,10,.2)])
  pcbnew.SaveBoard(str(self.path),self.board)
  self.args=dict(board_name='test',pour_nets=('G',),post_route_contract='test-v1')
  seed.extract(self.path,self.seed,origin_note='router stage completed; stock blocked; no receipt',**self.args)
 def target(self):
  b=pcbnew.LoadBoard(str(self.path))
  for t in seed.items(b):b.Remove(t)
  return b
 def test_reuses_actual_route_and_marks_incomplete_origin(self):
  b=self.target();result=seed.apply(b,self.seed,**self.args)
  self.assertEqual(seed.copper(b),seed.copper(self.board));self.assertEqual(result['origin_state'],'pipeline-incomplete');self.assertTrue(result['requires_full_pipeline'])
  self.assertEqual(result['origin_sha256'],seed.sha(self.path));self.assertFalse(seed.load(self.seed)['origin']['manufacturing_pass']);self.assertEqual(kg.open_escapes(b,['N']),[])
 def test_post_route_verification_rejects_changed_copper(self):
  b=self.target();seed.apply(b,self.seed,**self.args);seed.verify_installed(b,self.seed)
  seed.items(b)[0].SetWidth(150000)
  with self.assertRaisesRegex(ValueError,'installed full-route copper changed'):seed.verify_installed(b,self.seed)
 def test_manual_candidate_records_real_origin_and_requires_fresh_pipeline(self):
  candidate=self.path.with_name('manual-local-repair.kicad_pcb');candidate.write_bytes(self.path.read_bytes())
  with self.assertRaisesRegex(ValueError,'pipeline routed-stage'):seed.extract(candidate,self.seed,origin_note='manual local repair',**self.args)
  seed.extract(candidate,self.seed,origin_note='manual local repair; no pipeline or receipt',design_candidate=True,**self.args)
  origin=seed.load(self.seed)['origin'];self.assertEqual(origin['file'],candidate.name);self.assertEqual(origin['sha256'],seed.sha(candidate));self.assertEqual(origin['state'],'design-candidate');self.assertIsNone(origin['receipt_sha256']);self.assertFalse(origin['manufacturing_pass'])
  result=seed.apply(self.target(),self.seed,**self.args);self.assertTrue(result['requires_full_pipeline']);self.assertEqual(result['origin_state'],'design-candidate')
  with self.assertRaisesRegex(ValueError,'cannot carry a completed receipt'):seed.extract(candidate,self.seed,origin_note='manual',design_candidate=True,completed_build=candidate.parent,**self.args)
  origin['receipt_sha256']='a'*64;p=seed.load(self.seed);p['origin']=origin;p['payload_sha256']=seed.digest({k:v for k,v in p.items() if k!='payload_sha256'});self.seed.write_text(json.dumps(p))
  with self.assertRaisesRegex(ValueError,'cannot carry a completed receipt'):seed.load(self.seed)
 def test_manual_candidate_rejects_open_nonpour_connections(self):
  candidate=self.path.with_name('manual-open.kicad_pcb');b=self.target();pcbnew.SaveBoard(str(candidate),b);self.seed.unlink()
  with self.assertRaisesRegex(ValueError,'origin non-pour'):seed.extract(candidate,self.seed,origin_note='unfinished local repair',design_candidate=True,**self.args)
  self.assertFalse(self.seed.exists())
 def test_placement_normalization_accepts_only_declared_exact_states(self):
  b=self.target();fp=b.FindFootprintByReference('A')
  seed.normalize_placement(b,'A',(10000000,10000000),(10000001,10000000))
  self.assertEqual(fp.GetPosition().x,10000001)
  seed.normalize_placement(b,'A',(10000000,10000000),(10000001,10000000))
  fp.SetPosition(pcbnew.VECTOR2I(10000002,10000000))
  with self.assertRaisesRegex(ValueError,'normalization: moved'):seed.normalize_placement(b,'A',(10000000,10000000),(10000001,10000000))
 def test_silk_changes_and_new_uuids_do_not_change_route_guards(self):
  b=self.target();word=pcbnew.PCB_TEXT(b);word.SetText('NEW LOGO');word.SetLayer(pcbnew.F_SilkS);b.Add(word)
  fp=next(iter(b.GetFootprints()));fp.Reference().SetTextSize(pcbnew.VECTOR2I(1200000,1200000))
  seed.apply(b,self.seed,**self.args);self.assertEqual(seed.copper(b),seed.copper(self.board))
 def test_pad_width_offset_shape_layer_drill_and_pinmap_mutations_reject(self):
  for change in [lambda p:p.SetSize(pcbnew.VECTOR2I(700000,800000)),lambda p:p.SetOffset(pcbnew.VECTOR2I(1000,0)),lambda p:p.SetShape(pcbnew.PAD_SHAPE_OVAL),lambda p:p.SetLayerSet(back_layers()),lambda p:p.SetDrillSize(pcbnew.VECTOR2I(300000,300000)),lambda p:p.SetNumber('2')]:
   b=self.target();p=next(iter(next(iter(b.GetFootprints())).Pads()));change(p)
   with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
   self.assertEqual(len(seed.items(b)),0)
 def test_moved_footprint_and_net_mutation_reject(self):
  b=self.target();fp=next(iter(b.GetFootprints()));fp.SetPosition(pcbnew.VECTOR2I(11000000,10000000))
  with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
  b=self.target();net=pcbnew.NETINFO_ITEM(b,'M');b.Add(net);next(iter(next(iter(b.GetFootprints())).Pads())).SetNet(net)
  with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
 def test_same_bounds_roundrect_radius_and_exact_orientation_reject(self):
  for fp in self.board.GetFootprints():
   for p in fp.Pads():p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);p.SetRoundRectRadiusRatio(.1)
  pcbnew.SaveBoard(str(self.path),self.board);seed.extract(self.path,self.seed,origin_note='roundrect route stage only',**self.args)
  for change in (lambda p:p.SetRoundRectRadiusRatio(.2),lambda p:p.SetOrientationDegrees(.123456)):
   b=self.target();p=next(iter(next(iter(b.GetFootprints())).Pads()));change(p)
   with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
 def test_board_outline_and_stackup_mutations_reject(self):
  b=self.target();line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetStart(pcbnew.VECTOR2I(0,0));line.SetEnd(pcbnew.VECTOR2I(1000000,0));line.SetLayer(pcbnew.Edge_Cuts);b.Add(line)
  with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
  b=self.target();b.SetCopperLayerCount(2)
  with self.assertRaisesRegex(ValueError,'geometry incompatible'):seed.apply(b,self.seed,**self.args)
 def test_open_copper_even_with_updated_body_hash_rejects_without_mutation(self):
  payload=seed.load(self.seed);payload['body']['copper'][0][5]=15000000;payload['body_sha256']=seed.digest(payload['body']);payload['payload_sha256']=seed.digest({k:v for k,v in payload.items() if k!='payload_sha256'});self.seed.write_text(json.dumps(payload));b=self.target()
  with self.assertRaisesRegex(ValueError,'route incomplete'):seed.apply(b,self.seed,**self.args)
  self.assertEqual(len(seed.items(b)),0)
 def test_corrupt_body_and_wrong_hook_contract_fail(self):
  payload=seed.load(self.seed);payload['body']['copper'][0][7]=123;self.seed.write_text(json.dumps(payload))
  with self.assertRaisesRegex(ValueError,'changed/truncated'):seed.apply(self.target(),self.seed,**self.args)
  seed.extract(self.path,self.seed,origin_note='incomplete',**self.args)
  with self.assertRaisesRegex(ValueError,'contract mismatch'):seed.apply(self.target(),self.seed,**(self.args|{'post_route_contract':'newphysicalfix'}))
 def test_incomplete_origin_cannot_claim_manufacturing_pass(self):
  p=seed.load(self.seed);p['origin']['manufacturing_pass']=True;p['payload_sha256']=seed.digest({k:v for k,v in p.items() if k!='payload_sha256'});self.seed.write_text(json.dumps(p))
  with self.assertRaisesRegex(ValueError,'origin state'):seed.load(self.seed)
 def test_source_open_is_rejected_and_no_seed_written(self):
  for t in seed.items(self.board):self.board.Remove(t)
  pcbnew.SaveBoard(str(self.path),self.board);self.seed.unlink()
  with self.assertRaisesRegex(ValueError,'origin non-pour'):seed.extract(self.path,self.seed,origin_note='incomplete',**self.args)
  self.assertFalse(self.seed.exists())
 def test_ground_is_not_implicitly_ignored(self):
  b=fixture.board([('A','G',10,10),('B','G',20,10)])
  self.assertEqual(seed.nonpour_open(b,()),['G']);self.assertEqual(seed.nonpour_open(b,('G',)),[])
 def test_via_diameter_drill_span_preserved(self):
  b=fixture.board([('A','N',10,10),('B','N',20,10)],tracks=[('N',pcbnew.F_Cu,10,10,15,10,.2),('N',pcbnew.B_Cu,15,10,20,10,.2)],vias=[('N',15,10)])
  # Move second pad to B.Cu so a throughvia is actually necessary.
  for fp in b.GetFootprints():
   if fp.GetReference()=='B':next(iter(fp.Pads())).SetLayerSet(back_layers())
  pcbnew.SaveBoard(str(self.path),b);seed.extract(self.path,self.seed,origin_note='route complete; pipeline incomplete',**self.args)
  target=self.target();seed.apply(target,self.seed,**self.args);self.assertEqual(seed.copper(target),seed.copper(b))
if __name__=='__main__':unittest.main()
