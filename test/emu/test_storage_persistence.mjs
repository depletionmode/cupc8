// Real CPU SAVE/CLOSE -> destroyed machine -> fresh boot -> first LOAD/RUN.
// Run separately for GPU and selected750; immutable compiled source supplied explicitly.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const args=process.argv.slice(2);
function take(flag){const i=args.indexOf(flag);assert.ok(i>=0 && args[i+1],`${flag} required`);return args[i+1];}
const source=path.resolve(take('--source')),out=path.resolve(take('--out'));
const profile=take('--profile');assert.ok(['gpu','eink750'].includes(profile),'explicit GPU or selected750 profile');
const top=path.join(path.dirname(source),'strict-top.json');assert.ok(fs.existsSync(top),'genuine strict routed top required');
process.env.CUPC8_COSIM_TOP=top;
assert.ok(!fs.existsSync(out),'preserve previous attempts');fs.mkdirSync(out,{recursive:true});
const sdk=process.env.CUPC8_SDK??path.join(process.env.HOME,'.local/share/cupc8-sdk');
const {Machine}=await import(pathToFileURL(path.join(source,'test/emu/machinenative.mjs')));
const protectedPaths=[top,...['build/boot/kernel.rom','build/emu-machine/machine.node',
 'build/rp2040/sysctl.elf','build/rp2040/io.elf','build/rp2040/storage.elf',
 `build/rp2040/${profile}.elf`,'build/esp32c3-qemu/flash.bin',
 'kernel/gpu.s','fw/rp2040/common/slotspi.c'].map(p=>path.join(source,p))];
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const hashes=()=>Object.fromEntries(protectedPaths.map(p=>[p,hash(p)]));
const before=hashes();const rom=fs.readFileSync(path.join(source,'build/boot/kernel.rom'));
assert.equal(rom.length,512*1024,'genuine complete built ROM');
const image=path.join(out,'sd.img');let sequence=0,checks=0,m=null;
function check(ok,message){checks++;assert.ok(ok,message);}
function fat(...a){const name=path.join(out,`fat-${sequence++}`),fd=fs.openSync(name+'.stderr','w');
 try{const data=execFileSync(path.join(sdk,'pyfat/bin/python'),[path.join(source,'test/emu/fatimg.py'),...a],{stdio:['ignore','pipe',fd]});fs.writeFileSync(name+'.stdout',data);return data;}finally{fs.closeSync(fd);}}
fat('mkfs',image,'16','16');
const slots={1:profile==='gpu'?'hdmi':'eink750',2:'io',3:'wifi',4:'storage'};
const text=()=>{const s=profile==='gpu'?m.screen():m.panelScreen();return s.error?'':s.text.join('\n').replace(/\n+$/,'');};
async function boot(system){m=await Machine.create({slots,sysctl:system,rom,spiLog:true});m.sd.insert(image,{highCapacity:false});m.powerOn();
 check(await m.runUntil(()=>text().includes('>>'),12e9,100e6),'real kernel/BASIC boots on actual fitted display');}
async function line(command,want){m.type(command+'\n');check(await m.runUntil(()=>{const t=text(),i=t.toLowerCase().lastIndexOf(command.toLowerCase());return i>=0 && /\n>> ?_?$/.test(t.slice(i+command.length)) && (!want || t.slice(i+command.length).includes(want));},20e9,100e6),`actual command ${command} completes`);}
function snapshot(){return {screen:text(),state:m.state(),cards:m.cards(),sd:m.sd.card(),slot4:m.spiLog(4)};}
try{
 await boot(true);await line('new');
 m.type('10 print 6*7\n20 print "FIRST SAVE PERSISTED"\n');await m.runAsync(400e6);
 await line('save "persist"','SAVED');
 const names=JSON.parse(fat('ls',image).toString());const entry=names.find(([name])=>/^PERSIST(\.BAS)?$/.test(name));check(entry,'independent PC FAT sees firmware-saved file');
 const saved=fat('get',image,entry[0]);check(/10 PRINT 6\*7/i.test(saved.toString('latin1')) && /FIRST SAVE PERSISTED/i.test(saved.toString('latin1')),'saved bytes contain original typed program');
 check(fat('check',image).toString().startsWith('ok'),'independent FAT reader/check validates closed file');
 check(m.sd.card().stats.blocksWritten>0,'actual storage firmware wrote SD blocks');
 fs.writeFileSync(path.join(out,'first-save.json'),JSON.stringify(snapshot(),null,2)+'\n');
 fs.writeFileSync(path.join(out,'saved-file-before.bin'),saved);
 m.stop();m=null; // Destroy CPU/RP RAM, handles, DMA, panel and System before fresh instance.
 const imageBefore=hash(image);await boot(false);
 // This is deliberately the first file operation in a fresh CPU after boot.
 // No SAVE, file injection or second host write can recreate the program.
 await line('new');await line('load "persist"','LOADED');await line('run','FIRST SAVE PERSISTED');
 const afterRun=text().slice(text().toLowerCase().lastIndexOf('run')+3);
 check(afterRun.includes('42'),'first persisted LOAD executes original arithmetic on genuine fresh CPU');
 check(m.sd.card().violations.length===0,'actual SD transfer has no protocol violations');
 check(fat('get',image,entry[0]).equals(saved),'independent PC read equals first SAVE bytes after cold LOAD/RUN');
 check(fat('check',image).toString().startsWith('ok'),'independent FAT remains valid after cold LOAD/RUN');
 check(hash(image)===imageBefore,'read-only persistence phase makes no SD image writes');
 if(profile==='eink750'){const p=m.panel();check(p.w===800 && p.h===480 && p.errors===0,'actual matching750 UC8179 glass receives cold loaded output');}
 else check(!m.frame().error && m.frame().rgb.length>0,'actual decoded HDMI pixels exist');
 check(JSON.stringify(hashes())===JSON.stringify(before),'immutable supplied source/assets unchanged');
 const result={status:'PASS',profile,checks,source,slots,first_SAVE_only:true,fresh_machine_after_poweroff:true,second_phase_first_file_command:'LOAD persist',second_SAVE:false,system_present_then_removed:true,first_saved_file_sha256:createHash('sha256').update(saved).digest('hex'),image_before_cold_read_sha256:imageBefore,image_after_cold_read_sha256:hash(image),source_and_assets_before_after_identical:before,cold_phase:snapshot(),scope:'Genuine CPU/kernel/RP/FatFs and actual SD image, independent PC FAT checks; first LOAD after fresh whole-machine instance before any new SAVE. Native models, not physical silicon or all-media compatibility.',manufacturing_release:false};
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');console.log(`PASS ${profile}: ${checks} actual persistence checks`);
}catch(error){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:String(error),checks,source,profile,machine:m?snapshot():null},null,2)+'\n');throw error;}finally{m?.stop();}
