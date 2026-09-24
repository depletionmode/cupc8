#!/usr/bin/env node
// Differential test of the native peripherals (emu/rp2040/src/peripherals/
// {dma,uart,spi,i2c,timer,watchdog,rtc,adc,pwm}.cpp, src/utils/timer32.cpp)
// against rp2040js (the patched dist in the cupc8 SDK). No CPU core runs.
//
//   node emu/rp2040/test/periph/periph_diff.mjs --cxx build/emu-native-periph/test_periph_diff \
//        [--seeds 200] [--ops 20000] [--first-seed 1] [--keep DIR] [--seed N]
//
// For each seed it writes a scenario (seeded random bus reads/writes to every
// register of the ported peripherals, incl. the XOR/SET/CLR aliases and
// 8/16-bit writes; clock ticks of random fractional length; UART byte
// injection; SPI/I2C device callbacks answered synchronously or later; DREQ
// toggles; GPIO inputs; ADC channel values; PWM resets), runs it through
// rp2040js (in this process) and through test_periph_diff, and compares the
// two traces line by line. A trace records every bus read value, every
// callback (onByte, onBaudRateChange, onTransmit, I2C callbacks, ADC reads,
// watchdog trigger, GPIO pin listeners), every RP2040.setInterrupt call,
// every clock alarm firing (alarm id = order of first schedule(), fire time),
// every logger message, nanosToNextAlarm after each op, and a checksum of the
// SRAM window the DMA writes to. Times are printed as the IEEE-754 bits of
// the double.
//
// Last line: "PERIPH DIFF PASS ..." (exit 0) or "PERIPH DIFF FAIL ..." (exit 1).
//
// Scenario format (one op per line, integers in hex, doubles as 16 hex digits
// of their bits) is documented in test_periph_diff.cpp.

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const SDK = process.env.CUPC8_SDK || join(homedir(), '.local/share/cupc8-sdk');
const RP2040JS = process.env.RP2040JS_DIR || join(SDK, 'rp2040js');
const { RP2040 } = await import(pathToFileURL(join(RP2040JS, 'dist/esm/index.js')).href);
const { SimulationClock } = await import(
  pathToFileURL(join(RP2040JS, 'dist/esm/clock/simulation-clock.js')).href
);

// ---------------------------------------------------------------- arguments
const args = process.argv.slice(2);
function opt(name, def) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
}
const CXX = opt('--cxx', null);
const SEEDS = Number(opt('--seeds', 200));
const FIRST_SEED = Number(opt('--first-seed', 1));
const OPS = Number(opt('--ops', 20000));
const ONLY_SEED = opt('--seed', null);
const KEEP = opt('--keep', null);
if (!CXX) {
  console.error('usage: periph_diff.mjs --cxx <test_periph_diff> [--seeds N] [--ops N]');
  process.exit(2);
}

// ---------------------------------------------------------------- helpers
const f64 = new Float64Array(1);
const u32v = new Uint32Array(f64.buffer);
const hex8 = (v) => (v >>> 0).toString(16);
function hexd(x) {
  f64[0] = x;
  return u32v[1].toString(16).padStart(8, '0') + u32v[0].toString(16).padStart(8, '0');
}
function unhexd(s) {
  u32v[1] = parseInt(s.slice(0, 8), 16);
  u32v[0] = parseInt(s.slice(8), 16);
  return f64[0];
}

/** xorshift32 (identical in test_periph_diff.cpp) */
class Rng {
  constructor(seed) {
    this.s = seed >>> 0 || 0x9e3779b9;
  }
  next() {
    let x = this.s;
    x ^= x << 13;
    x >>>= 0;
    x ^= x >>> 17;
    x ^= x << 5;
    this.s = x >>> 0;
    return this.s;
  }
  below(n) {
    return this.next() % n;
  }
  chance(p) {
    return this.next() / 4294967296 < p;
  }
  pick(arr) {
    return arr[this.below(arr.length)];
  }
}

// ---------------------------------------------------------------- scenario generator
const UART_BASE = [0x40034000, 0x40038000];
const SPI_BASE = [0x4003c000, 0x40040000];
const I2C_BASE = [0x40044000, 0x40048000];
const ADC_BASE = 0x4004c000;
const PWM_BASE = 0x40050000;
const TIMER_BASE = 0x40054000;
const WATCHDOG_BASE = 0x40058000;
const RTC_BASE = 0x4005c000;
const DMA_BASE = 0x50000000;
const SRAM = 0x20000000;
const IO_BANK0 = 0x40014000;

const UART_REGS = [0x0, 0x18, 0x24, 0x28, 0x2c, 0x30, 0x38, 0x3c, 0x40, 0x44,
  0xfe0, 0xfe4, 0xfe8, 0xfec, 0xff0, 0xff4, 0xff8, 0xffc, 0x4, 0x34, 0x48];
const SPI_REGS = [0x0, 0x4, 0x8, 0xc, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24,
  0xfe0, 0xfe4, 0xfe8, 0xfec, 0xff0, 0xff4, 0xff8, 0xffc, 0x28];
const I2C_REGS = [0x00, 0x04, 0x08, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x2c, 0x30, 0x34, 0x38, 0x3c,
  0x40, 0x44, 0x48, 0x4c, 0x50, 0x54, 0x58, 0x5c, 0x60, 0x64, 0x68, 0x6c, 0x70, 0x74, 0x78,
  0x7c, 0x80, 0x84, 0x88, 0x9c, 0xa0, 0xa8, 0xf4, 0xf8, 0xfc, 0x0c];
const ADC_REGS = [0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24];
const TIMER_REGS = [0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x2c,
  0x30, 0x34, 0x38, 0x3c, 0x40, 0x44];
const WATCHDOG_REGS = [0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x2c, 0x30];
const RTC_REGS = [0x00, 0x04, 0x08, 0x0c, 0x10, 0x14, 0x18, 0x1c, 0x20];
const DMA_GEN_REGS = [0x400, 0x404, 0x408, 0x40c, 0x410, 0x414, 0x418, 0x41c, 0x420, 0x424,
  0x428, 0x42c, 0x430, 0x434, 0x438, 0x43c, 0x440, 0x444, 0x448, 0x44c];
const TRANS_COUNT_OFFS = [0x08, 0x1c, 0x24, 0x38];
const CTRL_OFFS = [0x0c, 0x10, 0x20, 0x30];
const READ_OFFS = [0x00, 0x14, 0x28, 0x3c];
const WRITE_OFFS = [0x04, 0x18, 0x2c, 0x34];

/** Registers where a negative int32 value (JS-SIGN) is observable in TS: never written with bit 31. */
function jsSignRegister(addr) {
  const a = addr & ~0x3000;
  if (a >= TIMER_BASE + 0x10 && a <= TIMER_BASE + 0x1c) return true;
  if (a === I2C_BASE[0] + 0xa0 || a === I2C_BASE[1] + 0xa0) return true;
  if (a >= DMA_BASE && a < DMA_BASE + 0x300 && TRANS_COUNT_OFFS.includes(a & 0x3f)) return true;
  return false;
}

function dmaReadSource(r) {
  switch (r.below(10)) {
    case 0:
    case 1:
    case 2:
      return SRAM + (r.below(0x2000) & ~3);
    case 3:
      return 0x10000000 + (r.below(0x1000) & ~3);
    case 4:
      return r.pick([UART_BASE[0], UART_BASE[1], SPI_BASE[0] + 8, SPI_BASE[1] + 8]);
    case 5:
      return r.pick([ADC_BASE + 0x0c, I2C_BASE[0] + 0x10, TIMER_BASE + 0x28, PWM_BASE + 0x08]);
    case 6:
      return DMA_BASE + 0x400 + (r.below(0x40) & ~3);
    case 7:
      // (not the bootrom: an unaligned readUint32 there is `bootrom[address / 4]`, undefined in
      // TS, which then crashes a logger message; the C++ bus reads 0 -- a bus-level difference)
      return 0x10000000 + r.below(0x100);
    default:
      return SRAM + r.below(0x800);
  }
}

function dmaWriteTarget(r) {
  switch (r.below(10)) {
    case 0:
    case 1:
    case 2:
    case 3:
      return SRAM + (r.below(0x300) & ~3);
    case 4:
      return SRAM + r.below(0x300);
    case 5:
      return r.pick([UART_BASE[0], UART_BASE[1]]);
    case 6:
      return r.pick([SPI_BASE[0] + 8, SPI_BASE[1] + 8]);
    case 7:
      // (not I2C DATA_CMD: 32-bit transfers with INCR_WRITE reach IC_FS_SPKLEN, a JS-SIGN register.
      // PWM registers rarely: a TOP of 0 there ends the scenario, see pwmOp)
      return r.chance(0.3) ? PWM_BASE + 0x0c + 0x14 * r.below(8) : SRAM + 0x200 + (r.below(0x100) & ~3);
    case 8:
      return WATCHDOG_BASE + 0x0c + 4 * r.below(8);
    default:
      return SRAM + 0x100 + (r.below(0x100) & ~1);
  }
}

function dmaCtrl(r, ch) {
  let v = 0;
  if (r.chance(0.8)) v |= 1; // EN
  if (r.chance(0.2)) v |= 1 << 1; // HIGH_PRIORITY
  v |= r.below(4) << 2; // DATA_SIZE (3 = invalid -> 8 bit)
  if (r.chance(0.6)) v |= 1 << 4; // INCR_READ
  if (r.chance(0.6)) v |= 1 << 5; // INCR_WRITE
  if (r.chance(0.3)) v |= (1 + r.below(10)) << 6; // RING_SIZE 1..10
  if (r.chance(0.5)) v |= 1 << 10; // RING_SEL
  // chain only to itself or upwards: a chain cycle of permanent-TREQ channels never ends
  const chain = r.chance(0.5) ? ch : ch + 1 + r.below(15 - ch);
  v |= chain << 11;
  let treq;
  switch (r.below(10)) {
    case 0:
    case 1:
    case 2:
    case 3:
      treq = 0x3f;
      break;
    case 4:
    case 5:
      treq = 0x3b + r.below(4);
      break;
    case 6:
    case 7:
    case 8:
      treq = r.pick([16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 36, 32]);
      break;
    default:
      treq = r.below(64);
  }
  v |= treq << 15;
  if (r.chance(0.3)) v |= 1 << 21; // IRQ_QUIET
  if (r.chance(0.3)) v |= 1 << 22; // BSWAP
  if (r.chance(0.2)) v |= 1 << 23; // SNIFF_EN
  if (r.chance(0.1)) v |= 1 << 24; // BUSY (read-only)
  if (r.chance(0.1)) v |= 1 << 29; // WRITE_ERROR (WC)
  if (r.chance(0.1)) v |= 1 << 30; // READ_ERROR (WC)
  return v >>> 0;
}

function dmaOp(r, ops) {
  const ch = r.below(12);
  const base = DMA_BASE + ch * 0x40;
  switch (r.below(16)) {
    case 0:
    case 1:
      ops.push(`W ${hex8(base + r.pick(READ_OFFS))} ${hex8(dmaReadSource(r))}`);
      break;
    case 2:
    case 3:
      ops.push(`W ${hex8(base + r.pick(WRITE_OFFS))} ${hex8(dmaWriteTarget(r))}`);
      break;
    case 4:
    case 5:
      ops.push(`W ${hex8(base + r.pick(TRANS_COUNT_OFFS))} ${hex8(r.chance(0.1) ? 0 : r.below(40))}`);
      break;
    case 6:
    case 7:
    case 8: {
      const alias = r.chance(0.8) ? 0 : r.pick([0x1000, 0x2000, 0x3000]);
      ops.push(`W ${hex8(base + r.pick(CTRL_OFFS) + alias)} ${hex8(dmaCtrl(r, ch))}`);
      break;
    }
    case 9: {
      const t = r.below(4);
      const v = r.chance(0.1) ? 0 : ((1 + r.below(4)) << 16) | (r.chance(0.1) ? 0 : 1 + r.below(0x40));
      const val = t === 3 && r.chance(0.5) ? (v | ((1 + r.below(0xfff)) << 20)) >>> 0 : v;
      ops.push(`W ${hex8(DMA_BASE + 0x420 + 4 * t)} ${hex8(val)}`);
      break;
    }
    case 10:
      ops.push(`W ${hex8(DMA_BASE + 0x430)} ${hex8(r.below(0x1000))}`);
      break;
    case 11:
      ops.push(`W ${hex8(DMA_BASE + 0x444)} ${hex8(r.below(0x1000))}`);
      break;
    case 12: {
      const reg = r.pick([0x400, 0x404, 0x408, 0x40c, 0x414, 0x418, 0x41c]);
      const alias = r.pick([0, 0, 0x1000, 0x2000, 0x3000]);
      ops.push(`W ${hex8(DMA_BASE + reg + alias)} ${hex8(r.chance(0.5) ? r.below(0x10000) : r.next())}`);
      break;
    }
    case 13:
      ops.push(`W ${hex8(DMA_BASE + 0x800 + ch * 0x40 + r.pick([0, 4]))} ${hex8(r.next())}`);
      break;
    case 14:
      ops.push(`${r.chance(0.7) ? 'D' : 'DC'} ${hex8(r.chance(0.7) ? r.pick([16, 17, 18, 19, 20, 21, 22, 23, 24, 36, 32]) : r.below(64))}`);
      break;
    default: {
      // reads of all channel / general registers (never (offset & 0x7ff) == 0x300: TS throws)
      let off;
      const k = r.below(3);
      if (k === 0) off = ch * 0x40 + r.below(16) * 4;
      else if (k === 1) off = r.pick(DMA_GEN_REGS);
      else off = 0x800 + ch * 0x40 + r.below(16) * 4;
      if (r.chance(0.1)) off += r.pick([0x1000, 0x2000, 0x3000]);
      if ((off & 0x7ff) === 0x300) off = 0x448;
      ops.push(`R ${hex8(DMA_BASE + off)}`);
    }
  }
}

function pwmOp(r, ops) {
  const ch = r.below(8);
  const base = PWM_BASE + ch * 0x14;
  switch (r.below(12)) {
    case 0:
    case 1: {
      // CSR: EN, PH_CORRECT, A_INV, B_INV, DIVMODE, PH_RET, PH_ADV
      ops.push(`W ${hex8(base)} ${hex8(r.below(0x100) | (r.chance(0.05) ? r.next() & 0xffff00 : 0))}`);
      break;
    }
    case 2: {
      const int = r.chance(0.05) ? 0 : 1 + r.below(r.chance(0.5) ? 8 : 255);
      ops.push(`W ${hex8(base + 4)} ${hex8((int << 4) | r.below(16) | (r.chance(0.05) ? r.next() & 0xfff00000 : 0))}`);
      break;
    }
    case 3:
      ops.push(`W ${hex8(base + 8)} ${hex8(r.chance(0.9) ? r.below(0x400) : r.next())}`);
      break;
    case 4:
    case 5: {
      const hi = r.chance(0.2) ? 0 : r.below(r.chance(0.8) ? 0x400 : 0x10000);
      const lo = r.chance(0.2) ? 0 : r.below(r.chance(0.8) ? 0x400 : 0x10000);
      ops.push(`W ${hex8(base + 0xc)} ${hex8(((hi << 16) | lo) >>> 0)}`);
      break;
    }
    case 6: {
      // (TOP 0 with PH_CORRECT makes TS's ZigZag `% (top * 2)` NaN and the wrap alarm
      // re-fire at the same instant forever: reproduced, but it ends the scenario)
      const top = r.chance(0.03) ? 1 + r.below(8) : r.chance(0.1) ? 0xffff : 40 + r.below(0x3c0);
      ops.push(`W ${hex8(base + 0x10)} ${hex8(top | (r.chance(0.05) ? r.next() & 0xffff0000 : 0))}`);
      break;
    }
    case 7: {
      const alias = r.pick([0, 0, 0x1000, 0x2000, 0x3000]);
      ops.push(`W ${hex8(PWM_BASE + r.pick([0xa0, 0xa4, 0xa8, 0xac, 0xb0, 0xb4]) + alias)} ${hex8(r.below(0x200))}`);
      break;
    }
    case 8:
      ops.push(`G ${hex8(r.below(30))} ${r.below(2)}`);
      break;
    case 9:
      if (r.chance(0.05)) ops.push('PR');
      else ops.push(`R ${hex8(base + 8)}`);
      break;
    default: {
      let off = r.chance(0.8) ? ch * 0x14 + r.below(5) * 4 : r.pick([0xa0, 0xa4, 0xa8, 0xac, 0xb0, 0xb4, 0xb8]);
      if (r.chance(0.05)) off += 0x1000;
      ops.push(`R ${hex8(PWM_BASE + off)}`);
    }
  }
}

function genericValue(r) {
  switch (r.below(6)) {
    case 0:
      return r.next();
    case 1:
      return r.below(2) ? 0 : 0xffffffff;
    case 2:
      return r.below(0x100);
    case 3:
      return r.below(0x10000);
    default:
      return (1 << r.below(32)) >>> 0;
  }
}

function busWrite(r, ops, addr, value) {
  let alias = 0;
  if (r.chance(0.2)) alias = r.pick([0x1000, 0x2000, 0x3000]);
  if (jsSignRegister(addr)) {
    value &= 0x7fffffff;
    ops.push(`W ${hex8(addr + alias)} ${hex8(value)}`);
    return;
  }
  const kind = r.below(12);
  if (kind === 0) ops.push(`W8 ${hex8(addr + alias + r.below(4))} ${hex8(value & 0xff)}`);
  else if (kind === 1) ops.push(`W16 ${hex8(addr + alias + (r.below(2) << 1))} ${hex8(value & 0xffff)}`);
  else ops.push(`W ${hex8(addr + alias)} ${hex8(value)}`);
}

function busRead(r, ops, addr) {
  const kind = r.below(14);
  if (kind === 0) ops.push(`R8 ${hex8(addr + r.below(4))}`);
  else if (kind === 1) ops.push(`R16 ${hex8(addr + (r.below(2) << 1))}`);
  else if (kind === 2) ops.push(`R ${hex8(addr + r.pick([0x1000, 0x2000, 0x3000]))}`);
  else ops.push(`R ${hex8(addr)}`);
}

function uartOp(r, ops) {
  const u = r.below(2);
  const base = UART_BASE[u];
  switch (r.below(8)) {
    case 0:
    case 1:
      ops.push(`U ${u} ${hex8(r.below(0x100))}`);
      break;
    case 2: {
      const reg = r.pick([0x0, 0x24, 0x28, 0x2c, 0x30, 0x38, 0x44, 0x4]);
      let v = genericValue(r);
      if (reg === 0x30) v = r.chance(0.7) ? (r.below(2) | 0x300) : v;
      if (reg === 0x38) v = r.below(0x800);
      busWrite(r, ops, base + reg, v);
      break;
    }
    default:
      busRead(r, ops, base + r.pick(UART_REGS));
  }
}

function spiOp(r, ops) {
  const s = r.below(2);
  const base = SPI_BASE[s];
  switch (r.below(9)) {
    case 0:
      ops.push(`SC ${s} ${hex8(r.chance(0.9) ? r.below(0x10000) : r.next())}`);
      break;
    case 1:
      if (r.chance(0.1)) ops.push(`SM ${s} ${r.below(3)}`);
      else ops.push(`SC ${s} ${hex8(r.below(0x100))}`);
      break;
    case 2:
    case 3: {
      const reg = r.pick([0x0, 0x4, 0x8, 0x8, 0x8, 0x10, 0x14, 0x20, 0x24, 0x18]);
      let v = genericValue(r);
      if (reg === 0x0) v = r.chance(0.8) ? (r.below(16) | (r.below(4) << 4) | (r.below(4) << 6) | (r.below(0x100) << 8)) : v;
      busWrite(r, ops, base + reg, v);
      break;
    }
    default:
      busRead(r, ops, base + r.pick(SPI_REGS));
  }
}

function i2cOp(r, ops) {
  const i = r.below(2);
  const base = I2C_BASE[i];
  switch (r.below(14)) {
    case 0:
      if (r.chance(0.15)) ops.push(`IM ${i} ${r.below(3)}`);
      else ops.push(`IS ${i}`);
      break;
    case 1:
      ops.push(`IC ${i} ${r.chance(0.7) ? 1 : 0} ${r.below(2)}`);
      break;
    case 2:
      ops.push(`IW ${i} ${r.chance(0.8) ? 1 : 0}`);
      break;
    case 3:
      ops.push(`IR ${i} ${hex8(r.below(0x100))}`);
      break;
    case 4:
      ops.push(r.chance(0.9) ? `IP ${i}` : `IA ${i}`);
      break;
    case 5:
    case 6: {
      let v = r.below(0x100);
      if (r.chance(0.4)) v |= 1 << 8; // CMD (read)
      if (r.chance(0.3)) v |= 1 << 9; // STOP
      if (r.chance(0.2)) v |= 1 << 10; // RESTART
      busWrite(r, ops, base + 0x10, v);
      break;
    }
    case 7: {
      const v = r.chance(0.7) ? r.pick([1, 1, 1, 0, 3, 5, 2, 7]) : genericValue(r);
      busWrite(r, ops, base + 0x6c, v);
      break;
    }
    case 8: {
      const reg = r.pick([0x00, 0x04, 0x08, 0x14, 0x18, 0x1c, 0x20, 0x30, 0x38, 0x3c, 0x7c, 0xa0, 0x88, 0x40]);
      let v = genericValue(r);
      if (reg === 0x04) v = r.chance(0.2) ? 0 : r.below(0x800);
      if (reg === 0x38 || reg === 0x3c) v = r.below(0x20);
      if (reg === 0x30) v = r.below(0x2000);
      busWrite(r, ops, base + reg, v);
      break;
    }
    default:
      busRead(r, ops, base + r.pick(I2C_REGS));
  }
}

function adcOp(r, ops, longTime) {
  switch (r.below(9)) {
    case 0:
    case 1: {
      let v = r.below(2); // EN
      if (r.chance(0.5)) v |= 1 << 2; // START_ONE
      if (!longTime && r.chance(0.2)) v |= 1 << 3; // START_MANY
      if (r.chance(0.3)) v |= 1 << 1; // TS_EN
      if (r.chance(0.1)) v |= 1 << 10; // ERR_STICKY (WC)
      v |= r.below(8) << 12; // AINSEL
      if (r.chance(0.3)) v |= r.below(32) << 16; // RROBIN
      busWrite(r, ops, ADC_BASE, v);
      break;
    }
    case 2: {
      let v = r.below(16) | (r.below(16) << 24);
      if (r.chance(0.2)) v |= r.below(4) << 10; // OVER / UNDER (WC)
      busWrite(r, ops, ADC_BASE + 8, v >>> 0);
      break;
    }
    case 3:
      busWrite(r, ops, ADC_BASE + 0x10, r.chance(0.5) ? r.below(0x10000) : r.chance(0.5) ? r.below(0x1000000) : r.next());
      break;
    case 4:
      busWrite(r, ops, ADC_BASE + r.pick([0x18, 0x1c, 0x14, 0x24]), r.below(4));
      break;
    case 5:
      ops.push(`AV ${r.below(5)} ${hex8(r.chance(0.8) ? r.below(0x1000) : r.below(0x100000))}`);
      break;
    default:
      busRead(r, ops, ADC_BASE + r.pick(ADC_REGS));
  }
}

function timerOp(r, ops, nowUs) {
  switch (r.below(8)) {
    case 0:
    case 1: {
      let v;
      const k = r.below(5);
      if (k === 0) v = r.next();
      else if (k === 1) v = Math.floor(nowUs) - r.below(100);
      else v = Math.floor(nowUs) + r.below(k === 2 ? 20 : 3000);
      busWrite(r, ops, TIMER_BASE + 0x10 + 4 * r.below(4), v >>> 0);
      break;
    }
    case 2:
      busWrite(r, ops, TIMER_BASE + r.pick([0x20, 0x34, 0x38, 0x3c, 0x30, 0x00, 0x04, 0x44]), r.chance(0.8) ? r.below(0x10) : genericValue(r));
      break;
    default:
      busRead(r, ops, TIMER_BASE + r.pick(TIMER_REGS));
  }
}

function watchdogOp(r, ops) {
  switch (r.below(7)) {
    case 0: {
      let v = 0;
      if (r.chance(0.6)) v |= 1 << 30;
      if (r.chance(0.03)) v |= 1 << 31;
      v |= r.below(8) << 24;
      if (r.chance(0.1)) v |= r.next() & 0xffffff;
      busWrite(r, ops, WATCHDOG_BASE, v >>> 0);
      break;
    }
    case 1:
      busWrite(r, ops, WATCHDOG_BASE + 4, r.chance(0.7) ? r.below(0x2000) : r.next());
      break;
    case 2:
      busWrite(r, ops, WATCHDOG_BASE + 0x2c, r.chance(0.7) ? r.pick([0x200, 0x200, 0, 0x201]) : genericValue(r));
      break;
    case 3:
      busWrite(r, ops, WATCHDOG_BASE + 0x0c + 4 * r.below(9), genericValue(r));
      break;
    default:
      busRead(r, ops, WATCHDOG_BASE + r.pick(WATCHDOG_REGS));
  }
}

function rtcOp(r, ops) {
  switch (r.below(7)) {
    case 0: {
      const v = r.chance(0.7)
        ? ((r.chance(0.5) ? 1900 + r.below(300) : r.below(0x1000)) << 12) | ((r.chance(0.8) ? 1 + r.below(12) : r.below(16)) << 8) | r.below(32)
        : r.next();
      busWrite(r, ops, RTC_BASE + 4, v >>> 0);
      break;
    }
    case 1: {
      const v = r.chance(0.7)
        ? (r.below(7) << 24) | (r.below(32) << 16) | (r.below(64) << 8) | r.below(64)
        : r.next();
      busWrite(r, ops, RTC_BASE + 8, v >>> 0);
      break;
    }
    case 2:
      busWrite(r, ops, RTC_BASE + 0xc, r.pick([0x10, 0x01, 0x11, 0x00, 0x10, 0x01]) | (r.chance(0.1) ? r.next() : 0));
      break;
    case 3:
      busWrite(r, ops, RTC_BASE + r.pick([0x10, 0x14, 0x18, 0x1c, 0x00]), genericValue(r));
      break;
    default:
      busRead(r, ops, RTC_BASE + r.pick([0x18, 0x1c, 0x18, 0x1c, ...RTC_REGS]));
  }
}

function tickOp(r, ops, longTime) {
  let d;
  const k = r.below(100);
  if (k < 10) d = 0;
  else if (k < 50) d = r.below(5000) / 7;
  else if (k < 80) d = r.below(1000) + r.below(1000) / 1000;
  else if (k < 95) d = r.below(20000) + r.next() / 4294967296;
  else if (k < 99) d = r.below(200000) / 3;
  else d = longTime ? r.below(2000) * 1e9 + r.next() / 1024 : r.below(100000) + 0.5;
  ops.push(`T ${hexd(d)}`);
  return d;
}

function generate(seed, nOps) {
  const r = new Rng(seed * 2654435761);
  const ops = [];
  // scenario flavour: 0 = everything, 1 = long times (no PWM/ADC multi-shot), 2..6 = one peripheral emphasised
  const flavour = seed % 7;
  const longTime = flavour === 1;
  ops.push(`S ${hex8(r.next())}`);
  // SRAM / flash contents
  ops.push(`FILL ${hex8(r.next())}`);
  // GPIO functions: mostly PWM
  for (let pin = 0; pin < 30; pin++) {
    if (r.chance(0.85)) ops.push(`W ${hex8(IO_BANK0 + 8 * pin + 4)} 4`);
  }
  // DMA addresses start at 0 (the bootrom), where an unaligned 32-bit read is undefined in TS
  for (let ch = 0; ch < 12; ch++) {
    ops.push(`W ${hex8(DMA_BASE + ch * 0x40)} ${hex8(dmaReadSource(r))}`);
    ops.push(`W ${hex8(DMA_BASE + ch * 0x40 + 4)} ${hex8(dmaWriteTarget(r))}`);
  }
  for (let s = 0; s < 2; s++) ops.push(`SM ${s} ${r.below(3)}`);
  for (let i = 0; i < 2; i++) ops.push(`IM ${i} ${r.below(3)}`);

  const weights = {
    tick: 14, dma: 14, pwm: longTime ? 0 : 10, uart: 7, spi: 8, i2c: 9, adc: 5, timer: 7, watchdog: 4, rtc: 4, sram: 2, ck: 2,
  };
  const emph = ['dma', 'pwm', 'i2c', 'adc', 'timer'][flavour - 2];
  if (emph) weights[emph] *= 4;
  const names = Object.keys(weights);
  const total = names.reduce((s, n) => s + weights[n], 0);
  let nowNs = 0;
  for (let n = 0; n < nOps; n++) {
    let x = r.below(total);
    let kind = names[0];
    for (const name of names) {
      if (x < weights[name]) {
        kind = name;
        break;
      }
      x -= weights[name];
    }
    switch (kind) {
      case 'tick':
        nowNs += tickOp(r, ops, longTime);
        break;
      case 'dma':
        dmaOp(r, ops);
        break;
      case 'pwm':
        pwmOp(r, ops);
        break;
      case 'uart':
        uartOp(r, ops);
        break;
      case 'spi':
        spiOp(r, ops);
        break;
      case 'i2c':
        i2cOp(r, ops);
        break;
      case 'adc':
        adcOp(r, ops, longTime);
        break;
      case 'timer':
        timerOp(r, ops, nowNs / 1000);
        break;
      case 'watchdog':
        watchdogOp(r, ops);
        break;
      case 'rtc':
        rtcOp(r, ops);
        break;
      case 'sram':
        if (r.chance(0.5)) ops.push(`W ${hex8(SRAM + (r.below(0x2000) & ~3))} ${hex8(r.next())}`);
        else ops.push(`R ${hex8(SRAM + (r.below(0x800) & ~3))}`);
        break;
      case 'ck':
        ops.push('CK');
        break;
    }
  }
  ops.push('CKALL');
  return ops;
}

// ---------------------------------------------------------------- the JS executor
class RunawayError extends Error {}
/** alarm firings allowed per op: more means a runaway scenario (e.g. a DMA chain cycle); both sides stop there */
const ALARM_BUDGET = 500000;

function fnv(bytes, start, end) {
  let h = 0x811c9dc5;
  for (let i = start; i < end; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

function normaliseMessage(msg) {
  // JS-SIGN in BasePeripheral: `value.toString(16)` of a negative int32 prints "-..."
  return msg.replace(/0x-([0-9a-f]+)/g, (_, h) => '0x' + ((0x100000000 - parseInt(h, 16)) >>> 0).toString(16));
}

function runJS(ops) {
  const out = [];
  const log = (s) => out.push(s);

  class TestClock extends SimulationClock {
    constructor() {
      super();
      this.nextId = 0;
      this.fired = 0;
    }
    createAlarm(callback) {
      const st = { id: -1 };
      const alarm = super.createAlarm(() => {
        if (++this.fired > ALARM_BUDGET) throw new RunawayError();
        log(`A ${st.id} ${hexd(this.nanos)}`);
        callback();
      });
      const schedule = alarm.schedule.bind(alarm);
      alarm.schedule = (delta) => {
        if (st.id < 0) st.id = this.nextId++;
        schedule(delta);
      };
      return alarm;
    }
  }
  const clock = new TestClock();
  const mcu = new RP2040(clock);
  const cb = new Rng(1);

  mcu.logger = {
    debug: (c, m) => log(`L D ${c} ${normaliseMessage(m)}`),
    info: (c, m) => log(`L I ${c} ${normaliseMessage(m)}`),
    warn: (c, m) => log(`L W ${c} ${normaliseMessage(m)}`),
    error: (c, m) => log(`L E ${c} ${normaliseMessage(m)}`),
  };
  const origSetInterrupt = mcu.setInterrupt.bind(mcu);
  mcu.setInterrupt = (irq, value) => {
    if (irq !== 13) log(`I ${irq} ${value ? 1 : 0} ${hexd(clock.nanos)}`);
    origSetInterrupt(irq, value);
  };
  for (let u = 0; u < 2; u++) {
    mcu.uart[u].onByte = (b) => log(`B ${u} ${hex8(b)}`);
    mcu.uart[u].onBaudRateChange = (b) => log(`BR ${u} ${hexd(b)}`);
  }
  const spiMode = [0, 0];
  const spiDefault = mcu.spi.map((s) => s.onTransmit);
  for (let s = 0; s < 2; s++) {
    mcu.spi[s].onTransmit = (v) => {
      log(`X ${s} ${hex8(v)}`);
      if (spiMode[s] === 0) spiDefault[s](v);
      else if (spiMode[s] === 1) mcu.spi[s].completeTransmit(cb.next() & 0xff);
      // 2: answered later by an SC op
    };
  }
  const i2cDefaults = mcu.i2c.map((i) => ({
    onStart: i.onStart, onConnect: i.onConnect, onWriteByte: i.onWriteByte, onReadByte: i.onReadByte, onStop: i.onStop,
  }));
  function setI2CMode(n, mode) {
    const i = mcu.i2c[n];
    if (mode === 0) {
      Object.assign(i, i2cDefaults[n]);
      return;
    }
    const sync = mode === 1;
    i.onStart = (rs) => {
      log(`IS ${n} ${rs ? 1 : 0}`);
      if (sync) i.completeStart();
    };
    i.onConnect = (addr, m) => {
      log(`IC ${n} ${hex8(addr)} ${m}`);
      if (sync) i.completeConnect(cb.below(4) !== 0, cb.below(2));
    };
    i.onWriteByte = (v) => {
      log(`IW ${n} ${hex8(v)}`);
      if (sync) i.completeWrite(cb.below(5) !== 0);
    };
    i.onReadByte = (ack) => {
      log(`IR ${n} ${ack ? 1 : 0}`);
      if (sync) i.completeRead(cb.next() & 0xff);
    };
    i.onStop = () => {
      log(`IP ${n}`);
      if (sync) i.completeStop();
    };
  }
  const adcRead = mcu.adc.onADCRead;
  mcu.adc.onADCRead = (ch) => {
    log(`AR ${ch}`);
    adcRead(ch);
  };
  const wd = mcu.peripherals[(0x40058000 >>> 14) << 2];
  // Once the watchdog counter has expired, TS's alarm re-fires at the same
  // instant forever (a real reset handler never returns); the "handler" here
  // either disables the watchdog or reloads it.
  wd.onWatchdogTrigger = () => {
    log(`WD ${hexd(clock.nanos)}`);
    if (cb.below(2)) mcu.writeUint32(0x40058000, 0);
    else mcu.writeUint32(0x40058004, 1 + cb.below(0x1000));
  };
  for (let pin = 0; pin < 30; pin++) {
    mcu.gpio[pin].addListener((state, old) => log(`G ${pin} ${state} ${old} ${hexd(clock.nanos)}`));
  }

  const rd = (v) => {
    if (v !== undefined && !Number.isInteger(v)) log(`NONINT ${v}`);
    return hex8(v === undefined ? 0 : v);
  };

  try {
    for (const line of ops) {
      clock.fired = 0;
      const f = line.split(' ');
      const a = (k) => parseInt(f[k], 16);
      switch (f[0]) {
        case 'S':
          cb.s = a(1) >>> 0 || 1;
          break;
        case 'FILL': {
          const fr = new Rng(a(1));
          for (let i = 0; i < 0x4000; i++) mcu.sram[i] = fr.next() & 0xff;
          for (let i = 0; i < 0x2000; i++) mcu.flash[i] = fr.next() & 0xff;
          break;
        }
        case 'W':
          mcu.writeUint32(a(1), a(2));
          break;
        case 'W8':
          mcu.writeUint8(a(1), a(2));
          break;
        case 'W16':
          mcu.writeUint16(a(1), a(2));
          break;
        case 'R':
          log(`r ${f[1]} ${rd(mcu.readUint32(a(1)))}`);
          break;
        case 'R8':
          log(`r ${f[1]} ${rd(mcu.readUint8(a(1)))}`);
          break;
        case 'R16':
          log(`r ${f[1]} ${rd(mcu.readUint16(a(1)))}`);
          break;
        case 'T':
          clock.tick(unhexd(f[1]));
          break;
        case 'U':
          mcu.uart[a(1)].feedByte(a(2));
          break;
        case 'SM':
          spiMode[a(1)] = a(2);
          break;
        case 'SC':
          mcu.spi[a(1)].completeTransmit(a(2));
          break;
        case 'IM':
          setI2CMode(a(1), a(2));
          break;
        case 'IS':
          mcu.i2c[a(1)].completeStart();
          break;
        case 'IC':
          mcu.i2c[a(1)].completeConnect(a(2) !== 0, a(3));
          break;
        case 'IW':
          mcu.i2c[a(1)].completeWrite(a(2) !== 0);
          break;
        case 'IR':
          mcu.i2c[a(1)].completeRead(a(2));
          break;
        case 'IP':
          mcu.i2c[a(1)].completeStop();
          break;
        case 'IA':
          mcu.i2c[a(1)].arbitrationLost();
          break;
        case 'D':
          mcu.dma.setDREQ(a(1));
          break;
        case 'DC':
          mcu.dma.clearDREQ(a(1));
          break;
        case 'G':
          mcu.gpio[a(1)].setInputValue(a(2) !== 0);
          break;
        case 'AV':
          mcu.adc.channelValues[a(1)] = a(2);
          break;
        case 'PR':
          mcu.pwm.reset();
          break;
        case 'CK':
          log(`CK ${hex8(fnv(mcu.sram, 0, 0x800))}`);
          break;
        case 'CKALL':
          log(`CKALL ${hex8(fnv(mcu.sram, 0, mcu.sram.length))} ${hex8(fnv(mcu.flash, 0, 0x4000))}`);
          break;
        default:
          throw new Error('bad op ' + line);
      }
      log(`N ${hexd(clock.nanosToNextAlarm)} ${hexd(clock.nanos)}`);
    }
  } catch (e) {
    if (e instanceof RunawayError) log('RUNAWAY');
    else log(`EXCEPTION ${e.name}: ${e.message}`);
  }
  return out;
}

// ---------------------------------------------------------------- the runner
function runCxx(file) {
  return new Promise((res, rej) => {
    const p = spawn(resolve(CXX), [file], { stdio: ['ignore', 'pipe', 'pipe'] });
    const chunks = [];
    let err = '';
    p.stdout.on('data', (d) => chunks.push(d));
    p.stderr.on('data', (d) => (err += d));
    p.on('error', rej);
    p.on('close', (code) => {
      if (code !== 0) err += `\n(exit code ${code})`;
      res({ lines: Buffer.concat(chunks).toString('latin1').split('\n').filter((l) => l.length), err });
    });
  });
}

const dir = KEEP ? resolve(KEEP) : mkdtempSync(join(tmpdir(), 'periph-diff-'));
mkdirSync(dir, { recursive: true });
const seeds = ONLY_SEED !== null ? [Number(ONLY_SEED)] : Array.from({ length: SEEDS }, (_, i) => FIRST_SEED + i);
let totalLines = 0,
  totalOps = 0,
  runaways = 0,
  failures = 0,
  exceptions = 0;
const ckValues = new Set();
const stats = { A: 0, I: 0, r: 0, B: 0, X: 0, G: 0, L: 0, IS: 0, IC: 0, IW: 0, IR: 0, IP: 0, AR: 0, WD: 0 };
for (const seed of seeds) {
  const ops = generate(seed, OPS);
  const file = join(dir, `scenario-${seed}.txt`);
  writeFileSync(file, ops.join('\n') + '\n');
  const cxxP = runCxx(file);
  const js = runJS(ops);
  const { lines: cx, err } = await cxxP;
  totalOps += ops.length;
  totalLines += js.length;
  for (const l of js) {
    const k = l.slice(0, l.indexOf(' '));
    if (k in stats) stats[k]++;
  }
  if (js[js.length - 1] === 'RUNAWAY') runaways++;
  if (js[js.length - 1].startsWith('EXCEPTION')) exceptions++;
  for (const l of js) if (l.startsWith('CK ')) ckValues.add(l);
  let bad = -1;
  const n = Math.max(js.length, cx.length);
  for (let i = 0; i < n; i++) {
    if (js[i] !== cx[i]) {
      bad = i;
      break;
    }
  }
  if (bad >= 0) {
    failures++;
    console.log(`seed ${seed}: MISMATCH at trace line ${bad} (js ${js.length} lines, c++ ${cx.length} lines)`);
    // locate the op: count N lines (one per op) before the mismatch
    let opIndex = 0;
    for (let i = 0; i < bad; i++) if (js[i] && js[i].startsWith('N ')) opIndex++;
    console.log(`  op #${opIndex}: ${ops[opIndex]}`);
    for (let i = Math.max(0, bad - 8); i < Math.min(n, bad + 4); i++) {
      console.log(`  ${i === bad ? '>' : ' '} js : ${js[i]}`);
      console.log(`  ${i === bad ? '>' : ' '} c++: ${cx[i]}`);
    }
    if (err) console.log('  c++ stderr: ' + err.slice(0, 2000));
    writeFileSync(join(dir, `trace-${seed}.js.txt`), js.join('\n') + '\n');
    writeFileSync(join(dir, `trace-${seed}.cxx.txt`), cx.join('\n') + '\n');
    console.log(`  scenario and traces kept in ${dir}`);
    if (failures >= 3) break;
  }
}
if (!KEEP && failures === 0) rmSync(dir, { recursive: true, force: true });
const summary =
  `${seeds.length} seeds, ${totalOps} ops, ${totalLines} trace lines compared ` +
  `(${stats.r} reads, ${stats.A} alarms, ${stats.I} IRQ changes, ${stats.G} GPIO changes, ` +
  `${stats.B} UART bytes, ${stats.X} SPI bytes, ${stats.IS + stats.IC + stats.IW + stats.IR + stats.IP} I2C callbacks, ` +
  `${stats.AR} ADC reads, ${stats.WD} watchdog triggers, ${stats.L} log messages, ${ckValues.size} distinct DMA-window checksums, ${runaways} scenarios ended by a runaway, ${exceptions} by a JS exception)`;
if (failures) {
  console.log(`PERIPH DIFF FAIL ${failures} seed(s) mismatched; ${summary}`);
  process.exit(1);
}
console.log(`PERIPH DIFF PASS ${summary}`);
