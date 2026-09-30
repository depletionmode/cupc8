// Actual native CPU/chipset + ROM boot. Candidate passive bias is explicit;
// it is not an attestation that this candidate has been manufactured.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { Machine } from './machinenative.mjs';
const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const results = [];
for (const scenario of config.scenarios) {
  process.env.CUPC8_COSIM_TOP = scenario.top;
  const machine = await Machine.create({ slots: scenario.slots,
    rom: fs.readFileSync(scenario.rom), threaded: true, hostPort: false,
    sysctl: false, spiLog: true });
  let probeStart = null, probeEnd = null, maxSampleGap = 0;
  try {
    machine.powerOn();
    if (scenario.kind === 'slot-table') {
      for (let step=0; step<2000 && !machine.state().halted; step++) {
        const previous=machine.ns;
        machine.runFor(1e6);
        maxSampleGap=Math.max(maxSampleGap,machine.ns-previous);
        const gpo=machine.state().gpo;
        if (gpo===4 && probeStart===null) probeStart=machine.ns;
        if (probeStart!==null && gpo!==4 && probeEnd===null) probeEnd=machine.ns;
      }
      assert.equal(machine.state().halted, 1, `${scenario.name}: boot did not finish`);
      assert.equal(machine.state().gpo, 0xa5, `${scenario.name}: slot/RX assertion kernel failed`);
    } else {
      assert.equal(scenario.kind, 'basic');
      let text='';
      for (let step=0; step<60 && !text.includes('>>'); step++) {
        machine.runFor(50e6);
        const screen=machine.screen();
        if (!screen.error) text=screen.text.join('\n');
      }
      assert.ok(text.includes('CUPC/8 BASIC') && text.includes('>>'), 'sparse installed cards failed BASIC boot');
      const promptAt=machine.ns;
      machine.type('10 print 6*7\nrun\n');
      for (let step=0; step<30 && !text.includes('42'); step++) {
        machine.runFor(50e6);
        const screen=machine.screen();
        if (!screen.error) text=screen.text.join('\n');
      }
      assert.ok(text.includes('42'), 'installed IO/card active bits failed actual BASIC execution');
      results.push({name:scenario.name, bias:scenario.bias, prompt_at_emulated_ms:promptAt/1e6,
        program_result:'42', state:machine.state(), scope:'actual native ROM/kernel/card firmware execution; emulated time only'});
      continue;
    }
    const installed=Object.keys(scenario.slots);
    const frames=Object.fromEntries(installed.map(slot=>[slot,machine.spiLog(Number(slot)).slice(0,3)]));
    results.push({name:scenario.name,bias:scenario.bias,slots:scenario.slots,
      emulated_ms:machine.ns/1e6,probe_interval_emulated_ms:(probeEnd-probeStart)/1e6,
      requested_sample_period_ms:1,max_actual_sample_gap_ms:maxSampleGap/1e6,state:machine.state(),installed_frames:frames,
      checked:'all six slot-table entries and raw selected-empty SPI byte',
      scope:'declared passive-bias candidate, actual ROM/native execution; not physical elapsed time'});
  } finally { machine.stop(); }
}
console.log(JSON.stringify(results,null,2));
