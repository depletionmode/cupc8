// E2E-002..004 on the whole-machine emulator (test/emu/machine.mjs): the
// CPU and chipset RTL, the SRAM and ROM chip, and every card on its real
// firmware, with the host tool (tools/cupc8.py) talking to the system card.
//
//   node test/emu/test_e2e.mjs [E2E-002|E2E-003|E2E-004|E2E-007|E2E-008] [--record]
//
// E2E-007 (files on the storage card's microSD) and E2E-008 (the e-ink card)
// need CUPC8_EMU=native: the SD card and panel models are only in the native
// emulator.
//
// CUPC8_EMU=native runs them on the native emulator (emu/machine,
// test/emu/machinenative.mjs: the same machine, cycle for cycle, faster);
// the default is machine.mjs.
//
// Screens are compared with recorded text (test/emu/golden/*.txt); --record
// rewrites them after a human has checked the run.

import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
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
// Files on the storage card (doc/hardware/storage-card.md): the real kernel
// and BASIC, the real IO and storage card firmware, the SD card model with a
// FAT image made on the host (test/emu/fatimg.py). Type a program, SAVE it,
// power the machine off and on (the card keeps the image), LOAD and RUN it;
// DIR; a program written on the host LOADs; keys typed during a slow SAVE
// are not lost; SAVE with no card, a full card and a write-protected card
// gives the kernel's messages. Native only.
async function e2e007() {
  log('E2E-007: BASIC SAVE, power cycle, LOAD, RUN, DIR on the storage card (microSD model)');
  if (backend !== 'native') {
    expect(false, 'E2E-007 needs CUPC8_EMU=native (the SD card model)');
    return;
  }
  const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-e2e007-'));
  const fat = (...a) => execFileSync(path.join(SDK, 'pyfat/bin/python'), [path.join(ROOT, 'test/emu/fatimg.py'), ...a]);
  const img = path.join(dir, 'card.img');
  fat('mkfs', img, '16', '16');
  fs.writeFileSync(path.join(dir, 'host.bas'), '10 print 100+23\r\n20 print "FROM THE HOST"\r\n');
  fat('put', img, 'HOSTPROG.BAS', path.join(dir, 'host.bas'));
  const slots = { 1: 'gpu', 2: 'io', 3: 'storage' };
  const boot = async (opts = {}) => {
    const m = await Machine.create({ slots });
    if (opts.image !== null) m.sd.insert(opts.image ?? img, { highCapacity: false, ...opts.sd });
    m.powerOn();
    expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
    return m;
  };
  // run a command line and wait for the prompt after it (or `want`)
  const line = async (m, text, want, ns = 10e9) => {
    m.type(text + '\n');
    return m.runUntil(() => {
      const t = screenText(m);
      const i = t.toLowerCase().lastIndexOf(text.toLowerCase());
      if (i < 0) return false;
      const after = t.slice(i + text.length);
      return /\n>> ?_?$/.test(after) && (!want || after.includes(want));
    }, ns, 100e6);
  };
  const shown = (m) => '---- screen\n' + screenText(m) + '\n----';

  let m = await boot();
  m.type('10 print "saved"\n20 print 6*7\n');
  await m.runAsync(300e6);
  if (!expect(await line(m, 'save "demo"'), 'SAVE "demo" returns to the prompt')) console.log(shown(m));
  const afterSave = screenText(m).slice(screenText(m).toLowerCase().lastIndexOf('save "demo"') + 11);
  expect(!/error|no card|full|protect/i.test(afterSave), `SAVE printed no error (${JSON.stringify(afterSave)})`);
  const card = m.sd.card();
  expect(card && card.violations.length === 0, `the storage firmware keeps to the SD protocol (${card?.violations.join('; ')})`);
  m.stop();

  // the file on the host: text, one line per program line
  const ls = JSON.parse(fat('ls', img).toString());
  const saved = ls.find(([n]) => /^DEMO(\.BAS)?$/.test(n));
  expect(saved, `the host sees the saved program (${JSON.stringify(ls)})`);
  if (saved) {
    const body = fat('get', img, saved[0]).toString('latin1');
    expect(/10 PRINT "saved"/i.test(body) && /20 PRINT 6\*7/i.test(body), `SAVE wrote the program as text: ${JSON.stringify(body)}`);
  }

  log('power cycle');
  m = await boot();
  if (!expect(await line(m, 'load "demo"') && !/not found|error/i.test(screenText(m).split(/load "demo"/i).at(-1)),
    'LOAD "demo" after the power cycle')) console.log(shown(m));
  if (!expect(await line(m, 'run', '42'), 'RUN prints "saved" and 42')) console.log(shown(m));
  expect(screenText(m).includes('saved'), 'the loaded program printed "saved"');
  if (!expect(await line(m, 'dir', 'HOSTPROG'), 'DIR lists the files')) console.log(shown(m));
  expect(/DEMO/.test(screenText(m)), 'DIR shows DEMO');
  if (!expect(await line(m, 'load "hostprog.bas"') && !/not found/i.test(screenText(m).split(/load "hostprog.bas"/i).at(-1)),
    'LOAD a program written on the host (HOSTPROG.BAS)')) console.log(shown(m));
  if (!expect(await line(m, 'run', 'FROM THE HOST'), 'it runs: 123 and "FROM THE HOST"')) console.log(shown(m));
  expect(screenText(m).includes('123'), 'the host program printed 123');
  m.stop();

  // a slow card: keys typed while SAVE waits on the card still arrive
  log('slow card: typing during SAVE');
  m = await boot({ sd: { writeMs: 250 } });
  m.type('10 print "slow"\n');
  await m.runAsync(200e6);
  m.type('save "slow"\n20 print 7*6+1\nrun\n');   // typed at once: most of it while SAVE waits on the card
  if (!expect(await m.runUntil(() => screenText(m).includes('43'), 20e9, 100e6), 'lines typed during a slow SAVE are kept and run afterwards (43)')) console.log(shown(m));
  expect(m.sd.card().stats.busyNs >= 250e6, `the card was busy ${m.sd.card().stats.busyNs / 1e6} ms`);
  m.stop();

  // SAVE with no card, a full card, a write-protected card
  const errors = [
    ['no card', { image: null }, /no (sd )?card|no medium/i],
    ['write-protected', { sd: { writeProtect: true } }, /protect/i],
    ['full', { image: 'full' }, /full/i],
  ];
  for (const [what, opts, msg] of errors) {
    if (opts.image === 'full') {
      opts.image = path.join(dir, 'full.img');
      fat('mkfs', opts.image, '2', '12');
      fat('fill', opts.image, 'BIG.DAT');
    }
    m = await boot(opts);
    m.type('10 print 1\n');
    await m.runAsync(200e6);
    const ok = await line(m, 'save "x"', undefined);
    if (!expect(ok && msg.test(screenText(m)), `SAVE with ${what}: the error message, then the prompt`)) console.log(shown(m));
    m.stop();
  }
  fs.rmSync(dir, { recursive: true, force: true });
}

// ------------------------------------------------------------------ E2E-008
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

async function e2e008() {
  log('E2E-008: the e-ink card as the console: boot to BASIC on the panel, run a program');
  if (!expect(backend === 'native', 'E2E-008 needs the native emulator (CUPC8_EMU=native)')) return;
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
  golden('E2E-008', panelText(m));
  panelGolden('E2E-008', p);
  // 10 s unused puts the controller in deep sleep; the next change wakes it
  // with a reset, after a partial refresh's row compare ran in the same poll
  await m.runAsync(11e9);
  m.type('x');
  expect(await m.runUntil(() => m.panel().refreshes[3] > p.refreshes[3], 3e9, 50e6), 'a key after deep sleep reaches the glass');
  const w = m.panel();
  expect(w.errors === 0, `waking from deep sleep: RST_N held low long enough (${w.errors}: ${w.error})`);
  m.stop();
}

const tests = { 'E2E-002': e2e002, 'E2E-003': e2e003, 'E2E-007': e2e007, 'E2E-008': e2e008 };
log(`backend: ${backend === 'native' ? 'native (emu/machine)' : 'machine.mjs'}`);
for (const [id, fn] of Object.entries(tests)) if (only ? only === id : !['E2E-007', 'E2E-008'].includes(id) || backend === 'native') await fn();
console.log(`${only ?? 'E2E'}: the whole-machine emulator, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
