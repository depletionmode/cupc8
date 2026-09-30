"""Guarded full copper design seeds; never manufacturing receipts.

Only a board wrapper may decide that its post_route transformation already
ran in the origin. This module never calls or skips that board-specific hook.
Unsupported geometry, changed guards and open non-pour nets raise ValueError,
so seeded_route callbacks must not catch these errors and invoke a router.
"""
import hashlib,json,tempfile,re
from pathlib import Path
import pcbnew
import kicadgen as kg

SCHEMA=1

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def items(board):
 ts=board.Tracks();return [ts[i].Cast() for i in range(len(ts))]
def field(node,key):
 return next((v for v in node if isinstance(v,list) and v and v[0]==key),None)
def strip(node,nets):
 if not isinstance(node,list):return str(node)
 if node and node[0]=='net':
  name=str(node[-1]);return ['net',nets.get(name,name)]
 return [strip(v,nets) for v in node if not(isinstance(v,list) and v and v[0] in ('uuid','tstamp'))]
def snapshot(board):
 with tempfile.TemporaryDirectory(prefix='cupc8-seed-guard-') as tmp:
  path=Path(tmp)/'snapshot.kicad_pcb'
  if not pcbnew.SaveBoard(str(path),board):raise ValueError('cannot serialize route guards')
  tree=kg.parse(path.read_text())
 nets={str(n[1]):str(n[2]) for n in tree if isinstance(n,list) and n and n[0]=='net' and len(n)>2}
 physical={}
 for fp in (v for v in tree if isinstance(v,list) and v and v[0]=='footprint'):
  props={str(p[1]):str(p[2]) for p in fp if isinstance(p,list) and p and p[0]=='property'}
  ref=props.get('Reference')
  if ref is None:raise ValueError('footprint missing reference')
  if ref in physical:raise ValueError('duplicate footprint reference: '+ref)
  pads=[strip(v,nets) for v in fp if isinstance(v,list) and v and v[0]=='pad']
  copper=[]
  for v in fp:
   if not isinstance(v,list) or not v:continue
   layer=field(v,'layer')
   if layer and (str(layer[1]).endswith('.Cu') or layer[1]=='Edge.Cuts'):copper.append(strip(v,nets))
  physical[ref]={'library':str(fp[1]),'at':strip(field(fp,'at'),nets),
                 'layer':strip(field(fp,'layer'),nets),'value':props.get('Value'),
                 'pads':sorted(pads,key=encoded),'physical_graphics':sorted(copper,key=encoded)}
 board_geometry=[]
 for v in tree:
  if not isinstance(v,list) or not v:continue
  layer=field(v,'layer')
  if v[0] in ('gr_line','gr_arc','gr_rect','gr_poly','gr_circle') and layer and (layer[1]=='Edge.Cuts' or str(layer[1]).endswith('.Cu')):board_geometry.append(strip(v,nets))
  if v[0]=='zone' and field(v,'keepout'):board_geometry.append(strip(v,nets))
 setup=field(tree,'setup')
 return {'footprints':physical,'copper_layers':[[board.GetLayerName(l),int(l)] for l in board.GetEnabledLayers().CuStack()],
         'general':strip(field(tree,'general'),nets),
         'setup':strip([v for v in setup if not(isinstance(v,list) and v and v[0]=='pcbplotparams')],nets),
         'board_geometry':sorted(board_geometry,key=encoded)}
def copper(board):
 rows=[]
 for t in items(board):
  if t.Type()==pcbnew.PCB_TRACE_T:
   a,b=t.GetStart(),t.GetEnd();rows.append(['track',t.GetNetname(),board.GetLayerName(t.GetLayer()),a.x,a.y,b.x,b.y,t.GetWidth()])
  elif t.Type()==pcbnew.PCB_VIA_T:
   if t.GetViaType()!=pcbnew.VIATYPE_THROUGH:raise ValueError('only through-via seeds implemented')
   widths=[t.GetWidth(l) for l in board.GetEnabledLayers().CuStack()]
   if len(set(widths))!=1:raise ValueError('per-layer via diameters unsupported')
   a=t.GetPosition();rows.append(['via',t.GetNetname(),a.x,a.y,widths[0],t.GetDrillValue(),board.GetLayerName(t.TopLayer()),board.GetLayerName(t.BottomLayer()),int(t.GetViaType())])
  else:raise ValueError('unsupported routed geometry: '+t.GetClass())
 return sorted(rows,key=encoded)
def nonpour_open(board,pour_nets):
 # Evaluate actual routed tracks and pads; a preexisting fill cannot mask an
 # incomplete seed. Connectivity clones isolate this destructive probe.
 with tempfile.TemporaryDirectory(prefix='cupc8-seed-connectivity-') as tmp:
  path=Path(tmp)/'probe.kicad_pcb';pcbnew.SaveBoard(str(path),board);b=pcbnew.LoadBoard(str(path))
  zones=b.Zones();z=[zones[i] for i in range(len(zones))]
  for zone in z:
   b.Remove(zone);zone.thisown=False
  nets=sorted({p.GetNetname() for fp in b.GetFootprints() for p in fp.Pads()}-set(pour_nets)-{''})
  return kg.open_escapes(b,nets)
def extract(pcb,seed,*,board_name,pour_nets,post_route_contract,origin_note,completed_build=None,design_candidate=False):
 pcb,seed=Path(pcb),Path(seed)
 if design_candidate and completed_build is not None:raise ValueError('design candidate cannot carry a completed receipt')
 if not design_candidate and pcb.name!=board_name+'-routed.kicad_pcb':raise ValueError('origin must be the pipeline routed-stage board')
 if not origin_note or not post_route_contract:raise ValueError('origin note and board post-route contract required')
 origin_digest=sha(pcb)
 b=pcbnew.LoadBoard(str(pcb));opened=nonpour_open(b,pour_nets)
 if sha(pcb)!=origin_digest:raise ValueError('origin changed while extracting route seed')
 if opened:raise ValueError('origin non-pour connections open: '+', '.join(opened))
 origin={'file':pcb.name,'sha256':origin_digest,'state':'design-candidate' if design_candidate else 'pipeline-incomplete','note':origin_note,
         'manufacturing_pass':False,'receipt_sha256':None}
 if completed_build is not None:
  import boardevidence
  out=Path(completed_build);e=boardevidence.validate(board_name,out)
  relative=str(pcb.resolve().relative_to(out.resolve()))
  if e['artifacts'].get(relative)!=origin['sha256']:raise ValueError('origin not in current completed receipt')
  origin['state']='pipeline-completed';origin['receipt_sha256']=sha(out/'evidence.json')
 body={'board':board_name,'pour_nets':sorted(set(pour_nets)),'post_route_contract':post_route_contract,
       'guards':snapshot(b),'copper':copper(b)}
 payload={'schema':SCHEMA,'kind':'route-design-seed','origin':origin,'body_sha256':digest(body),'body':body}
 payload['payload_sha256']=digest(payload)
 seed.write_text(json.dumps(payload,indent=2)+'\n');return payload

def load(seed):
 payload=json.loads(Path(seed).read_text())
 if payload.get('payload_sha256')!=digest({k:v for k,v in payload.items() if k!='payload_sha256'}):raise ValueError('changed/truncated route seed payload')
 if payload.get('schema')!=SCHEMA or payload.get('kind')!='route-design-seed':raise ValueError('unsupported route seed schema')
 if payload.get('body_sha256')!=digest(payload['body']):raise ValueError('changed/truncated route seed body')
 origin=payload.get('origin',{})
 if origin.get('state') not in ('design-candidate','pipeline-incomplete','pipeline-completed') or origin.get('manufacturing_pass') is not False:raise ValueError('invalid design-seed origin state')
 if not origin.get('file') or Path(origin['file']).name!=origin['file']:raise ValueError('missing recorded origin filename')
 if origin['state']!='pipeline-completed' and origin.get('receipt_sha256') is not None:raise ValueError('incomplete design origin cannot carry a completed receipt')
 if re.fullmatch('[0-9a-f]{64}',origin.get('sha256','')) is None or not origin.get('note'):raise ValueError('missing recorded origin SHA/note')
 if origin['state']=='pipeline-completed' and re.fullmatch('[0-9a-f]{64}',origin.get('receipt_sha256') or '') is None:raise ValueError('completed origin missing receipt SHA')
 return payload

def verify_installed(board, seed):
 """Verify a board-specific hook did not change the already-finished route."""
 if copper(board) != load(seed)['body']['copper']:
  raise ValueError('installed full-route copper changed before post-route verification')

def normalize_placement(board, ref, source_nm, exact_nm):
 """Normalize one explicitly reviewed FromMM/SES nanometre roundtrip.

 This is a board-source placement correction, not a tolerance in seed
 compatibility. Only the two exact declared states are accepted.
 """
 footprint = board.FindFootprintByReference(ref)
 if footprint is None:
  raise ValueError('route placement normalization: missing ' + ref)
 position = footprint.GetPosition()
 actual = (position.x, position.y)
 if actual not in (tuple(source_nm), tuple(exact_nm)):
  raise ValueError('route placement normalization: moved ' + ref)
 footprint.SetPosition(pcbnew.VECTOR2I(*exact_nm))

def install(board,rows):
 nets=board.GetNetsByName();layers={board.GetLayerName(l):l for l in board.GetEnabledLayers().CuStack()}
 prepared=[]
 for r in rows:
  if r[1] not in nets:raise ValueError('seed net missing: '+r[1])
  if r[0]=='track' and len(r)==8:
   t=pcbnew.PCB_TRACK(board);t.SetLayer(layers[r[2]]);t.SetStart(pcbnew.VECTOR2I(*r[3:5]));t.SetEnd(pcbnew.VECTOR2I(*r[5:7]));t.SetWidth(r[7])
  elif r[0]=='via' and len(r)==9 and r[8]==int(pcbnew.VIATYPE_THROUGH):
   t=pcbnew.PCB_VIA(board);t.SetPosition(pcbnew.VECTOR2I(*r[2:4]));t.SetWidth(r[4]);t.SetDrill(r[5]);t.SetViaType(pcbnew.VIATYPE_THROUGH);t.SetLayerPair(layers[r[6]],layers[r[7]])
  else:raise ValueError('unsupported seed copper item')
  t.SetNet(nets[r[1]]);t.SetLocked(True);prepared.append(t)
 for t in items(board):
  board.Remove(t);t.thisown=False
 for t in prepared:board.Add(t)

def apply(board,seed,*,board_name,pour_nets,post_route_contract):
 payload=load(seed);body=payload['body']
 if body['board']!=board_name or body['pour_nets']!=sorted(set(pour_nets)) or body['post_route_contract']!=post_route_contract:raise ValueError('board/pour/post-route contract mismatch')
 actual=snapshot(board)
 if actual!=body['guards']:
  refs=actual['footprints'].keys()|body['guards']['footprints'].keys()
  changed=[r for r in sorted(refs) if actual['footprints'].get(r)!=body['guards']['footprints'].get(r)]
  raise ValueError('route geometry incompatible: '+(', '.join(changed) or 'board stackup/outline/keepout/settings'))
 # Reject bad copper before touching the live target. No autorouter fallback.
 with tempfile.TemporaryDirectory(prefix='cupc8-seed-trial-') as tmp:
  path=Path(tmp)/'trial.kicad_pcb';pcbnew.SaveBoard(str(path),board);trial=pcbnew.LoadBoard(str(path));install(trial,body['copper'])
  opened=nonpour_open(trial,pour_nets)
  if opened:raise ValueError('recorded route incomplete: '+', '.join(opened))
 install(board,body['copper'])
 return {'added':len(body['copper']),'origin_state':payload['origin']['state'],
         'origin_sha256':payload['origin']['sha256'],'nonpour_open':[],
         'requires_full_pipeline':True}
