"""Actual generated Main netlist plus denied CS termination counterexamples."""
from pathlib import Path
import copy, importlib.util, sys, unittest
from unittest.mock import patch
import yaml
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'))
candidate=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'hw/tools/pincheck.py'
spec=importlib.util.spec_from_file_location('candidate_pincheck',candidate)
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p);p.ROOT=str(ROOT);p.DOCS=str(ROOT/'doc/hardware')
NET=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'build/hw/main/main.net'
class MainCS(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=p.read_netlist(NET);cls.pins=yaml.safe_load((ROOT/'hw/pins.yaml').read_text())
 def check(self,data):
  p.errors.clear()
  with patch.object(p,'read_netlist',return_value=data): count=p.check_mainboard(self.pins,str(NET))
  return count,list(p.errors)
 def test_actual_main_all_contacts_pass(self):
  count,errors=self.check(copy.deepcopy(self.data));self.assertEqual(count,381);self.assertEqual(errors,[])
 def test_legacy_policy_reproduces_six_failures(self):
  with patch.object(p,'approved_main_cs68',return_value=False):
   count,errors=self.check(copy.deepcopy(self.data))
  self.assertEqual(count,381);self.assertEqual(len(errors),6)
  self.assertTrue(all('CS_n' in error for error in errors))
 def test_six_actual_authorized_branches(self):
  c,n,_=self.data
  for i in range(37,43):self.assertTrue(p.approved_main_cs68('R'+str(i),c,n))
 def mutate_and_reject(self,mutation):
  data=copy.deepcopy(self.data);mutation(*data)
  self.assertFalse(p.approved_main_cs68('R37',data[0],data[1]))
  self.assertTrue(any('CS_n' in e for e in self.check(data)[1]))
 def test_wrong_value(self):self.mutate_and_reject(lambda c,n,f:c.__setitem__('R37',('Device','R','69')))
 def test_wrong_reference(self):
  def change(c,n,f):
   c['R137']=c.pop('R37')
   for pin in ('1','2'):n[('R137',pin)]=n.pop(('R37',pin))
  self.mutate_and_reject(change)
 def test_wrong_fpga_numeric_pin(self):self.mutate_and_reject(lambda c,n,f:n.__setitem__(('U7','34'),'BROKEN_CS'))
 def test_wrong_socket_numeric_pin(self):self.mutate_and_reject(lambda c,n,f:n.__setitem__(('J11','A14'),'BROKEN_CS'))
 def test_swapped_slot(self):
  def change(c,n,f):n[('R37','2')],n[('R38','2')]=n[('R38','2')],n[('R37','2')]
  self.mutate_and_reject(change)
 def test_unknown_load(self):self.mutate_and_reject(lambda c,n,f:n.__setitem__(('U7','1'),'SPI_nCS0_SRC'))
 def test_missing_testpoint(self):self.mutate_and_reject(lambda c,n,f:n.pop(('TP59','1')))
 def test_no_generic_68_allowance(self):
  c,n,_=copy.deepcopy(self.data);c['R999']=('Device','R','68');n[('R999','1')]='OTHER_A';n[('R999','2')]='OTHER_B'
  self.assertFalse(p.approved_main_cs68('R999',c,n))
if __name__=='__main__':unittest.main(argv=[sys.argv[0]])
