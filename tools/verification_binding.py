"""Content-bound full verification reports; source/board identity is not a pass."""
import hashlib,json,sys,fnmatch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hw/tools'))
import boardevidence
BOARDS=('main','cpu','system','gpu','io','storage','eink','wifi')
SOURCE_DIRS=('soc','rom','kernel','fw','hw','tools','test','basic','emu')
SKIP={'build','__pycache__','.pytest_cache','node_modules','.git','nimcache'}
GENERATED=('kernel/kernel.o','kernel/kernel.map','kernel/kernel.rom','kernel/merged.ss','tools/sim','tools/simtest','tools/simtui','tools/testdata/*.o','tools/testdata/*.map','tools/testdata/*.prg','*.exe')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sources(root):
 root=Path(root);files=[]
 for directory in SOURCE_DIRS:
  files.extend(p for p in (root/directory).rglob('*')if p.is_file()and not SKIP.intersection(p.relative_to(root).parts)and p.suffix not in ('.pyc','.prl')and not any(fnmatch.fnmatch(str(p.relative_to(root)),pattern)for pattern in GENERATED))
 files.extend(root/p for p in ('Makefile','doc/hardware/verification.md','doc/hardware/fab-waivers.md','doc/milestone-1.md','doc/hardware/slot.md','doc/hardware/jlc-order-checklist.md','doc/hardware/parts.md','doc/hardware/first-article-plan.md')if(root/p).is_file())
 return {str(p.relative_to(root)):sha(p)for p in sorted(set(files))}
def boards(root):
 root=Path(root);rows={}
 for b in BOARDS:
  out=root/'build/hw'/b
  try:
   receipt=boardevidence.validate(b,out,root);scope=json.loads((out/'pipeline-scope.json').read_text())
   rows[b]={'validated':True,'quantity':receipt['boards'],'receipt_sha256':sha(out/'evidence.json'),'pipeline_scope':scope}
  except (OSError,ValueError,KeyError)as e:rows[b]={'validated':False,'error':str(e)}
 return rows

def capture(root):return {'sources':sources(root),'boards':boards(root)}

def release_problems(root,report,tests):
 binding=report.get('binding') or {};problems=[]
 if binding.get('version')!=1 or not binding.get('full_gate_run'):
  return ['last report is not a content-bound complete gate run']
 before=binding.get('before');after=binding.get('after');current=capture(root)
 if before!=after:problems.append('source or board inputs changed during verification')
 if after!=current:problems.append('last verification report is stale: source or board content differs')
 catalogue_ids=[t['id'] for t in tests]
 if len(catalogue_ids)!=len(set(catalogue_ids)):problems.append('catalogue has duplicate test IDs; command ownership is ambiguous')
 required={t['id']:t.get('cmd')for t in tests if t['kind']!='hw'}
 if binding.get('commands')!=required:problems.append('report does not cover the current complete non-hardware catalogue')
 result_ids=[r['id'] for r in report.get('results',[])]
 if len(result_ids)!=len(set(result_ids)):problems.append('report has duplicate test IDs; result ownership is ambiguous')
 rows={r['id']:r for r in report.get('results',[])}
 for tid,cmd in required.items():
  row=rows.get(tid,{})
  if not isinstance(cmd,str) or not cmd.strip():
   problems.append(f'{tid}: required non-hardware test has no implemented command');continue
  if row.get('status')!='pass':
   problems.append(f'{tid}: required non-hardware test is not passing');continue
  log=Path(root)/row.get('log','__missing_log__')
  if not log.is_file()or row.get('log_sha256')!=sha(log):problems.append(f'{tid}: missing or changed actual test log')
 for b,row in current['boards'].items():
  if not row.get('validated'):problems.append(f'{b}: missing/stale board evidence');continue
  if row['quantity']!=2:problems.append(f'{b}: required assembly quantity is two')
  scope=row['pipeline_scope']
  if scope.get('pipeline_mode')!='live-stock-checked' or scope.get('live_stock_check',{}).get('status')!='passed':
   problems.append(f'{b}: development/offline or missing live stock scope')
 return problems
