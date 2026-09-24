#!/usr/bin/env node
// Differential test of the C++ CortexM0Core / RPPPB port against rp2040js.
//
//   node emu/rp2040/test/core/core-diff.mjs --driver build/emu-native-core/test_core_diff \
//       [--seeds 1-10] [--steps 50000] [--systick]
//
// This script is the generator and the reference: it runs rp2040js (the built
// dist of the patched checkout) instruction by instruction and, for every
// step, streams to the C++ driver (test_core_diff.cpp) the exact operations it
// did (memory pokes, register/field patches, setInterrupt calls, clock ticks)
// followed by `X <state>`: the full core state rp2040js had after
// `core0.executeInstruction()`. The driver replays the operations on the C++
// RP2040, executes the same instruction and compares its state string.
//
// Instructions are generated one step at a time, knowing the JS state, so that
// every bus access goes to SRAM, flash, the bootrom, the PPB (NVIC, SCB,
// SysTick), SIO CPUID or SYSCFG (the ported parts of the chip): the base
// registers of loads/stores are patched to reach a chosen address (with
// register sums that wrap past 2**32). Everything else is random: register
// values, flags, PRIMASK, CONTROL, mode, NVIC state, exceptions (pended by
// STR to ISPR/ICSR, SVC, setInterrupt, and with --systick the SysTick timer),
// exception returns (BX / POP PC with EXC_RETURN), WFI/WFE/SEV, BKPT/UDF,
// MSR/MRS of every SYSm, unimplemented encodings (their warnings are
// compared too).
//
// State compared after every instruction: r0-r15, banked SP, xPSR, IPSR, PM,
// SPSEL, nPRIV, mode, cycles, the returned deltaCycles, NVIC pending/enabled/
// priorities, pendingNMI/PendSV/SVCall/Systick, interruptsUpdated, VTOR,
// SHPR2/3, event/waiting flags (both cores), breakRewind, interruptNMIMask,
// SysTick fields, blTaken calls, onBreak codes, every logger message, and an
// FNV hash of the vector tables, data and stack windows; the whole SRAM is
// hashed at the end of every block of instructions.
//
// Prints one line, PASS or FAIL, and exits 0 on PASS.
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
function opt(name, dflt) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
}
const driver = opt('--driver');
const seedsArg = opt('--seeds', '1-10');
const stepsPerSeed = Number(opt('--steps', '50000'));
const blockLen = Number(opt('--block', '256'));
const systickMode = args.includes('--systick');
const statsMode = args.includes('--stats');
if (!driver) {
  console.log('FAIL core-diff: --driver <path to test_core_diff> is required');
  process.exit(2);
}
const seeds = [];
for (const part of seedsArg.split(',')) {
  const [a, b] = part.split('-').map(Number);
  for (let s = a; s <= (b ?? a); s++) seeds.push(s);
}

const sdk = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
const dist = process.env.RP2040JS_DIST ?? path.join(sdk, 'rp2040js/dist/esm/index.js');
const { RP2040 } = await import(pathToFileURL(dist).href);

// ---- memory layout --------------------------------------------------------
const VT = [0x20000000, 0x20000100]; // two vector tables (48 entries each)
const CODE_LO = 0x20001000;
const CODE_HI = 0x20002000;
const HANDLERS = Array.from({ length: 8 }, (_, k) => CODE_LO + 0x100 + 0x200 * k);
const HSET = new Set(HANDLERS);
// Each block runs its code in one of these windows (the exception handlers stay
// in the SRAM one): SRAM, flash, a flash XIP mirror (0x11/0x12/0x13, written
// through 0x10: the mirrors only read) or the bootrom (which TS lets a store
// write), so instruction fetches cover every memory the fetch path reads directly.
// [lo, hi, write offset]
const RUN_WINDOWS = [
  [CODE_LO, CODE_HI, 0],
  [0x10002000, 0x10003000, 0],
  [0x11002000, 0x11003000, -0x01000000],
  [0x12002000, 0x12003000, -0x02000000],
  [0x13002000, 0x13003000, -0x03000000],
  [0x00002000, 0x00003000, 0],
];
let run = RUN_WINDOWS[0];
const inWindow = (w, a) => a >= w[0] && a <= w[1] - 4;
const codeAddr = (a) => (inWindow(run, a) ? a + run[2] : a) >>> 0;
const DATA_LO = 0x20010000;
const DATA_HI = 0x20010400;
const MS_LO = 0x2001fc00;
const MS_HI = 0x20020000;
const PS_LO = 0x20030c00;
const PS_HI = 0x20031000;
const SP_MARGIN = 128;
const HASH_RANGES = [
  [0x20000000, 0x20000200],
  [DATA_LO, DATA_HI],
  [MS_LO, MS_HI],
  [PS_LO, PS_HI],
];
const SRAM_WORDS = (264 * 1024) / 4;

// ---- PRNG (sfc32) ---------------------------------------------------------
let sa, sb, sc, sd;
function seedRng(seed) {
  sa = 0x9e3779b9;
  sb = 0x243f6a88;
  sc = 0xb7e15162;
  sd = seed >>> 0;
  for (let i = 0; i < 20; i++) rnd();
}
function rnd() {
  const t = (((sa + sb) | 0) + sd) | 0;
  sd = (sd + 1) | 0;
  sa = sb ^ (sb >>> 9);
  sb = (sc + (sc << 3)) | 0;
  sc = (sc << 21) | (sc >>> 11);
  sc = (sc + t) | 0;
  return t >>> 0;
}
const ri = (n) => rnd() % n;
const chance = (p) => rnd() / 4294967296 < p;
const pick = (arr) => arr[ri(arr.length)];
function weighted(list) {
  let total = 0;
  for (const [w] of list) total += w;
  let r = ri(total);
  for (const [w, v] of list) {
    if (r < w) return v;
    r -= w;
  }
  return list[list.length - 1][1];
}
function randValue() {
  switch (ri(10)) {
    case 0:
      return 0;
    case 1:
      return pick([0xffffffff, 0x80000000, 0x7fffffff, 1, 0xfffffffe, 0x80000001]);
    case 2:
      return ri(256);
    case 3:
      return (1 << ri(32)) >>> 0;
    case 4:
      return (-1 - ri(256)) >>> 0;
    case 5:
      return (0x20000000 + ri(264 * 1024)) >>> 0;
    default:
      return rnd();
  }
}

// ---- output to the driver -------------------------------------------------
const child = spawn(driver, [], { stdio: ['pipe', 'pipe', 'inherit'] });
let childOut = '';
child.stdout.on('data', (d) => (childOut += d));
const childExit = once(child, 'exit');
let buf = [];
let bufLen = 0;
async function emit(line) {
  buf.push(line);
  bufLen += line.length + 1;
  if (bufLen > 1 << 20) await flush();
}
async function flush() {
  if (!buf.length) return;
  const s = buf.join('\n') + '\n';
  buf = [];
  bufLen = 0;
  if (!child.stdin.write(s)) await once(child.stdin, 'drain');
}

// ---- state ----------------------------------------------------------------
const hex = (v) => (v >>> 0).toString(16);
let mcu, core, sram32;
let logs, breaks, blCount;

function hashRange(h, lo, hi) {
  for (let i = (lo - 0x20000000) >> 2, e = (hi - 0x20000000) >> 2; i < e; i++) {
    h = Math.imul(h ^ sram32[i], 16777619);
  }
  return h;
}
function windowHash() {
  let h = 0x811c9dc5 | 0;
  for (const [lo, hi] of HASH_RANGES) h = hashRange(h, lo, hi);
  return hex(h);
}
function sramHash() {
  let h = 0x811c9dc5 | 0;
  for (let i = 0; i < SRAM_WORDS; i++) h = Math.imul(h ^ sram32[i], 16777619);
  return hex(h);
}
function stateLine(delta) {
  const c = core;
  const c1 = mcu.core1;
  const ppb = mcu.ppb;
  const f = [
    ...Array.from(c.registers, hex),
    hex(c.bankedSP),
    hex(c.xPSR),
    hex(c.IPSR),
    +c.PM,
    +c.SPSEL,
    +c.nPRIV,
    +c.currentMode,
    String(c.cycles),
    String(delta),
    hex(c.pendingInterrupts),
    hex(c.enabledInterrupts),
    ...c.interruptPriorities.map(hex),
    +c.pendingNMI,
    +c.pendingPendSV,
    +c.pendingSVCall,
    +c.pendingSystick,
    +c.interruptsUpdated,
    hex(c.VTOR),
    hex(c.SHPR2),
    hex(c.SHPR3),
    +c.eventRegistered,
    +c.waiting,
    +c.waitingForEvent,
    String(c.breakRewind),
    hex(c.interruptNMIMask),
    +c1.eventRegistered,
    +c1.waiting,
    +c1.waitingForEvent,
    +ppb.systickCountFlag,
    +ppb.systickClkSource,
    +ppb.systickIntEnable,
    hex(ppb.systickReload),
    windowHash(),
    String(blCount),
    'b' + breaks.join(','),
    'L' + logs.join('|'),
  ];
  logs = [];
  breaks = [];
  blCount = 0;
  return f.join(' ');
}

// ---- operations (applied to JS and sent to the driver) --------------------
async function setReg(i, v) {
  core.registers[i] = v;
  await emit(`R ${i} ${hex(v)}`);
}
const FIELDS = {
  N: (v) => (core.N = !!v),
  Z: (v) => (core.Z = !!v),
  C: (v) => (core.C = !!v),
  V: (v) => (core.V = !!v),
  PM: (v) => (core.PM = !!v),
  SPSEL: (v) => (core.SPSEL = v),
  nPRIV: (v) => (core.nPRIV = !!v),
  mode: (v) => (core.currentMode = v),
  IPSR: (v) => (core.IPSR = v),
  bankedSP: (v) => (core.bankedSP = v),
  VTOR: (v) => (core.VTOR = v),
  SHPR2: (v) => (core.SHPR2 = v),
  SHPR3: (v) => (core.SHPR3 = v),
  pend: (v) => (core.pendingInterrupts = v),
  en: (v) => (core.enabledInterrupts = v),
  p0: (v) => (core.interruptPriorities[0] = v),
  p1: (v) => (core.interruptPriorities[1] = v),
  p2: (v) => (core.interruptPriorities[2] = v),
  p3: (v) => (core.interruptPriorities[3] = v),
  nmi: (v) => (core.pendingNMI = !!v),
  pendsv: (v) => (core.pendingPendSV = !!v),
  svc: (v) => (core.pendingSVCall = !!v),
  systick: (v) => (core.pendingSystick = !!v),
  upd: (v) => (core.interruptsUpdated = !!v),
  evt: (v) => (core.eventRegistered = !!v),
  wait: (v) => (core.waiting = !!v),
  wfe: (v) => (core.waitingForEvent = !!v),
  nmimask: (v) => (core.interruptNMIMask = v),
};
async function setField(name, v) {
  FIELDS[name](v);
  await emit(`F ${name} ${hex(v)}`);
}
async function poke32(addr, v) {
  mcu.writeUint32(addr, v);
  await emit(`P ${hex(addr)} ${hex(v)}`);
}
async function poke16(addr, v) {
  mcu.writeUint16(addr, v);
  await emit(`H ${hex(addr)} ${hex(v)}`);
}
async function pokeWords(addr, words) {
  for (let i = 0; i < words.length; i++) mcu.writeUint32(addr + 4 * i, words[i]);
  await emit(`W ${hex(addr)} ${words.map(hex).join(' ')}`);
}
async function setInterrupt(irq, v) {
  core.setInterrupt(irq, v);
  await emit(`I ${irq} ${+v}`);
}
async function tick(ns) {
  mcu.clock.tick(ns);
  await emit(`T ${ns}`);
}

// ---- instruction generators -----------------------------------------------
const lo = () => ri(8);
const r16 = () => ri(16);
const ALU_REG = [
  0x4000, 0x4040, 0x4080, 0x40c0, 0x4100, 0x4140, 0x4180, 0x41c0, 0x4200, 0x4240, 0x4280,
  0x42c0, 0x4300, 0x4340, 0x4380, 0x43c0,
];
const EXT = [0xb200, 0xb240, 0xb280, 0xb2c0, 0xba00, 0xba40, 0xbac0];
const HINTS = [0xbf00, 0xbf10, 0xbf20, 0xbf30, 0xbf40];
const SYSMS = [0, 1, 2, 3, 5, 6, 7, 8, 9, 16, 20];

function isMemory(hw) {
  return (
    hw >> 11 === 0b01001 ||
    hw >> 12 === 0b0101 ||
    hw >> 13 === 0b011 ||
    hw >> 12 === 0b1000 ||
    hw >> 12 === 0b1001 ||
    hw >> 12 === 0b1100 ||
    hw >> 9 === 0b1011010 ||
    hw >> 9 === 0b1011110
  );
}
const isWide = (hw) => hw >> 12 === 0b1111 || hw >> 11 === 0b11101;

/** A non-memory instruction: [hw1] or [hw1, hw2]. */
function genSafe(allowWide) {
  for (;;) {
    const r = genSafe1();
    if (r.length === 1 || allowWide) return r;
  }
}
function genSafe1() {
  switch (ri(40)) {
    case 0:
    case 1:
    case 2:
    case 3:
      return [pick(ALU_REG) | (lo() << 3) | lo()];
    case 4:
      return [0xa800 | (lo() << 8) | ri(256)]; // ADD Rd, SP, #imm
    case 5:
      return [(chance(0.5) ? 0xb000 : 0xb080) | ri(128)]; // ADD/SUB SP, #imm
    case 6:
      return [pick([0x1c00, 0x1e00, 0x1800, 0x1a00]) | (ri(8) << 6) | (lo() << 3) | lo()];
    case 7:
      return [pick([0x3000, 0x3800, 0x2000, 0x2800]) | (lo() << 8) | ri(256)];
    case 8:
    case 9: {
      // shifts by immediate
      const imm5 = chance(0.3) ? pick([0, 1, 31]) : ri(32);
      return [pick([0x0000, 0x0800, 0x1000]) | (imm5 << 6) | (lo() << 3) | lo()];
    }
    case 10:
      return [0x4400 | (ri(2) << 7) | (r16() << 3) | lo()]; // ADD (register), incl. SP/PC
    case 11:
      return [0x4600 | (ri(2) << 7) | (r16() << 3) | lo()]; // MOV (register)
    case 12:
      return [0x4500 | (ri(2) << 7) | (r16() << 3) | lo()]; // CMP T2
    case 13:
      return [0xa000 | (lo() << 8) | ri(256)]; // ADR
    case 14:
    case 15:
      return [0xd000 | (ri(14) << 8) | ri(256)]; // B<cond>
    case 16:
      return [0xe000 | ri(2048)]; // B
    case 17:
      return [pick([0x4700, 0x4780]) | (r16() << 3)]; // BX / BLX
    case 18: {
      // BL: near (in the code window) or anywhere
      // near: J1 = J2 = 1 makes I1 = I2 = S, a short offset (imm10 all S bits)
      const S = ri(2);
      const near = chance(0.6);
      const J1 = near ? 1 : ri(2);
      const J2 = near ? 1 : ri(2);
      const imm10 = near ? (S ? 0x3ff : 0) : ri(1024);
      return [0xf000 | (S << 10) | imm10, 0xd000 | (J1 << 13) | (J2 << 11) | ri(2048)];
    }
    case 19:
      return [pick(EXT) | (lo() << 3) | lo()];
    case 20:
      return [pick([0xb672, 0xb662])]; // CPSID / CPSIE
    case 21:
      return [pick(HINTS)];
    case 22:
      return [0xdf00 | ri(256)]; // SVC
    case 23:
      return [pick([0xbe00, 0xde00]) | ri(256)]; // BKPT / UDF
    case 24:
      return [0xf7f0 | ri(16), 0xa000 | ri(4096)]; // UDF.W
    case 25:
      return [0xf3bf, pick([0x8f50, 0x8f40, 0x8f60]) | ri(16)]; // DMB / DSB / ISB
    case 26:
    case 27: {
      const sysm = chance(0.9) ? pick(SYSMS) : ri(256);
      return [0xf3ef, 0x8000 | (r16() << 8) | sysm]; // MRS
    }
    case 28:
    case 29: {
      const sysm = chance(0.9) ? pick(SYSMS) : ri(256);
      return [0xf380 | r16(), 0x8800 | sysm]; // MSR
    }
    case 30:
    case 31:
      return [pick(ALU_REG) | (lo() << 3) | lo()];
    case 32:
    case 33:
      return [0x2000 | (lo() << 8) | ri(256)]; // MOVS
    default: {
      // any non-memory halfword (and any second halfword): mostly unimplemented encodings
      for (;;) {
        const hw = ri(0x10000);
        if (isMemory(hw)) continue;
        return isWide(hw) ? [hw, ri(0x10000)] : [hw];
      }
    }
  }
}

// PPB offsets (from 0xe000e000) the generator reads/writes
const PPB_READ = [
  0x014, 0x01c, 0x100, 0x180, 0x200, 0x280, 0x400, 0x404, 0x408, 0x40c, 0x410, 0x414, 0x418,
  0x41c, 0xd00, 0xd04, 0xd08, 0xd1c, 0xd20, 0xd10, 0x000,
];
const PPB_WRITE = [
  0x014, 0x100, 0x180, 0x200, 0x280, 0x400, 0x404, 0x408, 0x40c, 0x410, 0x414, 0x418, 0x41c,
  0xd04, 0xd08, 0xd1c, 0xd20, 0xd10, 0xd00, 0x010, 0x01c,
];
if (systickMode) {
  PPB_READ.push(0x010, 0x018);
  PPB_WRITE.push(0x018);
}
const ICSR_BITS = [1 << 31, 1 << 28, 1 << 27, 1 << 26, 1 << 25];

function ppbValue(off) {
  switch (off) {
    case 0xd08:
      return pick(VT);
    case 0xd04: {
      let v = 0;
      for (const b of ICSR_BITS) if (chance(b === 1 << 31 ? 0.1 : 0.35)) v |= b;
      return (v | (chance(0.2) ? rnd() & 0x01ffffff : 0)) >>> 0;
    }
    case 0x010:
      return (rnd() & (systickMode ? 0xffffffff : 0xfffffffe)) >>> 0;
    case 0x014:
      return systickMode && chance(0.8) ? 20 + ri(2000) : randValue();
    case 0x100:
    case 0x200:
      return chance(0.5) ? (1 << ri(32)) >>> 0 : rnd();
    default:
      return randValue();
  }
}

/** A target for a data access of `size` bytes: { addr, value? } (value for stores that must be crafted). */
function target(size, write, allowOdd) {
  const kind = write
    ? weighted([
        [60, 'data'],
        [10, 'ms'],
        [10, 'ps'],
        [16, 'ppb'],
        [4, 'syscfg'],
      ])
    : weighted([
        [40, 'data'],
        [8, 'ms'],
        [8, 'ps'],
        [10, 'flash'],
        [5, 'rom'],
        [20, 'ppb'],
        [4, 'sio'],
        [5, 'syscfg'],
      ]);
  const ramAddr = (lo, hi) => {
    let a = lo + ri(hi - lo - 4);
    if (!(allowOdd && chance(size === 1 ? 1 : size === 2 ? 0.1 : 0.05))) a &= ~(size - 1);
    return a >>> 0;
  };
  switch (kind) {
    case 'data':
      return { addr: ramAddr(DATA_LO, DATA_HI) };
    case 'ms':
      return { addr: ramAddr(MS_LO, MS_HI) };
    case 'ps':
      return { addr: ramAddr(PS_LO, PS_HI) };
    case 'flash':
      return { addr: ((0x10000000 + ri(4) * 0x01000000 + ri(0x1000)) & ~(size - 1)) >>> 0 };
    case 'rom':
      return { addr: ri(0x4000) & ~(size - 1) };
    case 'sio':
      return { addr: (0xd0000000 + (ri(4) & ~(size - 1))) >>> 0 };
    case 'syscfg': {
      // offset 4 is unimplemented: BasePeripheral warns with the value, which JS prints as a
      // negative number after an atomic OR / XOR or a byte replication (peripheral.ts, not the
      // core), so offset 4 only gets plain word accesses
      let off = pick([0, 0, 0, 4]);
      if (off === 4 && write && size < 4) off = 0;
      const alias = write && off === 0 ? ri(4) * 0x1000 : 0;
      return {
        addr: (0x40004000 + alias + off + (ri(4) & ~(size - 1) & (size === 4 ? 0 : 3))) >>> 0,
        value: randValue(),
      };
    }
    case 'ppb': {
      let off;
      for (;;) {
        off = pick(write ? PPB_WRITE : PPB_READ);
        // partial accesses read-modify-write the word: keep VTOR a vector table, SysTick CSR
        // (its enable bit comes from the timer) out of it unless --systick
        if (size < 4 && write && (off === 0xd08 || (!systickMode && off === 0x010))) continue;
        break;
      }
      const sub = size === 4 ? 0 : ri(4) & ~(size - 1);
      return { addr: (0xe000e000 + off + sub) >>> 0, value: ppbValue(off) };
    }
  }
}

function spOK() {
  const msp = core.SPmain;
  const psp = core.SPprocess;
  return (
    msp >= MS_LO + SP_MARGIN &&
    msp <= MS_HI - SP_MARGIN &&
    psp >= PS_LO + SP_MARGIN &&
    psp <= PS_HI - SP_MARGIN
  );
}

/** Generate a memory instruction; may patch registers / poke the stack. Returns [hw] or null. */
async function genMem() {
  const kinds = [
    [6, 'ldr_imm'],
    [6, 'str_imm'],
    [3, 'ldrb_imm'],
    [3, 'strb_imm'],
    [3, 'ldrh_imm'],
    [3, 'strh_imm'],
    [4, 'ldr_reg'],
    [4, 'str_reg'],
    [2, 'ldrb_reg'],
    [2, 'strb_reg'],
    [2, 'ldrh_reg'],
    [2, 'strh_reg'],
    [2, 'ldrsb'],
    [2, 'ldrsh'],
    [3, 'ldr_sp'],
    [3, 'str_sp'],
    [3, 'ldr_lit'],
    [3, 'ldm'],
    [3, 'stm'],
    [4, 'push'],
    [4, 'pop'],
  ];
  const kind = weighted(kinds);
  const IMM = {
    ldr_imm: [0x6800, 4, false],
    str_imm: [0x6000, 4, true],
    ldrb_imm: [0x7800, 1, false],
    strb_imm: [0x7000, 1, true],
    ldrh_imm: [0x8800, 2, false],
    strh_imm: [0x8000, 2, true],
  };
  const REG = {
    str_reg: [0x5000, 4, true],
    strh_reg: [0x5200, 2, true],
    strb_reg: [0x5400, 1, true],
    ldrsb: [0x5600, 1, false],
    ldr_reg: [0x5800, 4, false],
    ldrh_reg: [0x5a00, 2, false],
    ldrb_reg: [0x5c00, 1, false],
    ldrsh: [0x5e00, 2, false],
  };
  if (IMM[kind]) {
    const [base, size, write] = IMM[kind];
    const t = target(size, write, true);
    const imm5 = ri(32);
    const Rn = lo();
    let Rt = lo();
    if (t.value !== undefined && write) while (Rt === Rn) Rt = lo();
    await setReg(Rn, (t.addr - imm5 * size) >>> 0);
    if (t.value !== undefined && write) await setReg(Rt, t.value);
    return [base | (imm5 << 6) | (Rn << 3) | Rt];
  }
  if (REG[kind]) {
    const [base, size, write] = REG[kind];
    const t = target(size, write, true);
    const Rm = lo();
    let Rn = lo();
    if (Rn === Rm && (t.addr & 1)) while (Rn === Rm) Rn = lo();
    let Rt = lo();
    if (t.value !== undefined && write) while (Rt === Rn || Rt === Rm) Rt = lo();
    if (Rn === Rm) {
      await setReg(Rn, ((t.addr >>> 1) + (chance(0.5) ? 0x80000000 : 0)) >>> 0);
    } else {
      if (chance(0.3)) await setReg(Rm, randValue());
      await setReg(Rn, (t.addr - core.registers[Rm]) >>> 0);
    }
    if (t.value !== undefined && write) await setReg(Rt, t.value);
    return [base | (Rm << 6) | (Rn << 3) | Rt];
  }
  switch (kind) {
    case 'ldr_sp':
      return [0x9800 | (lo() << 8) | ri(256)];
    case 'str_sp':
      return [0x9000 | (lo() << 8) | ri(256)];
    case 'ldr_lit':
      return [0x4800 | (lo() << 8) | ri(256)];
    case 'ldm':
    case 'stm': {
      const write = kind === 'stm';
      const Rn = lo();
      const list = chance(0.03) ? 0 : ri(256);
      const region = write ? pick(['data', 'data', 'ms', 'ps']) : pick(['data', 'ms', 'ps', 'flash', 'rom']);
      let addr;
      if (region === 'flash') addr = 0x10000000 + (ri(0x1000) & ~3);
      else if (region === 'rom') addr = ri(0x3f00) & ~3;
      else {
        const [l, h] = { data: [DATA_LO, DATA_HI], ms: [MS_LO, MS_HI], ps: [PS_LO, PS_HI] }[region];
        addr = l + ri(h - l - 40);
        if (!chance(0.05)) addr &= ~3;
      }
      await setReg(Rn, addr >>> 0);
      return [(write ? 0xc000 : 0xc800) | (Rn << 8) | list];
    }
    case 'push':
      return [0xb400 | ri(512)];
    case 'pop': {
      const list = ri(256);
      const P = ri(2);
      if (P && core.currentMode === 1 && chance(0.5)) {
        // exception return through POP {..., PC}
        let n = 0;
        for (let i = 0; i < 8; i++) if (list & (1 << i)) n++;
        await poke32(core.SP + 4 * n, excReturn());
      }
      return [0xbc00 | (P << 8) | list];
    }
  }
  return null;
}

function excReturn() {
  return chance(0.85)
    ? pick([0xfffffff1, 0xfffffff9, 0xfffffffd])
    : (0xf0000000 | (rnd() & 0x0fffffff)) >>> 0;
}

// ---- coverage (--stats) --------------------------------------------------------
// The branches of CortexM0Core.executeInstruction, in its order.
const DECODE = [
  ['ADCS', (o) => o >> 6 === 0b0100000101],
  ['ADD Rd,SP,#', (o) => o >> 11 === 0b10101],
  ['ADD SP,#', (o) => o >> 7 === 0b101100000],
  ['ADDS T1', (o) => o >> 9 === 0b0001110],
  ['ADDS T2', (o) => o >> 11 === 0b00110],
  ['ADDS reg', (o) => o >> 9 === 0b0001100],
  ['ADD reg', (o) => o >> 8 === 0b01000100],
  ['ADR', (o) => o >> 11 === 0b10100],
  ['ANDS', (o) => o >> 6 === 0b0100000000],
  ['ASRS imm', (o) => o >> 11 === 0b00010],
  ['ASRS reg', (o) => o >> 6 === 0b0100000100],
  ['B cond', (o) => o >> 12 === 0b1101 && ((o >> 9) & 0x7) !== 0b111],
  ['B', (o) => o >> 11 === 0b11100],
  ['BICS', (o) => o >> 6 === 0b0100001110],
  ['BKPT', (o) => o >> 8 === 0b10111110],
  ['BL', (o, o2) => o >> 11 === 0b11110 && o2 >> 14 === 0b11 && ((o2 >> 12) & 0x1) == 1],
  ['BLX', (o) => o >> 7 === 0b010001111 && (o & 0x7) === 0],
  ['BX', (o) => o >> 7 === 0b010001110 && (o & 0x7) === 0],
  ['CMN', (o) => o >> 6 === 0b0100001011],
  ['CMP imm', (o) => o >> 11 === 0b00101],
  ['CMP reg', (o) => o >> 6 === 0b0100001010],
  ['CMP T2', (o) => o >> 8 === 0b01000101],
  ['CPSID', (o) => o === 0xb672],
  ['CPSIE', (o) => o === 0xb662],
  ['DMB', (o, o2) => o === 0xf3bf && (o2 & 0xfff0) === 0x8f50],
  ['DSB', (o, o2) => o === 0xf3bf && (o2 & 0xfff0) === 0x8f40],
  ['EORS', (o) => o >> 6 === 0b0100000001],
  ['ISB', (o, o2) => o === 0xf3bf && (o2 & 0xfff0) === 0x8f60],
  ['LDMIA', (o) => o >> 11 === 0b11001],
  ['LDR imm', (o) => o >> 11 === 0b01101],
  ['LDR sp', (o) => o >> 11 === 0b10011],
  ['LDR lit', (o) => o >> 11 === 0b01001],
  ['LDR reg', (o) => o >> 9 === 0b0101100],
  ['LDRB imm', (o) => o >> 11 === 0b01111],
  ['LDRB reg', (o) => o >> 9 === 0b0101110],
  ['LDRH imm', (o) => o >> 11 === 0b10001],
  ['LDRH reg', (o) => o >> 9 === 0b0101101],
  ['LDRSB', (o) => o >> 9 === 0b0101011],
  ['LDRSH', (o) => o >> 9 === 0b0101111],
  ['LSLS imm', (o) => o >> 11 === 0b00000],
  ['LSLS reg', (o) => o >> 6 === 0b0100000010],
  ['LSRS imm', (o) => o >> 11 === 0b00001],
  ['LSRS reg', (o) => o >> 6 === 0b0100000011],
  ['MOV', (o) => o >> 8 === 0b01000110],
  ['MOVS', (o) => o >> 11 === 0b00100],
  ['MRS', (o, o2) => o === 0b1111001111101111 && o2 >> 12 == 0b1000],
  ['MSR', (o, o2) => o >> 4 === 0b111100111000 && o2 >> 8 == 0b10001000],
  ['MULS', (o) => o >> 6 === 0b0100001101],
  ['MVNS', (o) => o >> 6 === 0b0100001111],
  ['ORRS', (o) => o >> 6 === 0b0100001100],
  ['POP', (o) => o >> 9 === 0b1011110],
  ['PUSH', (o) => o >> 9 === 0b1011010],
  ['REV', (o) => o >> 6 === 0b1011101000],
  ['REV16', (o) => o >> 6 === 0b1011101001],
  ['REVSH', (o) => o >> 6 === 0b1011101011],
  ['ROR', (o) => o >> 6 === 0b0100000111],
  ['RSBS', (o) => o >> 6 === 0b0100001001],
  ['NOP', (o) => o === 0b1011111100000000],
  ['SBCS', (o) => o >> 6 === 0b0100000110],
  ['SEV', (o) => o === 0b1011111101000000],
  ['STMIA', (o) => o >> 11 === 0b11000],
  ['STR imm', (o) => o >> 11 === 0b01100],
  ['STR sp', (o) => o >> 11 === 0b10010],
  ['STR reg', (o) => o >> 9 === 0b0101000],
  ['STRB imm', (o) => o >> 11 === 0b01110],
  ['STRB reg', (o) => o >> 9 === 0b0101010],
  ['STRH imm', (o) => o >> 11 === 0b10000],
  ['STRH reg', (o) => o >> 9 === 0b0101001],
  ['SUB SP,#', (o) => o >> 7 === 0b101100001],
  ['SUBS T1', (o) => o >> 9 === 0b0001111],
  ['SUBS T2', (o) => o >> 11 === 0b00111],
  ['SUBS reg', (o) => o >> 9 === 0b0001101],
  ['SVC', (o) => o >> 8 === 0b11011111],
  ['SXTB', (o) => o >> 6 === 0b1011001001],
  ['SXTH', (o) => o >> 6 === 0b1011001000],
  ['TST', (o) => o >> 6 == 0b0100001000],
  ['UDF', (o) => o >> 8 == 0b11011110],
  ['UDF.W', (o, o2) => o >> 4 === 0b111101111111 && o2 >> 12 === 0b1010],
  ['UXTB', (o) => o >> 6 == 0b1011001011],
  ['UXTH', (o) => o >> 6 == 0b1011001010],
  ['WFE', (o) => o === 0b1011111100100000],
  ['WFI', (o) => o === 0b1011111100110000],
  ['YIELD', (o) => o === 0b1011111100010000],
];
const stats = new Map();
const count = (k) => stats.set(k, (stats.get(k) ?? 0) + 1);
function classify(pc) {
  // (quietly: a fetch outside the memories warns, and the C++ side does not classify)
  const logger = mcu.logger;
  mcu.logger = { debug() {}, info() {}, warn() {}, error() {} };
  const o = mcu.readUint16(pc & ~1);
  const o2 = isWide(o) ? mcu.readUint16((pc & ~1) + 2) : 0;
  mcu.logger = logger;
  for (const [name, test] of DECODE) if (test(o, o2)) return name;
  return 'unimplemented';
}

// ---- test --------------------------------------------------------------------
async function newBlock() {
  // memory
  const rw = (n) => Array.from({ length: n }, randValue);
  await pokeWords(DATA_LO, rw((DATA_HI - DATA_LO) / 4));
  await pokeWords(MS_LO, rw((MS_HI - MS_LO) / 4));
  await pokeWords(PS_LO, rw((PS_HI - PS_LO) / 4));
  const code = [];
  for (let a = CODE_LO; a < CODE_HI; ) {
    const ins = genSafe(a + 4 <= CODE_HI && !HSET.has(a + 2));
    code.push(...ins);
    a += 2 * ins.length;
  }
  const words = [];
  for (let i = 0; i < code.length; i += 2) words.push((code[i] | ((code[i + 1] ?? 0) << 16)) >>> 0);
  await pokeWords(CODE_LO, words);
  run = chance(0.6) ? RUN_WINDOWS[0] : pick(RUN_WINDOWS);
  if (run !== RUN_WINDOWS[0]) {
    const other = [];
    for (let a = run[0]; a < run[1]; ) {
      const ins = genSafe(a + 4 <= run[1]);
      other.push(...ins);
      a += 2 * ins.length;
    }
    const w = [];
    for (let i = 0; i < other.length; i += 2) w.push((other[i] | ((other[i + 1] ?? 0) << 16)) >>> 0);
    await pokeWords(codeAddr(run[0]), w);
  }

  // registers and fields
  for (let i = 0; i <= 12; i++) await setReg(i, randValue());
  await setReg(14, chance(0.3) ? excReturn() : randValue());
  const handler = chance(0.3);
  await setField('mode', handler ? 1 : 0);
  const spsel = handler ? 0 : ri(2);
  await setField('SPSEL', spsel);
  const msp = (MS_LO + SP_MARGIN + ri(MS_HI - MS_LO - 2 * SP_MARGIN)) & ~3;
  const psp = (PS_LO + SP_MARGIN + ri(PS_HI - PS_LO - 2 * SP_MARGIN)) & ~(chance(0.9) ? 3 : 0);
  await setReg(13, spsel ? psp & ~3 : msp);
  await setField('bankedSP', spsel ? msp : psp);
  await setReg(15, (run[0] + ri(run[1] - run[0] - 4)) & ~(chance(0.9) ? 1 : 0));
  for (const f of ['N', 'Z', 'C', 'V', 'nPRIV']) await setField(f, ri(2));
  await setField('PM', chance(0.3) ? 1 : 0);
  await setField(
    'IPSR',
    handler ? pick([2, 3, 11, 14, 15, 16 + ri(32), ri(64)]) : chance(0.9) ? 0 : ri(64),
  );
  await setField('VTOR', pick(VT));
  await setField('SHPR2', rnd() & 0xc0000000);
  await setField('SHPR3', rnd() & 0xc0c00000);
  // each IRQ at exactly one priority level (as the NVIC_IPR writes keep it), or anything
  if (chance(0.8)) {
    const p = [0, 0, 0, 0];
    for (let i = 0; i < 32; i++) p[ri(4)] |= 1 << i;
    for (let i = 0; i < 4; i++) await setField(`p${i}`, p[i] >>> 0);
  } else {
    for (let i = 0; i < 4; i++) await setField(`p${i}`, rnd());
  }
  await setField('pend', chance(0.5) ? 0 : rnd() & rnd());
  await setField('en', chance(0.3) ? 0 : rnd());
  await setField('nmi', chance(0.03) ? 1 : 0);
  for (const f of ['pendsv', 'svc', 'systick']) await setField(f, chance(0.1) ? 1 : 0);
  await setField('upd', ri(2));
  await setField('evt', ri(2));
  const w = chance(0.2);
  await setField('wait', +w);
  await setField('wfe', +(w && chance(0.5)));
  await setField('nmimask', chance(0.5) ? 0 : rnd());
  if (systickMode) {
    await poke32(0xe000e014, 20 + ri(3000));
    await poke32(0xe000e018, 0);
    await poke32(0xe000e010, rnd() & 7);
  }
}

async function step() {
  // keep PC in the code window and both stacks in their windows
  const pc = core.PC & ~1;
  if (!inWindow(RUN_WINDOWS[0], pc) && !inWindow(run, pc)) {
    await setReg(15, (run[0] + ri(run[1] - run[0] - 4)) & ~(chance(0.9) ? 1 : 0));
  }
  // now and then a fetch at the end of a memory (a 32-bit instruction's second
  // halfword outside it) or outside every memory
  const edgeFetch = chance(0.004);
  if (edgeFetch) {
    await setReg(15, pick([0x20041ffe, 0x10fffffe, 0x11fffffe, 0x13fffffe, 0x00003ffe, 0x00004000, 0x20042000, 0x30000000]));
  }
  if (!spOK()) {
    const msp = (MS_LO + SP_MARGIN + ri(MS_HI - MS_LO - 2 * SP_MARGIN)) & ~3;
    const psp = (PS_LO + SP_MARGIN + ri(PS_HI - PS_LO - 2 * SP_MARGIN)) & ~3;
    if (core.SPSEL === 0) {
      await setReg(13, msp);
      await setField('bankedSP', psp);
    } else {
      await setReg(13, psp);
      await setField('bankedSP', msp);
    }
  }
  if (core.VTOR !== VT[0] && core.VTOR !== VT[1]) await setField('VTOR', pick(VT));

  // external interrupt lines
  if (chance(0.02)) {
    await setInterrupt(chance(0.8) ? ri(26) : ri(32), chance(0.6));
  }

  const opcodePC = core.PC & ~1;
  // An instruction at a handler entry, or one that may run after an exception entry, must
  // not access memory (it could run with other register values than it was made for).
  const safeOnly = core.interruptsUpdated || HSET.has(opcodePC);
  const allowWide =
    edgeFetch || (!HSET.has(opcodePC + 2) && opcodePC + 4 <= (inWindow(run, opcodePC) ? run[1] : CODE_HI));
  let ins = null;
  if (!safeOnly && chance(0.35)) ins = await genMem();
  if (!ins && core.currentMode === 1 && chance(0.05)) {
    // exception return through BX
    const Rm = r16();
    if (Rm !== 13 && Rm !== 15) {
      await setReg(Rm, excReturn());
      ins = [0x4700 | (Rm << 3)];
    }
  }
  if (!ins && chance(0.01)) {
    // WFE right after SEV / an exception
    ins = [0xbf20];
  }
  if (!ins) ins = genSafe(allowWide);
  await poke16(codeAddr(opcodePC), ins[0]);
  if (ins.length > 1) await poke16(codeAddr(opcodePC) + 2, ins[1]);

  let fetchPC = core.PC;
  let entered = null;
  if (statsMode) {
    const entry = core.exceptionEntry;
    core.exceptionEntry = function (n) {
      entry.call(this, n);
      count(`exception entry ${n < 16 ? n : 'IRQ'}`);
      fetchPC = core.PC;
      entered = n;
    };
    const ret = core.exceptionReturn;
    core.exceptionReturn = function (r) {
      count(`exception return ${hex(r & 0xf)}`);
      ret.call(this, r);
    };
  }
  const fetched = statsMode ? classify(fetchPC) : null;
  if (statsMode) count(`fetch from ${hex(fetchPC >>> 24).padStart(2, '0')}xxxxxx`);
  let delta;
  try {
    delta = core.executeInstruction();
  } catch (e) {
    // a DataView RangeError (STRH at reg + reg >= 2**32 with address & 3 == 3) ends a JS run;
    // compare the state it leaves and go on
    if (!(e instanceof RangeError)) throw e;
    delta = 'RangeError';
  }
  if (statsMode) {
    // (an entry inside the instruction's own checkForInterrupts runs the handler's instruction)
    count(entered === null ? fetched : classify(fetchPC));
    if (delta === 'RangeError') count('RangeError');
    delete core.exceptionEntry;
    delete core.exceptionReturn;
  }
  await emit('X ' + stateLine(delta));
  if (systickMode && typeof delta === 'number') await tick(delta * 8);
}

let total = 0;
const t0 = Date.now();
for (const seed of seeds) {
  seedRng(seed);
  mcu = new RP2040();
  core = mcu.core0;
  sram32 = new Uint32Array(mcu.sram.buffer, mcu.sram.byteOffset, SRAM_WORDS);
  logs = [];
  breaks = [];
  blCount = 0;
  mcu.logger = {
    debug: (c, m) => logs.push(`d:${c}:${m}`),
    info: (c, m) => logs.push(`i:${c}:${m}`),
    warn: (c, m) => logs.push(`w:${c}:${m}`),
    error: (c, m) => logs.push(`e:${c}:${m}`),
  };
  mcu.onBreak = (code) => breaks.push(code);
  core.blTaken = () => blCount++;
  await emit(`N ${seed}`);
  // vector tables: every entry is a handler entry, most with the Thumb bit
  for (const vt of VT) {
    await pokeWords(
      vt,
      Array.from({ length: 48 }, () => (pick(HANDLERS) | (chance(0.9) ? 1 : 0)) >>> 0),
    );
  }
  // flash contents
  await pokeWords(0x10000000, Array.from({ length: 0x1000 / 4 + 16 }, randValue));
  for (let n = 0; n < stepsPerSeed; ) {
    await newBlock();
    const len = Math.min(blockLen, stepsPerSeed - n);
    for (let i = 0; i < len; i++) await step();
    n += len;
    total += len;
    await emit(`K ${sramHash()}`);
  }
}
await emit('E');
await flush();
child.stdin.end();
const [code] = await childExit;
const secs = ((Date.now() - t0) / 1000).toFixed(1);
const m = /steps=(\d+) mismatches=(\d+)/.exec(childOut);
const desc = `${total} instructions, seeds ${seedsArg}, ${stepsPerSeed}/seed${systickMode ? ', systick' : ''}, ${secs}s`;
if (statsMode) {
  for (const [name] of DECODE) if (!stats.has(name)) stats.set(name, 0);
  for (const [k, v] of [...stats].sort()) process.stderr.write(`${k.padEnd(24)} ${v}\n`);
}
if (code === 0 && m && Number(m[1]) === total && m[2] === '0') {
  console.log(`PASS core-diff: ${desc}, 0 mismatches`);
  process.exit(0);
} else {
  process.stderr.write(childOut);
  console.log(`FAIL core-diff: ${desc}, driver exit ${code}, ${m ? m[2] : '?'} mismatches`);
  process.exit(1);
}
