"""Exercise manufacturing gates against real parsed neck geometry."""
from pathlib import Path
import sys,tempfile,unittest,importlib.util
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hw/tools'));sys.path.insert(0,str(ROOT/'tools'))
import fabcheck
spec=importlib.util.spec_from_file_location('neck_fixture',ROOT/'test/hw/test_fab_neck_coverage.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
class Integration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.board=fabcheck.pcbnew.BOARD();self.board.SetCopperLayerCount(2)
  self.board.GetDesignSettings().m_TrackMinWidth=fabcheck.pcbnew.FromMM(.1)
  self.board.GetDesignSettings().m_MinSilkTextHeight=fabcheck.pcbnew.FromMM(.8)
  self.copper=[self.root/'test.gtl',self.root/'test.gbl'];self.silk=[self.root/'test.gto',self.root/'test.gbo']
  for p in self.copper:p.write_text(fixture.plot(fixture.dumbbell(100000)))
  for p in self.silk:p.write_text(fixture.plot(fixture.dumbbell(150000),True))
  self.silk[1].write_text(self.silk[1].read_text().replace('Legend,Top','Legend,Bot'))
 def test_real_complete_regions_are_proved(self):
  rows=fabcheck.filled_region_checks(self.board,self.copper,self.silk)
  self.assertEqual(len(rows),4);self.assertTrue(all(r['complete_for_filled_regions'] for r in rows.values()))
 def test_real_thin_copper_rejected_with_layer_and_region(self):
  self.copper[0].write_text(fixture.plot(fixture.dumbbell(80000)))
  with self.assertRaisesRegex(ValueError,r'test.gtl: 0/1 regions proved.*region lines'):fabcheck.filled_region_checks(self.board,self.copper,self.silk)
 def test_real_thin_silk_rejected(self):
  self.silk[0].write_text(fixture.plot(fixture.dumbbell(80000),True))
  with self.assertRaisesRegex(ValueError,'test.gto: 0/1 regions proved'):fabcheck.filled_region_checks(self.board,self.copper,self.silk)
 def test_nominal_text_pass_needs_actual_matching_glyphs(self):
  word=fabcheck.pcbnew.PCB_TEXT(self.board);word.SetText('H51');word.SetLayer(fabcheck.pcbnew.F_SilkS);word.SetTextSize(fabcheck.pcbnew.VECTOR2I(1000000,1000000));self.board.Add(word)
  with self.assertRaisesRegex(ValueError,'missing'):fabcheck.require_complete_plotted_drc(.1,self.board,self.copper,self.silk)
 def test_complete_empty_text_inventory_returns_independent_proof(self):
  proof=fabcheck.require_complete_plotted_drc(.1,self.board,self.copper,self.silk)
  self.assertTrue(proof['glyphs']['complete']);self.assertEqual(proof['glyphs']['text_count'],0);self.assertEqual(len(proof['glyphs']['font_ascii_sha256']),64)
 def test_short_source_text_rejected(self):
  word=fabcheck.pcbnew.PCB_TEXT(self.board);word.SetText('bad');word.SetLayer(fabcheck.pcbnew.F_SilkS);word.SetTextSize(fabcheck.pcbnew.VECTOR2I(fabcheck.pcbnew.FromMM(.7),fabcheck.pcbnew.FromMM(.7)));self.board.Add(word)
  with self.assertRaisesRegex(ValueError,'nominal silk text height'):fabcheck.require_complete_plotted_drc(.1,self.board,self.copper,self.silk)
 def test_positive_mask_rule_and_complete_inputs_required(self):
  with self.assertRaisesRegex(ValueError,'positive solder-mask web'):fabcheck.require_complete_plotted_drc(0,self.board,self.copper,self.silk)
  with self.assertRaisesRegex(ValueError,'parity-bound'):fabcheck.require_complete_plotted_drc(.1)
  with self.assertRaisesRegex(ValueError,'all copper'):fabcheck.require_complete_plotted_drc(.1,self.board,self.copper[:1],self.silk)
 def test_corrupt_layer_fails_closed(self):
  self.silk[0].write_text('not a Gerber')
  with self.assertRaises(ValueError):fabcheck.filled_region_checks(self.board,self.copper,self.silk)
if __name__=='__main__':unittest.main()
