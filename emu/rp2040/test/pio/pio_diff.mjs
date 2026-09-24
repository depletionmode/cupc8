#!/usr/bin/env node
// Differential test of the native PIO (emu/rp2040/src/peripherals/pio.cpp)
// against rp2040js's peripherals/pio.ts (the patched dist in the cupc8 SDK).
//
//   node emu/rp2040/test/pio/pio_diff.mjs --cxx build/emu-native-pio/test_pio_diff \
//        [--seeds 40] [--cycles 250000] [--real-cycles 1000000] [--jobs N] [--keep DIR]
//
// Writes scenarios (random PIO programs, register configurations and bus/GPIO
// stimulus, plus the project's real programs: PicoDVI's TMDS serialiser and
// tmds_encode_1bpp, fw/rp2040's slotspi SPI slave and sysctl's UART), runs
// each through rp2040js (this script with --run) and through test_pio_diff,
// and compares a hash of the full state of both PIO blocks after every cycle
// (checked every HASH_EVERY cycles). On a mismatch it dumps both sides around
// the first bad block and prints the first differing fields. Last line:
// "PIO DIFF PASS ..." (exit 0) or "PIO DIFF FAIL ..." (exit 1).
//
// Scenario format: see test_pio_diff.cpp.

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { cpus, homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '../../../..');
const SDK = process.env.CUPC8_SDK || join(homedir(), '.local/share/cupc8-sdk');
const RP2040JS = process.env.RP2040JS_DIR || join(SDK, 'rp2040js');
const HASH_EVERY = 1000;

const PIO_BASE = [0x50200000, 0x50300000];
const R_CTRL = 0x000,
  R_FSTAT = 0x004,
  R_FDEBUG = 0x008,
  R_FLEVEL = 0x00c,
  R_TXF0 = 0x010,
  R_RXF0 = 0x020,
  R_IRQ = 0x030,
  R_IRQ_FORCE = 0x034,
  R_INPUT_SYNC_BYPASS = 0x038,
  R_DBG_PADOUT = 0x03c,
  R_DBG_PADOE = 0x040,
  R_DBG_CFGINFO = 0x044,
  R_INSTR_MEM0 = 0x048,
  R_INTR = 0x128,
  R_IRQ0_INTE = 0x12c,
  R_IRQ0_INTF = 0x130,
  R_IRQ0_INTS = 0x134,
  R_IRQ1_INTE = 0x138,
  R_IRQ1_INTF = 0x13c,
  R_IRQ1_INTS = 0x140;
const SM_CLKDIV = 0,
  SM_EXECCTRL = 4,
  SM_SHIFTCTRL = 8,
  SM_ADDR = 0xc,
  SM_INSTR = 0x10,
  SM_PINCTRL = 0x14;
const ATOMIC_XOR = 0x1000,
  ATOMIC_SET = 0x2000,
  ATOMIC_CLR = 0x3000;
const IO_BANK0 = 0x40014000;
const PADS_BANK0 = 0x4001c000;
const PAD_IE = 1 << 6,
  PAD_PUE = 1 << 3,
  PAD_PDE = 1 << 2;

const smReg = (pio, sm, reg) => PIO_BASE[pio] + 0xc8 + 0x18 * sm + reg;
const hex = (v) => (v >>> 0).toString(16);

// ---------------------------------------------------------------------------
// State vector (must match test_pio_diff.cpp)

function smState(sm, out) {
  out.push(
    sm.enabled ? 1 : 0,
    sm.x >>> 0,
    sm.y >>> 0,
    sm.pc >>> 0,
    sm.inputShiftReg >>> 0,
    sm.inputShiftCount >>> 0,
    sm.outputShiftReg >>> 0,
    sm.outputShiftCount >>> 0,
    sm.cycles >>> 0,
    Math.floor(sm.cycles / 4294967296) >>> 0,
    sm.execOpcode >>> 0,
    sm.execValid ? 1 : 0,
    sm.updatePC ? 1 : 0,
    sm.clockDivInt >>> 0,
    sm.clockDivFrac >>> 0,
    sm.divPhase >>> 0,
    sm.delayLeft >>> 0,
    sm.execCtrl >>> 0,
    sm.shiftCtrl >>> 0,
    sm.pinCtrl >>> 0,
    sm.outPinValues >>> 0,
    sm.outPinDirection >>> 0,
    sm.waiting ? 1 : 0,
    sm.waitType >>> 0,
    sm.waitIndex >>> 0,
    sm.waitPolarity ? 1 : 0,
    sm.waitDelay >>> 0,
  );
  for (const f of [sm.txFIFO, sm.rxFIFO]) {
    out.push(f.size >>> 0, f.itemCount >>> 0);
    const items = f.items;
    for (let i = 0; i < 8; i++) {
      out.push(i < items.length ? items[i] >>> 0 : 0);
    }
  }
}

function pioState(pio, out) {
  for (const sm of pio.machines) {
    smState(sm, out);
  }
  out.push(
    pio.stopped ? 1 : 0,
    pio.fdebug >>> 0,
    pio.txStall >>> 0,
    pio.rxStall >>> 0,
    pio.inputSyncBypass >>> 0,
    pio.irq >>> 0,
    pio.pinValues >>> 0,
    pio.pinDirections >>> 0,
    pio.oldPinValues >>> 0,
    pio.oldPinDirections >>> 0,
    pio.irq0IntEnable >>> 0,
    pio.irq0IntForce >>> 0,
    pio.irq1IntEnable >>> 0,
    pio.irq1IntForce >>> 0,
    pio.intRaw >>> 0,
    pio.irq0IntStatus >>> 0,
    pio.irq1IntStatus >>> 0,
  );
}

function stateVector(mcu, irqLines, out) {
  out.length = 0;
  pioState(mcu.pio[0], out);
  pioState(mcu.pio[1], out);
  let dreq = 0;
  for (let i = 0; i < 16; i++) if (mcu.dma.dreq[i]) dreq |= 1 << i; // DREQ_PIO0_TX0..DREQ_PIO1_RX3
  out.push(dreq >>> 0);
  if (irqLines) {
    out.push((mcu.core0.pendingInterrupts >>> 7) & 0xf);
  }
  return out;
}

function stateLabels(irqLines) {
  const sm = [
    'enabled', 'x', 'y', 'pc', 'isr', 'isrCount', 'osr', 'osrCount', 'cyclesLo', 'cyclesHi',
    'execOpcode', 'execValid', 'updatePC', 'clockDivInt', 'clockDivFrac', 'divPhase', 'delayLeft',
    'execCtrl', 'shiftCtrl', 'pinCtrl', 'outPinValues', 'outPinDirection', 'waiting', 'waitType',
    'waitIndex', 'waitPolarity', 'waitDelay',
  ];
  for (const f of ['tx', 'rx']) {
    sm.push(`${f}.size`, `${f}.count`);
    for (let i = 0; i < 8; i++) sm.push(`${f}[${i}]`);
  }
  const pio = [
    'stopped', 'fdebug', 'txStall', 'rxStall', 'inputSyncBypass', 'irq', 'pinValues',
    'pinDirections', 'oldPinValues', 'oldPinDirections', 'irq0IntEnable', 'irq0IntForce',
    'irq1IntEnable', 'irq1IntForce', 'intRaw', 'irq0IntStatus', 'irq1IntStatus',
  ];
  const labels = [];
  for (let p = 0; p < 2; p++) {
    for (let m = 0; m < 4; m++) for (const n of sm) labels.push(`pio${p}.sm${m}.${n}`);
    for (const n of pio) labels.push(`pio${p}.${n}`);
  }
  labels.push('dma.dreq[0..15]');
  if (irqLines) labels.push('core0.pendingInterrupts[7..10]');
  return labels;
}

// ---------------------------------------------------------------------------
// The JS half: run a scenario through rp2040js

function parseScenario(file) {
  const lines = readFileSync(file, 'utf8').split('\n');
  let cycles = 0;
  const ev = [];
  for (const line of lines) {
    if (!line || line[0] === '#') continue;
    const f = line.split(' ');
    if (f[0] === 'C') {
      cycles = Number(f[1]);
      continue;
    }
    ev.push([Number(f[0]), f[1], parseInt(f[2], 16) >>> 0, f.length > 3 ? parseInt(f[3], 16) >>> 0 : 0]);
  }
  return { cycles, ev };
}

async function runJs(file, mode, a, b, irqLines) {
  const { RP2040 } = await import(pathToFileURL(join(RP2040JS, 'dist/esm/index.js')).href);
  const mcu = new RP2040();
  mcu.pio[0].run = () => {};
  mcu.pio[1].run = () => {};
  const { cycles, ev } = parseScenario(file);
  const dump = mode === 'dump';
  const out = [];
  const flush = () => {
    if (out.length) process.stdout.write(out.join(''));
    out.length = 0;
  };
  let h = 0x811c9dc5;
  const mix = (v) => {
    h = Math.imul(h ^ v, 0x01000193) >>> 0;
    h = (h ^ (h >>> 15)) >>> 0;
  };
  let cycle = 0;
  const observe = (what, addr, v) => {
    if (dump) {
      if (cycle >= a && cycle < b) out.push(`${what} ${cycle} ${hex(addr)} ${hex(v)}\n`);
    } else {
      mix((0xa5a50000 ^ addr) >>> 0);
      mix(v >>> 0);
    }
  };
  // Sync every pin's lastValue first, so that GPIO state left by other
  // peripherals' reset() (PWM touches pin 1) does not enter the comparison.
  for (const pin of mcu.gpio) pin.checkForUpdates();
  mcu.gpio.forEach((pin, index) => pin.addListener((state) => observe('gpio', index, state)));
  out.push(`irqlines ${irqLines ? 1 : 0}\n`);
  const state = [];
  let next = 0;
  for (cycle = 0; cycle < cycles; cycle++) {
    for (; next < ev.length && ev[next][0] === cycle; next++) {
      const [, op, x, y] = ev[next];
      switch (op) {
        case 'w':
          mcu.writeUint32(x, y);
          break;
        case 'r':
          observe('r', x, mcu.readUint32(x));
          break;
        case 'g':
          mcu.gpio[x].setInputValue(!!y);
          break;
        case 't':
          if (!mcu.pio[x >> 2].machines[x & 3].txFIFO.full) {
            mcu.writeUint32(PIO_BASE[x >> 2] + R_TXF0 + 4 * (x & 3), y);
          }
          break;
        case 'x':
          if (!mcu.pio[x >> 2].machines[x & 3].rxFIFO.empty) {
            const addr = PIO_BASE[x >> 2] + R_RXF0 + 4 * (x & 3);
            observe('r', addr, mcu.readUint32(addr));
          }
          break;
        default:
          throw new Error(`bad event op ${op}`);
      }
    }
    mcu.pio[0].step();
    mcu.pio[1].step();
    if (dump) {
      if (cycle >= a && cycle < b) {
        stateVector(mcu, irqLines, state);
        out.push(`s ${cycle} ${state.map(hex).join(' ')}\n`);
      }
      if (cycle + 1 >= b) break;
      continue;
    }
    stateVector(mcu, irqLines, state);
    for (let i = 0; i < state.length; i++) mix(state[i]);
    if ((cycle + 1) % a === 0 || cycle + 1 === cycles) {
      for (const pio of mcu.pio) for (const v of pio.instructions) mix(v);
      out.push(`h ${cycle} ${h.toString(16).padStart(8, '0')}\n`);
      if (out.length > 1000) flush();
    }
  }
  flush();
}

// ---------------------------------------------------------------------------
// Scenario generation

function rng(seed) {
  let s = seed >>> 0;
  const u32 = () => {
    // mulberry32
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return (t ^ (t >>> 14)) >>> 0;
  };
  const float = () => u32() / 4294967296;
  return {
    u32,
    float,
    int: (n) => Math.floor(float() * n),
    chance: (p) => float() < p,
    pick: (arr) => arr[Math.floor(float() * arr.length)],
  };
}

class Scenario {
  constructor(name) {
    this.name = name;
    this.lines = [];
    this.cycles = 0;
  }
  at(cycle, op, a, b) {
    this.lines.push(b === undefined ? `${cycle} ${op} ${hex(a)}` : `${cycle} ${op} ${hex(a)} ${hex(b)}`);
  }
  w(c, addr, value) {
    this.at(c, 'w', addr, value);
  }
  r(c, addr) {
    this.at(c, 'r', addr);
  }
  g(c, pin, v) {
    this.at(c, 'g', pin, v ? 1 : 0);
  }
  text() {
    // events must be in cycle order (stable: same-cycle events keep their order)
    const parsed = this.lines.map((l, i) => [Number(l.slice(0, l.indexOf(' '))), i, l]);
    parsed.sort((p, q) => p[0] - q[0] || p[1] - q[1]);
    return `# ${this.name}\nC ${this.cycles}\n${parsed.map((p) => p[2]).join('\n')}\n`;
  }
}

function randInstr(R) {
  const cls = R.int(8);
  let arg;
  switch (cls) {
    case 4: {
      // PUSH/PULL: mostly the valid encodings
      arg = (R.int(2) << 7) | (R.int(2) << 6) | (R.int(2) << 5) | (R.chance(0.05) ? R.int(32) : 0);
      break;
    }
    case 6: {
      // IRQ: bit 7 is an unknown encoding
      arg = (R.chance(0.05) ? 0x80 : 0) | (R.int(2) << 6) | (R.chance(0.3) ? 1 << 5 : 0) | R.int(32);
      break;
    }
    case 1: {
      // WAIT: IRQ waits, relative indices and reserved sources included
      arg = R.int(256);
      break;
    }
    default:
      arg = R.int(256);
  }
  const delaySideset = R.chance(0.5) ? 0 : R.chance(0.5) ? R.int(32) : R.int(4);
  return (cls << 13) | (delaySideset << 8) | arg;
}

function randClkdiv(R) {
  const k = R.float();
  if (k < 0.4) return 1 << 16;
  if (k < 0.65) return ((1 + R.int(3)) << 16) | (R.int(256) << 8);
  if (k < 0.8) return (R.int(16) << 16) | (R.int(256) << 8) | R.int(256);
  if (k < 0.9) return (1 << 16) | (R.int(256) << 8);
  if (k < 0.97) return ((1 + R.int(40)) << 16) | (R.int(256) << 8);
  return R.u32() & 0x00ffffff; // INT 0..255, sometimes 0 (= 65536)
}

function randShiftctrl(R) {
  let v = R.u32() & 0x3fffffff;
  if (R.chance(0.2)) v |= 1 << 30;
  if (R.chance(0.2)) v |= 1 << 31;
  return v >>> 0;
}

function randPinctrl(R) {
  let v = R.u32();
  if (R.chance(0.6)) v = (v & 0x1fffffff) | (R.int(3) << 29); // sideset count 0..2
  if (R.chance(0.5)) v = (v & ~(0x3f << 20)) | ((R.int(9)) << 20); // out count 0..8
  return v >>> 0;
}

const READ_REGS = [
  R_CTRL, R_FSTAT, R_FDEBUG, R_FLEVEL, R_IRQ, R_IRQ_FORCE, R_INPUT_SYNC_BYPASS, R_DBG_PADOUT,
  R_DBG_PADOE, R_DBG_CFGINFO, R_INTR, R_IRQ0_INTE, R_IRQ0_INTF, R_IRQ0_INTS, R_IRQ1_INTE,
  R_IRQ1_INTF, R_IRQ1_INTS,
];

function genRandom(seed, cycles) {
  const R = rng(seed * 0x9e3779b1 + 12345);
  const S = new Scenario(`random seed ${seed}`);
  S.cycles = cycles;
  const pins = Math.max(1, R.pick([2, 4, 8, 30]));
  for (let p = 0; p < 2; p++) {
    for (let i = 0; i < 32; i++) S.w(0, PIO_BASE[p] + R_INSTR_MEM0 + 4 * i, randInstr(R));
    for (let m = 0; m < 4; m++) {
      S.w(0, smReg(p, m, SM_CLKDIV), randClkdiv(R));
      S.w(0, smReg(p, m, SM_EXECCTRL), R.u32());
      S.w(0, smReg(p, m, SM_SHIFTCTRL), randShiftctrl(R));
      S.w(0, smReg(p, m, SM_PINCTRL), randPinctrl(R));
    }
    S.w(0, PIO_BASE[p] + R_IRQ0_INTE, R.u32());
    S.w(0, PIO_BASE[p] + R_IRQ1_INTE, R.u32());
  }
  for (let pin = 0; pin < 30; pin++) {
    const f = R.float();
    if (f < 0.6) S.w(0, IO_BANK0 + 4 + 8 * pin, f < 0.3 ? 6 : 7); // funcsel PIO0 / PIO1
    // input enable (off after reset in rp2040js), random pulls; sometimes left disabled
    if (R.chance(0.9)) S.w(0, PADS_BANK0 + 4 + 4 * pin, PAD_IE | (R.int(4) << 2) | 0x30);
    S.g(0, pin, R.int(2));
  }
  for (let p = 0; p < 2; p++) {
    S.w(0, PIO_BASE[p] + R_CTRL, (R.chance(0.7) ? 0xf : R.int(16)) | 0xff0);
  }
  const rate = {
    gpio: R.pick([0.005, 0.05, 0.3]),
    tx: R.pick([0.01, 0.1, 0.5]),
    rx: R.pick([0.01, 0.1, 0.5]),
    read: R.pick([0.002, 0.02]),
    irq: R.pick([0.001, 0.01, 0.05]),
    exec: R.pick([0.0005, 0.005, 0.02]),
    ctrl: R.pick([0.0002, 0.002]),
    cfg: R.pick([0.0002, 0.002]),
    imem: R.pick([0.0002, 0.003]),
    misc: 0.001,
  };
  for (let c = 1; c < cycles; c++) {
    const p = R.int(2),
      m = R.int(4);
    const base = PIO_BASE[p];
    if (R.float() < rate.gpio) S.g(c, R.int(pins), R.int(2));
    if (R.float() < rate.tx) {
      if (R.chance(0.7)) S.at(c, 't', p * 4 + m, R.u32());
      else S.w(c, base + R_TXF0 + 4 * m, R.u32()); // may overflow (TXOVER)
    }
    if (R.float() < rate.rx) {
      if (R.chance(0.7)) S.at(c, 'x', p * 4 + m);
      else S.r(c, base + R_RXF0 + 4 * m); // may underflow (RXUNDER)
    }
    if (R.float() < rate.read) {
      if (R.chance(0.5)) S.r(c, base + R.pick(READ_REGS));
      else S.r(c, smReg(p, m, R.pick([SM_CLKDIV, SM_EXECCTRL, SM_SHIFTCTRL, SM_ADDR, SM_INSTR, SM_PINCTRL])));
    }
    if (R.float() < rate.irq) {
      const k = R.int(3);
      if (k === 0) S.w(c, base + R_IRQ_FORCE, R.chance(0.9) ? 1 << R.int(8) : R.u32());
      else if (k === 1) S.w(c, base + R_IRQ, R.chance(0.8) ? 1 << R.int(8) : R.u32());
      else S.w(c, base + R_IRQ + ATOMIC_CLR, R.u32()); // atomic alias: rawWriteValue
    }
    if (R.float() < rate.exec) {
      const alias = R.chance(0.05) ? R.pick([ATOMIC_XOR, ATOMIC_SET, ATOMIC_CLR]) : 0;
      S.w(c, smReg(p, m, SM_INSTR) + alias, R.chance(0.9) ? randInstr(R) : R.u32());
    }
    if (R.float() < rate.ctrl) {
      const alias = R.pick([0, 0, ATOMIC_XOR, ATOMIC_SET, ATOMIC_CLR]);
      let v = R.chance(0.7) ? 0xf : R.int(16);
      if (R.chance(0.3)) v |= R.int(16) << 4;
      if (R.chance(0.3)) v |= R.int(16) << 8;
      if (alias === ATOMIC_CLR && R.chance(0.7)) v &= ~0xf;
      S.w(c, base + R_CTRL + alias, v);
    }
    if (R.float() < rate.cfg) {
      const reg = R.pick([SM_CLKDIV, SM_EXECCTRL, SM_SHIFTCTRL, SM_PINCTRL]);
      const v =
        reg === SM_CLKDIV ? randClkdiv(R) : reg === SM_SHIFTCTRL ? randShiftctrl(R) : reg === SM_PINCTRL ? randPinctrl(R) : R.u32();
      if (R.chance(0.2)) S.w(c, smReg(p, m, reg) + R.pick([ATOMIC_XOR, ATOMIC_SET, ATOMIC_CLR]), v);
      else S.w(c, smReg(p, m, reg), v);
    }
    if (R.float() < rate.imem) S.w(c, base + R_INSTR_MEM0 + 4 * R.int(32), R.chance(0.9) ? randInstr(R) : R.u32());
    if (R.float() < rate.misc) {
      const k = R.int(5);
      if (k === 0) S.w(c, base + R_FDEBUG, R.u32());
      else if (k === 1) S.w(c, base + R.pick([R_IRQ0_INTE, R_IRQ1_INTE]), R.u32());
      else if (k === 2) S.w(c, base + R.pick([R_IRQ0_INTF, R_IRQ1_INTF]), R.chance(0.7) ? 0 : R.u32());
      else if (k === 3) S.w(c, base + R_INPUT_SYNC_BYPASS, R.u32());
      else S.w(c, base + R.pick([R_IRQ0_INTE, R_IRQ1_INTF]) + R.pick([ATOMIC_XOR, ATOMIC_SET, ATOMIC_CLR]), R.u32());
    }
  }
  return S;
}

// --- the project's real programs (pioasm output) ---

const EMBEDDED_PROGRAMS = {
  // PicoDVI libdvi/dvi_serialiser.pio
  dvi_serialiser: { words: [0x70a1, 0x68a1], wrapTarget: 0, wrap: 1 },
  dvi_serialiser_debug: {
    words: [0x98e0, 0xb042, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001, 0x6001],
    wrapTarget: 0,
    wrap: 11,
  },
  // PicoDVI libdvi/tmds_encode_1bpp.pio
  tmds_encode_1bpp: {
    words: [0x6021, 0xa049, 0x4041, 0x4021, 0xa02b, 0x4028, 0x6021, 0xa049, 0x4041, 0x402d],
    wrapTarget: 0,
    wrap: 9,
  },
  // fw/rp2040/common/slotspi.pio
  slotspi: {
    words: [0x2005, 0xe081, 0x80a0, 0x0005, 0x8080, 0xe047, 0x6001, 0x2082, 0x4001, 0x2002, 0x0086, 0x0004],
    wrapTarget: 0,
    wrap: 11,
  },
  // fw/rp2040/sysctl/uart.pio
  port_uart_tx: { words: [0x9fa0, 0xf727, 0x6001, 0x0642], wrapTarget: 0, wrap: 3 },
  port_uart_rx: { words: [0x2020, 0xea27, 0x4001, 0x0642, 0x00c7, 0x20a0, 0x0000, 0x8020], wrapTarget: 0, wrap: 7 },
};

/** Prefer the pioasm headers of the last firmware build (build/rp2040), else the copy above. */
function loadPrograms() {
  const programs = { ...EMBEDDED_PROGRAMS };
  const found = [];
  const walk = (dir) => {
    if (!existsSync(dir)) return;
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (e.endsWith('.pio.h')) found.push(p);
    }
  };
  walk(join(REPO, 'build/rp2040'));
  const sources = [];
  for (const file of found) {
    const text = readFileSync(file, 'utf8');
    for (const name of Object.keys(EMBEDDED_PROGRAMS)) {
      const m = text.match(new RegExp(`${name}_program_instructions\\[\\] = \\{([^}]*)\\}`));
      if (!m) continue;
      const words = [...m[1].matchAll(/0x([0-9a-f]{4}),/g)].map((x) => parseInt(x[1], 16));
      const wt = text.match(new RegExp(`#define ${name}_wrap_target (\\d+)`));
      const w = text.match(new RegExp(`#define ${name}_wrap (\\d+)`));
      programs[name] = { words, wrapTarget: Number(wt[1]), wrap: Number(w[1]) };
      sources.push(`${name} from ${file.slice(REPO.length + 1)}`);
    }
  }
  return { programs, sources };
}

/** A tiny model of the pico-sdk calls the firmware makes, as bus writes. */
class Sdk {
  constructor(S) {
    this.S = S;
  }
  addProgram(c, pio, prog, offset) {
    prog.words.forEach((w, i) => {
      // pio_add_program relocates JMP targets
      const word = w >> 13 === 0 ? (w & ~0x1f) | ((w + offset) & 0x1f) : w;
      this.S.w(c, PIO_BASE[pio] + R_INSTR_MEM0 + 4 * (offset + i), word);
    });
    return offset;
  }
  static config(prog, offset) {
    // pio_get_default_sm_config + sm_config_set_wrap
    return {
      clkdiv: 1 << 16,
      execctrl: ((offset + prog.wrap) << 12) | ((offset + prog.wrapTarget) << 7),
      shiftctrl: (1 << 18) | (1 << 19),
      pinctrl: 0,
    };
  }
  static sideset(c, bitCount, optional, pindirs) {
    c.pinctrl = (c.pinctrl & ~(7 << 29)) | (bitCount << 29);
    c.execctrl = (c.execctrl & ~(3 << 29)) | ((optional ? 1 : 0) << 30) | ((pindirs ? 1 : 0) << 29);
  }
  static outShift(c, right, autopull, threshold) {
    c.shiftctrl = (c.shiftctrl & ~((1 << 19) | (1 << 17) | (0x1f << 25))) | ((right ? 1 : 0) << 19) | ((autopull ? 1 : 0) << 17) | ((threshold & 0x1f) << 25);
  }
  static inShift(c, right, autopush, threshold) {
    c.shiftctrl = (c.shiftctrl & ~((1 << 18) | (1 << 16) | (0x1f << 20))) | ((right ? 1 : 0) << 18) | ((autopush ? 1 : 0) << 16) | ((threshold & 0x1f) << 20);
  }
  static join(c, tx, rx) {
    c.shiftctrl = (c.shiftctrl & 0x3fffffff) | (tx ? 1 << 30 : 0) | (rx ? 1 << 31 : 0);
  }
  static pins(c, field, base, count) {
    // field: 'out' | 'set' | 'sideset' | 'in'
    if (field === 'out') c.pinctrl = (c.pinctrl & ~(0x1f | (0x3f << 20))) | base | (count << 20);
    if (field === 'set') c.pinctrl = (c.pinctrl & ~((7 << 26) | (0x1f << 5))) | (base << 5) | (count << 26);
    if (field === 'sideset') c.pinctrl = (c.pinctrl & ~(0x1f << 10)) | (base << 10);
    if (field === 'in') c.pinctrl = (c.pinctrl & ~(0x1f << 15)) | (base << 15);
  }
  static clkdiv(c, div) {
    const int = Math.floor(div);
    const frac = Math.floor((div - int) * 256);
    c.clkdiv = (int << 16) | (frac << 8);
  }
  /** pio_gpio_init: pad input enabled (gpio_set_input_enabled), funcsel PIOn */
  gpioInit(cycle, pio, pin) {
    this.padInit(cycle, pin, false);
    this.S.w(cycle, IO_BANK0 + 4 + 8 * pin, 6 + pio);
  }
  /** gpio_init / gpio_pull_up on an input the PIO reads */
  padInit(cycle, pin, pullUp) {
    this.S.w(cycle, PADS_BANK0 + 4 + 4 * pin, PAD_IE | (pullUp ? PAD_PUE : PAD_PDE) | 0x10);
  }
  exec(cycle, pio, sm, instr) {
    this.S.w(cycle, smReg(pio, sm, SM_INSTR), instr);
  }
  setEnabled(cycle, pio, mask, on) {
    this.S.w(cycle, PIO_BASE[pio] + R_CTRL + (on ? ATOMIC_SET : ATOMIC_CLR), mask);
  }
  clearFifos(cycle, pio, sm) {
    // hw_xor_bits(&shiftctrl, FJOIN_RX) twice
    this.S.w(cycle, smReg(pio, sm, SM_SHIFTCTRL) + ATOMIC_XOR, 1 << 31);
    this.S.w(cycle, smReg(pio, sm, SM_SHIFTCTRL) + ATOMIC_XOR, 1 << 31);
  }
  restart(cycle, pio, sm) {
    this.S.w(cycle, PIO_BASE[pio] + R_CTRL + ATOMIC_SET, 1 << (4 + sm));
  }
  init(cycle, pio, sm, initialPc, c) {
    this.setEnabled(cycle, pio, 1 << sm, false);
    this.S.w(cycle, smReg(pio, sm, SM_CLKDIV), c.clkdiv >>> 0);
    this.S.w(cycle, smReg(pio, sm, SM_EXECCTRL), c.execctrl >>> 0);
    this.S.w(cycle, smReg(pio, sm, SM_SHIFTCTRL), c.shiftctrl >>> 0);
    this.S.w(cycle, smReg(pio, sm, SM_PINCTRL), c.pinctrl >>> 0);
    this.clearFifos(cycle, pio, sm);
    this.S.w(cycle, PIO_BASE[pio] + R_FDEBUG, ((1 << 24) | (1 << 16) | (1 << 8) | 1) << sm);
    this.restart(cycle, pio, sm);
    this.S.w(cycle, PIO_BASE[pio] + R_CTRL + ATOMIC_SET, 1 << (8 + sm));
    this.exec(cycle, pio, sm, initialPc & 0x1f); // jmp initialPc
  }
  /** pio_sm_set_pins_with_mask / set_pindirs_with_mask (SET with a temporary PINCTRL) */
  setPinsWithMask(cycle, pio, sm, values, mask, dirs, pinctrl) {
    for (let pin = 0; pin < 32; pin++) {
      if (!(mask & (1 << pin))) continue;
      this.S.w(cycle, smReg(pio, sm, SM_PINCTRL), (1 << 26) | (pin << 5));
      this.exec(cycle, pio, sm, 0xe000 | ((dirs ? 4 : 0) << 5) | ((values >>> pin) & 1));
    }
    this.S.w(cycle, smReg(pio, sm, SM_PINCTRL), pinctrl >>> 0);
  }
}

function genDvi(seed, cycles, programs) {
  const R = rng(seed);
  const S = new Scenario(`PicoDVI serialiser + tmds_encode_1bpp + uart tx, seed ${seed}`);
  S.cycles = cycles;
  const sdk = new Sdk(S);
  // PIO0: three TMDS lanes (dvi_serialiser_program_init, debug = false)
  const ser = programs.dvi_serialiser;
  const off = sdk.addProgram(0, 0, ser, 0);
  const lanes = [12, 14, 16];
  lanes.forEach((pin, sm) => {
    sdk.setPinsWithMask(0, 0, sm, 2 << pin, 3 << pin, false, 0);
    sdk.setPinsWithMask(0, 0, sm, ~0, 3 << pin, true, 0);
    sdk.gpioInit(0, 0, pin);
    sdk.gpioInit(0, 0, pin + 1);
    const c = Sdk.config(ser, off);
    Sdk.sideset(c, 2, false, false);
    Sdk.pins(c, 'sideset', pin, 0);
    Sdk.outShift(c, true, true, 10 * 2);
    Sdk.join(c, true, false);
    sdk.init(0, 0, sm, off, c);
    sdk.setEnabled(0, 0, 1 << sm, false);
  });
  // pio_enable_sm_mask_in_sync
  S.w(1, PIO_BASE[0] + R_CTRL + ATOMIC_SET, 0x7 | (0x7 << 8));
  // PIO1 SM0: tmds_encode_1bpp_init
  const enc = programs.tmds_encode_1bpp;
  const encOff = sdk.addProgram(0, 1, enc, 32 - enc.words.length);
  {
    const c = Sdk.config(enc, encOff);
    Sdk.outShift(c, true, true, 32);
    Sdk.inShift(c, true, true, 24);
    sdk.init(0, 1, 0, encOff, c);
    sdk.setEnabled(0, 1, 1, true);
  }
  // PIO1 SM1: the debug serialiser (optional side-set, pull ifempty)
  const dbg = programs.dvi_serialiser_debug;
  const dbgOff = sdk.addProgram(0, 1, dbg, 32 - enc.words.length - dbg.words.length);
  {
    const pin = 20;
    sdk.setPinsWithMask(0, 1, 1, 2 << pin, 3 << pin, false, 0);
    sdk.setPinsWithMask(0, 1, 1, ~0, 3 << pin, true, 0);
    sdk.gpioInit(0, 1, pin);
    sdk.gpioInit(0, 1, pin + 1);
    const c = Sdk.config(dbg, dbgOff);
    Sdk.sideset(c, 2, true, false);
    Sdk.pins(c, 'sideset', pin, 0);
    Sdk.pins(c, 'out', pin, 1);
    Sdk.outShift(c, true, false, 20);
    Sdk.join(c, true, false);
    Sdk.clkdiv(c, 2.5);
    sdk.init(0, 1, 1, dbgOff, c);
    sdk.setEnabled(0, 1, 2, true);
  }
  // PIO1 SM2: sysctl's UART TX (optional side-set with delays, fractional divider)
  const utx = programs.port_uart_tx;
  const utxOff = sdk.addProgram(0, 1, utx, 0);
  {
    const c = Sdk.config(utx, utxOff);
    Sdk.outShift(c, true, false, 32);
    Sdk.pins(c, 'out', 18, 1);
    Sdk.pins(c, 'sideset', 18, 0);
    Sdk.sideset(c, 2, true, false);
    Sdk.join(c, true, false);
    Sdk.clkdiv(c, 125e6 / (8 * 921600));
    sdk.gpioInit(0, 1, 18);
    sdk.setPinsWithMask(0, 1, 2, 1 << 18, 1 << 18, false, c.pinctrl);
    sdk.setPinsWithMask(0, 1, 2, 1 << 18, 1 << 18, true, c.pinctrl);
    sdk.init(0, 1, 2, utxOff, c);
    sdk.setEnabled(0, 1, 4, true);
  }
  // DMA-like feeding: TMDS symbol pairs, pixels, UART bytes; drain the encoder
  const next = [2, 2, 2, 2, 2, 2, 100];
  for (let c = 2; c < cycles; c++) {
    for (let lane = 0; lane < 3; lane++) {
      if (c >= next[lane]) {
        S.at(c, 't', lane, R.u32() & 0xfffff);
        next[lane] = c + (R.chance(0.995) ? 1 + R.int(8) : 50 + R.int(200)); // occasional underrun
      }
    }
    if (c >= next[3]) {
      S.at(c, 't', 4, R.u32());
      next[3] = c + 1 + R.int(40);
    }
    if (c >= next[4]) {
      S.at(c, 'x', 4);
      next[4] = c + 1 + R.int(40);
    }
    if (c >= next[5]) {
      S.at(c, 't', 5, R.u32() & 0xfffff);
      next[5] = c + 1 + R.int(80);
    }
    if (c >= next[6]) {
      S.at(c, 't', 6, R.int(256));
      next[6] = c + 200 + R.int(3000);
    }
    if (R.chance(0.001)) S.r(c, PIO_BASE[R.int(2)] + R.pick(READ_REGS));
  }
  return S;
}

function genSpi(seed, cycles, programs) {
  const R = rng(seed);
  const S = new Scenario(`slotspi SPI slave + uart rx, seed ${seed}`);
  S.cycles = cycles;
  const sdk = new Sdk(S);
  // gpu pins: SCK 2, MOSI 3, MISO 4, nCS 5 (slotspi.pio hard-codes 2 and 5)
  const SCK = 2,
    MOSI = 3,
    MISO = 4,
    NCS = 5;
  const PIO = 0,
    SM = 1;
  const spi = programs.slotspi;
  const prog = sdk.addProgram(0, PIO, spi, 32 - spi.words.length);
  const c0 = Sdk.config(spi, prog);
  Sdk.pins(c0, 'in', MOSI, 0);
  Sdk.pins(c0, 'out', MISO, 1);
  Sdk.pins(c0, 'set', MISO, 1);
  Sdk.inShift(c0, false, true, 8);
  Sdk.outShift(c0, false, false, 32);
  sdk.gpioInit(0, PIO, MISO);
  sdk.padInit(0, SCK, false);
  sdk.padInit(0, MOSI, false);
  sdk.padInit(0, NCS, true);
  S.g(0, NCS, 1);
  S.g(0, SCK, 0);
  sdk.init(0, PIO, SM, prog, c0);
  const smRestart = (c) => {
    sdk.setEnabled(c, PIO, 1 << SM, false);
    sdk.exec(c, PIO, SM, 0xe080); // set pindirs, 0
    sdk.clearFifos(c, PIO, SM);
    sdk.restart(c, PIO, SM);
    sdk.exec(c, PIO, SM, 0xe020); // set x, 0
    sdk.exec(c, PIO, SM, prog); // jmp start
  };
  const armTx = (c) => {
    for (let i = 0; i < 4; i++) S.at(c + i, 't', PIO * 4 + SM, R.u32());
  };
  smRestart(0);
  armTx(0);
  sdk.setEnabled(4, PIO, 1 << SM, true);

  // PIO1 SM0: sysctl's UART RX on pin 19 (RX join, fractional divider)
  const urx = programs.port_uart_rx;
  const urxOff = sdk.addProgram(0, 1, urx, 0);
  const div = 125e6 / (8 * 460800);
  {
    const c = Sdk.config(urx, urxOff);
    Sdk.pins(c, 'in', 19, 0);
    c.execctrl = (c.execctrl & ~(0x1f << 24)) | (19 << 24);
    Sdk.inShift(c, true, false, 32);
    Sdk.join(c, false, true);
    Sdk.clkdiv(c, div);
    sdk.init(0, 1, 0, urxOff, c);
    sdk.setEnabled(0, 1, 1, true);
  }
  sdk.padInit(0, 19, true);
  S.g(0, 19, 1);

  // the SPI host: frames of 1..8 bytes, mode 0, then the fw's CS-rise handler
  let c = 200;
  while (c < cycles - 1000) {
    const half = 3 + R.int(20);
    S.g(c, NCS, 0);
    c += half + R.int(20);
    const n = 1 + R.int(8);
    for (let byte = 0; byte < n; byte++) {
      const v = R.int(256);
      for (let bit = 7; bit >= 0; bit--) {
        S.g(c, MOSI, (v >> bit) & 1);
        c += half;
        S.g(c, SCK, 1);
        c += half;
        S.g(c, SCK, 0);
      }
      // the RX DMA drains, the TX DMA refills
      S.at(c + R.int(half), 'x', PIO * 4 + SM);
      S.at(c + R.int(half), 't', PIO * 4 + SM, R.u32());
    }
    c += half;
    S.g(c, NCS, 1);
    const handler = c + 20 + R.int(100);
    for (let i = 0; i < 6; i++) S.at(handler + i, 'x', PIO * 4 + SM);
    smRestart(handler + 6);
    armTx(handler + 7);
    sdk.setEnabled(handler + 12, PIO, 1 << SM, true);
    c = handler + 20 + R.int(400);
  }
  // UART bytes from the host on pin 19 (8N1, bit = 8 SM clocks)
  const bit = 8 * div;
  let t = 500;
  while (t < cycles - 20 * bit) {
    const v = R.int(256);
    const frame = [0, ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (v >> i) & 1), R.chance(0.97) ? 1 : 0];
    frame.forEach((b, i) => S.g(Math.floor(t + i * bit), 19, b));
    S.g(Math.floor(t + 10 * bit), 19, 1);
    t += 10 * bit + R.int(3000);
    S.at(Math.floor(t), 'x', 4);
  }
  return S;
}

// ---------------------------------------------------------------------------
// Orchestration

function run(cmd, args) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    const out = [];
    const err = [];
    child.stdout.on('data', (d) => out.push(d));
    child.stderr.on('data', (d) => err.push(d));
    child.on('error', reject);
    child.on('close', (code) =>
      resolvePromise({ code, out: Buffer.concat(out).toString(), err: Buffer.concat(err).toString() }),
    );
  });
}

const jsRunner = (file, args) => run(process.execPath, [fileURLToPath(import.meta.url), '--run', file, ...args]);

async function checkScenario(cxx, file, name, cycles) {
  const c = await run(cxx, [file, 'hash', String(HASH_EVERY)]);
  if (c.code !== 0) return { ok: false, msg: `${name}: test_pio_diff exited ${c.code}\n${c.err}` };
  const irqLines = c.out.startsWith('irqlines 1');
  const j = await jsRunner(file, ['hash', String(HASH_EVERY), ...(irqLines ? ['--irq-lines'] : [])]);
  if (j.code !== 0) return { ok: false, msg: `${name}: rp2040js run exited ${j.code}\n${j.err}` };
  const cl = c.out.trim().split('\n');
  const jl = j.out.trim().split('\n');
  const noise = (c.err + j.err).trim();
  let bad = -1;
  for (let i = 0; i < Math.max(cl.length, jl.length); i++) {
    if (cl[i] !== jl[i]) {
      bad = i;
      break;
    }
  }
  if (bad < 0) {
    if (cl.length !== Math.ceil(cycles / HASH_EVERY) + 1) return { ok: false, msg: `${name}: short output` };
    return { ok: true, irqLines, noise };
  }
  // dump the first bad block on both sides and find the first differing line
  const prev = bad >= 2 ? Number(cl[bad - 1].split(' ')[1]) + 1 : 0;
  const end = cl[bad] ? Number(cl[bad].split(' ')[1]) + 1 : cycles;
  const cd = await run(cxx, [file, 'dump', String(prev), String(end)]);
  const jd = await jsRunner(file, ['dump', String(prev), String(end), ...(irqLines ? ['--irq-lines'] : [])]);
  const cdl = cd.out.split('\n');
  const jdl = jd.out.split('\n');
  const labels = stateLabels(irqLines);
  for (let i = 0; i < Math.max(cdl.length, jdl.length); i++) {
    if (cdl[i] === jdl[i]) continue;
    let msg = `${name}: first mismatch in cycles ${prev}..${end - 1}\n  C++: ${(cdl[i] || '<none>').slice(0, 200)}\n  JS:  ${(jdl[i] || '<none>').slice(0, 200)}`;
    const cf = (cdl[i] || '').split(' ');
    const jf = (jdl[i] || '').split(' ');
    if (cf[0] === 's' && jf[0] === 's' && cf[1] === jf[1]) {
      const diffs = [];
      for (let k = 2; k < cf.length; k++) {
        if (cf[k] !== jf[k]) diffs.push(`${labels[k - 2]}: C++ ${cf[k]} JS ${jf[k]}`);
      }
      msg += `\n  cycle ${cf[1]}: ${diffs.slice(0, 20).join('; ')}`;
    }
    return { ok: false, msg };
  }
  return { ok: false, msg: `${name}: hashes differ at block ${bad} but dumps agree (${cl[bad]} vs ${jl[bad]})` };
}

async function main(argv) {
  const opt = { seeds: 40, cycles: 250000, realCycles: 1000000, realSeeds: 2, jobs: Math.max(1, cpus().length), cxx: null, keep: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--cxx') opt.cxx = argv[++i];
    else if (a === '--seeds') opt.seeds = Number(argv[++i]);
    else if (a === '--cycles') opt.cycles = Number(argv[++i]);
    else if (a === '--real-cycles') opt.realCycles = Number(argv[++i]);
    else if (a === '--real-seeds') opt.realSeeds = Number(argv[++i]);
    else if (a === '--jobs') opt.jobs = Number(argv[++i]);
    else if (a === '--keep') opt.keep = argv[++i];
    else throw new Error(`unknown option ${a}`);
  }
  if (!opt.cxx) {
    opt.cxx = join(REPO, 'build/emu-native/test_pio_diff');
  }
  if (!existsSync(opt.cxx)) {
    console.log(`PIO DIFF FAIL: ${opt.cxx} not found (build the test_pio_diff target)`);
    return 1;
  }
  const dir = opt.keep || mkdtempSync(join(tmpdir(), 'pio-diff-'));
  const { programs, sources } = loadPrograms();
  if (sources.length) console.log(`programs: ${sources.join(', ')}`);

  const jobs = [];
  for (let s = 0; s < opt.realSeeds; s++) {
    jobs.push(() => genDvi(1000 + s, opt.realCycles, programs));
    jobs.push(() => genSpi(2000 + s, opt.realCycles, programs));
  }
  for (let s = 0; s < opt.seeds; s++) jobs.push(() => genRandom(s, opt.cycles));

  let failures = 0,
    totalCycles = 0,
    done = 0,
    irqLinesAll = true;
  const failMsgs = [];
  const noises = new Set();
  let index = 0;
  const worker = async () => {
    while (index < jobs.length) {
      const k = index++;
      const S = jobs[k]();
      const file = join(dir, `scenario${k}.txt`);
      writeFileSync(file, S.text());
      const r = await checkScenario(opt.cxx, file, S.name, S.cycles);
      done++;
      totalCycles += S.cycles;
      if (!r.ok) {
        failures++;
        failMsgs.push(r.msg);
        console.log(`[${done}/${jobs.length}] FAIL ${r.msg}`);
      } else {
        irqLinesAll &&= r.irqLines;
        if (r.noise) noises.add(r.noise.split('\n')[0]);
        console.log(`[${done}/${jobs.length}] ok ${S.name} (${S.cycles} cycles)`);
        if (!opt.keep) rmSync(file);
      }
    }
  };
  await Promise.all(Array.from({ length: opt.jobs }, worker));
  for (const n of noises) console.log(`note: stderr output (identical on both sides was not checked): ${n}`);

  // speed of the native PIO on the busiest random scenario
  const benchFile = join(dir, 'bench.txt');
  const B = genRandom(7, 2000000);
  writeFileSync(benchFile, B.text());
  const bench = await run(opt.cxx, [benchFile, 'bench']);
  console.log(bench.out.trim());
  if (!opt.keep) rmSync(dir, { recursive: true, force: true });

  const what = `${jobs.length} scenarios, ${totalCycles} cycles (x 8 state machines), IRQ lines ${irqLinesAll ? 'compared' : 'not compared (core setInterrupt not ported yet)'}`;
  if (failures) {
    console.log(`PIO DIFF FAIL: ${failures} of ${what} mismatched`);
    return 1;
  }
  console.log(`PIO DIFF PASS: ${what}, 0 mismatches`);
  return 0;
}

const argv = process.argv.slice(2);
if (argv[0] === '--run') {
  const [, file, mode, a, b] = argv;
  const irqLines = argv.includes('--irq-lines');
  await runJs(file, mode, Number(a), mode === 'dump' ? Number(b) : 0, irqLines);
} else {
  process.exit(await main(argv));
}
