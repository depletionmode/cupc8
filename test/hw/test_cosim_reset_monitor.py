#!/usr/bin/env python3
"""Exact fitted rail-monitor reset source binding; analog runtime is separate."""
from pathlib import Path
import copy,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'hw/cosim'),str(ROOT/'test/hw')]
from gen_top import reset_monitor_source_binding,sysctl_manual_reset_route,reset_monitor_runtime
from netlist import read
from cosim_mutate import board_args

def main():
 args=board_args(__doc__).parse_args();original=read(args.main_netlist)
 system=read(args.system_board.with_suffix('.net'))
 assert len(reset_monitor_source_binding(original))==7
 sysctl_manual_reset_route(original,system,None,None)
 def refused(label,mutate,manual=False):
  c=copy.deepcopy(original);mutate(c)
  try:
   if manual:sysctl_manual_reset_route(c,system,None,None)
   else:reset_monitor_source_binding(c)
  except ValueError:print('refused:',label);return
  raise AssertionError(label+' was silently accepted')
 def part(c,ref,value):c.components[ref]=value
 def swap(c,a,b):
  c.pins[a],c.pins[b]=c.pins[b],c.pins[a]
  c.nets={n:tuple(b if x==a else a if x==b else x for x in nodes) for n,nodes in c.nets.items()}
 refused('BAT54C common cathode substituted',lambda c:part(c,'D7',('BAT54C',('jlc','BAT54CLT1G'))))
 refused('D7 common anode on wrong net',lambda c:swap(c,('D7','3'),('D7','1')))
 refused('D7 polarity pin name changed',lambda c:c.pin_names.__setitem__(('D7','3'),'K'))
 refused('OPA comparator inputs exchanged',lambda c:swap(c,('U18','3'),('U18','4')))
 refused('REF sense and enable exchanged',lambda c:swap(c,('U17','5'),('U17','3')))
 refused('reference voltage family changed',lambda c:part(c,'U17',('REF3430',('jlc','REF3430IDBVR'))))
 refused('hysteresis resistor changed',lambda c:part(c,'R115',('1M',('Device','R'))))
 refused('1V2 sensing rail changed',lambda c:c.pins.__setitem__(('R116','1'),'/+3V3'))
 refused('reference bypass capacitor changed',lambda c:part(c,'C52',('100n',('Device','C'))))
 refused('unknown logic load on monitor output',lambda c:c.nets.__setitem__('/MON33_OK',c.nets['/MON33_OK']+(('U7','74'),)))
 refused('unrecognized extra nMR load',lambda c:c.nets.__setitem__('/nMR',c.nets['/nMR']+(('U7','74'),)),True)
 refused('monitor branch removed',lambda c:c.nets.__setitem__('/nMR',tuple(x for x in c.nets['/nMR'] if x!=('D7','3'))),True)
 for label,mutate in (
  ('U19 push-pull substituted',lambda c:part(c,'U19',('SN74LVC04A',('jlc','SN74LVC04A')))),
  ('U19 wrong supply',lambda c:c.pins.__setitem__(('U19','14'),'/+3V3')),
  ('U19 input polarity changed',lambda c:c.pin_names.__setitem__(('U19','1'),'1Y')),
  ('U19 output slot exchanged',lambda c:swap(c,('U19','2'),('U19','4'))),
  ('unknown extra slot-reset driver',lambda c:c.nets.__setitem__('/SLOT1_RST_n',c.nets['/SLOT1_RST_n']+(('U7','74'),))),
  ('supervisor voltage family changed',lambda c:part(c,'U6',('MAX811L',('jlc','MAX811L')))),
  ('supervisor supply disconnected',lambda c:c.pins.__setitem__(('U6','4'),'/GND')),
  ('slot reset pull-up value changed',lambda c:part(c,'R204',('1M',('Device','R')))),
  ('slot reset pull-up supply changed',lambda c:c.pins.__setitem__(('R204','1'),'/GND')),
  ('expander reset bit mapping changed',lambda c:c.pin_names.__setitem__(('U13','4'),'P07')),
  ('nPOR pull-down omitted',lambda c:part(c,'R118',('1M',('Device','R'))))):
  c=copy.deepcopy(original);mutate(c)
  try:reset_monitor_runtime(c,None)
  except ValueError:print('refused:',label)
  else:raise AssertionError(label+' silently accepted')
 config,paths,missing,_=reset_monitor_runtime(original,None)
 assert not config['complete'] and missing and len(paths)==64
 assert not any(config['slots']) and not config['diode33']
 print('Actual U19/supervisor source mutations and missing physical proof failclosed PASS.')
 print('Actual fitted reset-monitor binding and12 meaningful sourcecounterexamples PASS; no analog coverage claim.')
if __name__=='__main__':main()
