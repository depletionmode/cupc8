// GPU-004 and GPU-005: the real graphics card firmware (build/rp2040/gpu.elf)
// on the emulated RP2040, driven through its slot pins with CUPC/8 SPI timing,
// its DVI output captured and decoded from the TMDS serialisers.
//
//   node test/emu/test_gpu.mjs [GPU-004|GPU-005]
//   (CUPC8_EMU=native: on the C++ emulator, see emu_backend.mjs)
//
// GPU-004: the SPI slave: IDENT at every clk_div, the host timing minimums,
//   responses and their discard rule, and FREE counting bytes still queued.
// GPU-005: 640x480@60 timing, and TEXT and GFX frames decoded from TMDS equal
//   the golden frames gpu_render() makes from the same commands (compared at
//   the precision the card encodes: RGB222 in TEXT, RGB565 in GFX). Core 1,
//   which makes every scanline in real time, runs 15% slower than silicon: a
//   late scanline shows as PicoDVI's red error line, so the frames only match
//   if every scanline has at least 15% to spare (it passes at 20%).

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Emu, SlotHost, TmdsCapture } from './emu_backend.mjs';     // CUPC8_EMU=native: the C++ emulator

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const ELF = path.join(ROOT, 'build/rp2040/gpu.elf');
const GOLDEN = path.join(ROOT, 'build/fw/gpu_golden');
const OUT = path.join(ROOT, 'build/emu');
fs.mkdirSync(OUT, { recursive: true });
const only = process.argv[2];

let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
}

const CORE1_SLOW = 1.15;
const emu = await Emu.load(ELF, { mhz: 252, core1Slow: CORE1_SLOW });
const cap = new TmdsCapture(emu);
const host = new SlotHost(emu, { clkDiv: 1 });
const sent = [];               // every frame sent, for the golden model

function run(script, ns = 2e9) {
  host.run(script);
  let done;
  try {
    done = emu.runUntil(() => host.done, ns);
  } catch (e) {
    // the firmware did something the chip would fault on (the emulator throws)
    console.log(`FAIL the card crashed at ${(emu.ns / 1e6).toFixed(3)} ms: ${e.message}`);
    process.exit(1);
  }
  if (!done) {
    console.log('FAIL the card stopped answering (host script timed out)');
    process.exit(1);
  }
  return host.result;
}
const send = (frames) =>
  run(function* () {
    for (const f of frames) {
      sent.push(f);
      yield* this.frame(f);
    }
  });
const u16 = (v) => [v & 0xff, (v >> 8) & 0xff];
const ascii = (s) => [...s].map((c) => c.charCodeAt(0));

// ---------------------------------------------------------------- boot
const status0 = run(function* () {
  for (let i = 0; i < 200; i++) {
    const m = yield* this.frame([0x00]);
    if (m[0] !== 0xff) return m[0];
    yield 1e6;
  }
  return 0xff;
});
expect(status0 !== 0xff, 'the card answers within 200 ms of power-on');
sent.push([0x00]);

if (!only || only === 'GPU-004') {
  // IDENT at every SPI clock divider the chipset offers
  for (let d = 1; d <= 31; d++) {
    host.clkDiv = d;
    const r = run(function* () {
      const m = yield* this.frame([0xf0]);
      return { status: m[0], resp: yield* this.read() };
    });
    expect(r.status === 127, `clk_div ${d}: idle status FREE=127 (got ${r.status})`);
    expect(r.resp && r.resp.data.length === 4 && r.resp.data[0] === 0x01 && r.resp.data[3] === 0xc8,
      `clk_div ${d}: IDENT ${JSON.stringify(r.resp)}`);
  }
  host.clkDiv = 1;

  // a response, and a new command discarding it
  send([[0x12, 5, 7], [0x18]]);
  const xy = run(function* () { return yield* this.read(); });
  expect(xy && xy.data.join() === '5,7', `GETXY after GOTOXY 5,7: ${JSON.stringify(xy)}`);
  send([[0x18], [0x00]]);
  const gone = run(function* () { return yield* this.read({ tries: 5 }); });
  expect(gone === null, 'a new command discards the unread response');

  // FREE counts bytes still queued in the SPI ring: straight after an
  // 8006-byte BLIT8, the next status byte allows at most (8192-8008)/64 = 2
  const blit = [0x24, ...u16(0), 0, 100, 80];
  for (let i = 0; i < 8000; i++) blit.push(i & 0xff);
  const after = run(function* () {
    sent.push(blit);
    yield* this.frame(blit);
    const m = yield* this.frame([0x00]);
    yield 20e6;
    const later = yield* this.frame([0x00]);
    return [m[0], later[0]];
  });
  sent.push([0x00], [0x00]);
  expect(after[0] <= 2, `FREE straight after a full-size frame is <= 2 (got ${after[0]})`);
  expect(after[1] === 127, `FREE is back to 127 once executed (got ${after[1]})`);

  // PUTC keeps up with the wire: 300 PUTCs at the fastest clock and the
  // minimum gaps never leave more than one frame queued (FREE >= 126)
  const puts = run(function* () {
    let low = 127;
    for (let i = 0; i < 300; i++) {
      const m = yield* this.frame([0x10, 0x41 + (i % 26)]);
      low = Math.min(low, m[0]);
    }
    return low;
  });
  for (let i = 0; i < 300; i++) sent.push([0x10, 0x41 + (i % 26)]);
  expect(puts >= 126, `PUTC keeps up at full SPI speed (lowest FREE ${puts})`);

  // full-screen CLS and FILL_RECT in GFX mode execute within one frame
  // (16.7 ms): from the command's CS_n rising to its FENCE being read back
  for (const [name, cmd] of [['CLS', [0x02, 3]], ['FILL_RECT', [0x21, ...u16(0), 0, ...u16(320), 240, 5]]]) {
    const ns = run(function* () {
      yield* this.frame([0x01, 1]);
      yield 20e6;
      yield* this.frame(cmd);
      const t0 = this.emu.ns - this.frameGapNs;
      yield* this.frame([0x05, 0x5a]);
      for (;;) {
        yield* this.frame([0x06]);
        const r = yield* this.read();
        if (r && r.data[0] === 0x5a) return this.emu.ns - t0;
      }
    });
    sent.push([0x01, 1], cmd, [0x05, 0x5a], [0x06]);
    expect(ns < 16.7e6, `full-screen ${name} within one frame (${(ns / 1e6).toFixed(2)} ms)`);
  }
  send([[0x01, 0]]);

  // the host timing minimums at the fastest clock: 50 POKEs back to back,
  // then every cell read back in the frame check below (GPU-005 runs them)
  host.csSetupNs = 2000; host.byteGapNs = 1000; host.frameGapNs = 20000;
  send([[0x02, 0x07]]);
  const pokes = [];
  for (let i = 0; i < 50; i++) pokes.push([0x17, i, 3, 0x41 + (i % 26), 0x1e]);
  send(pokes);
}

// -------------------------------------------------------------- frames
function golden(vsyncs = 0) {
  const bin = path.join(OUT, 'gpu_frames.bin');
  const parts = [];
  for (const f of sent) parts.push(Buffer.from([f.length & 0xff, f.length >> 8]), Buffer.from(f));
  fs.writeFileSync(bin, Buffer.concat(parts));
  const out = path.join(OUT, 'gpu_golden.rgb');
  execFileSync(GOLDEN, [bin, String(vsyncs), out]);
  const b = fs.readFileSync(out);
  return new Uint32Array(b.buffer, b.byteOffset, b.length / 4);
}

// capture the next whole frame, after the card has had `settleNs` to execute
function captureFrame(settleNs = 40e6) {
  emu.runUntil(() => false, settleNs);
  cap.start();
  emu.runUntil(() => false, 40e6);            // > 2 frames at 60 Hz
  cap.stop();
  const lines = cap.analyse();
  const f = cap.frame(lines);
  return { lines, ...f };
}

const q2 = (v) => Math.round(v / 85);
function codes(px, text, card) {
  const r = (px >> 16) & 255, g = (px >> 8) & 255, b = px & 255;
  if (text) return (q2(r) << 4) | (q2(g) << 2) | q2(b);
  // the card: PicoDVI sends code<<3 (5-bit) or code<<2 (6-bit), 1 LSB dither;
  // the golden: gpu_render()'s code*255/31 (or /63)
  if (card) return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
  return (Math.round((r * 31) / 255) << 11) | (Math.round((g * 63) / 255) << 5) | Math.round((b * 31) / 255);
}

function compare(name, frame, want, text) {
  if (frame.error) {
    expect(false, `${name}: ${frame.error}`);
    return;
  }
  let diffs = 0, first = '';
  for (let i = 0; i < 640 * 480; i++) {
    if (codes(frame.rgb[i], text, true) !== codes(want[i], text, false)) {
      if (!diffs) first = ` first at (${i % 640},${Math.floor(i / 640)}): card ${frame.rgb[i].toString(16)} golden ${want[i].toString(16)}`;
      diffs++;
    }
  }
  expect(diffs === 0, `${name}: ${diffs} pixels differ from the golden frame${first}`);
  // keep both for inspection
  const ppm = (px, file) => {
    const b = Buffer.alloc(640 * 480 * 3);
    for (let i = 0; i < 640 * 480; i++) {
      b[3 * i] = px[i] >> 16; b[3 * i + 1] = px[i] >> 8; b[3 * i + 2] = px[i];
    }
    fs.writeFileSync(path.join(OUT, file), Buffer.concat([Buffer.from('P6 640 480 255\n'), b]));
  };
  ppm(frame.rgb, `${name}-card.ppm`);
  ppm(want, `${name}-golden.ppm`);
}

if (!only || only === 'GPU-005') {
  // TEXT: every fg/bg pair, PUTS with control codes, a redefined glyph
  const t = [[0x14, 0], [0x02, 0x1f]];
  for (let fg = 0; fg < 16; fg++)
    for (let bg = 0; bg < 16; bg++) t.push([0x17, bg * 5, fg + 5, 0x41 + ((fg + bg) % 26), (bg << 4) | fg]);
  t.push([0x12, 0, 22], [0x13, 0x4e], [0x11, ...[...'Hello, CUPC/8!\tTAB\nnext line\rCR'].map((c) => c.length && c.charCodeAt(0))].map((v, i, a) => v));
  t[t.length - 1].splice(1, 0, t[t.length - 1].length - 1);
  t.push([0x19, 0x80, 0xff, 0x81, 0x81, 0x99, 0xa5, 0xc3, 0x81, 0xff, 0, 0xaa, 0x55, 0xaa, 0x55, 0, 0x18, 0x3c]);
  t.push([0x17, 79, 29, 0x80, 0x2a], [0x17, 0, 29, 0xdb, 0x0c]);
  send(t);
  const text = captureFrame();
  const L = text.lines.filter((l) => l.total);
  const frameLines = [];
  for (let i = 1, start = -1; i < L.length; i++) {
    if (L[i - 1].vsync && !L[i].vsync) {
      if (start >= 0) frameLines.push({ n: i - start, ns: L[i].t - L[start].t });
      start = i;
    }
  }
  expect(L.every((l) => l.total === 800 && l.hsyncLen === 96), 'every line: 800 symbols, hsync 96');
  expect(L.every((l) => !l.dataLen || (l.dataLen === 640 && l.dataStart - l.start === 144)),
    'active video: 640 symbols from symbol 144 (sync 96 + back porch 48)');
  expect(frameLines.length >= 1 && frameLines.every((f) => f.n === 525), `525 lines per frame: ${JSON.stringify(frameLines)}`);
  expect(frameLines.every((f) => Math.abs(f.ns - 800 * 525 / 25.2e6 * 1e9) < 20e3),
    `frame period 16.667 ms: ${frameLines.map((f) => (f.ns / 1e6).toFixed(3))}`);
  expect(L.filter((l) => l.vsync).length % 2 === 0, 'vsync is 2 lines');
  compare('GPU-005-text', text, golden(), true);

  // the block cursor: wait until VSYNC_COUNT is early in the blink's visible
  // half (on for frames 0-14 of every 30), then the next frame shows it
  send([[0x12, 10, 12], [0x14, 2]]);
  run(function* () {
    for (;;) {
      yield* this.frame([0x07]);
      const r = yield* this.read();
      if (r && r.data[0] % 30 >= 1 && r.data[0] % 30 <= 9) return;
      yield 8e6;
    }
  });
  sent.push([0x07]);
  compare('GPU-005-cursor', captureFrame(0), golden(0), true);   // vsync 0: visible

  // GFX: all 256 palette entries, a redefined entry, every drawing command
  const g = [[0x01, 1], [0x02, 4]];
  const pal = [0x24, ...u16(8), 8, 16, 16];
  for (let i = 0; i < 256; i++) pal.push(i);
  g.push(pal, [0x03, 200, 0x12, 0x34, 0x56]);
  g.push([0x21, ...u16(40), 30, ...u16(100), 50, 9], [0x22, ...u16(150), 20, ...u16(60), 40, 14]);
  g.push([0x23, ...u16(0), 239, ...u16(319), 0, 13], [0x20, ...u16(319), 239, 15]);
  g.push([0x26, ...u16(10), 200, 15, 0xff, 6, ...ascii('CUPC/8')], [0x26, ...u16(10), 210, 0, 11, 3, ...ascii('abc')]);
  g.push([0x25, ...u16(200), 100, 16, 2, 12, 0xff, 0xf0, 0x0f, 0xaa, 0x55]);
  send(g);
  compare('GPU-005-gfx', captureFrame(), golden(), false);

  // the video survives SPI traffic at any moment: 200 frames at seeded
  // random gaps (so some land in a porch, when PicoDVI's DMA interrupt has
  // ~2 us to set up the next line), then the frame must still be golden
  let seed = 12345;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  run(function* () {
    for (let i = 0; i < 200; i++) {
      yield 20000 + Math.floor(rnd() * 280000);
      if (i % 2) yield* this.frame([0x00]);                       // a command: replay, refresh
      else yield* this.read({ tries: 1 });                        // READ: the preload path
    }
  });
  for (let i = 0; i < 200; i += 2) sent.push([0x00]);
  compare('GPU-005-traffic', captureFrame(), golden(), false);
}

console.log(`${only ?? 'GPU-004/005'}: real gpu.elf on the emulated RP2040, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
