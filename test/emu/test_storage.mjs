// STO-010: the real storage card firmware (build/rp2040/storage.elf) on the
// native RP2040 emulator with the SD card model in its microSD socket
// (emu/rp2040/harness/sdcard.h, SPI1), driven through its slot pins by the
// CPU-side slot host with CUPC/8 SPI timing, as IOC-004 drives the IO card.
// The commands are doc/hardware/storage-card.md's. The card images are FAT
// volumes made and checked on the host with a separate FAT implementation
// (test/emu/fatimg.py: pyfatfs, and fsck.fat when installed), so files go
// both ways: written by the card and read on the host, and the reverse.
//
//   CUPC8_EMU=native node test/emu/test_storage.mjs [fat16,fat32,slow,removal,wp,full]
//   GAP=ns: the host's gap between frames (default slot.md's minimum, 20 us)
//
// Native only (the SD model is not in rp2040js).

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Emu, SlotHost, SdSocket, NATIVE } from './emu_backend.mjs';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
const PY = path.join(SDK, 'pyfat/bin/python');
const only = process.argv[2];
if (!NATIVE) {
  console.log('STO-010: needs the native emulator (CUPC8_EMU=native)');
  process.exit(1);
}
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-storage-'));
const fat = (...a) => execFileSync(PY, [path.join(ROOT, 'test/emu/fatimg.py'), ...a]);
const fatLs = (img) => Object.fromEntries(JSON.parse(fat('ls', img).toString()));
// a file as the host reads it, or null
function fatGet(img, name) {
  try {
    return execFileSync(PY, [path.join(ROOT, 'test/emu/fatimg.py'), 'get', img, name], { stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return null;
  }
}
function fatCheck(img) {
  try {
    fat('check', img);
    return 'ok';
  } catch (e) {
    return (e.stdout?.toString() ?? '') + (e.stderr?.toString() ?? e.message);
  }
}
function image(name, mb, bits, files = {}) {
  const img = path.join(dir, name);
  fat('mkfs', img, String(mb), String(bits));
  for (const [n, data] of Object.entries(files)) {
    const f = path.join(dir, 'put.bin');
    fs.writeFileSync(f, data);
    fat('put', img, n, f);
  }
  return img;
}

let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
  return cond;
}

const emu = await Emu.load(path.join(ROOT, 'build/rp2040/storage.elf'), { mhz: 125 });
const host = new SlotHost(emu, { clkDiv: 2, frameGapNs: Number(process.env.GAP ?? 20000) });
const sd = new SdSocket(emu);

function run(script, ns = 10e9) {
  host.run(script);
  let done;
  try {
    done = emu.runUntil(() => host.done, ns);
  } catch (e) {
    console.log(`FAIL the card crashed at ${(emu.ns / 1e6).toFixed(3)} ms: ${e.message}`);
    process.exit(1);
  }
  if (!done) {
    console.log('FAIL the card stopped answering (host script timed out)');
    process.exit(1);
  }
  return host.result;
}
const wait = (ns) => run(function* () { yield ns; });
// the status byte, from a bare READ frame (READ is not a command: it neither
// starts nor discards anything, slot.md)
const status = () => run(function* () { return (yield* this.frame([0xfe]))[0]; });
// a command with no response (BUF_PUT): done when BUSY clears
function post(bytes) {
  run(function* () { yield* this.frame(bytes); });
  return until(S.BUSY, false, 3000);
}
// a command and its response; medium operations may take long (RESP_LEN 0 meanwhile)
const LONG = { tries: 60000, retryNs: 50000 };  // 3 s
function cmd(bytes, opts = LONG) {
  const n0 = host.log.length;
  const r = run(function* () { yield* this.frame(bytes); return yield* this.read(opts); });
  if (process.env.DEBUG > 1) for (const f of host.log.slice(n0)) console.log('   mosi', f.mosi.slice(0, 6).map((b) => b.toString(16)).join(' '), 'miso', f.miso.slice(0, 8).map((b) => b.toString(16)).join(' '), '@', (emu.ns / 1e6).toFixed(3));
  if (process.env.DEBUG) console.log('cmd', bytes.slice(0, 8).map((b) => b.toString(16)).join(' '), '->', r && [r.status.toString(16), ...r.data.slice(0, 12)].join(' '));
  return r;
}
const S = { MEDIA: 0x40, MOUNTED: 0x20, BUSY: 0x10, WP: 0x08 };
const E = { OK: 0, NOMEDIA: 1, NOTMOUNTED: 2, NOTFOUND: 3, EXISTS: 4, FULL: 5, WP: 6, BADHANDLE: 7, BADNAME: 8, IO: 9, TOOMANY: 10 };
const nm = (s) => [s.length, ...Buffer.from(s, 'latin1')];
const le32 = (v) => [v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255];
const u32 = (d, i) => (d[i] | (d[i + 1] << 8) | (d[i + 2] << 16) | (d[i + 3] << 24)) >>> 0;
const err = (r) => (r && r.data.length ? r.data[0] : -1);

const info = () => {
  const r = cmd([0x01]);
  return r && { media: r.data[0], err: r.data[1], flags: r.data[2], free: u32(r.data, 3), total: u32(r.data, 7) };
};
const open = (h, mode, name) => err(cmd([0x10, h, mode, ...nm(name)]));
const close = (h) => err(cmd([0x13, h]));
const write = (h, bytes) => err(cmd([0x12, h, bytes.length, ...bytes]));
function read(h, n) {
  const r = cmd([0x11, h, n]);
  return r ? r.data.slice(1, 1 + r.data[0]) : null;
}
function writeFile(name, data, mode = 1, h = 0) {
  let e = open(h, mode, name);
  if (e) return { at: 'open', e };
  for (let i = 0; i < data.length; i += 128) {
    e = write(h, [...data.subarray(i, i + 128)]);
    if (e) {
      close(h);
      return { at: `write @${i}`, e };
    }
  }
  e = close(h);
  return e ? { at: 'close', e } : null;
}
function readFile(name, h = 0) {
  if (open(h, 0, name)) return null;
  const out = [];
  for (;;) {
    const d = read(h, 128);
    if (!d) return null;
    out.push(...d);
    if (d.length < 128) break;
  }
  close(h);
  return Buffer.from(out);
}
// the directory: name -> size; a DIR entry is size32, attr, name (length-prefixed or not)
function listDir() {
  const out = {};
  for (let r = cmd([0x15]), n = 0; r && !(r.data.length === 1 && r.data[0] === 0xff) && n < 100; r = cmd([0x16]), n++) {
    const d = r.data;
    let name = d.slice(5);
    if (name.length && name[0] === name.length - 1) name = name.slice(1);
    out[Buffer.from(name).toString('latin1').replace(/\0+$/, '')] = u32(d, 0);
  }
  return out;
}
// until the status byte has all of `bits` (or none of them), for up to `ms`
function until(bits, set, ms = 3000) {
  let st = 0;
  for (let i = 0; i < ms; i++) {
    st = status();
    if (!(st & 0x80) && (set ? (st & bits) === bits : !(st & bits))) return st;
    wait(1e6);
  }
  return st;
}
const text = (n, seed = 0) => Buffer.from(Array.from({ length: n }, (_, i) => (i % 64 === 63 ? 10 : 32 + ((i * 7 + seed) % 95))));
function insert(img, opts = {}) {
  sd.insert(img, opts);
  return until(S.MEDIA | S.MOUNTED, true);
}
function pull() {
  const card = sd.card();
  sd.remove();
  return card;
}
function noViolations(card, what) {
  expect(card && card.violations.length === 0, `${what}: the firmware keeps to the SD protocol (${card?.violations.join('; ')})`);
  expect(card && card.stats.maxHzBeforeInit <= 400e3, `${what}: SCK <= 400 kHz until initialised (${card?.stats.maxHzBeforeInit} Hz)`);
}
const section = (name) => !only || only.split(',').includes(name);
const t0 = performance.now();

// ---------------------------------------------------------------- no card
let s0 = 0xff;
for (let i = 0; i < 200 && s0 === 0xff; i++) {
  s0 = status();
  if (s0 === 0xff) wait(1e6);
}
expect(s0 !== 0xff, 'the card answers within 200 ms of power-on');
const ident = cmd([0xf0]);
expect(ident && ident.data[0] === 0x04 && ident.data[3] === 0xc8, `IDENT says storage card ($04): ${JSON.stringify(ident?.data)}`);
expect(!(s0 & (S.MEDIA | S.MOUNTED)), `no card: MEDIA and MOUNTED clear (status $${s0.toString(16)})`);
let inf = info();
expect(inf && inf.media === 0, `no card: ST_INFO media 0 (${JSON.stringify(inf)})`);
expect(open(0, 0, 'ANY.TXT') === E.NOMEDIA, 'no card: F_OPEN is "no medium" ($01)');
expect(writeFile('ANY.TXT', text(10))?.e === E.NOMEDIA, 'no card: SAVE-like write is "no medium"');

// ------------------------------------------------ an SDSC FAT16 card, both ways
if (section('fat16')) {
  const hostText = text(700, 3);
  const img = image('fat16.img', 16, 16, { 'HOST.TXT': hostText, 'EMPTY.TXT': Buffer.alloc(0) });
  const st = insert(img, { highCapacity: false });
  expect((st & (S.MEDIA | S.MOUNTED)) === (S.MEDIA | S.MOUNTED), `SDSC: mounted on insertion (status $${st.toString(16)})`);
  inf = info();
  expect(inf && inf.media === 1 && inf.err === 0, `ST_INFO: media 1 (microSD), err 0 (${JSON.stringify(inf)})`);
  expect(inf && inf.total > 15000 && inf.total <= 16384 && inf.free > 14000 && inf.free < inf.total, `ST_INFO: total ${inf?.total} KB, free ${inf?.free} KB of a 16 MB FAT16 card`);
  const d = listDir();
  expect(d['HOST.TXT'] === 700 && d['EMPTY.TXT'] === 0, `DIR: the host's files with their sizes (${JSON.stringify(d)})`);
  const got = readFile('HOST.TXT');
  expect(got && got.equals(hostText), `a file written on the host reads back on the card (${got?.length} bytes)`);
  const empty = readFile('EMPTY.TXT');
  expect(empty && empty.length === 0, 'an empty file reads as end of file at once');

  // files written by the card: several chunks, a partial one, append, two handles at once
  const a = text(1000, 1), b = text(300, 2), c = text(100, 4);
  expect(writeFile('CARD.TXT', a) === null, 'F_OPEN write, 8 F_WRITEs (the last partial), F_CLOSE: all ok');
  expect(writeFile('CARD.TXT', c, 2) === null, 'F_OPEN append, F_WRITE, F_CLOSE: ok');
  expect(open(1, 1, 'ONE.TXT') === 0 && open(2, 1, 'TWO.TXT') === 0, 'two files open for writing at once (handles 1, 2)');
  let ok = true;
  for (let i = 0; i < 300; i += 100) {
    ok &&= write(1, [...b.subarray(i, i + 100)]) === 0;
    ok &&= write(2, [...a.subarray(i, i + 100)]) === 0;
  }
  ok &&= close(1) === 0 && close(2) === 0;
  expect(ok, 'interleaved writes on two handles, both closed');
  expect(readFile('CARD.TXT')?.equals(Buffer.concat([a, c])), 'CARD.TXT reads back on the card');
  const d2 = listDir();
  expect(d2['CARD.TXT'] === 1100 && d2['ONE.TXT'] === 300 && d2['TWO.TXT'] === 300, `DIR after writing (${JSON.stringify(d2)})`);

  // F_SEEK
  expect(open(0, 0, 'CARD.TXT') === 0 && err(cmd([0x14, 0, ...le32(990)])) === 0, 'F_SEEK to 990');
  const tail = read(0, 20);
  close(0);
  expect(tail && Buffer.from(tail).equals(Buffer.concat([a, c]).subarray(990, 1010)), 'F_READ after F_SEEK gives bytes 990..1009');

  // errors
  expect(open(0, 0, 'NOPE.TXT') === E.NOTFOUND, 'F_OPEN of a missing file: "not found" ($03)');
  expect(open(0, 1, 'TOOLONGNAME.TXT') === E.BADNAME, 'F_OPEN of a name that is not 8.3: "bad name" ($08)');
  expect(open(7, 0, 'CARD.TXT') === E.BADHANDLE, 'handle 7: "bad handle" ($07)');
  expect(read(3, 10) === null || err(cmd([0x13, 3])) !== 0, 'a handle that is not open cannot be read or closed');
  expect(err(cmd([0x18, ...nm('ONE.TXT'), ...nm('TWO.TXT')])) === E.EXISTS, 'F_RENAME onto an existing name: "exists" ($04)');
  expect(err(cmd([0x18, ...nm('ONE.TXT'), ...nm('UNO.TXT')])) === 0, 'F_RENAME ONE.TXT to UNO.TXT');
  expect(err(cmd([0x17, ...nm('TWO.TXT')])) === 0 && err(cmd([0x17, ...nm('TWO.TXT')])) === E.NOTFOUND, 'F_DELETE, then "not found"');

  // raw blocks: the boot sector, and a write to the last sector (restored after)
  const img0 = fs.readFileSync(img);
  expect(err(cmd([0x20, ...le32(0)])) === 0, 'BLK_READ 0');
  let boot = [];
  for (let off = 0; off < 512; off += 128) boot.push(...(cmd([0x22, off & 255, off >> 8, 128])?.data ?? []));
  expect(Buffer.from(boot).equals(img0.subarray(0, 512)), 'BUF_GET x4: the boot sector as on the image');
  const last = img0.length / 512 - 1;
  const pat = Buffer.from(Array.from({ length: 512 }, (_, i) => (i * 13) & 255));
  for (let off = 0; off < 512; off += 128) post([0x23, off & 255, off >> 8, 128, ...pat.subarray(off, off + 128)]);
  expect(err(cmd([0x21, ...le32(last)])) === 0, `BUF_PUT x4, BLK_WRITE ${last}`);
  expect(err(cmd([0x20, ...le32(last)])) === 0, 'BLK_READ it back');
  const back = [];
  for (let off = 0; off < 512; off += 128) back.push(...(cmd([0x22, off & 255, off >> 8, 128])?.data ?? []));
  expect(Buffer.from(back).equals(pat), 'the sector reads back as written');
  const saved = img0.subarray(last * 512, last * 512 + 512);
  for (let off = 0; off < 512; off += 128) post([0x23, off & 255, off >> 8, 128, ...saved.subarray(off, off + 128)]);
  cmd([0x21, ...le32(last)]);

  expect(err(cmd([0x03])) === 0, 'ST_EJECT: ok');
  const se = until(S.MOUNTED, false);
  expect(!(se & S.MOUNTED), `ST_EJECT: MOUNTED clear (status $${se.toString(16)})`);
  const card = pull();
  noViolations(card, 'SDSC');
  expect(fs.readFileSync(img).subarray(last * 512, last * 512 + 512).equals(saved), 'the raw block write reached the image and was restored');
  const ls = fatLs(img);
  expect(ls['CARD.TXT'] === 1100 && ls['UNO.TXT'] === 300 && !('TWO.TXT' in ls) && !('ONE.TXT' in ls), `the host sees the card's files (${JSON.stringify(ls)})`);
  expect(fatGet(img, 'CARD.TXT')?.equals(Buffer.concat([a, c])), 'the host reads CARD.TXT as the card wrote it');
  expect(fatGet(img, 'UNO.TXT')?.equals(b), 'the host reads UNO.TXT (renamed) as written');
  const chk = fatCheck(img);
  expect(chk.startsWith('ok'), `the host's FAT check passes on the card's writes (${chk.trim()})`);
  const s1 = until(S.MEDIA, false);
  expect(!(s1 & (S.MEDIA | S.MOUNTED)), `card out: MEDIA and MOUNTED clear (status $${s1.toString(16)})`);
}

// ------------------------------------------------ an SDHC FAT32 card
if (section('fat32')) {
  const img = image('fat32.img', 40, 32, { 'README.TXT': text(2000, 9) });
  const st = insert(img, { highCapacity: true });
  expect((st & S.MOUNTED) !== 0, `SDHC FAT32: mounted (status $${st.toString(16)})`);
  expect(readFile('README.TXT')?.equals(text(2000, 9)), 'SDHC: a 2000-byte host file reads back');
  const big = text(5000, 5);
  expect(writeFile('BIG.TXT', big) === null, 'SDHC: a 5000-byte file written (40 chunks)');
  expect(readFile('BIG.TXT')?.equals(big), 'SDHC: and read back on the card');
  cmd([0x03]);
  noViolations(pull(), 'SDHC');
  expect(fatGet(img, 'BIG.TXT')?.equals(big), 'SDHC: the host reads BIG.TXT');
  const chk = fatCheck(img);
  expect(chk.startsWith('ok'), `SDHC: the host's FAT check passes (${chk.trim()})`);
}

// ------------------------------------- a slow card: the slot stays live
if (section('slow')) {
  const img = image('slow.img', 16, 16);
  insert(img, { highCapacity: false, writeMs: 250 });
  const data = text(1024, 7);
  expect(open(0, 1, 'SLOW.TXT') === 0, 'slow card (250 ms per block): F_OPEN');
  for (let i = 0; i < 1024; i += 128) write(0, [...data.subarray(i, i + 128)]);
  // F_CLOSE flushes: time it while polling the status byte every 200 us
  const polled = run(function* () {
    yield* this.frame([0x13, 0]);
    yield 1e6;
    const early = yield* this.frame([0xfe, 0x00]);  // a bare READ 1 ms in: not ready yet
    let n = 0, busy = 0, answered = 0, resp = null;
    for (let i = 0; i < 20000 && !resp; i++) {
      yield 200e3;
      const st = (yield* this.frame([0xfe]))[0];
      n++;
      if (!(st & 0x80)) answered++;
      if (st & 0x10) busy++;
      else resp = yield* this.read(LONG);
    }
    return { early, n, busy, answered, resp };
  });
  expect(polled.resp && polled.resp.data[0] === 0, `slow card: F_CLOSE completes ok (${JSON.stringify(polled.resp)})`);
  expect(polled.early[1] === 0 && (polled.early[0] & S.BUSY), `slow card: a READ during the write gives RESP_LEN 0 with BUSY set (${polled.early})`);
  expect(polled.answered === polled.n, `slow card: every status frame answered while the card writes (${polled.answered}/${polled.n})`);
  expect(polled.busy >= 1000, `slow card: BUSY stays set through the write (${polled.busy} polls x 200 us)`);
  const card = pull();
  expect(card.stats.busyNs >= 250e6, `the model was busy ${card.stats.busyNs / 1e6} ms`);
  noViolations(card, 'slow card');
  expect(fatGet(img, 'SLOW.TXT')?.equals(data), 'slow card: the host reads SLOW.TXT');
}

// ------------------------------------------------ hot removal
if (section('removal')) {
  const img = image('hot.img', 16, 16, { 'KEEP.TXT': text(500, 11) });
  insert(img, { highCapacity: false, writeMs: 50 });
  expect(writeFile('DONE.TXT', text(400, 12)) === null, 'removal: a file written and closed first');
  expect(open(0, 1, 'WIP.TXT') === 0, 'removal: another opened for writing');
  write(0, [...text(128, 13)]);
  write(0, [...text(128, 14)]);
  // pull it in the middle of the next write
  run(function* () { yield* this.frame([0x12, 0, 128, ...text(128, 15)]); yield 20e6; });
  pull();
  const st = until(S.MEDIA | S.MOUNTED, false, 50);
  expect(!(st & (S.MEDIA | S.MOUNTED)), `card pulled: MEDIA and MOUNTED clear within 50 ms (status $${st.toString(16)})`);
  expect(write(0, [...text(10, 16)]) === E.NOMEDIA, 'card pulled: F_WRITE on the open handle fails with "no medium"');
  close(0);
  const s2 = insert(img, { highCapacity: false });
  expect((s2 & S.MOUNTED) !== 0, `put back: mounted again (status $${s2.toString(16)})`);
  expect(readFile('KEEP.TXT')?.equals(text(500, 11)) && readFile('DONE.TXT')?.equals(text(400, 12)), 'put back: the closed files are intact');
  cmd([0x03]);
  noViolations(pull(), 'removal');
  const ls = fatLs(img);
  expect(ls['KEEP.TXT'] === 500 && ls['DONE.TXT'] === 400, `the host still reads the closed files (${JSON.stringify(ls)})`);
}

// ------------------------------------------------ write-protected
if (section('wp')) {
  const img = image('wp.img', 16, 16, { 'RO.TXT': text(200, 21) });
  const before = fs.readFileSync(img);
  const st = insert(img, { highCapacity: false, writeProtect: true });
  expect((st & (S.MOUNTED | S.WP)) === (S.MOUNTED | S.WP), `write-protected card: mounted, WP set in the status byte (status $${st.toString(16)})`);
  expect(readFile('RO.TXT')?.equals(text(200, 21)), 'write-protected: files still read');
  const w = writeFile('NEW.TXT', text(100));
  expect(w && w.e === E.WP, `write-protected: writing a file is "write-protected" ($06): ${JSON.stringify(w)}`);
  expect(err(cmd([0x17, ...nm('RO.TXT')])) === E.WP, 'write-protected: F_DELETE is "write-protected"');
  cmd([0x03]);
  noViolations(pull(), 'write-protected');
  expect(fs.readFileSync(img).equals(before), 'write-protected: the image is unchanged');
}

// ------------------------------------------------ a full card
if (section('full')) {
  const img = image('full.img', 2, 12);
  fat('fill', img, 'BIG.DAT');
  insert(img, { highCapacity: false });
  inf = info();
  expect(inf && inf.free === 0, `full card: ST_INFO free 0 KB (${JSON.stringify(inf)})`);
  const w = writeFile('MORE.TXT', text(1000));
  expect(w && w.e === E.FULL, `full card: writing a file is "full" ($05): ${JSON.stringify(w)}`);
  cmd([0x03]);
  noViolations(pull(), 'full card');
  const chk = fatCheck(img);
  expect(chk.startsWith('ok'), `full card: the volume is still consistent (${chk.trim()})`);
}

const torn = host.log.filter((f) => f.miso.length && f.miso[0] & 0x80 && f.miso[0] !== 0xff);
expect(torn.length === 0, `the status byte's bit 7 is always 0 (slot.md): ${torn.length} frames had ${[...new Set(torn.map((f) => '$' + f.miso[0].toString(16)))].slice(0, 8).join(' ')}`);
fs.rmSync(dir, { recursive: true, force: true });
console.log(`STO-010: real storage.elf with the SD card model, ${checks} checks, ${bad} failures ` +
  `(${(emu.ns / 1e9).toFixed(2)} s emulated in ${((performance.now() - t0) / 1e3).toFixed(1)} s)`);
process.exit(bad ? 1 : 0);
