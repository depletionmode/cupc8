// E2E-002..004 on the whole-machine emulator (test/emu/machine.mjs): the
// CPU and chipset RTL, the SRAM and ROM chip, and every card on its real
// firmware, with the host tool (tools/cupc8.py) talking to the system card.
//
//   node test/emu/test_e2e.mjs [E2E-002|E2E-003|E2E-004|E2E-007|E2E-008|E2E-009|E2E-010|E2E-011|E2E-012|E2E-013|E2E-014|E2E-015|E2E-016|E2E-017|E2E-020] [--record]
//
// E2E-007 (files on the storage card's microSD), E2E-008 (the e-ink card),
// E2E-010..012 (programs at $7000), E2E-013..014 (networking) and
// E2E-015..016 (BASIC graphics on the HDMI picture and the e-ink glass) need
// CUPC8_EMU=native: the SD card, panel and Wi-Fi models are only in the
// native emulator.
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
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' }, rom: Buffer.alloc(512 * 1024, 0xff), sysctl: true });
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
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'wifi' } });
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
  const slots = { 1: 'hdmi', 2: 'io', 3: 'storage' };
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

// ------------------------------------------------------------------ E2E-009
// Banked RAM (doc/proposals/extended-ram.md) on the whole machine: the
// chipset RTL's RAM_BANK and window, the SRAM's A16-A18, the real sysctl
// firmware's RAM_WRITE_FAR/RAM_READ_FAR through the bridge's 24-bit access,
// and the real kernel. The host writes across the bank 4/5 boundary; BASIC
// switches banks with POKE to $f205, reads what the host wrote through the
// window at $8000-$bfff and writes into banks 5 and 31; the host reads those
// back by physical address and by bank:offset.
async function e2e009() {
  log('E2E-009: banked RAM: far writes from the PC, BASIC through the window, far reads back');
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' }, sysctl: true });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  const pattern = Buffer.alloc(1024);
  for (let i = 0; i < pattern.length; i++) pattern[i] = (i * 7 + (i >> 8) * 3 + 1) & 0xff;
  const file = path.join(ROOT, 'build/emu/e2e009.bin');
  fs.writeFileSync(file, pattern);
  // SRAM $13e00-$141ff: the last 512 bytes of bank 4 and the first 512 of bank 5
  const w = await cupc8(m, 'ram', 'write', '0x13e00', file);
  expect(w.code === 0, `cupc8.py ram write 0x13e00 (far): ${w.out.trim()}`);
  const prog = [
    '10 poke 242, 5, 4', '20 peek 191, 0, a',            // bank 4, $bf00: SRAM $13f00
    '30 poke 242, 5, 5', '40 peek 128, 16, b',           // bank 5, $8010: SRAM $14010
    '50 poke 128, 32, 99',                               // bank 5, $8020: SRAM $14020
    '60 poke 242, 5, 31', '70 poke 191, 255, 123',       // bank 31, $bfff: SRAM $7ffff
    '80 poke 242, 5, 2', '90 peek 242, 5, c',
    '100 print a', '110 print b', '120 print c'];
  m.type(prog.join('\n') + '\nrun\n');
  const want = [pattern[0x100], pattern[0x210], 2].join('\n');
  if (!expect(await m.runUntil(() => screenText(m).includes(want), 5e9, 100e6),
    `BASIC reads the host's bytes through the window (${want.replace(/\n/g, ', ')})`)) console.log('---- screen\n' + screenText(m));
  const byte = async (...addr) => {
    const r = await cupc8(m, 'ram', 'read', ...addr, '1');
    const hex = /^[0-9a-f]{6} {2}([0-9a-f]{2})/m.exec(r.out);
    return r.code === 0 && hex ? parseInt(hex[1], 16) : `(${r.out.trim()})`;
  };
  const b5 = await byte('0x14020');
  expect(b5 === 99, `BASIC's POKE into bank 5 is at SRAM $14020 (${b5})`);
  const b31 = await byte('31:0x3fff');
  expect(b31 === 123, `BASIC's POKE into bank 31 is SRAM $7ffff, read as 31:$3fff (${b31})`);
  const back = path.join(ROOT, 'build/emu/e2e009-back.bin');
  const r = await cupc8(m, 'ram', 'read', '4:0x3e00', '1024', '-o', back);
  const got = r.code === 0 ? fs.readFileSync(back) : Buffer.alloc(0);
  const expectBack = Buffer.from(pattern);
  expectBack[0x220] = 99;                              // BASIC's write into bank 5
  expect(got.equals(expectBack), `cupc8.py ram read 4:0x3e00 1024 (far, across banks 4/5) gives the pattern and BASIC's byte (${r.out.trim()})`);
  m.stop();
}

// ------------------------------------------------------------------ programs at $7000
// The kernel API (doc/proposals/kernel-api.md): a program for $7000 built by
// tools/mkprg.py, run from the PC with `cupc8.py run` through the system card
// (E2E-010, E2E-012) or from the SD card with `exec` (E2E-011).
function mkprg(src) {
  fs.mkdirSync(path.join(ROOT, 'build/emu'), { recursive: true });
  const out = path.join(ROOT, 'build/emu', path.basename(src, '.s') + '.prg');
  execFileSync('python3', [path.join(ROOT, 'tools/mkprg.py'), path.join(ROOT, src), '-o', out], { stdio: 'pipe' });
  return out;
}

const count = (text, want) => text.split(want).length - 1;

// ------------------------------------------------------------------ E2E-010
// `cupc8.py run` on the HDMI machine: the program's body over USB into RAM at
// $7000 while the CPU runs, API_RUN set last; the terminal starts it from its
// key wait. tools/testdata/eink_prog.s calls the e-ink entries, which do
// nothing on HDMI and leave $ff. Then the bare binary, a second time, and
// the terminal still works.
async function e2e010() {
  log('E2E-010: cupc8.py run: a program into RAM at $7000 over USB, started by the terminal (HDMI)');
  if (!expect(backend === 'native', 'E2E-010 needs the native emulator (CUPC8_EMU=native)')) return;
  const prg = mkprg('tools/testdata/eink_prog.s');
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' }, sysctl: true });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  let r = await cupc8(m, 'run', prg);
  expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run eink_prog.prg: ${r.out.trim()}`);
  if (!expect(await waitFor(m, 'ST FF FF FF FF', 3e9), 'the program ran and printed')) console.log('---- screen\n' + screenText(m));
  const t = screenText(m);
  expect(t.includes('AUTO FF'), 'API_EINK_AUTO on HDMI: r0 = $ff');
  expect(t.includes('GET FF FF FF FF FF FF FF'), 'API_EINK_GET on HDMI: $ff, and $ff left in API_ARGS');
  expect(await m.runUntil(() => /ST FF FF FF FF\n+>> ?_?$/.test(screenText(m)), 2e9, 50e6), 'back at the prompt');
  // the bare binary (no header), again
  const bin = path.join(ROOT, 'build/emu/eink_prog.bin');
  fs.writeFileSync(bin, fs.readFileSync(prg).subarray(4));
  r = await cupc8(m, 'run', bin);
  expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run eink_prog.bin: ${r.out.trim()}`);
  expect(await m.runUntil(() => count(screenText(m), 'ST FF FF FF FF') === 2, 3e9, 50e6), 'it ran a second time');
  m.type('10 print 6*7\nrun\n');
  if (!expect(await waitFor(m, '42', 3e9), 'the terminal still works: a typed program runs')) console.log('---- screen\n' + screenText(m));
  // examples/hello: its light steps once a "second", ten API_WAIT_MS 100 on
  // the chipset's millisecond counter (each 100-101 ms) and its printing;
  // timed here in emulated time on the RTL, by its LEDs (GPO, to 0.2 ms;
  // the sim gives 1012-1013 ms)
  r = await cupc8(m, 'run', mkprg('examples/hello/hello.s'));
  expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run hello.prg: ${r.out.trim()}`);
  const at = [];
  for (const led of [2, 4, 8]) {
    if (!expect(await m.runUntil(() => m.state().gpo === led, 3e9, 0.2e6), `hello's light reaches $${led.toString(16)}`)) break;
    at.push(m.ns);
  }
  const gaps = at.slice(1).map((t, i) => Math.round((t - at[i]) / 1e6));
  log(`hello's steps: ${gaps} ms apart`);
  expect(gaps.length === 2 && gaps.every((g) => g >= 1000 && g <= 1015), `hello steps every 1000-1015 ms of emulated time (${gaps} ms)`);
  expect(screenText(m).includes('seconds 00'), 'hello counts seconds on the screen');
  m.type('x');
  expect(await waitFor(m, "You pressed 'x'", 2e9), 'a key stops hello; the terminal is back');
  m.stop();
}

// ------------------------------------------------------------------ E2E-011
// `exec "NAME"` from the SD card model: a program file (the "C8P" header,
// version 1; three of exec's chunks) runs at $7000; a BASIC file is loaded
// and run; a missing file says so.
async function e2e011() {
  log('E2E-011: exec from the storage card (microSD model): a program at $7000, a BASIC file');
  if (!expect(backend === 'native', 'E2E-011 needs the native emulator (CUPC8_EMU=native)')) return;
  const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-e2e011-'));
  const fat = (...a) => execFileSync(path.join(SDK, 'pyfat/bin/python'), [path.join(ROOT, 'test/emu/fatimg.py'), ...a]);
  const img = path.join(dir, 'card.img');
  fat('mkfs', img, '16', '16');
  const prg = mkprg('tools/testdata/exec_prog.s');
  fat('put', img, 'PROG.PRG', prg);
  // the same program with 24 KB after it (192 of exec's 128-byte chunk
  // reads, back to back: they caught the emulator's stray CS_n edges,
  // 08496f0, which the three chunks above no longer meet)
  const big = Buffer.concat([fs.readFileSync(prg), Buffer.alloc(24 * 1024 - (fs.statSync(prg).size - 4), 0xa5)]);
  fs.writeFileSync(path.join(dir, 'big'), big);
  fat('put', img, 'BIG.PRG', path.join(dir, 'big'));
  fs.writeFileSync(path.join(dir, 'bas'), '10 print 6*7\r\n20 print "BASIC OK"\r\n');
  fat('put', img, 'BAS', path.join(dir, 'bas'));
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage' } });
  m.sd.insert(img, { highCapacity: false });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  const shown = () => '---- screen\n' + screenText(m) + '\n----';
  // a command, then its output up to the prompt after it
  const line = async (text, want) => {
    m.type(text + '\n');
    return m.runUntil(() => {
      const t = screenText(m);
      const i = t.lastIndexOf(text);
      return i >= 0 && /\n>> ?_?$/.test(t.slice(i + text.length)) && t.slice(i + text.length).includes(want);
    }, 10e9, 100e6);
  };
  if (!expect(await line('exec "prog.prg"', 'NATIVE OK'), 'exec a program file: it prints NATIVE OK')) console.log(shown());
  m.type('clr\n');
  if (!expect(await line('exec "big.prg"', 'NATIVE OK'), 'exec a 24 KB program file (192 chunks): it prints NATIVE OK')) console.log(shown());
  if (!expect(await line('exec "bas"', 'BASIC OK'), 'exec a BASIC file: loaded and run')) console.log(shown());
  expect(screenText(m).includes('42'), 'the BASIC file printed 42');
  if (!expect(await line('exec "nothing"', 'file not found'), 'exec a missing file')) console.log(shown());
  // every rising CS_n edge a card's GPIO latched was a real deselect by the
  // chipset (08496f0: the emulator set CS_n high again at every sync, and
  // each call latched an edge the pin never had)
  for (const c of m.cards().filter((k) => k.csRises !== undefined)) {
    log(`slot ${c.slot} (${c.kind}): ${c.csEdges} CS_n rising edges latched, ${c.csRises} deselects`);
    expect(c.csRises > 0 && c.csEdges <= c.csRises,
      `slot ${c.slot} (${c.kind}): ${c.csEdges} rising CS_n edges latched for ${c.csRises} deselects`);
  }
  const card = m.sd.card();
  expect(card && card.violations.length === 0, `the storage firmware keeps to the SD protocol (${card?.violations.join('; ')})`);
  m.stop();
  fs.rmSync(dir, { recursive: true, force: true });
}

// ------------------------------------------------------------------ E2E-012
// The e-ink API on the e-ink card (eink-card.md: AUTO_EXT, AUTO_GET): a
// program run with `cupc8.py run` sets the policy through API_EINK_AUTO (on,
// idle10 5, full_after 2, cap10 50, full_kind 3 greyscale, sleep_s 3) and
// reads it back with API_EINK_GET; the panel model shows the effect: after 2
// partial refreshes the full one is greyscale, and the controller goes into
// deep sleep about 3 s after the last refresh (10 s by default).
async function e2e012() {
  log('E2E-012: the e-ink API on the e-ink card: set the refresh policy, read it back, see it on the panel');
  if (!expect(backend === 'native', 'E2E-012 needs the native emulator (CUPC8_EMU=native)')) return;
  const prg = mkprg('tools/testdata/eink_prog.s');
  const m = await Machine.create({ slots: { 1: 'eink', 2: 'io' }, sysctl: true });
  m.powerOn();
  const on = (want, ns) => m.runUntil(() => panelText(m).includes(want), ns, 50e6);
  expect(await on('>>', 10e9), 'the BASIC prompt appears on the panel');
  expect(await m.runUntil(() => m.panel().refreshes[0] >= 1 && m.panel().busy === 0, 10e9, 50e6),
    'the power-on clean refresh is done');
  const p0 = m.panel();
  const r = await cupc8(m, 'run', prg);
  expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run eink_prog.prg: ${r.out.trim()}`);
  if (!expect(await on('GET 00 01 05 02 32 03 03', 10e9),
    'API_EINK_GET reads back what API_EINK_AUTO set (on 1, idle10 5, full_after 2, cap10 50, full_kind 3, sleep_s 3)')) {
    console.log('---- panel\n' + panelText(m));
  }
  expect(panelText(m).includes('AUTO 00'), 'API_EINK_AUTO: r0 = 0');
  expect(/ST 00 [0-9A-F]{2} [0-9A-F]{2} [0-9A-F]{2}/.test(panelText(m)), 'API_EINK_STATUS: r0 = 0 and three bytes');
  // the program's output was one partial refresh; a key is the second
  expect(await m.runUntil(() => m.panel().refreshes[3] > p0.refreshes[3], 5e9, 50e6), 'a partial refresh for the output');
  await m.runUntil(() => m.panel().busy === 0, 5e9, 50e6);
  m.type('x');
  expect(await m.runUntil(() => m.panel().refreshes[3] >= p0.refreshes[3] + 2, 5e9, 50e6), 'a second partial refresh, for the key');
  // full_after 2, full_kind 3: once quiet, a greyscale full refresh (by default: after 30, a fast one)
  expect(await m.runUntil(() => m.panel().refreshes[2] > p0.refreshes[2], 10e9, 50e6), 'after 2 partials, a greyscale full refresh');
  expect(m.panel().refreshes[1] === p0.refreshes[1], `no fast full refresh (${m.panel().refreshes})`);
  await m.runUntil(() => m.panel().busy === 0, 5e9, 50e6);
  // sleep_s 3: deep sleep about 3 s after the last refresh
  expect(m.panel().asleep === 0, 'awake right after the refresh');
  await m.runAsync(2e9);
  expect(m.panel().asleep === 0, 'still awake 2 s later');
  expect(await m.runUntil(() => m.panel().asleep === 1, 2.5e9, 50e6), 'in deep sleep by 4.5 s (sleep_s 3; the default is 10)');
  const p = m.panel();
  expect(p.errors === 0, `the panel model saw nothing the chip would ignore (${p.errors}: ${p.error})`);
  m.stop();
}

// ------------------------------------------------------------------ E2E-013
// Networking in CUPC/8 assembly (doc/proposals/kernel-api.md, "Networking")
// on the real Wi-Fi firmware in QEMU: the kernel's DNS client asks a DNS
// server this test runs on the PC (`net config dns 10.0.2.2 PORT`),
// `net lookup` prints the address (and NXDOMAIN), `net get NAME PORT`
// resolves the name itself and fetches from the PC, `net ping 10.0.2.2`
// gets QEMU's echo replies over the card's raw ICMP socket. Native only.
function dnsAnswer(q, rcode, ip) {
  // q's id and question; QR RD RA; one A record named by a pointer to it
  let end = 12;
  while (q[end] !== 0) end += q[end] + 1;
  const question = q.subarray(12, end + 5);
  const head = Buffer.from([q[0], q[1], 0x81, 0x80 | rcode, 0, 1, 0, ip ? 1 : 0, 0, 0, 0, 0]);
  const rr = ip ? Buffer.from([0xc0, 12, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, ...ip]) : Buffer.alloc(0);
  return Buffer.concat([head, question, rr]);
}

function dnsName(q) {
  const parts = [];
  for (let i = 12; q[i] !== 0; i += q[i] + 1) parts.push(q.subarray(i + 1, i + 1 + q[i]).toString('latin1'));
  return parts.join('.');
}

async function e2e013() {
  log('E2E-013: net config, net lookup, net get NAME, net ping on the real Wi-Fi firmware');
  if (!expect(backend === 'native', 'E2E-013 needs the native emulator (CUPC8_EMU=native)')) return;
  const dgram = await import('node:dgram');
  const asked = [];
  const dns = dgram.createSocket('udp4');
  dns.on('message', (q, from) => {
    const name = dnsName(q);
    asked.push(name);
    const reply = name === 'host.cupc8.test' ? dnsAnswer(q, 0, [10, 0, 2, 2]) : dnsAnswer(q, 3, null);
    dns.send(reply, from.port, from.address);
  });
  await new Promise((r) => dns.bind(0, '127.0.0.1', r));
  const dnsPort = dns.address().port;
  const page = 'FETCHED BY NAME';
  let hostHeader = null;
  const server = http.createServer((req, res) => {
    hostHeader = req.headers.host;
    res.sendDate = false;
    res.writeHead(200, { 'Content-Type': 'text/plain', Connection: 'close' });
    res.end(page + '\n');
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const httpPort = server.address().port;

  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'wifi' } });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  // each command on a clear screen, run until its prompt (or `want`)
  const run = async (cmd, want, ns = 30e9) => {
    m.type('clr\n');
    await m.runUntil(() => !screenText(m).includes(cmd) && /^>> ?_?$/m.test(screenText(m)), 3e9, 50e6);
    m.type(cmd + '\n');
    const ok = await m.runUntil(() => {
      const t = screenText(m);
      const i = t.indexOf(cmd);
      return i >= 0 && t.slice(i + cmd.length).includes(want);
    }, ns, 50e6);
    if (!ok) console.log('---- screen\n' + screenText(m) + '\n----');
    return ok;
  };
  expect(await run('net join cupc8 password', 'joined, address 10.0.2.15'), 'net join');
  expect(await run(`net config dns 10.0.2.2 ${dnsPort}`, `dns 10.0.2.2 port ${dnsPort}`),
    'net config dns 10.0.2.2 PORT: the settings shown');
  expect(await run('net lookup host.cupc8.test', 'host.cupc8.test 10.0.2.2'), 'net lookup: the address the PC\'s DNS server gave');
  expect(asked.includes('host.cupc8.test'), `the PC's DNS server was asked (${asked})`);
  expect(await run('net lookup nx.cupc8.test', 'name not found'), 'net lookup of a name that does not exist: NXDOMAIN');
  expect(await run(`net get host.cupc8.test ${httpPort}`, page), 'net get NAME PORT: resolved by the kernel, fetched from the PC');
  expect(hostHeader === 'host.cupc8.test', `the request's Host header is the name (${hostHeader})`);
  expect(await run('net ping 10.0.2.2 2', 'received'), 'net ping 10.0.2.2 finishes');
  const t = screenText(m);
  expect(/seq 1 time \d+ ms/.test(t) && /seq 2 time \d+ ms/.test(t) && t.includes('2 sent, 2 received'),
    'net ping 10.0.2.2: QEMU answers both echo requests, times and the summary');
  expect(await run('net config', 'not saved'), 'net config shows the settings');
  m.stop();
  server.close();
  dns.close();
}

// ------------------------------------------------------------------ E2E-014
// The example echo servers (examples/net: user programs for $7000 on the
// kernel's net API, built by tools/mkprg.py after kernel/api.inc) loaded
// with `cupc8.py run` through the system card, on the real Wi-Fi firmware
// in QEMU, and reached from the PC through QEMU's port forwards
// (Machine.create({ forward })): two TCP clients one after the other, then
// (a second machine) UDP datagrams from two ports. Native only.
async function freePort(kind) {
  const net = await import('node:net');
  const dgram = await import('node:dgram');
  return new Promise((resolve) => {
    if (kind === 'tcp') {
      const s = net.createServer();
      s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
    } else {
      const s = dgram.createSocket('udp4');
      s.bind(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
    }
  });
}

async function e2e014() {
  log('E2E-014: the TCP and UDP echo servers (examples/net) run with cupc8.py run, reached through port forwards');
  if (!expect(backend === 'native', 'E2E-014 needs the native emulator (CUPC8_EMU=native)')) return;
  const net = await import('node:net');
  const dgram = await import('node:dgram');
  const tcpPrg = mkprg('examples/net/tcpecho.s');
  const udpPrg = mkprg('examples/net/udpecho.s');
  // a machine joined to QEMU's network with the server running
  const serve = async (prg, forward) => {
    const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'wifi' }, sysctl: true, forward });
    m.powerOn();
    expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
    m.type('net join cupc8 password\n');
    if (!expect(await waitFor(m, 'joined, address 10.0.2.15', 30e9), 'net join')) console.log('---- screen\n' + screenText(m));
    await m.runUntil(() => /\n>> ?_?$/.test(screenText(m)), 3e9, 50e6);
    const r = await cupc8(m, 'run', prg);
    expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run ${path.basename(prg)}: ${r.out.trim()}`);
    await m.runAsync(0.5e9, 50e6);            // it opens its socket and listens (or binds)
    return m;
  };

  // TCP: two clients in turn, each line comes back
  const tp = await freePort('tcp');
  let m = await serve(tcpPrg, [`tcp:${tp}:7007`]);
  for (const msg of ['hello cupc8\n', 'a second client, and a longer line to echo back\n']) {
    let got = '', closed = false, error = null;
    const c = net.connect(tp, '127.0.0.1', () => c.write(msg));
    c.on('data', (d) => (got += d));
    c.on('error', (e) => (error = e.message));
    c.on('close', () => (closed = true));
    const ok = await m.runUntil(() => got.length >= msg.length || error !== null, 20e9, 20e6);
    expect(ok && got === msg, `TCP: ${JSON.stringify(msg.trim())} comes back (${JSON.stringify(got)}${error ? ', ' + error : ''})`);
    c.end();
    await m.runUntil(() => closed, 5e9, 20e6);
    await m.runAsync(0.2e9, 20e6);            // the server takes the next client
  }
  expect(m.state().halted === 0, 'tcpecho still runs (the CPU not halted)');
  m.stop();

  // UDP: datagrams from two ports each come back to their sender
  const up = await freePort('udp');
  m = await serve(udpPrg, [`udp:${up}:7007`]);
  for (const msg of ['ping over UDP', 'another datagram, from another port']) {
    const s = dgram.createSocket('udp4');
    await new Promise((r) => s.bind(0, '127.0.0.1', r));
    let got = null;
    s.on('message', (d) => (got = d.toString()));
    s.send(msg, up, '127.0.0.1');
    const ok = await m.runUntil(() => got !== null, 20e9, 20e6);
    expect(ok && got === msg, `UDP from port ${s.address().port}: ${JSON.stringify(msg)} comes back (${JSON.stringify(got)})`);
    s.close();
  }
  m.stop();
}

// ------------------------------------------------------------------ E2E-015
// BASIC's graphics statements (doc/proposals/basic-graphics.md) on the HDMI
// card: a program draws in GFX mode (mode, cls, box filled and outlined,
// line, plot, palette) and the card's picture, decoded from its TMDS
// output, has the colours at the places drawn (each GFX pixel is 2 x 2).
// The ended program keeps the picture until a key; then TEXT and DONE.
async function e2e015() {
  log('E2E-015: a BASIC program draws in GFX mode; the HDMI picture, decoded');
  if (!expect(backend === 'native', 'E2E-015 needs the native emulator (CUPC8_EMU=native)')) return;
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' } });
  m.powerOn();
  expect(await waitFor(m, '>>', 6e9), 'the BASIC prompt appears on HDMI');
  const prog = ['10 mode 1', '20 cls 1', '30 box 20, 20, 60, 40, 196, 1', '40 line 0, 120, 319, 120, 15',
    '50 plot 160, 200, 226', '60 box 200, 150, 50, 30, 46', '70 palette 100, 0, 0, 255',
    '80 box 250, 20, 20, 20, 100, 1'];
  for (const l of prog) {
    m.type(l + '\n');
    await m.runAsync(150e6);
  }
  m.type('run\n');
  // [x, y, [r, g, b], what]: the default palette's VGA blue 1, the cube's
  // red 196, yellow 226 and green 46, white 15; entry 100 set to blue
  const want = [[5, 5, [0, 0, 170], 'cls 1: VGA blue'], [50, 40, [255, 0, 0], 'the filled box: red 196'],
    [20, 20, [255, 0, 0], 'the filled box\'s corner'], [79, 59, [255, 0, 0], 'its far corner'],
    [80, 60, [0, 0, 170], 'just past it: the background'], [0, 120, [255, 255, 255], 'the line: white 15'],
    [319, 120, [255, 255, 255], 'its far end'], [160, 200, [255, 255, 0], 'plot: yellow 226'],
    [200, 150, [0, 255, 0], 'the outline: green 46'], [249, 179, [0, 255, 0], 'its far corner'],
    [225, 165, [0, 0, 170], 'inside the outline: the background'], [260, 30, [0, 0, 255], 'palette 100 set to blue']];
  const near = (v, w) => Math.abs(v - w) <= 12;
  let f = null;
  let bad = [];
  const check = () => {
    f = m.frame();
    if (f.error) return false;
    bad = [];
    for (const [x, y, rgb, what] of want) {
      for (const [dx, dy] of [[0, 0], [1, 1]]) {
        const p = f.rgb[(2 * y + dy) * 640 + 2 * x + dx];
        const got = [(p >> 16) & 0xff, (p >> 8) & 0xff, p & 0xff];
        if (!got.every((v, i) => near(v, rgb[i]))) bad.push(`${what} (${x}, ${y}): ${got} not ${rgb}`);
      }
    }
    return bad.length === 0;
  };
  if (!expect(await m.runUntil(check, 20e9, 200e6), 'the picture has the colours drawn')) {
    console.log(f?.error ?? bad.join('\n'));
  }
  expect(!screenText(m).includes('DONE.'), 'the program waits for a key with its picture up');
  m.type(' ');
  if (!expect(await waitFor(m, 'DONE.', 3e9), 'a key: TEXT again, and DONE.')) console.log('---- screen\n' + screenText(m));
  m.type('new\n10 print 6*7\nrun\n');
  expect(await waitFor(m, '42', 3e9), 'the terminal works on');
  m.stop();
}

// ------------------------------------------------------------------ E2E-016
// The e-ink card's native mode 2 from BASIC: mode 2, boxes in greys 0, 1
// and 2 on white, a line, an outline, then refresh (greyscale in mode 2).
// Once the UC8179 model has finished the refresh, its glass has the four
// greys at the places drawn. A key brings TEXT back on the panel.
async function e2e016() {
  log('E2E-016: a BASIC program draws in the e-ink card\'s mode 2; the four greys on the glass');
  if (!expect(backend === 'native', 'E2E-016 needs the native emulator (CUPC8_EMU=native)')) return;
  const m = await Machine.create({ slots: { 1: 'eink', 2: 'io' } });
  m.powerOn();
  const on = (text, ns) => m.runUntil(() => panelText(m).includes(text), ns, 50e6);
  expect(await on('>>', 10e9), 'the BASIC prompt appears on the panel');
  const prog = ['10 mode 2', '20 cls', '30 box 20, 20, 100, 60, 0, 1', '40 box 140, 20, 100, 60, 1, 1',
    '50 box 260, 20, 100, 60, 2, 1', '60 line 0, 300, 647, 300, 0', '70 box 400, 200, 50, 50, 1', '80 refresh'];
  for (const l of prog) {
    m.type(l + '\n');
    await m.runAsync(150e6);
  }
  const g0 = m.panel().refreshes[2];
  m.type('run\n');
  expect(await m.runUntil(() => m.panel().refreshes[2] > g0 && m.panel().busy === 0, 20e9, 50e6),
    'refresh: a greyscale refresh of the panel');
  const p = m.panel();
  const at = (x, y) => p.grey[y * p.w + x];
  const want = [[70, 50, 0, 'grey 0: black'], [190, 50, 85, 'grey 1: dark grey'], [310, 50, 170, 'grey 2: light grey'],
    [500, 400, 255, 'cls: white'], [0, 300, 0, 'the line\'s start'], [647, 300, 0, 'its end, at the panel\'s edge'],
    [400, 200, 85, 'the outline in grey 1'], [449, 249, 85, 'its far corner'], [425, 225, 255, 'inside it: white'],
    [20, 20, 0, 'the black box\'s corner'], [119, 79, 0, 'its far corner'], [120, 80, 255, 'just past it']];
  const bad = want.filter(([x, y, v]) => Math.abs(at(x, y) - v) > 8).map(([x, y, v, what]) => `${what} (${x}, ${y}): ${at(x, y)} not ${v}`);
  if (!expect(bad.length === 0, 'the four greys on the glass where drawn')) console.log(bad.join('\n'));
  expect(p.errors === 0, `the panel model saw nothing the chip would ignore (${p.errors}: ${p.error})`);
  m.type(' ');
  if (!expect(await on('DONE.', 20e9), 'a key: TEXT again on the panel, and DONE.')) console.log(panelText(m));
  m.stop();
}

// ------------------------------------------------------------------ E2E-017
// examples/snake on the e-ink card: mode 2, 16-pixel cells 4 in from the
// panel's left; a greyscale refresh shows the field, then a partial refresh
// after each step. S typed mid-game turns the snake down, and the glass shows
// it; Q gives TEXT and the goodbye on the panel (the automatic refresh back).
async function e2e017() {
  log('E2E-017: examples/snake on the e-ink card; S steers it, on the glass');
  if (!expect(backend === 'native', 'E2E-017 needs the native emulator (CUPC8_EMU=native)')) return;
  const prg = mkprg('examples/snake/snake.s');
  const m = await Machine.create({ slots: { 1: 'eink', 2: 'io' }, sysctl: true });
  m.powerOn();
  expect(await m.runUntil(() => panelText(m).includes('>>'), 10e9, 50e6), 'the BASIC prompt appears on the panel');
  const r = await cupc8(m, 'run', prg);
  expect(r.code === 0 && /bytes at \$7000, running/.test(r.out), `cupc8.py run snake.prg: ${r.out.trim()}`);
  const glass = (x, y) => { const p = m.panel(); return p.grey[y * p.w + x]; };
  const cell = (cx, cy) => glass(4 + cx * 16 + 8, cy * 16 + 8);
  expect(await m.runUntil(() => m.panel().refreshes[2] >= 1 && m.panel().busy === 0, 20e9, 50e6),
    'a greyscale refresh shows the field');
  expect(Math.abs(cell(0, 15) - 85) <= 8 && cell(12, 15) === 0 && cell(5, 5) === 255 && glass(1, 240) === 255,
    `the wall grey, the snake black, the ground and the margin white (${cell(0, 15)} ${cell(12, 15)} ${cell(5, 5)} ${glass(1, 240)})`);
  const p0 = m.panel().refreshes[3];
  expect(await m.runUntil(() => cell(14, 15) === 0, 10e9, 20e6), 'the snake moves right on the glass (partial refreshes)');
  expect(m.panel().refreshes[3] > p0, 'by partial refreshes');
  m.type('s');
  let at = -1;
  expect(await m.runUntil(() => {
    for (let x = 14; x <= 19; x++) if (cell(x, 16) === 0) { at = x; return true; }
    return false;
  }, 10e9, 20e6), 'S typed mid-game: the glass shows the snake turned down');
  expect(at >= 0 && cell(at + 1, 15) === 255, `... and not gone on right (cell ${at})`);
  m.type('q');
  if (!expect(await m.runUntil(() => panelText(m).includes('Thanks for playing snake.'), 20e9, 50e6),
    'Q: TEXT and the goodbye on the panel')) console.log(panelText(m));
  const p = m.panel();
  expect(p.errors === 0, `the panel model saw nothing the chip would ignore (${p.errors}: ${p.error})`);
  m.stop();
}

// ------------------------------------------------------------------ E2E-020
// The USB console (doc/proposals/usb-console.md) on the real system card
// firmware and the real kernel: the banner and a command's output read from
// the card's second serial port, a BASIC program pasted into it runs, and
// with the port closed (HOST clear) the kernel never waits on the ring.
async function e2e020() {
  log('E2E-020: the USB console: output, typed commands, a pasted program; closed, nothing waits');
  if (!expect(backend === 'native', 'E2E-020 needs the native emulator (CUPC8_EMU=native)')) return;
  const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' }, sysctl: true });
  let text = '';
  const got = () => (text += m.console.read().toString('latin1'));
  const until = async (want, ns) => {
    const ok = await m.runUntil(() => got().includes(want), ns, 20e6);
    if (!ok) console.log('---- console\n' + JSON.stringify(text) + '\n---- screen\n' + screenText(m) + '\n----');
    return ok;
  };
  m.console.open();                        // before power-on: the kernel's boot zeroes the rings, the card sets HOST again
  m.powerOn();
  expect(await until('>>', 6e9), 'the banner and the prompt arrive on the console port');
  expect(text.startsWith('\r\n      CUPC/8 BASIC'), `the banner first, no power-up junk before it: ${JSON.stringify(text.slice(0, 80))}`);
  expect(/\r\n/.test(text) && !/[^\r]\n/.test(text), 'newlines arrive as CR LF');
  expect(await waitFor(m, '>>', 1e9), 'and on HDMI, as before');

  // a command typed on the PC: echoed, run, its output back (and on HDMI)
  text = '';
  m.console.write('help\r');
  expect(await until('NEW RUN CLR', 3e9), 'help typed on the console: its output comes back');
  expect(text.startsWith('help'), `the typed line is echoed: ${JSON.stringify(text.slice(0, 20))}`);
  expect(await waitFor(m, 'NEW RUN CLR', 1e9), 'the output is on HDMI too');

  // a program pasted in one go (more than CON_IN's 64 bytes, LF line ends
  // as a PC's clipboard has them), then run
  text = '';
  const prog = ['10 rem pasted over the usb console', '20 for i = 1 to 3', '30 print i * 7', '40 next i', 'run'];
  m.console.write(prog.join('\n') + '\n');
  expect(await until('DONE.', 20e9), 'the pasted program runs to DONE.');
  expect(/\r\n7\r\n14\r\n21\r\n/.test(text), `its output on the console: ${JSON.stringify(text.slice(-60))}`);
  expect(await waitFor(m, '21', 1e9), 'and on HDMI');

  // closed: HOST is cleared, and a program printing ~5 KB (40 times the
  // ring) runs at the speed it runs with no system card at all
  m.console.close();
  await m.runAsync(20e6);
  m.console.read();
  // on the USB keyboard, each line once the last one is on screen
  const lines = ['new', '10 for i = 1 to 200', '20 print "the console port is closed"', '30 next i'];
  const typeLines = async (mm) => {
    for (const l of lines) {
      mm.type(l + '\n');
      expect(await mm.runUntil(() => {
        const t = screenText(mm), i = t.lastIndexOf('>> ' + l);   // the line, then the next prompt
        return i >= 0 && t.slice(i + 3 + l.length).includes('>>');
      }, 3e9, 20e6), `typed: ${l}`);
    }
    mm.type('clr\n');
    expect(await mm.runUntil(() => !screenText(mm).includes('30 next i'), 3e9, 20e6), 'clr');
  };
  await typeLines(m);
  const t0 = m.ns;
  m.type('run\n');
  const done = await waitFor(m, 'DONE.', 60e9);
  const took = (m.ns - t0) / 1e9;
  if (!expect(done && screenText(m).includes('the console port is closed'), 'closed: the long program runs to DONE.')) {
    console.log('---- screen\n' + screenText(m) + '\n----');
  }
  expect(m.console.read().length === 0, 'closed: nothing is sent to the PC');
  log(`closed: 200 lines in ${took.toFixed(2)} s emulated`);
  m.stop();

  // the same program with no system card: the kernel drops its ring output
  // the same way, so it takes as long
  const n = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' } });
  n.powerOn();
  expect(await waitFor(n, '>>', 6e9), 'no system card: the prompt');
  await typeLines(n);
  const t1 = n.ns;
  n.type('run\n');
  expect(await waitFor(n, 'DONE.', 60e9), 'no system card: the long program runs to DONE.');
  const bare = (n.ns - t1) / 1e9;
  log(`no system card: 200 lines in ${bare.toFixed(2)} s emulated`);
  expect(took < bare * 1.1 + 0.2, `closed console: no waiting (${took.toFixed(2)} s vs ${bare.toFixed(2)} s without the card)`);
  n.stop();
}

const tests = { 'E2E-002': e2e002, 'E2E-003': e2e003, 'E2E-007': e2e007, 'E2E-008': e2e008, 'E2E-009': e2e009,
  'E2E-010': e2e010, 'E2E-011': e2e011, 'E2E-012': e2e012, 'E2E-013': e2e013,
  'E2E-014': e2e014, 'E2E-015': e2e015, 'E2E-016': e2e016, 'E2E-017': e2e017, 'E2E-020': e2e020 };
const nativeOnly = ['E2E-007', 'E2E-008', 'E2E-010', 'E2E-011', 'E2E-012', 'E2E-013', 'E2E-014', 'E2E-015', 'E2E-016',
  'E2E-017', 'E2E-020'];
log(`backend: ${backend === 'native' ? 'native (emu/machine)' : 'machine.mjs'}`);
for (const [id, fn] of Object.entries(tests)) if (only ? only === id : !nativeOnly.includes(id) || backend === 'native') await fn();
console.log(`${only ?? 'E2E'}: the whole-machine emulator, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
