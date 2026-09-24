// E2E-002..004 on the whole-machine emulator (test/emu/machine.mjs): the
// CPU and chipset RTL, the SRAM and ROM chip, and every card on its real
// firmware, with the host tool (tools/cupc8.py) talking to the system card.
//
//   node test/emu/test_e2e.mjs [E2E-002|E2E-003|E2E-004|E2E-007] [--record]
//
// CUPC8_EMU=native runs them on the native emulator (emu/machine,
// test/emu/machinenative.mjs: the same machine, cycle for cycle, faster);
// the default is machine.mjs.
//
// Screens are compared with recorded text (test/emu/golden/*.txt); --record
// rewrites them after a human has checked the run.

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
const backend = process.env.CUPC8_EMU === 'native' ? 'native' : 'js';
const { Machine } = await import(backend === 'native' ? './machinenative.mjs' : './machine.mjs');
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
  // the cursor blinks: whether the prompt shows it depends on when the frame
  // was captured, so a cursor at the end of the last line is not compared
  text = text.replace(/ ?_$/, '');
  const file = path.join(ROOT, 'test/emu/golden', name + '.txt');
  if (record) fs.writeFileSync(file, text + '\n');
  const want = fs.existsSync(file) ? fs.readFileSync(file, 'utf8').replace(/\n$/, '') : null;
  if (!expect(want !== null, `${name}: no recorded golden screen (run with --record once checked)`)) console.log('---- screen\n' + text + '\n----');
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
  if (!expect(await waitFor(m, '42', 3e9), 'the typed program runs and prints 42')) console.log('---- screen\n' + screenText(m));
  await m.runAsync(200e6);
  golden('E2E-002', screenText(m));
  m.stop();
}

// ------------------------------------------------------------------ E2E-003
// The kernel's `net` command on the real Wi-Fi firmware (QEMU, user-mode NAT:
// the host is 10.0.2.2): join, then an HTTP GET from a server on this host,
// its page shown on HDMI.
async function e2e003() {
  log('E2E-003: Wi-Fi join, then an HTTP GET from a local server, shown on HDMI');
  const page = 'HELLO FROM THE HOST';
  let requests = 0;
  const server = http.createServer((req, res) => {
    requests++;
    res.sendDate = false;                         // the screen is compared with a recording
    res.writeHead(200, { 'Content-Type': 'text/plain', Connection: 'close' });
    res.end(page + '\n');
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const m = await Machine.create({ slots: { 1: 'gpu', 2: 'io', 3: 'wifi' } });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  m.type('net join cupc8 password\n');
  expect(await waitFor(m, 'joined, address 10.0.2.15', 20e9), 'net join joins and prints the DHCP address');
  log(`fetching from 10.0.2.2:${port}`);
  m.type(`net get 10.0.2.2 ${port}\n`);
  expect(await waitFor(m, page, 30e9), 'net get prints the page the host served');
  expect(requests === 1, `the server saw one request (${requests})`);
  await m.runAsync(200e6);
  golden('E2E-003', screenText(m).replace(new RegExp(`10\\.0\\.2\\.2 ${port}`, 'g'), '10.0.2.2 PORT'));
  m.stop();
  server.close();
}

// ------------------------------------------------------------------ E2E-007
// The e-ink card instead of the HDMI card (doc/hardware/eink-card.md): the
// real eink.elf with the UC8179 panel model on its header (native emulator
// only). The kernel finds it as the console by INFO; the panel shows BASIC's
// prompt, a typed program and its output, once the card's own refreshes
// have put them on the glass. The glass is compared with a golden image.
function panelText(m) {
  const s = m.panelScreen();
  return s.error ? `(no panel: ${s.error})` : s.text.join('\n').replace(/\n+$/, '');
}

function panelGolden(name, p) {
  const file = path.join(ROOT, 'test/eink/golden', name + '.pbm');
  const pbm = Buffer.alloc(p.w / 8 * p.h);
  for (let i = 0; i < p.w * p.h; i++) if (p.grey[i] < 128) pbm[i >> 3] |= 0x80 >> (i & 7);
  const img = Buffer.concat([Buffer.from(`P4\n${p.w} ${p.h}\n`), pbm]);
  if (record) fs.writeFileSync(file, img);
  fs.writeFileSync(path.join(ROOT, 'build/emu', name + '.pbm'), img);
  const want = fs.existsSync(file) ? fs.readFileSync(file) : null;
  expect(want !== null && want.equals(img), `${name}: the panel's glass equals ${path.relative(ROOT, file)} ` +
    `(this run's is build/emu/${name}.pbm)`);
}

async function e2e007() {
  log('E2E-007: the e-ink card as the console: boot to BASIC on the panel, run a program');
  if (!expect(backend === 'native', 'E2E-007 needs the native emulator (CUPC8_EMU=native)')) return;
  const m = await Machine.create({ slots: { 1: 'eink', 2: 'io' } });
  m.powerOn();
  const on = async (want, ns) => m.runUntil(() => panelText(m).includes(want), ns, 50e6);
  expect(await on('>>', 10e9), 'the BASIC prompt appears on the panel');
  m.type('10 print 6*7\nrun\n');
  if (!expect(await on('42', 10e9), 'the typed program runs and prints 42 on the panel')) console.log(panelText(m));
  m.type('help\n');
  expect(await on('REFRESH', 10e9), 'help lists the refresh command');
  // the kernel found the e-ink card by INFO: `refresh` asks it for a clean
  // full refresh (on HDMI it does nothing)
  m.type('refresh\n');
  expect(await m.runUntil(() => m.panel().refreshes[0] === 2, 10e9, 50e6), 'refresh: a second clean full refresh');
  await m.runAsync(3e9);                       // every change refreshed, nothing pending
  const p = m.panel();
  expect(p.errors === 0, `the panel model saw nothing the chip would ignore (${p.errors}: ${p.error})`);
  expect(p.refreshes[0] === 2, `clean full refreshes at power-on and for refresh (${p.refreshes})`);
  expect(p.refreshes[3] >= 3, `partial refreshes for the typing (${p.refreshes})`);
  expect(p.busy === 0, 'the panel is idle');
  golden('E2E-007', panelText(m));
  panelGolden('E2E-007', p);
  m.stop();
}

const tests = { 'E2E-002': e2e002, 'E2E-003': e2e003, 'E2E-007': e2e007 };
log(`backend: ${backend === 'native' ? 'native (emu/machine)' : 'machine.mjs'}`);
for (const [id, fn] of Object.entries(tests)) if (only ? only === id : id !== 'E2E-007' || backend === 'native') await fn();
console.log(`${only ?? 'E2E'}: the whole-machine emulator, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
