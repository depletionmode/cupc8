// Real native CPU -> kernel API -> fitted750 firmware, loaded from actual SD.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const argv=process.argv.slice(2);
const take=(name)=>{const i=argv.indexOf(name);assert.ok(i>=0 && argv[i+1],name+' required');return path.resolve(argv[i+1]);};
const source=take('--source'),out=take('--out');
const top=path.join(path.dirname(source),'strict-top.json');
assert.ok(fs.existsSync(top),'genuine schematic-derived strict top required');
process.env.CUPC8_COSIM_TOP=top;
const expectLoss=argv.includes('--expect-loss');
assert.ok(!fs.existsSync(out),'preserve each attempt');fs.mkdirSync(out,{recursive:true});
const repo=path.resolve(path.dirname(new URL(import.meta.url).pathname),'../..');
const {Machine}=await import(pathToFileURL(path.join(source,'test/emu/machinenative.mjs')));
const SDK=process.env.CUPC8_SDK??path.join(process.env.HOME,'.local/share/cupc8-sdk');
const protectedPaths=['build/boot/kernel.rom','build/rp2040/eink750.elf','build/rp2040/io.elf','build/rp2040/storage.elf','build/esp32c3-qemu/flash.bin','build/emu-machine/machine.node','kernel/gpu.s','fw/rp2040/common/slotspi.c'].map(p=>path.join(source,p));
protectedPaths.push(top,path.join(repo,'tools/testdata/eink_queue_api.s'));
const hashes=()=>Object.fromEntries(protectedPaths.map(p=>[p,createHash('sha256').update(fs.readFileSync(p)).digest('hex')]));
const beforeHashes=hashes();
function child(program,args,name){const a=fs.openSync(path.join(out,name+'.stdout'),'w'),b=fs.openSync(path.join(out,name+'.stderr'),'w');try{execFileSync(program,args,{stdio:['ignore',a,b]});}finally{fs.closeSync(a);fs.closeSync(b);}}
const prg=path.join(out,'queue.prg'),image=path.join(out,'sd.img');
child('python3',[path.join(repo,'tools/mkprg.py'),path.join(repo,'tools/testdata/eink_queue_api.s'),'-o',prg],'assemble');
const fat=(...args)=>child(path.join(SDK,'pyfat/bin/python'),[path.join(source,'test/emu/fatimg.py'),...args],'fat-'+args[0]);
fat('mkfs',image,'16','16');fat('put',image,'QUEUE.PRG',prg);
let m;
try{
 m=await Machine.create({slots:{1:'eink750',2:'io',3:'wifi',4:'storage'},sysctl:false,rom:fs.readFileSync(path.join(source,'build/boot/kernel.rom')),spiLog:true});
 m.sd.insert(image,{highCapacity:false});m.powerOn();
 const text=()=>m.panelScreen().text.join('\n');
 assert.ok(await m.runUntil(()=>text().includes('>>'),12e9,100e6),'actual750 BASIC boot');
 const before=m.spiLog(1).length;m.type('exec "queue.prg"\n');
 assert.ok(await m.runUntil(()=>text().includes('API QUEUE COMPLETE') && /\n>> ?_?$/.test(text().replace(/\n+$/,'')),40e9,100e6),'real kernel API program completes on glass');
 const frames=m.spiLog(1).slice(before);
 fs.writeFileSync(path.join(out,'slot1-api.json'),JSON.stringify(frames,null,2)+'\n');
 const attrs=frames.filter(f=>f.bytes[0]===0x13);
 const short=frames.filter(f=>[0x01,0x02,0x09,0x12,0x13,0x14,0x16,0x17].includes(f.bytes[0]));
 const noCredit=short.filter(f=>(f.miso[0]&127)===0);
 const attrNoCredit=attrs.filter(f=>(f.miso[0]&127)===0);
 const refreshes=frames.filter(f=>f.bytes[0]===0x09);
 assert.equal(attrs.length,2400,'actual API_ATTR2400 calls reach slot pins');
 assert.equal(refreshes.length,40,'actual direct API_EINK_REFRESH40 calls reach slot pins');
 if(expectLoss)assert.ok(attrNoCredit.length>0,'old actual kernel ATTR path violates FREE under rendering');
 else{assert.equal(noCredit.length,0,'all real short API commands respect FREE');assert.ok(text().includes('#'.repeat(60)),'all60 actual API_POKE cells reach glass');}
 const panel=m.panel();assert.equal(panel.errors,0,'UC8179 accepts actual kernel workload');
 assert.equal(m.sd.card().violations.length,0,'actual SD programload has no protocol violations');
 assert.deepEqual(hashes(),beforeHashes,'source/assets unchanged through actual API execution');
 const result={status:'PASS',mode:expectLoss?'old-kernel-counterexample':'corrected-kernel',source,ns:m.ns,attrs:attrs.length,refreshes:refreshes.length,attrNoCredit:attrNoCredit.length,shortNoCredit:noCredit.length,screen:text(),cards:m.cards(),source_and_assets_before_after_identical:beforeHashes,rom_sha256:createHash('sha256').update(fs.readFileSync(path.join(source,'build/boot/kernel.rom'))).digest('hex'),scope:'Real CPU executes assembledkernelAPIprogramloadedfromactualSDwith750/IO/WiFi/storagefitted. Exposes FREE violation at incomingSPI; panel/controller checks retained. Notphysicalproof.',manufacturing_release:false};
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({status:result.status,mode:result.mode,attrs:result.attrs,attrNoCredit:result.attrNoCredit,shortNoCredit:result.shortNoCredit,ns:result.ns}));
}catch(error){if(m)fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:String(error),screen:m.panelScreen(),state:m.state(),cards:m.cards(),slot1:m.spiLog(1)},null,2)+'\n');throw error;}finally{m?.stop();}
