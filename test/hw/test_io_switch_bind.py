#!/usr/bin/env python3
"""Reject actual fitted switch source and behavioral-model mismatches."""
from pathlib import Path
import copy,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'hw/power'),str(ROOT/'hw/cosim')]
import io_switch_bind as b
from netlist import read
class Binding(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=read(Path(sys.argv[1])) if len(sys.argv)>1 else read(ROOT/'build/hw/io/io.net')
 def reject(self,mutation):
  c=copy.deepcopy(self.original);mutation(c)
  with self.assertRaises(ValueError):b.topology(c)
 def test_actual_topology(self):b.topology(self.original)
 def test_latchoff_family(self):self.reject(lambda c:c.components.__setitem__('U5',('TPS2553DBVR',('jlc','TPS2553DBVR'))))
 def test_ilim_resistor(self):self.reject(lambda c:c.components.__setitem__('R10',('49k9',('Device','R'))))
 def test_local_input_cap(self):self.reject(lambda c:c.components.__setitem__('C25',('100n',('Device','C'))))
 def test_port_bulk(self):self.reject(lambda c:c.components.__setitem__('C21',('10u',('Device','C'))))
 def test_fault_pullup_value(self):self.reject(lambda c:c.components.__setitem__('R12',('100k',('Device','R'))))
 def test_enable_pulldown_value(self):self.reject(lambda c:c.components.__setitem__('R11',('10k',('Device','R'))))
 def test_fault_supply(self):self.reject(lambda c:c.pins.__setitem__(('R12','1'),'/VBUS'))
 def test_control_gpio(self):self.reject(lambda c:c.pin_names.__setitem__(('U1','9'),'GPIO8'))
 def test_switch_pinmap(self):self.reject(lambda c:c.pin_names.__setitem__(('U5','4'),'EN'))
 def test_unknown_ilim_load(self):self.reject(lambda c:c.nets.__setitem__('/ILIM',c.nets['/ILIM']+(('U1','10'),)))
 def test_unknown_port_load(self):self.reject(lambda c:c.nets.__setitem__('/VBUS',c.nets['/VBUS']+(('U1','10'),)))
 def test_cap_return(self):self.reject(lambda c:c.pins.__setitem__(('C25','2'),'/3V3'))
 def test_stale_model_current(self):
  with patch.object(b.model,'R_ILIM',49900):
   with self.assertRaises(ValueError):b.topology(self.original)
 def test_stale_model_inductance(self):
  with patch.object(b.model,'L_IN',2e-9):
   with self.assertRaises(ValueError):b.topology(self.original)
 def test_stale_model_cap(self):
  with patch.object(b.model,'C_IN_LOCAL',1e-7):
   with self.assertRaises(ValueError):b.topology(self.original)
if __name__=='__main__':
 path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'build/hw/io/io.net'
 Binding.original=read(path)
 Binding.setUpClass=classmethod(lambda cls:None)
 unittest.main(argv=[sys.argv[0]])
