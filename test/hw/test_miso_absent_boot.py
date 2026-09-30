#!/usr/bin/env python3
"""Qualify low passive MISO bias against authentic boot ROM and native cards.

The top is a read-only routed baseline. Its one declared bias change is a
candidate fixture, not a generated physical-source receipt or SI proof.
"""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'))
import boardevidence

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def command(args,log,env=None):
 with log.open('a') as output:
  subprocess.run([str(x) for x in args],cwd=ROOT,env=env,stdout=output,stderr=output,check=True)

def kernel(expected,raw):
 lines=['main:']
 for slot,value in enumerate(expected):
  lines+= [f'  ld r0, ${2+slot:04x}',f'  eq r0, #{value}',f'  bzf slot_{slot}_ok',f'  mov r0, #{0xe0+slot}','  st $f000, r0','  halt',f'slot_{slot}_ok:']
 # The first physical slot is intentionally empty in every table fixture.
 lines += ['  mov r0, #1','  st $f104, r0','  mov r0, #0xa5','  st $f100, r0','  mov r0, #1','  st $f102, r0','wait_spi:','  ld r0, $f103','  eq r0, #0','  bzf wait_spi','  ld r0, $f101',f'  eq r0, #{raw}','  bzf raw_ok','  mov r0, #0xee','  st $f000, r0','  halt','raw_ok:','  mov r0, #0','  st $f104, r0','  mov r0, #0xa5','  st $f000, r0','  halt']
 return '\n'.join(lines)+'\n'

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--top',type=Path,required=True);parser.add_argument('--board-root',type=Path,required=True)
 parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
 directory=args.output_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
 snapshots={b:sha(args.board_root/b/'evidence.json') for b in ('main','cpu','gpu','io','wifi','storage','eink','system')}
 for b in snapshots:boardevidence.validate(b,args.board_root/b)
 baseline=json.loads(args.top.read_text());top_sha=sha(args.top)
 original=directory/'baseline-top.json';original.write_text(json.dumps(baseline))
 candidate=json.loads(json.dumps(baseline));candidate['runtime']['miso_idle']=0
 candidate['development_candidate_scope']='Only passive MISO idle=0 declared for proposed 4.7k shunt; no physical adoption proof'
 low=directory/'declared-low-bias-top.json';low.write_text(json.dumps(candidate))
 high_model=json.loads(json.dumps(baseline));high_model['runtime']['miso_idle']=1
 high=directory/'declared-high-bias-top.json';high.write_text(json.dumps(high_model))
 log=directory/'build.log'
 command([sys.executable,'tools/as.py','rom/boot.s',directory/'boot.bin','0xe000,0xe600,0x0f00'],log)
 scenarios=[]
 for name,bias,slots,expected in [('all-absent-high',1,{},[0]*6),('all-absent-low',0,{},[0]*6),('sparse-io-low',0,{'4':'io'},[0,0,0,2,0,0])]:
  source=directory/(name+'.s');source.write_text(kernel(expected,255*bias))
  body=directory/(name+'.bin');rom=directory/(name+'.rom')
  command([sys.executable,'tools/as.py',source,body,'0x1000,0x1100,0xe000'],log)
  command([sys.executable,'tools/mkrom.py',directory/'boot.bin',body,'-o',rom],log)
  scenarios.append(dict(name=name,kind='slot-table',bias=bias,slots=slots,top=str(high if bias else low),rom=str(rom)))
 # Use the genuine maintained file-FD ROM helper for full kernel and BASIC.
 environment=dict(os.environ,CUPC8_ROM_OUTPUT=str(directory/'kernel.rom'))
 command(['node','--input-type=module','-e',"import fs from 'node:fs'; import {kernelRom} from './test/emu/romimage.mjs'; fs.writeFileSync(process.env.CUPC8_ROM_OUTPUT,kernelRom());"],log,environment)
 scenarios.append(dict(name='sparse-gpu-io-low-real-basic',kind='basic',bias=0,slots={'2':'hdmi','4':'io'},top=str(low),rom=str(directory/'kernel.rom')))
 config=directory/'scenarios.json';config.write_text(json.dumps(dict(scenarios=scenarios)))
 probe_log=directory/'native-results.json'
 with probe_log.open('w') as output,log.open('a') as errors:
  subprocess.run(['node','test/emu/miso_absent_boot_probe.mjs',str(config)],cwd=ROOT,stdout=output,stderr=errors,check=True)
 for b in snapshots:
  boardevidence.validate(b,args.board_root/b)
  assert snapshots[b]==sha(args.board_root/b/'evidence.json')
 assert top_sha==sha(args.top)
 results=json.loads(probe_log.read_text())
 before=next(r for r in results if r['name']=='all-absent-high')['probe_interval_emulated_ms']
 after=next(r for r in results if r['name']=='all-absent-low')['probe_interval_emulated_ms']
 assert 0<after-before<1000,(before,after)  # Finite retry bound, not nominal 5ms shorthand.
 index={'scope':'candidate passive-bias functional qualification; no physical SI/production approval','manufacturing_release_approved':False,'original_top_sha256':top_sha,'validated_board_receipts':snapshots,'sources':{p:sha(ROOT/p)for p in ['rom/boot.s','emu/machine/miso_bus.h','emu/machine/machine.cpp','emu/machine/addon.cpp','test/emu/machinenative.mjs','test/emu/romimage.mjs','test/emu/miso_absent_boot_probe.mjs','test/hw/test_miso_absent_boot.py']},'native_binary_sha256':sha(ROOT/'build/emu-machine/machine.node'),'results':results,'extra_all_absent_emulated_ms':after-before,'artifacts':{str(p.name):sha(p)for p in directory.iterdir()if p.is_file()and p.name!='qualification.json'}}
 (directory/'qualification.json').write_text(json.dumps(index,indent=2)+'\n')
 print(json.dumps(results,indent=2));print('PASS: actual boot slot-table/raw-empty byte and sparse real BASIC; extra absent probing',after-before,'emulated ms')
if __name__=='__main__':main()
