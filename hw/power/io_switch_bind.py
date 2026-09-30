#!/usr/bin/env python3
"""Receipt-bound fitted TPS2553-1 source/copper binding for IC-005.

Binds the existing transient model's declared nominal/engineering scenario.
The 20nH loop and stress response are engineering assumptions, not inferred
inductance or guaranteed maximum silicon propagation. No manufacturing approval.
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'hw/tools'),str(ROOT/'hw/cosim'),str(ROOT/'hw/si')]
import boardevidence,io_port_switch as model,thermal_bind
from netlist import read
from ibis_bus import routed_connectivity,routed_distances
VALUES={'U5':('TPS2553DBVR-1',('jlc','TPS2553DBVR-1')),
        **{r:(v,('Device','R')) for r,v in {'R10':'45k3','R11':'100k','R12':'10k'}.items()},
        **{r:(v,('Device','C')) for r,v in {'C21':'100u','C22':'100n','C25':'4.7u','C23':'22u','C24':'22u'}.items()}}
PINMAP={'1':('IN','/VBOOST'),'2':('GND','/GND'),'3':('EN','/VBUS_EN'),
        '4':('FAULT','/VBUS_nFAULT'),'5':('ILIM','/ILIM'),'6':('OUT','/VBUS')}
NETS={'/ILIM':{('R10','1'),('U5','5')},
      '/VBUS_EN':{('R11','1'),('U1','9'),('U5','3')},
      '/VBUS_nFAULT':{('R12','2'),('U1','11'),('U5','4')},
      '/VBOOST':{('C23','1'),('C24','1'),('C25','1'),('R16','1'),('U5','1'),('U7','6')},
      '/VBUS':{('C21','1'),('C22','1'),('J2','1'),('U5','6'),('U6','5')}}
RETURNS=[('R10','2'),('R11','2'),('C21','2'),('C22','2'),('C25','2'),('C23','2'),('C24','2')]
def topology(circuit):
 for ref,expected in VALUES.items():
  if circuit.components.get(ref)!=expected:raise ValueError(f'{ref}: fitted switch-model value changed')
 for pin,(name,net) in PINMAP.items():
  if circuit.net('U5',pin)!=net or circuit.pin_names.get(('U5',pin))!=name:
   raise ValueError(f'U5.{pin}: wrong switch pin/polarity/net')
 for net,expected in NETS.items():
  if set(circuit.nets.get(net,()))!=expected or any(circuit.net(*p)!=net for p in expected):
   raise ValueError(f'{net}: extra/missing modeled load')
 if any(circuit.net(*p)!='/GND' for p in RETURNS) or circuit.net('R12','1')!='/3V3':
  raise ValueError('switch-model return or FAULT pull-up rail changed')
 if circuit.pin_names.get(('U1','9'))!='GPIO7' or circuit.pin_names.get(('U1','11'))!='GPIO8':
  raise ValueError('switch enable/fault GPIO changed')
 # Catch a stale behavioral model before attributing its results to this board.
 for name,value in {'R_ILIM':45300.,'R_ILIM_TOL':.01,'R_ILIM_TCR':100e-6,
                    'R_EN':100000.,'R_PULLUP':10000.,
                    'C_IN_LOCAL':1.6e-6,'C_BOOST':26e-6,'L_IN':20e-9}.items():
  if getattr(model,name)!=value:raise ValueError(f'{name}: behavioral model changed; requalify binding')
 if model.C_PORT!=(120e-6,10e-6):raise ValueError('port capacitor/USB load scenario changed')
 if model.PART!='TPS2553DBVR-1' or model.LCSC!='C111738':raise ValueError('model switch identity changed')
 return circuit

def physical(circuit,board_path,bom_path):
 import pcbnew
 board=pcbnew.LoadBoard(str(board_path));fps={f.GetReference():f for f in board.GetFootprints()}
 codes={}
 for row in csv.DictReader(Path(bom_path).open()):
  for ref in row['Designator'].split(','):codes[ref.strip()]=row['LCSC Part #']
 if codes.get('U5')!='C111738' or codes.get('R10')!='C26980' or codes.get('C25')!='C23733':raise ValueError('wrong switch/ILIM/local-cap BOM part')
 for ref in VALUES:
  fp=fps.get(ref)
  if fp is None or fp.GetValue()!=VALUES[ref][0]:raise ValueError(f'{ref}: missing or different PCB value')
  actual={p.GetNumber():p.GetNetname() for p in fp.Pads() if p.GetNumber()}
  expected={p:n for (r,p),n in circuit.pins.items() if r==ref}
  if actual!=expected:raise ValueError(f'{ref}: actual PCB pads differ from source')
  if ref=='U5' and f'{fp.GetFPID().GetLibNickname()}:{fp.GetFPID().GetLibItemName()}'!='jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL':
   raise ValueError('wrong actual switch footprint')
 rows=[]
 for net,nodes in NETS.items():
  first=('U5',next(p for p,(_,n) in PINMAP.items() if n==net));targets=sorted(nodes-{first})
  connected=routed_connectivity(board_path,net,first,targets)
  if not all(connected.values()):raise ValueError(f'{net}: missing actual switch copper {connected}')
  rows.append({'net':net,'source':first,'contacts':connected})
 grounds=routed_connectivity(board_path,'/GND',('U5','2'),RETURNS)
 if not all(grounds.values()):raise ValueError('switch cap/resistor ground return disconnected')
 pullup=routed_connectivity(board_path,'/3V3',('U1','48'),[('R12','1')])
 if not all(pullup.values()):raise ValueError('FAULT pull-up supply copper disconnected')
 rows.append({'net':'/3V3','source':('U1','48'),'contacts':pullup})
 for name,first,last,limit in [('boost input',('C24','1'),('U5','1'),13.850001),
                               ('local input capacitor',('C25','1'),('U5','1'),3.620001)]:
  length=routed_distances(board_path,'/VBOOST',first,[last])[f'{last[0]}.{last[1]}']
  if length is None or length>limit:raise ValueError(f'{name}: modeled launch length exceeded: {length}mm')
  rows.append({'geometry_diagnostic':name,'centerline_mm':length,'max_mm':limit,
               'not_inductance_proof':True})
 return rows

def check(out):
 out=Path(out);boardevidence.validate('io',out)
 sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (Path(__file__),HERE/'io_port_switch.py',HERE/'thermal_bind.py',
                    HERE/'boost.py',HERE/'budget.py',HERE/'design.py',HERE/'spice.py',
                    ROOT/'hw/si/ibis_bus.py')}
 thermal_bind.bind('io',out)
 circuit=topology(read(out/'io.net'));paths=physical(circuit,out/'io.kicad_pcb',out/'fab/bom.csv')
 boardevidence.validate('io',out)
 if sources!={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}:
  raise ValueError('switch checker/model source changed during proof')
 print(json.dumps({'scope':'receipt-bound fitted/source/copper binding; existing engineering transient scenario',
                   'model_sha256':sources,'pcb_sha256':hashlib.sha256((out/'io.kicad_pcb').read_bytes()).hexdigest(),
                   'evidence_sha256':hashlib.sha256((out/'evidence.json').read_bytes()).hexdigest(),
                   'assumptions':{'loop_inductance_h':model.L_IN,'physically_derived_loop_bound':False,
                                  'response_stress_s':model.T_RESP_STRESS,'guaranteed_max_response':False,
                                  'nominal_input_cap_f':4.7e-6,
                                  'modeled_effective_input_cap_f':model.C_IN_LOCAL,
                                  'guaranteed_operating_Ceff':False,
                                  'effective_capacitance_status':'engineering target; IC-104 measured qualification required'},
                   'paths':paths,'manufacturing_release_approved':False},indent=2))
 return 0
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('out',type=Path)
 args=parser.parse_args()
 try:sys.exit(check(args.out))
 except (ValueError,OSError) as exc:print('FAIL IO switch binding:',exc,file=sys.stderr);sys.exit(1)
