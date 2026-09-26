// EMU-009: the Wi-Fi card is in step with the native whole-machine emulator.
// Its firmware runs in QEMU (tools/qemu_build.sh, the cupc8 chardev) on a
// clock the machine drives; the same machine run must give the same Wi-Fi
// card run, cycle for cycle.
//
//   node test/emu/test_wifi_lockstep.mjs
//
// The kernel ROM with the HDMI, IO and Wi-Fi cards: boot, `net join`, then
// `net get` from an HTTP server on this host, serially, threaded, and
// threaded again. Compared: the board's clock count and CPU state, every
// card's time (QEMU's clock at its last answer for the Wi-Fi card) and core
// cycle counts, every slot SPI frame (the Wi-Fi card's with QEMU's clock at
// its end), the guest's network traffic (a pcap: every packet and its guest
// time) and the screen.
//
// The server runs in its own process and always sends the same bytes: the
// host network is outside the machine and never in step (QEMU gives the host
// CUPC8_LOCKSTEP_SETTLE_MS after each packet the guest sends; see
// emu/machine/README.md), so a server that answers late, or one in this
// process (it answers only when the event loop turns), can change the run.

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Machine } from './machinenative.mjs';
import { kernelRom } from './romimage.mjs';

const PAGE = 'HELLO FROM THE HOST';
const rom = kernelRom();

// an HTTP server in a child process: the port on its first line of output
const SERVER = `
const http = require('node:http');
const s = http.createServer((req, res) => {
  res.sendDate = false;
  res.writeHead(200, { 'Content-Type': 'text/plain', Connection: 'close' });
  res.end(${JSON.stringify(PAGE)} + '\\n');
});
s.listen(0, '127.0.0.1', () => console.log(s.address().port));`;
const server = spawn(process.execPath, ['-e', SERVER], { stdio: ['ignore', 'pipe', 'inherit'] });
const port = await new Promise((resolve, reject) => {
  server.stdout.once('data', (d) => resolve(Number(String(d).trim())));
  server.once('exit', (c) => reject(new Error(`EMU-009: the HTTP server exited (${c})`)));
});

function screenText(m) {
  const s = m.screen();
  return s.error ? `(no picture: ${s.error})` : s.text.join('\n').replace(/\n+$/, '');
}

// the pcap's packets, each with its guest time relative to the first
// (filter-dump adds the wall clock's seconds at QEMU's start)
function packets(file) {
  const b = fs.readFileSync(file);
  const out = [];
  let t0 = null;
  for (let o = 24; o + 16 <= b.length;) {
    const us = b.readUInt32LE(o) * 1e6 + b.readUInt32LE(o + 4), n = b.readUInt32LE(o + 8);
    t0 ??= us;
    out.push(`${us - t0} ${b.subarray(o + 16, o + 16 + n).toString('hex')}`);
    o += 16 + n;
  }
  return out;
}

let bad = 0;
async function run(threaded) {
  const pcap = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-emu009-')), 'net.pcap');
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'wifi' }, rom, threaded, spiLog: true, pcap });
  const t = Date.now();
  m.powerOn();
  const steps = [];
  const waitFor = async (want, ns) => {
    const ok = await m.runUntil(() => screenText(m).includes(want), ns, 100e6);
    steps.push(`${want}: ${ok ? m.ns : 'not seen'}`);
    if (!ok) bad++;
  };
  await waitFor('>>', 6e9);
  m.type('net join cupc8 password\n');
  await waitFor('joined, address 10.0.2.15', 20e9);
  m.type(`net get 10.0.2.2 ${port}\n`);
  await waitFor(PAGE, 30e9);
  const secs = (Date.now() - t) / 1000;
  const out = {
    ns: m.ns, state: m.state(), steps,
    cards: m.cards().map(({ slot, kind, ns, cycles }) => ({ slot, kind, ns, cycles })),
    logs: Object.fromEntries([1, 2, 3].map((s) => [String(s), m.spiLog(s)])),
    screen: screenText(m),
  };
  m.stop();
  await new Promise((r) => setTimeout(r, 200));  // QEMU flushes and exits
  out.net = packets(pcap);
  return { out, secs };
}

function compare(a, b, what) {
  const diffs = [];
  for (const k of ['ns', 'state', 'steps', 'cards', 'screen'])
    if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) diffs.push(`${k}: ${JSON.stringify(a[k])}\n    vs ${JSON.stringify(b[k])}`);
  for (const slot of Object.keys(a.logs)) {
    const x = a.logs[slot], y = b.logs[slot];
    const i = x.findIndex((f, k) => JSON.stringify(f) !== JSON.stringify(y[k]));
    if (x.length !== y.length || i >= 0) diffs.push(`slot ${slot} SPI log: ${x.length} vs ${y.length} frames, first difference at ${i}: ${JSON.stringify(x[i])} vs ${JSON.stringify(y[i])}`);
  }
  const j = a.net.findIndex((p, k) => p !== b.net[k]);
  if (a.net.length !== b.net.length || j >= 0) diffs.push(`network: ${a.net.length} vs ${b.net.length} packets, first difference at ${j}:\n    ${a.net[j]}\n    ${b.net[j]}`);
  const wifi = a.logs['3'];
  console.log(`${what}: ${diffs.length ? 'DIFFERENT' : 'identical'} (${(a.ns / 1e6).toFixed(1)} ms, ${wifi.length} Wi-Fi card frames, QEMU at ${(a.cards.find((c) => c.kind === 'wifi').ns / 1e6).toFixed(1)} ms, ${a.net.length} packets)`);
  for (const d of diffs) console.log('  ' + d);
  if (diffs.length) bad++;
}

const runs = {};
try {
  runs.serial = await run(false);
  runs.threaded = await run(true);
  runs.threaded2 = await run(true);
} finally {
  server.kill();
}
for (const [k, r] of Object.entries(runs)) console.log(`${k}: ${(r.out.ns / 1e9).toFixed(3)} s emulated in ${r.secs.toFixed(1)} s`);
console.log('---- screen (serial)\n' + runs.serial.out.screen + '\n----');
if (!runs.serial.out.logs['3'].length) {
  console.log('FAIL: the Wi-Fi card saw no frames');
  bad++;
}
// QEMU trails the board, except that each answer takes guest time while the
// board waits (about 1.3 ms: the firmware's UART driver waits out an RX
// timeout), so while the kernel polls the card back to back the card's clock
// runs ahead of the board's (emu/machine/README.md)
const lead = runs.serial.out.cards.find((c) => c.kind === 'wifi').ns - runs.serial.out.ns;
console.log(`QEMU's clock is ${(lead / 1e6).toFixed(3)} ms ahead of the board's at the end`);
// every packet the guest gets here answers one it sent (DHCP, ARP, TCP from a
// prompt server): QEMU lets the host answer before the guest runs on, so the
// answer reaches the guest at the guest time of the packet that asked for it
const GUEST_MAC = '525400123456';
let asked = null;
for (const p of runs.serial.out.net) {
  const [t, hex] = p.split(' ');
  if (hex.slice(12, 24) === GUEST_MAC) asked = t;
  else if (t !== asked) {
    console.log(`FAIL: a packet reached the guest at ${t} us, not when it asked (${asked} us): ${hex.slice(0, 80)}`);
    bad++;
  }
}
compare(runs.serial.out, runs.threaded.out, 'serial vs threaded');
compare(runs.threaded.out, runs.threaded2.out, 'threaded vs threaded again');
console.log(`wifi_lockstep: ${bad ? 'FAIL' : 'PASS'}`);
process.exit(bad ? 1 : 0);
