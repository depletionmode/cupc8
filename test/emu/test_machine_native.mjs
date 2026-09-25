// The native whole-machine emulator (emu/machine, test/emu/machinenative.mjs):
// the same run serially and on the card threads (twice) must give the same
// machine, cycle for cycle. (The legacy JS emulator, machine.mjs, is not
// maintained and no longer compared: David, 2026-09-25.)
//
//   node test/emu/test_machine_native.mjs [--ns N] [--type TEXT] [--expect TEXT]
//
// Runs the kernel ROM with the GPU and IO cards for N ns (default: boot to
// BASIC and type a program, 2.4 s: the boot ROM copies the 21.7 KB kernel
// body for 1.3 s of it), on the native machine serially, and
// threaded twice, and compares the main board's clock count and CPU state,
// every card's clock, core cycle counts and UART output, every SPI frame each
// card saw (bytes both ways, start and end times) and the screen read off the
// HDMI output. Exits 1 on any difference, or if the typed program's output is
// not on the screen.

import { Machine as NativeMachine } from './machinenative.mjs';
import { kernelRom } from './romimage.mjs';

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const NS = Number(arg('--ns', '2.4e9'));
const TYPE = (arg('--type', '10 print 6*7\\nrun\\n') || null)?.replace(/\\n/g, '\n');
const EXPECT = arg('--expect', process.argv.includes('--type') ? '' : '42');
const rom = kernelRom();

function screenText(m) {
  const s = m.screen();
  return s.error ? `(no picture: ${s.error})` : s.text.join('\n').replace(/\n+$/, '');
}

async function runNative(threaded) {
  const m = await NativeMachine.create({ slots: { 1: 'hdmi', 2: 'io' }, rom, threaded, spiLog: true });
  const t = Date.now();
  m.powerOn();
  if (TYPE) m.type(TYPE);
  m.runFor(NS);
  const secs = (Date.now() - t) / 1000;
  const out = {
    ns: m.ns, state: m.state(),
    clocks: Math.round(m.ns / (1000 / 12)),
    cards: m.cards().map(({ slot, kind, ns, uart, cycles }) => ({ slot, kind, ns, uart, cycles })),
    logs: Object.fromEntries([1, 2].map((s) => [String(s), m.spiLog(s)])),
  };
  out.screen = screenText(m);
  m.stop();
  return { out, secs };
}

let bad = 0;
function compare(a, b, what) {
  const diffs = [];
  if (a.ns !== b.ns) diffs.push(`board ns ${a.ns} vs ${b.ns}`);
  if (JSON.stringify(a.state) !== JSON.stringify(b.state)) diffs.push(`CPU state ${JSON.stringify(a.state)} vs ${JSON.stringify(b.state)}`);
  if (JSON.stringify(a.cards) !== JSON.stringify(b.cards)) diffs.push(`cards ${JSON.stringify(a.cards)} vs ${JSON.stringify(b.cards)}`);
  for (const slot of Object.keys(a.logs)) {
    const x = a.logs[slot], y = b.logs[slot];
    const i = x.findIndex((f, k) => JSON.stringify(f) !== JSON.stringify(y[k]));
    if (x.length !== y.length || i >= 0) diffs.push(`slot ${slot} SPI log: ${x.length} vs ${y.length} frames, first difference at ${i}: ${JSON.stringify(x[i])} vs ${JSON.stringify(y[i])}`);
  }
  if (a.screen !== b.screen) diffs.push(`screen:\n${a.screen}\n---- vs\n${b.screen}`);
  const frames = Object.values(a.logs).reduce((n, l) => n + l.length, 0);
  console.log(`${what}: ${diffs.length ? 'DIFFERENT' : 'identical'} (${a.ns / 1e6} ms, ${a.clocks} board clocks, ${frames} SPI frames, card cycles ${JSON.stringify(a.cards.map((c) => c.cycles))})`);
  for (const d of diffs) console.log('  ' + d);
  if (diffs.length) bad++;
}

const runs = {};
runs.serial = await runNative(false);
runs.threaded = await runNative(true);
runs.threaded2 = await runNative(true);
for (const [k, r] of Object.entries(runs)) console.log(`${k}: ${(r.out.ns / 1e9).toFixed(3)} s emulated in ${r.secs.toFixed(1)} s: ${(r.secs / (r.out.ns / 1e9)).toFixed(1)}x slower than real time`);
console.log('---- screen (native serial)\n' + runs.serial.out.screen + '\n----');
compare(runs.serial.out, runs.threaded.out, 'native serial vs native threaded');
compare(runs.threaded.out, runs.threaded2.out, 'native threaded vs native threaded again');
if (EXPECT && !runs.serial.out.screen.includes(EXPECT)) {
  console.log(`FAIL: '${EXPECT}' is not on the screen`);
  bad++;
}
console.log(`machine_native: ${bad ? 'FAIL' : 'PASS'}`);
process.exit(bad ? 1 : 0);
