from pathlib import Path
import tempfile,unittest,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'hw/tools'))
import pcbnew
import silk_glyph_coverage as proof

class GlyphTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name)
  self.board=pcbnew.BOARD();self.board.GetDesignSettings().m_MinSilkTextHeight=pcbnew.FromMM(.8)
  self.text=pcbnew.PCB_TEXT(self.board);self.text.SetText('H51');self.text.SetPosition(pcbnew.VECTOR2I(10000000,10000000));self.text.SetTextSize(pcbnew.VECTOR2I(1000000,1000000));self.text.SetTextThickness(150000);self.text.SetLayer(pcbnew.F_SilkS);self.board.Add(self.text)
 def export(self):
  pcb=self.out/'fixture.kicad_pcb';pcbnew.SaveBoard(str(pcb),self.board)
  subprocess.run(['kicad-cli','pcb','export','gerbers','--layers','F.SilkS,B.SilkS','-o',str(self.out)+'/',str(pcb)],check=True,capture_output=True)
  return sorted(self.out.glob('*Silkscreen.g*'))
 def certify(self,paths):return proof.certify(self.board,paths)
 def test_real_export_measures_height_instead_of_nominal_only(self):
  result=self.certify(self.export());self.assertEqual(result['text_count'],1);self.assertAlmostEqual(result['texts'][0]['height_mm'],1,places=5)
 def test_rotated_mirrored_back_text_at_minimum_is_measured(self):
  self.text.SetLayer(pcbnew.B_SilkS);self.text.SetMirrored(True);self.text.SetTextAngle(pcbnew.EDA_ANGLE(37,pcbnew.DEGREES_T));self.text.SetTextSize(pcbnew.VECTOR2I(800000,800000))
  self.assertAlmostEqual(self.certify(self.export())['texts'][0]['height_mm'],.8,places=5)
 def test_actual_smaller_export_fails_against_unchanged_source_identity(self):
  self.text.SetTextSize(pcbnew.VECTOR2I(1000000,600000));paths=self.export();self.text.SetTextSize(pcbnew.VECTOR2I(1000000,1000000))
  with self.assertRaisesRegex(ValueError,'height|missing'):self.certify(paths)
 def test_actual_moved_export_cannot_supply_original_identity(self):
  self.text.SetPosition(pcbnew.VECTOR2I(30000000,10000000));paths=self.export();self.text.SetPosition(pcbnew.VECTOR2I(10000000,10000000))
  with self.assertRaisesRegex(ValueError,'missing'):self.certify(paths)
 def test_missing_stroke_rejected_even_with_correct_aperture_and_nominal_height(self):
  paths=self.export();path=next(p for p in paths if p.suffix=='.gto');lines=path.read_text().splitlines();index=next(i for i,line in enumerate(lines) if line.endswith('D01*') and line.startswith('X'));del lines[index];path.write_text('\n'.join(lines)+'\n')
  with self.assertRaisesRegex(ValueError,'missing'):self.certify(paths)
 def test_horizontal_only_glyph_does_not_invent_vertical_measurement(self):
  self.text.SetText('-')
  with self.assertRaisesRegex(ValueError,'unmeasurable'):self.certify(self.export())
 def test_overlapping_duplicate_text_is_ambiguous(self):
  other=pcbnew.PCB_TEXT(self.board);other.SetText('H51');other.SetLayer(pcbnew.F_SilkS);other.SetPosition(self.text.GetPosition());other.SetTextSize(self.text.GetTextSize());other.SetTextThickness(150000);self.board.Add(other)
  with self.assertRaisesRegex(ValueError,'ambiguous|same plotted'):self.certify(self.export())
 def test_unsupported_style_fails_closed(self):
  self.text.SetItalic(True)
  with self.assertRaisesRegex(ValueError,'unsupported'):self.certify(self.export())

if __name__=='__main__':unittest.main()
