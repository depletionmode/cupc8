#!/usr/bin/env python3
"""Real emitted circuits and native-pad opens for the fitted SPI abstraction."""
import copy,sys,unittest,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'hw/cosim'),str(ROOT/'hw/si')]
from netlist import read
from slot_spi import network,routed,main_select,main_bias
import pcbnew
BOARDROOT=Path(sys.argv.pop(1)).resolve() if len(sys.argv)>1 else ROOT/'build/hw'

class ActualSlotNetwork(unittest.TestCase):
 def circuit(self,k):return read(BOARDROOT/k/(k+'.net'))
 def test_all_fitted_source_networks(self):
  for k in ('gpu','io','storage','eink','wifi'):
   with self.subTest(card=k):self.assertGreaterEqual(len(network(self.circuit(k),k)['legs']),24)
 def test_series_resistor_value_and_numeric_pin_swap(self):
  for k,r in (('gpu','R62'),('io','R63'),('storage','R64'),('eink','R65'),('wifi','R68'),('wifi','R66')):
   for mode in ('wrongvalue','swappedpins'):
    with self.subTest(card=k,ref=r,mutation=mode):
     c=self.circuit(k)
     if mode=='wrongvalue':c.components[r]=('68',('Device','R'))
     else:c.pins[r,'1'],c.pins[r,'2']=c.pins[r,'2'],c.pins[r,'1']
     with self.assertRaises(ValueError):network(c,k)
 def test_missing_or_wrong_capacitor(self):
  for k,refs in (('gpu',('C60','C61','C62','C63')),('wifi',('C60','C61','C62','C63','C64','C65','C66','C67','C68','C69'))):
   for r in refs:
    with self.subTest(card=k,ref=r):
     c=self.circuit(k);del c.components[r]
     with self.assertRaises(ValueError):network(c,k)
     c=self.circuit(k);c.components[r]=('47p',('Device','C'))
     with self.assertRaises(ValueError):network(c,k)
 def test_wrong_oe_part_pin_and_ground(self):
  for k,r in (('gpu','U4'),('wifi','U3'),('wifi','U4'),('wifi','U5'),('wifi','U6')):
   for mode in ('part','oe','ground'):
    with self.subTest(card=k,ref=r,mutation=mode):
     c=self.circuit(k)
     if mode=='part':c.components[r]=('SN74AHC1G125DCKR',('74xGxx','74AHC1G125'))
     else:c.pins[r,'1' if mode=='oe' else '3']='/MISO'
     with self.assertRaises(ValueError):network(c,k)
 def test_actual_wifi_cap_series_branches(self):
  baseline=self.circuit('wifi')
  if not {'R69','R70'}.intersection(baseline.components):
   self.skipTest('Historical direct-cap WiFi topology; output damping branch absent')
  for r,cap in (('R69','C61'),('R70','C64')):
   for mode in ('missing','wrongvalue','swappedpins','wrongcapnet'):
    with self.subTest(ref=r,mutation=mode):
     c=self.circuit('wifi')
     if mode=='missing':del c.components[r]
     elif mode=='wrongvalue':c.components[r]=('220',('Device','R'))
     elif mode=='swappedpins':c.pins[r,'1'],c.pins[r,'2']=c.pins[r,'2'],c.pins[r,'1']
     else:c.pins[cap,'1']=c.pins[r,'1']
     with self.assertRaises(ValueError):network(c,'wifi')
 def test_exact_selected_wifi_output_values_and_supplier_identity(self):
  expected={'R63':('270','C25099'),'R65':('270','C25099'),
            'R69':('15','C25083'),'R70':('15','C25083')}
  baseline=self.circuit('wifi')
  for ref,(value,sku) in expected.items():
   with self.subTest(ref=ref):
    self.assertEqual(baseline.components[ref],(value,('Device','R')))
    self.assertEqual(baseline.lcsc[ref],sku)
    for mode in ('wrongvalue','wrongSKU','missing','swappedpins'):
     c=self.circuit('wifi')
     if mode=='wrongvalue':c.components[ref]=('220' if value=='270' else '10',('Device','R'))
     elif mode=='wrongSKU':c.lcsc[ref]='C25091' if sku=='C25099' else 'C25077'
     elif mode=='missing':del c.components[ref]
     else:c.pins[ref,'1'],c.pins[ref,'2']=c.pins[ref,'2'],c.pins[ref,'1']
     with self.assertRaises(ValueError):network(c,'wifi')
 def test_actual_main_series_and_low_idle_bias(self):
  c=self.circuit('main');self.assertEqual(main_bias(c),0)
  for slot in range(1,7):self.assertEqual(main_select(c,slot),f'R{36+slot}')
  for ref in ('R37','R42','R107','R109'):
   with self.subTest(ref=ref):
    c=self.circuit('main');c.components[ref]=('33',('Device','R'))
    with self.assertRaises(ValueError):main_bias(c) if ref in ('R107','R109') else main_select(c,1 if ref=='R37' else 6)
  c=self.circuit('main');c.pins['U7','34']='/SPI_nCS1_SRC'
  with self.assertRaises(ValueError):main_select(c,1)
  c=self.circuit('main');c.pins['R109','2']='/+3V3'
  with self.assertRaises(ValueError):main_bias(c)
 def test_actual_copper_baselines_and_source_pad_opens(self):
  # Move only one physical launch pad. The emitted source is untouched; native
  # geometry must expose the open, including capacitor and active-buffer legs.
  cases=(('gpu','U1','4','sck'),('gpu','U4','1','enable'),
         ('wifi','U5','2','sck'),('wifi','C68','2','mosi'))
  if 'R69' in self.circuit('wifi').components:
   cases+=tuple(('wifi',r,p,g)for r,g in (('R69','cs'),('R70','sck'),('C61','cs'),('C64','sck'))for p in ('1','2'))
  with tempfile.TemporaryDirectory(prefix='cupc8-slot-open-') as tmp:
   for k,ref,pin,group in cases:
    with self.subTest(card=k,ref=ref,pin=pin):
     c=self.circuit(k);src=BOARDROOT/k/(k+'.kicad_pcb')
     links,_,missing,_=routed(c,k,src);self.assertFalse(missing);self.assertTrue(links[group])
     b=pcbnew.LoadBoard(str(src))
     fp=next(f for f in b.GetFootprints()if f.GetReference()==ref)
     pad=next(p for p in fp.Pads()if p.GetNumber()==pin)
     old=pad.GetPosition();distance=100 if ref in ('R69','R70','C61','C64') else 10;pad.SetPosition(pcbnew.VECTOR2I(old.x+pcbnew.FromMM(distance),old.y+pcbnew.FromMM(distance)))
     target=Path(tmp)/(k+ref+pin+'.kicad_pcb');pcbnew.SaveBoard(str(target),b)
     links,_,missing,_=routed(c,k,target);self.assertTrue(missing)
     if ref.startswith('C') or ref in ('R69','R70'):self.assertTrue(links[group]);self.assertFalse(links['complete'])
     else:self.assertFalse(links[group])
     if group=='enable':self.assertFalse(links['miso']);self.assertTrue(links['cs'])

if __name__=='__main__':unittest.main()
