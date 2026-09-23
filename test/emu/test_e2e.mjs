// E2E-002..004 on the whole-machine emulator (test/emu/machine.mjs): the
// CPU and chipset RTL, the SRAM and ROM chip, and every card on its real
// firmware, with the host tool (tools/cupc8.py) talking to the system card.
//
//   node test/emu/test_e2e.mjs [E2E-002|E2E-003|E2E-004] [--record]
//
// Screens are compared with recorded text (test/emu/golden/*.txt); --record
// rewrites them after a human has checked the run.

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { Machine } from './machine.mjs';
import { kernelRom, ROOT } from './romimage.mjs';

const only = process.argv.slice(2).find((a) => a.startsWith('E2E-'));
const record = process.argv.includes('--record');
let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
  return cond;
}
const log = (...a) => console.log(`[${new Date().toISOString().slice(11, 19)}]`, ...a);

// run cupc8.py against the emulated system card while the machine runs
async function cupc8(m, ...args) {
  const p = spawn('python3', [path.join(ROOT, 'tools/cupc8.py'), '--port', `tcp:127.0.0.1:${m.sysctlPort}`, ...args],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });   // the machine runs ~50x slower than real time
  let out = '';
  p.stdout.on('data', (d) => (out += d));
  p.stderr.on('data', (d) => (out += d));
  let code = null;
  p.on('exit', (c) => (code = c));
  await m.runUntil(() => code !== null, 60e9);
  return { code, out };
}

function screenText(m) {
  const s = m.screen();
  return s.error ? `(no picture: ${s.error})` : s.text.join('\n').replace(/\n+$/, '');
}

function golden(name, text) {
  const file = path.join(ROOT, 'test/emu/golden', name + '.txt');
  if (record) fs.writeFileSync(file, text + '\n');
  const want = fs.existsSync(file) ? fs.readFileSync(file, 'utf8').replace(/\n$/, '') : null;
  expect(want !== null, `${name}: no recorded golden screen (run with --record once checked)`);
  if (want !== null && !expect(text === want, `${name}: the screen differs from ${path.relative(ROOT, file)}`)) {
    console.log('---- screen\n' + text + '\n---- golden\n' + want + '\n----');
  }
}

async function waitFor(m, want, ns) {
  const found = await m.runUntil(() => {
    const t = screenText(m);
    return t.includes(want);
  }, ns, 100e6);
  return found;
}

// ------------------------------------------------------------------ E2E-002
async function e2e002() {
  log('E2E-002: blank ROM, program it over USB, boot to BASIC, run a program');
  const rom = kernelRom();
  let end = rom.length;
  while (end > 0 && rom[end - 1] === 0xff) end--;
  const image = path.join(ROOT, 'build/emu/e2e-rom.bin');
  fs.writeFileSync(image, rom.subarray(0, end));
  const m = await Machine.create({ slots: { 1: 'gpu', 2: 'io' }, rom: Buffer.alloc(512 * 1024, 0xff), sysctl: true });
  m.powerOn();
  await m.runAsync(20e6);
  const ping = await cupc8(m, 'ping');
  expect(ping.code === 0 && ping.out.startsWith('CUPC8 sysctl'), `cupc8.py ping: ${ping.out.trim()}`);
  log(`programming ${end} bytes into the blank ROM chip`);
  const w = await cupc8(m, 'rom', 'write', image);
  expect(w.code === 0 && w.out.includes(`wrote and verified ${end} bytes`), `cupc8.py rom write: ${w.out.trim()}`);
  const r = await cupc8(m, 'reset');
  expect(r.code === 0, `cupc8.py reset: ${r.out.trim()}`);
  log('booting');
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI after the reset');
  m.type('10 print 6*7\nrun\n');
  expect(await waitFor(m, '42', 3e9), 'the typed program runs and prints 42');
  await m.runAsync(200e6);
  golden('E2E-002', screenText(m));
  m.stop();
}

const tests = { 'E2E-002': e2e002 };
for (const [id, fn] of Object.entries(tests)) if (!only || only === id) await fn();
console.log(`${only ?? 'E2E'}: the whole-machine emulator, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
