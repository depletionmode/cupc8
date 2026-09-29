// The IO card's port switch on the native whole machine (emu/machine,
// Rp2040Card::vbus): the real io.elf with a short on the port. The TPS2553-1
// holds FAULT (GPIO8) low while EN (GPIO7) is high and releases it when EN
// goes low, so the firmware must drop EN for 1000 ms, raise it, meet the
// short again, and so on. Checked: the EN edge times (on the card's clock),
// the same serially and on the card threads, and none of it without a short.
//
//   node test/emu/test_machine_io_vbus.mjs

import { Machine } from './machinenative.mjs';

let bad = 0;
const expect = (cond, what) => {
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
};

async function run(ioOverload, threaded, ns) {
  const m = await Machine.create({ slots: { 1: 'io' }, threaded, ioOverload });
  m.powerOn();
  m.runFor(ns);
  const v = m.ioVbus(1);
  m.stop();
  return v;
}

const short = await run(true, false, 3.2e9);
const levels = short.edges.map((e) => e[1]).join();
expect(levels.startsWith('true,false,true,false,true,false'),
  `a short: EN goes high, then off/on/off/on/off (${levels})`);
for (let k = 2; k + 1 < short.edges.length; k += 2) {
  const off = (short.edges[k][0] - short.edges[k - 1][0]) / 1e6;
  expect(off > 999 && off < 1002, `EN low for 1000 ms (whole ms from a truncated clock) before retry ${k / 2} (${off.toFixed(3)} ms)`);
}
const on = (short.edges[2][0] - short.edges[1][0]) / 1e6;
console.log(`short: ${short.edges.length} EN edges, first off at ${(short.edges[1][0] / 1e6).toFixed(3)} ms, off ${on.toFixed(3)} ms`);

const threaded = await run(true, true, 3.2e9);
expect(JSON.stringify(threaded.edges) === JSON.stringify(short.edges),
  'the EN edges are identical on the card threads (cycle for cycle)');

const fine = await run(false, false, 1.2e9);
expect(fine.edges.length === 1 && fine.edges[0][1] === true && fine.en && !fine.nfaultLow,
  `no short: EN goes high once and stays (${fine.edges.length} edges)`);

console.log(`machine_io_vbus: ${bad ? 'FAIL' : 'PASS'}`);
process.exit(bad ? 1 : 0);
