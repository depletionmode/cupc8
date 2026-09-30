// Development regression, not routed hardware evidence. --top supplies a
// compatible runtime fixture; only proposed fitted-shunt/boot metadata changes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {Machine} from './machinenative.mjs';
import {kernelRom, ROOT} from './romimage.mjs';
const i=process.argv.indexOf('--top');
if(i<0) throw new Error('--top compatible development runtime JSON required');
const original=JSON.parse(fs.readFileSync(process.argv[i+1],'utf8'));
const physical=process.argv.includes('--physical');
if(physical) for(const card of ['gpu','io','storage','wifi','eink'])
 assert.equal(original.runtime.card_slot_links[card].miso_pulldown,true,`${card}: actual routed pull-down required`);
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cupc8-miso-boot-'));
const saved=process.env.CUPC8_COSIM_TOP;
try {
 const baseRom=kernelRom();
 for(const scenario of [{name:'no-card-FF',slots:{},gpu:0},
   {name:'fitted-active-00',slots:{1:'hdmi'},gpu:1},
   {name:'fitted-unbooted-00',slots:{1:'hdmi'},gpu:0,unbooted:true}]) {
  const top=structuredClone(original);
  if(!physical) top.runtime.card_slot_links.gpu.miso_pulldown=true;
  if(scenario.unbooted) top.runtime.qspi_boot_connected.gpu=false;
  const fixture=path.join(dir,'top.json');fs.writeFileSync(fixture,JSON.stringify(top));
  process.env.CUPC8_COSIM_TOP=fixture;
  // Keep actual POST and IDENT/retry code; stop after verifying its slot table.
  const verification=Array.from({length:6},(_,s)=>`\tld r0, $${(2+s).toString(16)}\n\teq r0, #${s===0?scenario.gpu:0}\n\tbzf .verified${s}\n\tb miso_failed\n.verified${s}:`).join('\n')+
   '\n\tmov r0, #0x55\n\tst GPO, r0\nmiso_done:\n\tb miso_done\nmiso_failed:\n\tmov r0, #0xee\n\tst GPO, r0\n\tb miso_failed\n';
  const boot=fs.readFileSync(path.join(ROOT,'rom/boot.s'),'utf8').replace('; ------------------------------------------------------------ POST $08 banner',verification+'\n; ------------------------------------------------------------ POST $08 banner');
  fs.writeFileSync(path.join(dir,'boot.s'),boot);
  execFileSync('python3',[path.join(ROOT,'tools/as.py'),path.join(dir,'boot.s'),path.join(dir,'boot.bin'),'0xe000,0xe600,0x0f00'],{stdio:'pipe'});
  const rom=Buffer.from(baseRom);fs.readFileSync(path.join(dir,'boot.bin')).copy(rom);
  const m=await Machine.create({slots:scenario.slots,rom,spiLog:true,threaded:false});
  try {
   m.powerOn();while(m.ns<1.5e9 && ![0x55,0xee].includes(m.state().gpo))m.runFor(10e6);
   assert.equal(m.state().gpo,0x55,`${scenario.name}: actual ROM probe table`);
   if(scenario.gpu) {
    const frames=m.spiLog(1).filter(f=>f.bytes.length);
    assert(frames.some(f=>f.miso.includes(0xc8)),'active high bits/signature survive low idle');
   }
   console.log(`${scenario.name}: real ROM slot table PASS at ${m.ns/1e6} ms`);
  } finally {m.stop();}
 }
} finally {if(saved===undefined)delete process.env.CUPC8_COSIM_TOP;else process.env.CUPC8_COSIM_TOP=saved;fs.rmSync(dir,{recursive:true,force:true});}
