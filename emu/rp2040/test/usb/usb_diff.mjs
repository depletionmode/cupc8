#!/usr/bin/env node
// Differential test of the C++ USB controller port (emu/rp2040/src/peripherals/usb*,
// src/usb/*) against rp2040js (patched dist) with no CPU core.
//
// The JS side runs seeded scenarios: a model of a TinyUSB-like device stack
// (driving USBCDC, or raw host-side events), a model of a TinyUSB-like host
// stack (driving test/emu/usbkbd.mjs's UsbKeyboard), random register / DPRAM
// fuzzing and clock ticks of random length. Every action is an op line; the
// JS executes the op text itself, and the C++ driver (test_usb_diff) replays
// the same op file. Both print a trace of every register / DPRAM read, every
// alarm schedule / cancel / fire (with times), every callback, logger message,
// interrupt-status change and DPRAM-content change, plus keyboard and CDC
// state dumps; the traces must be identical.
//
// usage: node usb_diff.mjs <path/to/test_usb_diff> [--scenarios N] [--steps M]
//        [--seed S] [--keep DIR]
// Prints one PASS/FAIL line; exit 0 on pass.

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const RPJS =
  process.env.RP2040JS_DIR ??
  path.join(process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk'), 'rp2040js');
const rp = await import(pathToFileURL(path.join(RPJS, 'dist/esm/index.js')).href);
const { SimulationClock } = await import(
  pathToFileURL(path.join(RPJS, 'dist/esm/clock/simulation-clock.js')).href
);
const { UsbKeyboard } = await import(new URL('../../../../test/emu/usbkbd.mjs', import.meta.url).href);

// ---- arguments
const args = process.argv.slice(2);
const bin = args[0];
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const SCENARIOS = Number(opt('scenarios', 300));
const STEPS = Number(opt('steps', 3000));
const SEED = Number(opt('seed', 1));
const KEEP = opt('keep', null);
if (!bin) {
  console.log('FAIL usb_diff: usage: node usb_diff.mjs <test_usb_diff> [--scenarios N] [--steps M] [--seed S]');
  process.exit(2);
}

// ---- helpers shared with the C++ driver's formatting
const hex = (v) => (v >>> 0).toString(16);
const f64 = new DataView(new ArrayBuffer(8));
const num = (v) => {
  if (Number.isInteger(v) && Math.abs(v) < 2 ** 53) return String(v);
  f64.setFloat64(0, v);
  return 'f' + f64.getBigUint64(0).toString(16);
};
const bytesHex = (b) => (b.length ? Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('') : '-');
const parseBytes = (s) => (s === '-' ? new Uint8Array(0) : Uint8Array.from(s.match(/../g), (x) => parseInt(x, 16)));

function mulberry32(a) {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- the JS side
let trace = [];
let ops = [];

class LogClock extends SimulationClock {
  constructor() {
    super();
    this.wrap = false;
    this.nextId = 0;
    this.after = () => {};
  }
  createAlarm(callback) {
    if (!this.wrap) return super.createAlarm(callback);
    const id = this.nextId++;
    const inner = super.createAlarm(() => {
      trace.push(`F ${id} ${num(this.nanos)}`);
      callback();
      this.after();
    });
    return {
      schedule: (delta) => {
        trace.push(`S ${id} ${num(delta)} ${num(this.nanos)}`);
        inner.schedule(delta);
      },
      cancel: () => {
        trace.push(`C ${id}`);
        inner.cancel();
      },
    };
  }
}

function fnv(bytes) {
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i++) h = Math.imul(h ^ bytes[i], 0x01000193);
  return h >>> 0;
}

class JsSide {
  constructor(mode, kspeed, kinterval) {
    this.mode = mode;
    this.clock = new LogClock();
    this.mcu = new rp.RP2040(this.clock);
    this.mcu.logger = {
      debug: (c, m) => c === 'USBT' && trace.push(`log D ${m}`),
      info: (c, m) => c === 'USBT' && trace.push(`log I ${m}`),
      warn: (c, m) => c === 'USBT' && trace.push(`log W ${m}`),
      error: (c, m) => c === 'USBT' && trace.push(`log E ${m}`),
    };
    this.clock.wrap = true;
    this.clock.nextId = 0;
    this.ctl = new rp.RPUSBController(this.mcu, 'USBT');
    this.clock.after = () => this.after();
    const ctl = this.ctl;
    if (mode === 'cdc') {
      this.cdc = new rp.USBCDC(ctl);
      this.cdc.onSerialData = (b) => trace.push(`cb ser ${bytesHex(b)}`);
      this.cdc.onDeviceConnected = () => trace.push('cb conn');
    }
    this.hooks = { reads: [], writes: [] };
    const en = ctl.onUSBEnabled,
      rs = ctl.onResetReceived,
      ew = ctl.onEndpointWrite,
      er = ctl.onEndpointRead;
    ctl.onUSBEnabled = () => {
      trace.push('cb en');
      en?.();
    };
    ctl.onResetReceived = () => {
      trace.push('cb rst');
      rs?.();
    };
    ctl.onEndpointWrite = (e, b) => {
      trace.push(`cb w ${e} ${bytesHex(b)}`);
      this.hooks.writes.push([e, Uint8Array.from(b)]);
      ew?.(e, b);
    };
    ctl.onEndpointRead = (e, n) => {
      trace.push(`cb r ${e} ${n}`);
      this.hooks.reads.push([e, n]);
      er?.(e, n);
    };
    if (mode === 'host') this.kbd = new UsbKeyboard({ speed: kspeed, interval: kinterval });
    this.lastInts = 0;
    this.lastIrq = '00';
    this.lastHash = fnv(this.mcu.usbDPRAM);
  }

  after() {
    const v = this.ctl.intStatus >>> 0;
    if (v !== this.lastInts) {
      trace.push(`ints ${hex(v)}`);
      this.lastInts = v;
    }
    // IRQ.USBCTRL (5) as the cores see it, through RP2040.setInterrupt
    const irq = `${(this.mcu.core0.pendingInterrupts >>> 5) & 1}${(this.mcu.core1.pendingInterrupts >>> 5) & 1}`;
    if (irq !== this.lastIrq) {
      trace.push(`irq ${irq}`);
      this.lastIrq = irq;
    }
    const h = fnv(this.mcu.usbDPRAM);
    if (h !== this.lastHash) {
      trace.push(`dh ${hex(h)}`);
      this.lastHash = h;
    }
  }

  exec(line) {
    const a = line.split(' ');
    const ctl = this.ctl;
    const view = this.mcu.usbDPRAMView;
    switch (a[0]) {
      case 'w':
        ctl.writeUint32Atomic(parseInt(a[1], 16), parseInt(a[2], 16), Number(a[3]));
        break;
      case 'r': {
        const v = ctl.readUint32(parseInt(a[1], 16));
        trace.push(`= ${hex(v)}`);
        return v >>> 0;
      }
      case 'd': {
        const off = parseInt(a[1], 16),
          v = parseInt(a[2], 16);
        view.setUint32(off, v, true);
        ctl.DPRAMUpdated(off, v);
        break;
      }
      case 'dr': {
        const v = view.getUint32(parseInt(a[1], 16), true);
        trace.push(`= ${hex(v)}`);
        return v;
      }
      case 't':
        this.clock.tick(Number(a[1]));
        break;
      case 'rd':
        if (a[2] === '-') ctl.endpointReadDone(Number(a[1]), parseBytes(a[3]));
        else ctl.endpointReadDone(Number(a[1]), parseBytes(a[3]), Number(a[2]));
        break;
      case 'sp':
        ctl.sendSetupPacket(parseBytes(a[1]));
        break;
      case 'rst':
        ctl.resetDevice();
        break;
      case 'rdly':
        ctl.readDelayMicroseconds = Number(a[1]);
        break;
      case 'wdly':
        ctl.writeDelayMicroseconds = Number(a[1]);
        break;
      case 'att':
        ctl.attachDevice(this.kbd);
        break;
      case 'det':
        ctl.detachDevice();
        break;
      case 'key':
        this.kbd.press(...a.slice(1).map(Number));
        break;
      case 'ser':
        this.cdc.sendSerialByte(Number(a[1]));
        break;
      case 'fifo':
        trace.push(`fifo ${this.cdc.txFIFO.itemCount}`);
        break;
      case 'kbd': {
        const k = this.kbd;
        const c = k.ctrl;
        let cs = '-';
        if (c) {
          if (c.in) cs = `in:${bytesHex(c.in)}:${c.pos}`;
          else if (c.out) cs = `out:${bytesHex(c.out)}:${c.length}`;
          else cs = 'st';
        }
        const leds = k.leds.map((x) => (x === undefined ? 'u' : String(x))).join(',');
        const log = k.log.map((e) => `${e.type}.${e.req}.${e.value}.${e.length}`).join(',');
        trace.push(
          `kbd a=${k.addr} c=${k.configured} p=${k.protocol} leds=${leds} n=${k.reports.length} log=${log} ctrl=${cs}`,
        );
        break;
      }
      case 'dump':
        trace.push(`dpram ${bytesHex(this.mcu.usbDPRAM)}`);
        break;
      case 'now':
        trace.push(`now ${num(this.clock.nanos)} next ${num(this.clock.nanosToNextAlarm)}`);
        break;
      default:
        throw new Error(`bad op ${line}`);
    }
    return undefined;
  }
}

// ---- constants the models use
const R_ADDR_ENDP = 0x0,
  R_MAIN_CTRL = 0x40,
  R_SOF_RD = 0x48,
  R_SIE_CTRL = 0x4c,
  R_SIE_STATUS = 0x50,
  R_INT_EP_CTRL = 0x54,
  R_BUFF_STATUS = 0x58,
  R_BUFF_CPU = 0x5c,
  R_MUXING = 0x74,
  R_PWR = 0x78,
  R_INTR = 0x8c,
  R_INTE = 0x90,
  R_INTF = 0x94,
  R_INTS = 0x98;
const ALL_REGS = [
  0x0, 0x4, 0x8, 0x3c, 0x40, 0x44, 0x48, 0x4c, 0x50, 0x54, 0x58, 0x5c, 0x60, 0x74, 0x78, 0x8c, 0x90,
  0x94, 0x98, 0x9c,
];
const FULL = 1 << 15,
  LAST = 1 << 14,
  AVAIL = 1 << 10,
  PID1 = 1 << 13;

const CDC_CONFIG = (inEp, outEp, notif) => [
  9, 2, 75, 0, 2, 1, 0, 0x80, 50,
  8, 0x0b, 0, 2, 2, 2, 0, 0,
  9, 4, 0, 0, 1, 2, 2, 0, 0,
  5, 0x24, 0, 0x20, 1,
  5, 0x24, 1, 0, 1,
  4, 0x24, 2, 2,
  5, 0x24, 6, 0, 1,
  7, 5, 0x80 | notif, 3, 8, 0, 16,
  9, 4, 1, 0, 2, 0x0a, 0, 0, 0,
  7, 5, outEp, 2, 64, 0, 0,
  7, 5, 0x80 | inEp, 2, 64, 0, 0,
];
const DEV_DESC = [18, 1, 0, 2, 0xef, 2, 1, 64, 0x8a, 0x2e, 0x0a, 0, 0, 1, 1, 2, 3, 1];

// ---- one scenario
function runScenario(index, rand) {
  const ri = (n) => Math.floor(rand() * n);
  const chance = (p) => rand() < p;
  const pick = (arr) => arr[ri(arr.length)];
  const modes = ['dev', 'cdc', 'cdc', 'host', 'host'];
  const mode = pick(modes);
  const kspeed = chance(0.7) ? 1 : 2;
  const kinterval = pick([1, 2, 5, 10]);
  const head = `scn ${mode} ${kspeed} ${kinterval}`;
  ops.push(head);
  trace.push(`> ${head}`);
  const js = new JsSide(mode, kspeed, kinterval);

  const emit = (line) => {
    ops.push(line);
    trace.push(`> ${line}`);
    let v;
    try {
      v = js.exec(line);
    } catch (e) {
      // a DataView / TypedArray RangeError ends the op (the C++ throws std::range_error there)
      if (!(e instanceof RangeError)) throw e;
      trace.push('throw');
    }
    js.after();
    return v;
  };
  const W = (off, v, t = 0) => emit(`w ${hex(off)} ${hex(v)} ${t}`);
  const R = (off) => emit(`r ${hex(off)}`);
  const D = (off, v) => emit(`d ${hex(off)} ${hex(v)}`);
  const DR = (off) => emit(`dr ${hex(off)}`);
  const T = (ns) => emit(`t ${num(ns)}`);
  const writeBytes = (off, bytes) => {
    for (let i = 0; i < bytes.length; i += 4) {
      const w = (bytes[i] | ((bytes[i + 1] ?? 0) << 8) | ((bytes[i + 2] ?? 0) << 16) | ((bytes[i + 3] ?? 0) << 24)) >>> 0;
      D(off + i, w);
    }
  };
  const readBytes = (off, n) => {
    const out = [];
    for (let i = 0; i < n; i += 4) {
      const w = DR(off + i);
      for (let k = 0; k < 4 && i + k < n; k++) out.push((w >>> (8 * k)) & 0xff);
    }
    return out;
  };
  const randBytes = (n) => Array.from({ length: n }, () => ri(256));
  const bufAddr = () => (6 + ri(56)) * 64; // 0x180 .. 0xf40, + 2 * 64 stays inside the DPRAM

  const tickRandom = () => {
    const r = rand();
    if (r < 0.45) T(ri(3000));
    else if (r < 0.7) T(ri(40000));
    else if (r < 0.85) {
      const n = js.clock.nanosToNextAlarm;
      T(n > 0 ? n : ri(1000)); // land exactly on the next alarm
    } else if (r < 0.97) T(ri(1_500_000));
    else T(ri(15_000_000));
  };

  let forced = false; // INTF set by the fuzzer: the models clear it again
  const unforce = () => {
    if (forced && chance(0.5)) {
      W(R_INTF, 0);
      forced = false;
    }
  };
  const fuzz = () => {
    const r = rand();
    if (r < 0.25) {
      R(pick(ALL_REGS));
    } else if (r < 0.5) {
      const off = pick([R_SIE_STATUS, R_BUFF_STATUS, R_INTE, R_INTF, R_ADDR_ENDP, R_SIE_CTRL, R_INT_EP_CTRL, R_PWR, R_MUXING, 0x4 + 4 * ri(15), 0x9c]);
      let v = (ri(0x10000) | (ri(0x10000) << 16)) >>> 0;
      if (off === R_INTF) v = chance(0.9) ? 0 : v & 0xfffff;
      if (off === R_INTF) forced = v !== 0;
      if (off === R_SIE_CTRL && mode === 'host') v &= ~((1 << 13) | 1); // keep bus resets/transfers to the model
      // 0x9c with an atomic type: TS BasePeripheral warns `0x${value.toString(16)}` of a
      // negative int32 ("0x-..."); the C++ bus value is a uint32 (README "JS-SIGN")
      W(off, v, off === 0x9c ? 0 : ri(4));
    } else if (r < 0.6 && mode === 'dev') {
      W(R_MAIN_CTRL, pick([0, 1, 3, 0x80000001, 0x80000003, 2]), ri(4));
    } else if (r < 0.8) {
      // endpoint control (device) / interrupt endpoint control (host)
      const off = 0x8 + 4 * ri(30);
      const flags = (ri(64) << 26) >>> 0;
      D(off, (flags | (ri(0x400) << 16) | bufAddr()) >>> 0);
    } else if (r < 0.95 && mode !== 'host') {
      // buffer control, both halves random
      const off = 0x80 + 4 * ri(32);
      const half = () => (ri(2) ? FULL : 0) | (ri(2) ? LAST : 0) | (ri(2) ? PID1 : 0) | (ri(3) ? AVAIL : 0) | ri(70);
      D(off, (half() | (half() << 16)) >>> 0);
    } else {
      // data
      D(mode === 'host' ? 0x180 + 4 * ri(0xe00 / 4) : 0x100 + 4 * ri(0xf00 / 4), (ri(0x10000) | (ri(0x10000) << 16)) >>> 0);
    }
  };

  // ---------------- device side (TinyUSB-like device stack)
  const dev = {
    started: false,
    pendingAddr: null,
    ep0q: [],
    ep0Busy: false,
    pid0: 0,
    inEp: 2,
    outEp: 2,
    notif: 1,
    configured: false,
    inBusy: false,
    inDouble: false,
    outDouble: false,
    inAddr: 0,
    outAddr: 0,
  };
  const devStart = () => {
    W(R_MUXING, pick([0b1100, 0b1101, 0b1000]));
    W(R_PWR, 0b1100);
    W(R_MAIN_CTRL, chance(0.2) ? 0x80000001 : 1);
    W(R_SIE_CTRL, (1 << 29) | (1 << 16));
    W(R_INTE, (1 << 16) | (1 << 12) | (1 << 4) | (chance(0.3) ? 1 << 13 : 0));
    dev.started = true;
  };
  const ep0Next = () => {
    if (!dev.ep0q.length) {
      dev.ep0Busy = false;
      if (dev.pendingAddr !== null) {
        W(R_ADDR_ENDP, dev.pendingAddr);
        dev.pendingAddr = null;
      }
      return;
    }
    const pkt = dev.ep0q.shift();
    dev.ep0Busy = true;
    writeBytes(0x100, pkt);
    dev.pid0 ^= 1;
    D(0x80, FULL | AVAIL | (dev.pid0 ? PID1 : 0) | pkt.length);
  };
  const ep0Send = (bytes) => {
    dev.ep0q = [];
    if (bytes.length === 0) dev.ep0q.push([]);
    for (let i = 0; i < bytes.length; i += 64) dev.ep0q.push(bytes.slice(i, i + 64));
    dev.pid0 = 0;
    ep0Next();
  };
  const armOut = () => {
    const c = 0x84 + dev.outEp * 8;
    const len = pick([64, 64, 16, 1, 0]);
    let v = AVAIL | len;
    if (dev.outDouble && chance(0.6)) v |= (AVAIL | len) << 16;
    D(c, v >>> 0);
  };
  const configure = () => {
    dev.inAddr = bufAddr();
    dev.outAddr = bufAddr();
    dev.inDouble = chance(0.4);
    dev.outDouble = chance(0.3);
    const ctrl = (dbl, addr, type) => ((1 << 31) | (dbl ? 1 << 30 : 0) | (chance(0.8) ? 1 << 29 : 0) | (type << 26) | addr) >>> 0;
    D(0x8 + 8 * (dev.notif - 1), ctrl(false, bufAddr(), 3));
    D(0x8 + 8 * (dev.inEp - 1), ctrl(dev.inDouble, dev.inAddr, 2));
    D(0x8 + 8 * (dev.outEp - 1) + 4, ctrl(dev.outDouble, dev.outAddr, 2));
    dev.configured = true;
    dev.inBusy = false;
    armOut();
  };
  const devSetup = () => {
    W(R_SIE_STATUS, 1 << 17);
    const w0 = DR(0),
      w1 = DR(4);
    const type = w0 & 0xff,
      req = (w0 >>> 8) & 0xff,
      value = w0 >>> 16,
      length = w1 >>> 16;
    if (type === 0x00 && req === 5) {
      dev.pendingAddr = value & 0x7f;
      ep0Send([]);
    } else if (type === 0x80 && req === 6) {
      const kind = value >> 8;
      if (kind === 1) ep0Send(DEV_DESC.slice(0, length));
      else if (kind === 2) ep0Send(CDC_CONFIG(dev.inEp, dev.outEp, dev.notif).slice(0, length));
      else if (chance(0.5)) ep0Send([]);
    } else if (type === 0x00 && req === 9) {
      ep0Send([]);
      configure();
    } else if (chance(0.9)) {
      ep0Send([]);
    }
  };
  const devBuffStatus = () => {
    const bs = R(R_BUFF_STATUS);
    if (chance(0.8)) W(R_BUFF_STATUS, bs, pick([0, 0, 3]));
    else W(R_BUFF_STATUS, bs & -bs); // one bit at a time
    for (let bit = 0; bit < 32; bit++) {
      if (!(bs & (1 << bit))) continue;
      const ep = bit >> 1,
        out = bit & 1;
      if (ep === 0 && !out) ep0Next();
      else if (ep === dev.inEp && !out) dev.inBusy = false;
      else if (ep === dev.outEp && out && dev.configured) {
        const bc = DR(0x84 + ep * 8);
        readBytes(dev.outAddr, Math.min(bc & 0x3ff, 64));
        if (chance(0.9)) armOut();
      }
    }
  };
  const devService = () => {
    unforce();
    const ints = R(R_INTS);
    if (ints & (1 << 12)) {
      W(R_SIE_STATUS, 1 << 19);
      W(R_ADDR_ENDP, 0);
      dev.configured = false;
      dev.ep0q = [];
      dev.ep0Busy = false;
      dev.pendingAddr = null;
    }
    if (ints & (1 << 16)) devSetup();
    if (ints & (1 << 4)) devBuffStatus();
    if (ints & (1 << 13)) W(R_SIE_STATUS, 1 << 16);
  };
  const devTx = () => {
    const n = 1 + ri(64);
    writeBytes(dev.inAddr, randBytes(n));
    let v = FULL | AVAIL | n;
    if (dev.inDouble && chance(0.5)) {
      const m = ri(65);
      writeBytes(dev.inAddr + 64, randBytes(m));
      v |= (FULL | AVAIL | m) << 16;
    }
    D(0x80 + dev.inEp * 8, v >>> 0);
    dev.inBusy = true;
  };
  // raw host-side events (mode 'dev', no USBCDC)
  const hostEvent = () => {
    const r = rand();
    if (r < 0.3 && js.hooks.reads.length) {
      const [e, n] = js.hooks.reads.shift();
      const bytes = randBytes(Math.min(n, ri(70)));
      emit(`rd ${e} ${chance(0.7) ? '-' : pick([0, 1, 2.5, 10, 30])} ${bytesHex(bytes)}`);
    } else if (r < 0.55) {
      const pkt = pick([
        [0, 5, 1 + ri(10), 0, 0, 0, 0, 0],
        [0x80, 6, 0, 1, 0, 0, 18, 0],
        [0x80, 6, 0, 2, 0, 0, 9, 0],
        [0x80, 6, 0, 2, 0, 0, 75, 0],
        [0, 9, 1, 0, 0, 0, 0, 0],
        [0x21, 0x22, 3, 0, 0, 0, 0, 0],
        randBytes(8),
      ]);
      emit(`sp ${bytesHex(pkt)}`);
    } else if (r < 0.62) {
      emit('rst');
    } else if (r < 0.66) {
      emit(`${chance(0.5) ? 'rdly' : 'wdly'} ${pick([0, 1, 2.5, 10, 25])}`);
    } else if (r < 0.7) {
      emit(`rd ${ri(16)} - ${bytesHex(randBytes(ri(20)))}`);
    }
  };

  // ---------------- host side (TinyUSB-like host stack)
  const SIE_BASE = (1 << 15) | (1 << 16) | (1 << 9) | (1 << 8); // PULLDOWN_EN VBUS_EN SOF_EN KEEP_ALIVE_EN
  const host = {
    started: false,
    attached: false,
    xfer: null, // current control transfer
    queue: [],
    addr: 0,
    mps0: 8,
    intArmed: false,
    intAddr: 0,
    epxDouble: false,
  };
  const hostStart = () => {
    W(R_MAIN_CTRL, chance(0.2) ? 0x80000003 : 3);
    W(R_SIE_CTRL, SIE_BASE);
    W(R_INTE, 1 | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 6) | (1 << 10));
    host.started = true;
  };
  const ctlReq = (addr, setup, dataOut = null) => ({ addr, setup, dataOut, stage: 'setup', got: [] });
  const enumerate = () => {
    host.queue = [
      ctlReq(0, [0x80, 6, 0, 1, 0, 0, 64, 0]),
      ctlReq(0, [0x00, 5, 1, 0, 0, 0, 0, 0]),
      ctlReq(1, [0x80, 6, 0, 1, 0, 0, 18, 0]),
      ctlReq(1, [0x80, 6, 0, 2, 0, 0, 9, 0]),
      ctlReq(1, [0x80, 6, 0, 2, 0, 0, 34, 0]),
      ctlReq(1, [0x80, 6, 0, 3, 0, 0, 255, 0]), // string: stalls
      ctlReq(1, [0x00, 9, 1, 0, 0, 0, 0, 0]),
      ctlReq(1, [0x21, 0x0a, 0, 0, 0, 0, 0, 0]),
      ctlReq(1, [0x21, 0x0b, 0, 0, 0, 0, 0, 0]),
      ctlReq(1, [0x81, 6, 0, 0x22, 0, 0, 63, 0]),
    ];
    host.xfer = null;
    host.intArmed = false;
  };
  const startSetup = (x) => {
    writeBytes(0, x.setup);
    W(R_ADDR_ENDP, x.addr);
    W(R_SIE_CTRL, SIE_BASE | 1 | 2);
    x.stage = 'setup';
  };
  const armEpx = (x, dataIn) => {
    const len = x.setup[6] | (x.setup[7] << 8);
    const remaining = Math.max(0, len - x.got.length);
    const pkt = chance(0.8) ? Math.min(remaining, host.mps0) : remaining;
    let bc;
    if (x.stage === 'data' && dataIn) bc = AVAIL | pkt | (chance(0.5) && pkt >= remaining ? LAST : 0);
    else if (x.stage === 'data') {
      const data = x.dataOut.slice(0, pkt);
      writeBytes(0x180, data);
      bc = FULL | AVAIL | data.length | (data.length >= remaining ? LAST : 0);
    } else bc = AVAIL | LAST | (dataIn ? 0 : FULL); // status
    const ctrl = ((1 << 31) | (host.epxDouble ? 1 << 30 : 0) | (chance(0.9) ? 1 << 29 : 1 << 28) | 0x180) >>> 0;
    D(0x100, ctrl);
    if (host.epxDouble && chance(0.5)) bc |= bc << 16;
    D(0x80, bc >>> 0);
  };
  const startData = (x) => {
    const len = x.setup[6] | (x.setup[7] << 8);
    const dataIn = !!(x.setup[0] & 0x80);
    if (len === 0) return startStatus(x);
    x.stage = 'data';
    host.epxDouble = chance(0.2);
    if (chance(0.5)) {
      armEpx(x, dataIn);
      W(R_SIE_CTRL, SIE_BASE | 1 | (dataIn ? 8 : 0));
    } else {
      W(R_SIE_CTRL, SIE_BASE | 1 | (dataIn ? 8 : 0));
      armEpx(x, dataIn);
    }
  };
  const startStatus = (x) => {
    const dataIn = !(x.setup[0] & 0x80) || (x.setup[6] | (x.setup[7] << 8)) === 0; // status is IN for OUT/no-data
    x.stage = 'status';
    host.epxDouble = false;
    armEpx(x, dataIn);
    W(R_SIE_CTRL, SIE_BASE | 1 | (dataIn ? 8 : 0));
  };
  const nextXfer = () => {
    host.xfer = host.queue.shift() ?? null;
    if (host.xfer) startSetup(host.xfer);
    else if (!host.intArmed && js.kbd.configured) armInt();
  };
  const armInt = () => {
    host.intAddr = bufAddr();
    W(R_INT_EP_CTRL, 1 << 1);
    W(0x4, (1 | (1 << 16) | (js.kbd.speed === 1 ? 1 << 26 : 0)) >>> 0);
    D(0x8, ((1 << 31) | (1 << 29) | (1 << 26) * 3 | (ri(4) << 16) | host.intAddr) >>> 0);
    D(0x88, AVAIL | 8);
    host.intArmed = true;
  };
  const hostService = () => {
    unforce();
    const ints = R(R_INTS);
    if (ints & 1) {
      const s = R(R_SIE_STATUS);
      W(R_SIE_STATUS, 3 << 8);
      if (s & (3 << 8)) {
        host.mps0 = 8;
        W(R_SIE_CTRL, SIE_BASE | (1 << 13));
        enumerate();
        nextXfer();
      } else {
        host.xfer = null;
        host.queue = [];
      }
    }
    if (ints & (1 << 10)) {
      W(R_SIE_STATUS, 1 << 29);
      nextXfer();
    }
    if (ints & (1 << 6)) {
      W(R_SIE_STATUS, 1 << 27);
      nextXfer();
    }
    if (ints & (1 << 4)) {
      const bs = R(R_BUFF_STATUS);
      W(R_BUFF_STATUS, bs, chance(0.3) ? 3 : 0);
      if (bs & 1 && host.xfer && host.xfer.stage === 'data') {
        const x = host.xfer;
        const bc = DR(0x80);
        if (x.setup[0] & 0x80) {
          const n = bc & 0x3ff;
          x.got.push(...readBytes(0x180, n));
          if (x.setup[1] === 6 && x.setup[3] === 1 && x.got.length >= 8) host.mps0 = x.got[7];
          const len = x.setup[6] | (x.setup[7] << 8);
          if (n === host.mps0 && x.got.length < len && !(bc & LAST)) armEpx(x, true);
        } else {
          x.got.push(...x.dataOut.slice(x.got.length, x.got.length + host.mps0));
          if (x.got.length < x.dataOut.length) armEpx(x, false);
        }
      }
      if (bs & 4 && host.intArmed) {
        const bc = DR(0x88);
        readBytes(host.intAddr, bc & 0x3ff);
        if (chance(0.95)) D(0x88, AVAIL | 8);
      }
    }
    if (ints & (1 << 3)) {
      W(R_SIE_STATUS, (1 << 18) | (1 << 30));
      const x = host.xfer;
      if (x) {
        if (x.stage === 'setup') startData(x);
        else if (x.stage === 'data') startStatus(x);
        else nextXfer();
      }
    }
  };
  const hostEventH = () => {
    const r = rand();
    if (r < 0.06 && !host.attached) {
      emit('att');
      host.attached = true;
    } else if (r < 0.07 && host.attached && chance(0.3)) {
      emit('det');
      host.attached = false;
    } else if (r < 0.2) {
      const keys = Array.from({ length: ri(8) }, () => ri(256));
      emit(`key ${ri(256)}${keys.length ? ' ' + keys.join(' ') : ''}`);
    } else if (r < 0.25 && host.attached && !host.xfer && js.kbd.configured) {
      const leds = ri(32);
      host.queue.push(ctlReq(js.kbd.addr, [0x21, 0x09, 0, 2, 0, 0, 1, 0], [leds]));
      if (chance(0.1)) host.queue.push(ctlReq(js.kbd.addr, [0x21, 0x09, 0, 2, 0, 0, 0, 0], []));
      nextXfer();
    } else if (r < 0.28) {
      emit('kbd');
    } else if (r < 0.3) {
      R(R_SOF_RD);
    } else if (r < 0.31 && host.attached) {
      W(R_SIE_CTRL, SIE_BASE | (1 << 13)); // stray bus reset
    }
  };

  // ---------------- main loop
  for (let step = 0; step < STEPS; step++) {
    const r = rand();
    if (mode === 'host') {
      if (!host.started && chance(0.3)) hostStart();
      else if (js.ctl.intStatus && chance(0.7)) hostService();
      else if (r < 0.15) hostEventH();
      else if (r < 0.2) fuzz();
      else tickRandom();
    } else {
      if (!dev.started && chance(0.2)) devStart();
      else if (js.ctl.intStatus && chance(0.7)) devService();
      else if (mode === 'cdc' && r < 0.1) {
        const n = ri(40);
        for (let i = 0; i < n; i++) emit(`ser ${ri(512)}`);
        if (chance(0.3)) emit('fifo');
      } else if (mode === 'cdc' && r < 0.15 && dev.configured && !dev.inBusy) devTx();
      else if (mode === 'dev' && r < 0.2) hostEvent();
      else if (r < 0.25) fuzz();
      else tickRandom();
    }
    if (chance(0.002)) emit('now');
  }
  for (const off of ALL_REGS) R(off);
  if (mode === 'host') emit('kbd');
  if (mode === 'cdc') emit('fifo');
  emit('now');
  emit('dump');
}

// ---- run
const master = mulberry32(SEED);
for (let s = 0; s < SCENARIOS; s++) {
  runScenario(s, mulberry32(Math.floor(master() * 2 ** 32)));
}
const dir = KEEP ?? fs.mkdtempSync(path.join(os.tmpdir(), 'usb-diff-'));
fs.mkdirSync(dir, { recursive: true });
const opsFile = path.join(dir, 'ops.txt');
const jsTraceFile = path.join(dir, 'trace-js.txt');
const cppTraceFile = path.join(dir, 'trace-cpp.txt');
fs.writeFileSync(opsFile, ops.join('\n') + '\n');
fs.writeFileSync(jsTraceFile, trace.join('\n') + '\n');
const res = spawnSync(bin, [opsFile, cppTraceFile], { stdio: ['ignore', 'inherit', 'inherit'] });
if (res.status !== 0) {
  console.log(`FAIL usb_diff: ${bin} exited with ${res.status ?? res.signal} (files in ${dir})`);
  process.exit(1);
}
const cpp = fs.readFileSync(cppTraceFile, 'utf8').split('\n');
const jsl = trace.concat(['']);
let mismatch = -1;
for (let i = 0; i < Math.max(cpp.length, jsl.length); i++) {
  if (cpp[i] !== jsl[i]) {
    mismatch = i;
    break;
  }
}
const alarms = trace.filter((l) => l.startsWith('F ')).length;
const summary = `${SCENARIOS} scenarios, ${ops.length} ops, ${trace.length} trace lines, ${alarms} alarm firings`;
if (mismatch >= 0) {
  const ctx = [];
  for (let i = Math.max(0, mismatch - 8); i < mismatch; i++) ctx.push(`   ${jsl[i]}`);
  console.error(ctx.join('\n'));
  console.error(`js:  ${jsl[mismatch]}\ncpp: ${cpp[mismatch]}`);
  console.log(`FAIL usb_diff: first mismatch at trace line ${mismatch + 1} (${summary}; files in ${dir})`);
  process.exit(1);
}
if (!KEEP) fs.rmSync(dir, { recursive: true, force: true });
console.log(`PASS usb_diff: ${summary}, 0 mismatches (seed ${SEED})`);
