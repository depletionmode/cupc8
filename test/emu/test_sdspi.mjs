// EMU-008, on firmware: the SD card model under the pico-sdk's own SPI and
// DMA code (fw/rp2040/selftest/sdspi.c, build/rp2040/emu_sdspi.elf) on the
// native emulator, the storage card's pins: initialisation, a polled block
// read, a block write with its busy time measured by the firmware's timer,
// a DMA read back; the image file checked afterwards. Native only.
//
//   CUPC8_EMU=native node test/emu/test_sdspi.mjs

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Emu, SdSocket } from './emu_backend.mjs';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-sdspi-'));
let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
  return cond;
}

const cases = [
  { name: 'SDHC 1 MB', mb: 1, opts: {} },
  { name: 'SDSC 4 MB', mb: 4, opts: { highCapacity: false } },
  { name: 'SDHC, 250 ms busy', mb: 1, opts: { writeMs: 250 } },
];
for (const c of cases) {
  const img = path.join(dir, 'card.img');
  const bytes = Buffer.alloc(c.mb << 20);
  for (let i = 0; i < bytes.length; i++) bytes[i] = ((i >> 9) + (i & 511)) & 0xff;
  fs.writeFileSync(img, bytes);
  const emu = await Emu.load(path.join(ROOT, 'build/rp2040/emu_sdspi.elf'));
  const sd = new SdSocket(emu);
  emu.runUntil(() => emu.uart.includes('waiting'), 50e6);
  const t0 = performance.now();
  sd.insert(img, c.opts);
  const done = emu.runUntil(() => /SDSPI (PASS|FAIL)[^\n]*\n/.test(emu.uart), 2e9);
  const wall = performance.now() - t0;
  const m = /SDSPI PASS busy=(\d+) ccs=(\d) blocks=(\d+)/.exec(emu.uart);
  if (!expect(done && m, `${c.name}: the SDK host passes (${emu.uart.trim().split('\n').at(-1)})`)) continue;
  const busyUs = Number(m[1]), want = (c.opts.writeMs ?? 1) * 1000;
  expect(busyUs >= want - 100 && busyUs <= want + 200, `${c.name}: the firmware timed the write busy at ${busyUs} us (model ${want} us)`);
  expect(Number(m[2]) === (c.opts.highCapacity === false ? 0 : 1), `${c.name}: CCS ${m[2]} from CMD58`);
  expect(Number(m[3]) === (c.mb << 11), `${c.name}: capacity from the CSD, ${m[3]} blocks`);
  const card = sd.card();
  expect(card.violations.length === 0, `${c.name}: no protocol violations (${card.violations.join('; ')})`);
  expect(card.stats.maxHzBeforeInit <= 400e3 && card.stats.maxHz > 12e6, `${c.name}: SCK ${card.stats.maxHzBeforeInit} Hz while initialising, ${card.stats.maxHz} Hz after`);
  sd.remove();
  const out = fs.readFileSync(img);
  let ok = true;
  for (let i = 0; i < 512; i++) ok &&= out[5 * 512 + i] === ((0xa5 ^ i) & 0xff) && out[3 * 512 + i] === ((3 + i) & 0xff);
  expect(ok, `${c.name}: block 5 is in the image file, block 3 untouched (${out.subarray(5 * 512, 5 * 512 + 8).toString("hex")} ${out.subarray(3 * 512, 3 * 512 + 8).toString("hex")})`);
  console.log(`${c.name}: ${(emu.ns / 1e6).toFixed(1)} ms emulated in ${wall.toFixed(0)} ms`);
}
fs.rmSync(dir, { recursive: true, force: true });
console.log(`EMU-008 (firmware): the SD model under the pico-sdk's SPI and DMA, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
