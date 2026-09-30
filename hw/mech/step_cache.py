"""Content-bound cache of actual KiCad STEP exports, not release receipts.

Only record immediately after a real successful export with matching input
identities before and after. An unowned existing STEP must be regenerated.
"""
import hashlib,json,os,re,shutil
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def sidecar(step):return Path(str(step)+'.provenance.json')
def model_inputs(pcb):
 """Bind actual model bytes, including STEP substitutions for VRML models.

 The Linux KiCad default is used only when its standard model directory
 exists. Unsupported variables cannot produce a reusable cache identity.
 """
 pcb=Path(pcb).resolve()
 configs=sorted((Path.home()/'.config/kicad').glob('*/kicad_common.json'))
 variables={'KIPRJMOD':str(pcb.parent)}
 for config in configs:
  values=json.loads(config.read_text()).get('environment',{}).get('vars') or {}
  variables.update(values)
 variables.update(os.environ)
 result={}
 for encoded in re.findall(r'\(model\s+("(?:[^"\\]|\\.)*")',pcb.read_text()):
  name=json.loads(encoded)
  def expand(match):
   key=match.group(1)
   if key in variables:return variables[key]
   if re.fullmatch(r'KICAD[0-9]+_3DMODEL_DIR',key) and Path('/usr/share/kicad/3dmodels').is_dir():
    return '/usr/share/kicad/3dmodels'
   raise ValueError('unresolved STEP model variable: '+key)
  resolved=re.sub(r'\$\{([^}]+)\}',expand,name)
  if '$' in resolved:raise ValueError('unsupported STEP model path: '+name)
  path=Path(resolved)
  if not path.is_absolute():path=pcb.parent/path
  path=path.resolve()
  candidates=[path]
  if path.suffix.lower()=='.wrl':
   candidates += [path.with_suffix(suffix) for suffix in ('.step','.stp','.STEP','.STP')]
  for candidate in candidates:
   result[str(candidate)]=digest(candidate) if candidate.is_file() else None
 return result,{str(p):digest(p) for p in configs}

def identity(pcb,command):
 pcb=Path(pcb).resolve();binary=shutil.which(str(command[0]))
 if not binary:raise ValueError('STEP exporter unavailable: '+str(command[0]))
 directory=pcb.parent;receipt=directory/'evidence.json'
 inputs=json.loads(receipt.read_text())['inputs']
 models,configs=model_inputs(pcb)
 return {'version':2,'pcb':str(pcb),'pcb_sha256':digest(pcb),
         'exporter':str(Path(binary).resolve()),'exporter_sha256':digest(binary),
         'command':[str(x) for x in command],
         'project_files':{str(p):digest(p) for p in (directory/(pcb.stem+'.kicad_pro'),directory/'fp-lib-table') if p.exists()},
         'project_model_inputs':{n:h for n,h in inputs.items() if n.startswith('hw/lib/')},
         'model_files':models,'kicad_configs':configs,
         'model_environment':{k:v for k,v in os.environ.items() if k=='KIPRJMOD' or (k.startswith('KICAD') and k.endswith('_DIR'))}}
def reusable(step,expected):
 step=Path(step)
 try:
  actual=json.loads(sidecar(step).read_text())
  return (actual.get('scope')=='actual KiCad STEP export cache; not manufacturing approval'
          and actual.get('identity')==expected and actual.get('step_sha256')==digest(step))
 except (OSError,ValueError,TypeError):return False

def record(step,before,after):
 step=Path(step)
 if before!=after:raise ValueError('STEP exporter inputs changed during export')
 if not step.exists() or not step.stat().st_size:raise ValueError('missing/empty actual STEP export')
 p=sidecar(step);temp=p.with_name(p.name+'.tmp')
 temp.write_text(json.dumps({'scope':'actual KiCad STEP export cache; not manufacturing approval',
                            'identity':before,'step_sha256':digest(step)},indent=2)+'\n')
 temp.replace(p)
