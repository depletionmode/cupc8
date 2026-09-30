from pathlib import Path
import sys,unittest
import pcbnew as p
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'))
from fillfeature import remove_rounding_islands, round_main_fills, round_board_fills

def polygon(points):
 q=p.SHAPE_POLY_SET();q.NewOutline()
 for x,y in points:q.Append(x,y)
 return q

class FillFeatures(unittest.TestCase):
 def test_unlisted_board_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'unqualified board'):round_board_fills(p.BOARD(),'unknown')
 def test_other_board_is_not_qualified(self):
  b=p.BOARD();b.SetCopperLayerCount(6);b.GetDesignSettings().m_TrackMinWidth=p.FromMM(.1)
  with self.assertRaisesRegex(ValueError,'qualified chipset layout'):round_main_fills(b)
 def test_unanchored_nanometre_triangle_removed(self):
  q=polygon([(0,0),(2,0),(0,2)])
  self.assertEqual(remove_rounding_islands(q,[],can_prove_single_zone=True),[(0,2.0)])
  self.assertEqual(q.OutlineCount(),0)
 def test_real_unanchored_copper_fails_without_removal(self):
  q=polygon([(0,0),(1000,0),(1000,1000),(0,1000)])
  with self.assertRaisesRegex(ValueError,'nanometre-island proof'):remove_rounding_islands(q,[],can_prove_single_zone=True)
  self.assertEqual(q.OutlineCount(),1)
 def test_overlap_with_other_zones_needs_graph_proof(self):
  q=polygon([(0,0),(2,0),(0,2)])
  with self.assertRaisesRegex(ValueError,'nanometre-island proof'):remove_rounding_islands(q,[],can_prove_single_zone=False)
  self.assertEqual(q.OutlineCount(),1)
 def test_anchored_fragment_never_removed(self):
  q=polygon([(0,0),(2,0),(0,2)]);shape=p.SHAPE_CIRCLE(p.VECTOR2I(0,0),1)
  self.assertEqual(remove_rounding_islands(q,[(shape.BBox(),shape)],can_prove_single_zone=True),[])
  self.assertEqual(q.OutlineCount(),1)
 def test_round_opening_preserves_hole_after_fracture(self):
  q=polygon([(0,0),(1000000,0),(1000000,1000000),(0,1000000)]);hole=q.NewHole()
  for x,y in [(300000,300000),(300000,700000),(700000,700000),(700000,300000)]:q.Append(x,y,-1,hole)
  q.Fracture();q.Unfracture();q.Deflate(60000,p.CORNER_STRATEGY_ROUND_ALL_CORNERS,2);q.Inflate(60000,p.CORNER_STRATEGY_ROUND_ALL_CORNERS,2);q.Fracture()
  self.assertFalse(q.Contains(p.VECTOR2I(500000,500000)));self.assertTrue(q.Contains(p.VECTOR2I(100000,500000)))
 def test_narrow_bridge_is_separated_and_needs_final_connectivity_check(self):
  q=polygon([(0,0),(500000,0),(500000,460000),(1000000,460000),(1000000,0),(1500000,0),(1500000,1000000),(1000000,1000000),(1000000,540000),(500000,540000),(500000,1000000),(0,1000000)])
  q.Deflate(60000,p.CORNER_STRATEGY_ROUND_ALL_CORNERS,2);q.Inflate(60000,p.CORNER_STRATEGY_ROUND_ALL_CORNERS,2)
  self.assertGreater(q.OutlineCount(),1);self.assertFalse(q.Contains(p.VECTOR2I(750000,500000)))

if __name__ == '__main__':unittest.main()
