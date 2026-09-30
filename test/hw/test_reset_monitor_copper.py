#!/usr/bin/env python3
"""Actual copper disconnections: core unknown vs modeled MR/clamp branches."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'hw/cosim'),str(ROOT/'test/hw')]
from gen_top import reset_monitor_runtime
import boardevidence
from netlist import read
from cosim_mutate import board_args,open_pad

def main():
 args=board_args(__doc__).parse_args();boardevidence.validate('main',args.main_board.parent)
 circuit=read(args.main_netlist)
 config,paths,missing,_=reset_monitor_runtime(circuit,args.main_board)
 assert config['complete'] and config['core_complete'] and not missing and len(paths)==64
 with tempfile.TemporaryDirectory(prefix='cupc8-monitor-copper-') as tmp:
  for label,ref,pin,net in [('mr','U6','3','/nMR'),('sense','U18','3','/MON33_P'),('slot','U19','2','/SLOT1_RST_n')]:
   mutated=Path(tmp)/(label+'.kicad_pcb')
   removed=open_pad(args.main_board,mutated,ref,pin,net);assert removed>0
   cfg,_,gaps,_=reset_monitor_runtime(circuit,mutated)
   assert not cfg['complete'] and gaps
   if label=='mr':assert cfg['core_complete'] and not cfg['diode33'] and not cfg['diode12'] and all(cfg['slots'])
   elif label=='sense':assert not cfg['core_complete'] and cfg['diode33'] and cfg['diode12']
   else:assert cfg['core_complete'] and cfg['slots']==[False,True,True,True,True,True]
   print(json.dumps({'mutation':label,'removed_tracks':removed,'core_complete':cfg['core_complete'],
                     'diodes':[cfg['diode33'],cfg['diode12']],'slots':cfg['slots'],'gaps':gaps}))
 boardevidence.validate('main',args.main_board.parent)
 print('Actual64-leg baseline and source-specific copper branch/core counterexamples PASS')
if __name__=='__main__':main()
