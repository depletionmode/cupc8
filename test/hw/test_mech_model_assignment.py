#!/usr/bin/env python3
"""A real exported connector must not be assigned to a coincident silk legend."""
import ast, math, unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
# Load only coordinate/assignment functions: the full module performs FreeCAD
# geometry work at import. The native STEP/solid replay is separate evidence.
tree=ast.parse((ROOT/'hw/mech/fc_check.py').read_text())
ns={'math':math,'Part':SimpleNamespace(makeCompound=lambda shapes: tuple(shapes))}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('step_xy','assign')],type_ignores=[]),'fc_check assignment','exec'),ns)
class ModelAssignment(unittest.TestCase):
 def footprints(self):
  # Genuine eInk J2 and G2 positions/anchors from the exported mechanical job.
  return [{'ref':'G2','side':'F','pos':[36.5,-39.6],'model_at':[]},
          {'ref':'J2','side':'F','pos':[36.5,-39.6],'model_at':[[36.5,39.6]]}]
 def test_native_connector_anchor_wins_over_coincident_legend(self):
  shape=object();pos=SimpleNamespace(x=36.5,y=39.6,z=1.595)
  for fps in (self.footprints(),list(reversed(self.footprints()))):
   parts=ns['assign']([(pos,shape)],fps,.755,'eink')
   self.assertEqual(set(parts),{'J2'});self.assertIs(parts['J2'],shape)
 def test_missing_model_remains_missing(self):
  self.assertEqual(ns['assign']([],self.footprints(),.755,'eink'),{})
 def test_wrong_origin_still_rejected(self):
  with self.assertRaisesRegex(SystemExit,'matches no footprint'):
   ns['assign']([(SimpleNamespace(x=36.52,y=39.6,z=1.595),object())],self.footprints(),.755,'eink')
 def test_real_geometric_distance_is_not_overridden(self):
  fps=self.footprints();fps[1]['model_at']=[[36.51,39.6]];fps[1]['pos']=[36.51,-39.6]
  parts=ns['assign']([(SimpleNamespace(x=36.5,y=39.6,z=1.595),object())],fps,.755,'eink')
  self.assertEqual(set(parts),{'G2'})
if __name__=='__main__':unittest.main()
