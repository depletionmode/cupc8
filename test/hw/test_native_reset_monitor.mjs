import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const native=createRequire(import.meta.url)(path.join(root,'build/emu-machine/machine.node'));
const monitor={complete:true,core_complete:true,diode33:true,diode12:true,slots:Array(6).fill(true)};
const h=native.create({root,slots:{},rom:Buffer.alloc(32768),sysctl:true,threaded:false,resetMonitorEnabled:true,resetMonitor:monitor,expanders:[{address:0x20,inputs:[255,255]}]});
try {
 native.powerOn(h);
 assert.equal(native.resetMonitor(h).por,true);
 assert.equal(native.expanders(h)[0].pins[0]&63,63);
 native.setResetRails(h,3.17,1.2,3.3);
 assert.equal(native.resetMonitor(h).out33,.05);
 assert.equal(native.resetMonitor(h).por,false);
 native.setResetRails(h,3.3,1.1,3.3);
 assert.equal(native.resetMonitor(h).por,false);
 assert.equal(native.expanders(h)[0].pins[0]&63,0);
 native.setResetRails(h,3.3,1.2,3.3);
 assert.equal(native.resetMonitor(h).por,false);
 native.setResetRails(h,3.3,1.1,0);
 assert(native.resetMonitor(h).slots.every(Boolean)); // U19 Ioff only at VCC=0
 assert.equal(native.resetMonitor(h).por,false);
 console.log('native machine actual rail-fault → MR/nPOR → all six U19/TCA9555 lines, restoration withheld PASS');
}finally{native.destroy(h);}

// A lost 1V2 diode must visibly lose that fault indication, not silently pass.
const broken=native.create({root,slots:{},rom:Buffer.alloc(32768),threaded:false,resetMonitorEnabled:true,resetMonitor:{...monitor,diode12:false}});
try{native.powerOn(broken);native.setResetRails(broken,3.3,1.1,3.3);assert.equal(native.resetMonitor(broken).por,true);}finally{native.destroy(broken);}
// Missing source/copper proof forces reset rather than making a coverage flag.
const unproved=native.create({root,slots:{},rom:Buffer.alloc(32768),threaded:false,resetMonitorEnabled:true,resetMonitor:{...monitor,complete:false,core_complete:false}});
try{native.powerOn(unproved);assert.equal(native.resetMonitor(unproved).por,false);}finally{native.destroy(unproved);}
console.log('Native missing-diode behavioral counterexample and missing-binding failclosed PASS');

// Complete geometry remains false on a known diode branch open, but the
// supervisor's fitted internal MR pull-up keeps healthy nominal rails running.
const isolated=native.create({root,slots:{},rom:Buffer.alloc(32768),threaded:false,resetMonitorEnabled:true,resetMonitor:{...monitor,complete:false,core_complete:true,diode33:false,diode12:false}});
try{native.powerOn(isolated);assert.equal(native.resetMonitor(isolated).por,true);native.setResetRails(isolated,3.3,1.1,3.3);assert.equal(native.resetMonitor(isolated).por,true);native.setResetRails(isolated,3.1,1.2,3.3);assert.equal(native.resetMonitor(isolated).por,false);}finally{native.destroy(isolated);}
console.log('Modeled MR branch disconnection loses diode action while independent supervisor brownout still asserts PASS');
