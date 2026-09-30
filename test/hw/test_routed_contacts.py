#!/usr/bin/env python3
"""Physical zero-clearance copper contacts; missing copper never becomes a route."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'hw/si'))
import pcbnew as p
from ibis_bus import routed_distances,routed_connectivity
mm=p.FromMM
vec=lambda x,y:p.VECTOR2I(mm(x),mm(y))
class Contacts(unittest.TestCase):
 def board(self,net='/SIG'):
  b=p.BOARD();b.SetCopperLayerCount(2);n=p.NETINFO_ITEM(b,net);b.Add(n)
  for ref,x,y in [('A',0,0),('B',4,0)]:
   f=p.FOOTPRINT(b);f.SetReference(ref);f.SetPosition(vec(x,y));b.Add(f)
   q=p.PAD(f);q.SetNumber('1');q.SetShape(p.PAD_SHAPE_RECT);q.SetSize(vec(.4,.4));q.SetPosition(vec(x,y));q.SetAttribute(p.PAD_ATTRIB_SMD);ls=p.LSET();ls.AddLayer(p.F_Cu);q.SetLayerSet(ls);q.SetNet(n);f.Add(q)
  return b,n
 def track(self,b,n,a,c,width=.1,layer=p.F_Cu):
  t=p.PCB_TRACK(b);t.SetStart(vec(*a));t.SetEnd(vec(*c));t.SetWidth(mm(width));t.SetLayer(layer);t.SetNet(n);b.Add(t)
 def result(self,b,reach=False):
  return routed_distances('unused',b.FindFootprintByReference('A').Pads()[0].GetNetname(),('A','1'),[('B','1')],loaded_board=b,parsed_tree=[],pad_reach=reach)['B.1']
 def filled(self,b,n,outlines,hole=None):
  q=p.SHAPE_POLY_SET()
  for outline in outlines:
   q.NewOutline()
   for x,y in outline:q.Append(mm(x),mm(y))
  if hole:
   q.NewHole(0)
   for x,y in hole:q.Append(mm(x),mm(y),0,0)
  z=p.ZONE(b);z.SetNet(n);z.SetLayer(p.F_Cu);z.SetIsFilled(True);z.SetFilledPolysList(p.F_Cu,q);b.Add(z);return z
 def test_existing_endpoint_length(self):
  b,n=self.board();self.track(b,n,(0,0),(1,1));self.track(b,n,(1,1),(4,0));self.assertEqual(self.result(b),round(2**.5+10**.5,3))
 def test_pad_interior_touch(self):
  b,n=self.board();self.track(b,n,(.15,0),(3.85,0));self.assertEqual(self.result(b),4)
 def test_pad_clear_gap_reach_cannot_inflate(self):
  b,n=self.board();self.track(b,n,(.2501,0),(4,0));self.assertIsNone(self.result(b,True))
 def test_t_join_and_gap(self):
  b,n=self.board();self.track(b,n,(0,0),(2,0));self.track(b,n,(1,-1),(1,1));self.track(b,n,(1,1),(4,0));self.assertIsNotNone(self.result(b))
  b,n=self.board();self.track(b,n,(0,0),(2,0));self.track(b,n,(1,.1001),(1,1));self.track(b,n,(1,1),(4,0));self.assertIsNone(self.result(b))
 def test_changed_receiver_net_rejected(self):
  b,n=self.board();self.track(b,n,(0,0),(4,0));other=p.NETINFO_ITEM(b,'/OTHER');b.Add(other);b.FindFootprintByReference('B').Pads()[0].SetNet(other)
  with self.assertRaises(ValueError):self.result(b)
 def test_actual_ground_fill_and_empty_zone(self):
  b,n=self.board('/GND');self.filled(b,n,[[(-1,-1),(5,-1),(5,1),(-1,1)]]);self.assertEqual(self.result(b),0)
  b,n=self.board('/GND');z=p.ZONE(b);z.SetNet(n);z.SetLayer(p.F_Cu);b.Add(z);self.assertIsNone(self.result(b))
 def test_disconnected_filled_islands(self):
  b,n=self.board('/GND');self.filled(b,n,[[(-1,-1),(1,-1),(1,1),(-1,1)],[(3,-1),(5,-1),(5,1),(3,1)]]);self.assertIsNone(self.result(b))
 def test_ground_fill_hole(self):
  b,n=self.board('/GND');self.filled(b,n,[[(-1,-1),(5,-1),(5,1),(-1,1)]],[(3.5,-.5),(3.5,.5),(4.5,.5),(4.5,-.5)]);self.assertIsNone(self.result(b))
 def test_signal_pour_cannot_supply_trace_length(self):
  b,n=self.board();self.filled(b,n,[[(-1,-1),(5,-1),(5,1),(-1,1)]]);self.assertIsNone(self.result(b))
 def continuity(self,b):
  return routed_connectivity('unused',b.FindFootprintByReference('A').Pads()[0].GetNetname(),('A','1'),[('B','1')],loaded_board=b,parsed_tree=[])['B.1']
 def test_supply_fragment_continuity_only(self):
  b,n=self.board('/+3V3');self.filled(b,n,[[(-1,-1),(5,-1),(5,1),(-1,1)]]);self.assertTrue(self.continuity(b));self.assertIsNone(self.result(b))
 def test_supply_islands_and_holes_disconnected(self):
  b,n=self.board('/+3V3');self.filled(b,n,[[(-1,-1),(1,-1),(1,1),(-1,1)],[(3,-1),(5,-1),(5,1),(3,1)]]);self.assertFalse(self.continuity(b))
  b,n=self.board('/+3V3');self.filled(b,n,[[(-1,-1),(5,-1),(5,1),(-1,1)]],[(3.5,-.5),(3.5,.5),(4.5,.5),(4.5,-.5)]);self.assertFalse(self.continuity(b))
 def test_supply_unfilled_and_wrong_net_reject(self):
  b,n=self.board('/+3V3');z=p.ZONE(b);z.SetNet(n);z.SetLayer(p.F_Cu);b.Add(z);self.assertFalse(self.continuity(b))
  other=p.NETINFO_ITEM(b,'/OTHER');b.Add(other);self.filled(b,other,[[(-1,-1),(5,-1),(5,1),(-1,1)]]);self.assertFalse(self.continuity(b))
  b.FindFootprintByReference('B').Pads()[0].SetNet(other)
  with self.assertRaises(ValueError):self.continuity(b)
 def test_supply_fragment_100nm_gap_is_not_contact(self):
  b,n=self.board('/+3V3');self.filled(b,n,[[(-1,-1),(3.7999,-1),(3.7999,1),(-1,1)]]);self.assertFalse(self.continuity(b))
if __name__=='__main__':unittest.main()
