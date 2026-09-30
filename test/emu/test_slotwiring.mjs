import assert from 'node:assert/strict';
import { fittedSlotWiring } from './slotwiring.mjs';
const kinds = {hdmi:'gpu', io:'io', storage:'storage', wifi:'wifi', eink:'eink'};
const signals = ['sck','mosi','cs','miso','irq'];
const runtime = () => ({miso_idle:1, slots:Array.from({length:6},()=>Object.fromEntries(signals.map(s=>[`${s}_connected`,true]))), card_slot_links:Object.fromEntries(Object.values(kinds).map(k=>[k,Object.fromEntries(signals.map(s=>[s,true]))]))});
let r=runtime();
assert.equal(fittedSlotWiring(r,{},kinds).miso_idle,1);
assert.equal(fittedSlotWiring(r,{1:'hdmi'},kinds).miso_idle,1); // legacy network
r.card_slot_links.gpu.miso_pulldown=true;
assert.equal(fittedSlotWiring(r,{1:'hdmi'},kinds).miso_idle,0);
assert.equal(fittedSlotWiring(r,{},kinds).miso_idle,1);
r.card_slot_links.gpu.miso=false; // broken buffer does not disconnect passive R61
assert.equal(fittedSlotWiring(r,{1:'hdmi'},kinds).miso_idle,0);
r.slots[0].miso_connected=false;
assert.equal(fittedSlotWiring(r,{1:'hdmi'},kinds).miso_idle,1);
r=runtime();r.card_slot_links.gpu.miso_pulldown=false;
assert.equal(fittedSlotWiring(r,{1:'hdmi'},kinds).miso_idle,1);
r.card_slot_links.gpu.miso_pulldown='true';
assert.throws(()=>fittedSlotWiring(r,{1:'hdmi'},kinds),/invalid card MISO/);
console.log('Fitted-card passive MISO wiring checks passed');
