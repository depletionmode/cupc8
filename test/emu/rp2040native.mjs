// The card tests' RP2040 on the native emulator (emu/rp2040, cycle-identical
// to rp2040js): drop-in versions of Emu (rp2040emu.mjs), SlotHost
// (slothost.mjs), TmdsCapture (tmds.mjs), UsbKeyboard (usbkbd.mjs) and
// rp2040js's USBCDC over build/emu-native/rp2040emu.node. Tests get these
// through emu_backend.mjs with CUPC8_EMU=native. Build the addon with
//   cmake -G Ninja -S emu/rp2040 -B build/emu-native && ninja -C build/emu-native
//
// The per-cycle parts run natively: the Emu loop, the slot host's bit timing
// (a script's frame()/read()/byte()/select()/deselect() is one native
// operation; only the generator's control flow between operations is JS),
// TMDS capture, emu.ppbWriteTrap() and emu.everyCycles(). JS runs for the
// rare events: pin listeners, SPI/I2C device callbacks, USB CDC data.
//
// Differences from the JS classes:
// - emu.runUntil(cond) calls cond() at the same points as the JS Emu, but only
//   if a JS callback (or a UART byte) ran since the last call; cond must depend
//   only on state that JS callbacks change (true of every card test's).
// - per-cycle hooks run in a fixed order: the slot host, the PPB write trap,
//   everyCycles callbacks, then emu.onCycle (a JS function per cycle: works,
//   but slowly). That is the order the tests chain them in.
// - emu.mcu has only what the card tests use: gpio[n] (setInputValue,
//   inputValue, outputEnable, outputValue, addListener), spi[i] (onTransmit,
//   completeTransmit), i2c[i] (onConnect, onWriteByte, onReadByte,
//   completeConnect/Write/Read), adc.channelValues, usbCtrl (attachDevice,
//   detachDevice).

import { createRequire } from 'node:module';
import path from 'node:path';
import { TmdsCapture as JsTmdsCapture } from './tmds.mjs';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const ADDON = process.env.CUPC8_EMU_ADDON ?? path.join(ROOT, 'build/emu-native/rp2040emu.node');
const N = createRequire(import.meta.url)(ADDON);

class Pin {
  constructor(h, n) {
    this.h = h;
    this.index = n;
  }
  setInputValue(v) {
    N.pinSet(this.h, this.index, !!v);
  }
  get inputValue() {
    return !!(N.pinGet(this.h, this.index) & 1);
  }
  get outputEnable() {
    return !!(N.pinGet(this.h, this.index) & 2);
  }
  get outputValue() {
    return !!(N.pinGet(this.h, this.index) & 4);
  }
  // returns the function that removes the listener, as rp2040js does
  addListener(fn) {
    const id = N.pinListen(this.h, this.index, fn);
    return () => N.pinUnlisten(this.h, id);
  }
}

class Spi {
  constructor(h, i) {
    Object.assign(this, { h, i, _onTransmit: null });
  }
  get onTransmit() {
    return this._onTransmit;
  }
  set onTransmit(fn) {
    this._onTransmit = fn;
    N.spiOnTransmit(this.h, this.i, fn ?? undefined);
  }
  completeTransmit(v) {
    N.spiComplete(this.h, this.i, v);
  }
}

class I2c {
  constructor(h, i) {
    Object.assign(this, { h, i, cb: [null, null, null] });
  }
  get onConnect() { return this.cb[0]; }
  set onConnect(fn) { this.cb[0] = fn; N.i2cOn(this.h, this.i, 0, fn); }
  get onWriteByte() { return this.cb[1]; }
  set onWriteByte(fn) { this.cb[1] = fn; N.i2cOn(this.h, this.i, 1, fn); }
  get onReadByte() { return this.cb[2]; }
  set onReadByte(fn) { this.cb[2] = fn; N.i2cOn(this.h, this.i, 2, fn); }
  completeConnect(ack) { N.i2cComplete(this.h, this.i, 0, !!ack); }
  completeWrite(ack) { N.i2cComplete(this.h, this.i, 1, !!ack); }
  completeRead(v) { N.i2cComplete(this.h, this.i, 2, v); }
}

class UsbCtrl {
  constructor(emu) {
    this.emu = emu;
  }
  attachDevice(kbd) {
    if (!(kbd instanceof UsbKeyboard)) throw new Error('native usbCtrl: only a native UsbKeyboard can be attached');
    kbd.bind(this.emu);
    N.usbAttach(this.emu.h, kbd.id);
  }
  detachDevice() {
    N.usbDetach(this.emu.h);
  }
  get sieCtrl() {
    return N.usbSieCtrl(this.emu.h);
  }
}

export class Emu {
  static async load(elf, { mhz = 125, core1Slow = 1 } = {}) {
    return new Emu(elf, mhz, core1Slow);
  }

  constructor(elf, mhz, core1Slow) {
    this.native = true;
    this.h = N.create(elf, mhz, core1Slow);
    this.nsPerCycle = 1000 / mhz;
    const h = this.h;
    const channels = [];
    this.mcu = {
      gpio: Array.from({ length: 30 }, (_, n) => new Pin(h, n)),
      spi: [new Spi(h, 0), new Spi(h, 1)],
      i2c: [new I2c(h, 0), new I2c(h, 1)],
      adc: {
        channelValues: new Proxy(channels, {
          get: (t, k) => (typeof k === 'string' && /^\d+$/.test(k) ? N.adcGet(h, +k) : t[k]),
          set: (t, k, v) => (N.adcSet(h, +k, v), true),
        }),
      },
      usbCtrl: new UsbCtrl(this),
    };
    this._onCycle = null;
  }

  get ns() {
    return N.ns(this.h);
  }

  get uart() {
    return N.uart(this.h);
  }

  // per-cycle JS hook: works, but costs a JS call per cycle
  get onCycle() {
    return this._onCycle;
  }
  set onCycle(fn) {
    this._onCycle = fn;
    N.setOnCycle(this.h, fn ? () => fn(this) : undefined);
  }

  runUntil(cond, ns) {
    return N.runUntil(this.h, cond, ns);
  }

  // fn() on every nth cycle from now (see rp2040emu.mjs)
  everyCycles(n, fn) {
    N.every(this.h, n, fn);
  }

  // see rp2040emu.mjs
  ppbWriteTrap(offset, mask) {
    const h = this.h;
    N.trapInstall(h, offset, mask);
    return {
      arm: (k, fire) => N.trapArm(h, k, fire),
      disarm: () => N.trapDisarm(h),
      remove: () => N.trapRemove(h),
    };
  }
}

const OP_BYTE = 1, OP_SELECT = 2, OP_DESELECT = 3, OP_FRAME = 4, OP_READ = 5;

export class SlotHost {
  constructor(emu, { clkDiv = 2, csSetupNs = 2000, byteGapNs = 1000, frameGapNs = 20000 } = {}) {
    this.emu = emu;
    this.cfg = { clkDiv, csSetupNs, byteGapNs, frameGapNs };
    this.pin = (n) => emu.mcu.gpio[n];
    this.done = true;
    this.gen = null;
    this.log = [];
    N.hostCreate(emu.h, clkDiv, csSetupNs, byteGapNs, frameGapNs, (v) => this.resume(v));
  }

  config() {
    const c = this.cfg;
    N.hostConfig(this.emu.h, c.clkDiv, c.csSetupNs, c.byteGapNs, c.frameGapNs);
  }
  get clkDiv() { return this.cfg.clkDiv; }
  set clkDiv(v) { this.cfg.clkDiv = v; this.config(); }
  get csSetupNs() { return this.cfg.csSetupNs; }
  set csSetupNs(v) { this.cfg.csSetupNs = v; this.config(); }
  get byteGapNs() { return this.cfg.byteGapNs; }
  set byteGapNs(v) { this.cfg.byteGapNs = v; this.config(); }
  get frameGapNs() { return this.cfg.frameGapNs; }
  set frameGapNs(v) { this.cfg.frameGapNs = v; this.config(); }

  get halfNs() {
    return (Math.max(1, this.clkDiv) * 1000) / 12;
  }

  // MISO has a pull-up on the main board: an undriven line reads 1
  miso() {
    const p = this.pin(4);
    return p.outputEnable ? (p.outputValue ? 1 : 0) : 1;
  }

  run(script) {
    this.gen = script.call(this);
    this.done = false;
    this.result = undefined;
    N.hostRun(this.emu.h);
  }

  // the native host's next(): the result of the last operation in, the next
  // operation out (undefined when the script is done)
  resume(v) {
    const r = this.gen.next(v);
    if (r.done) {
      this.done = true;
      this.result = r.value;
      return undefined;
    }
    if (typeof r.value !== 'number' && !Array.isArray(r.value)) throw new Error(`SlotHost: a script yielded ${r.value}`);
    return r.value;
  }

  *byte(out) {
    return yield [OP_BYTE, out];
  }

  *select() {
    yield [OP_SELECT];
  }

  *deselect() {
    yield [OP_DESELECT];
  }

  *frame(bytes) {
    const miso = yield [OP_FRAME, bytes];
    this.log.push({ mosi: bytes, miso });
    return miso;
  }

  *read({ tries = 200, retryNs = 50000 } = {}) {
    const attempts = yield [OP_READ, tries, retryNs];
    for (const a of attempts) this.log.push({ mosi: [0xfe], miso: a });
    const last = attempts.at(-1);
    if (!last || last[1] === 0xff || !last[1]) return null;
    return { status: last[0], data: last.slice(2) };
  }

  *wait(ns) {
    yield ns;
  }
}

export class TmdsCapture {
  constructor(emu) {
    this.emu = emu;
    this.lanes = [[], [], []];
    this.times = [];
    this.on = false;
    N.tmdsCreate(emu.h);
  }

  start() {
    this.lanes = [[], [], []];
    this.times = [];
    this.on = true;
    N.tmdsStart(this.emu.h);
  }

  stop() {
    this.on = false;
    N.tmdsStop(this.emu.h);
    const [b, g, r, t] = N.tmdsData(this.emu.h);
    this.lanes = [b, g, r];
    this.times = t;
  }
}
TmdsCapture.prototype.analyse = JsTmdsCapture.prototype.analyse;
TmdsCapture.prototype.frame = JsTmdsCapture.prototype.frame;

// test/emu/usbkbd.mjs's keyboard, the C++ port (emu/rp2040/src/usb/usbkbd)
export class UsbKeyboard {
  constructor({ speed = 1, interval = 10 } = {}) {
    Object.assign(this, { speed, interval, emu: null, id: -1, queued: [] });
  }

  // made on the chip it is first attached to
  bind(emu) {
    if (this.emu === emu) return;
    if (this.emu) throw new Error('UsbKeyboard: already attached to another emulator');
    this.emu = emu;
    this.id = N.kbdCreate(emu.h, this.speed, this.interval);
    for (const [mods, keys] of this.queued) N.kbdPress(emu.h, this.id, mods, keys);
    this.queued = [];
  }

  press(mods, ...keys) {
    if (this.emu) N.kbdPress(this.emu.h, this.id, mods, keys);
    else this.queued.push([mods, keys]);
  }

  state() {
    return this.emu ? N.kbdState(this.emu.h, this.id) : { addr: 0, configured: 0, protocol: 1, leds: [] };
  }
  get addr() { return this.state().addr; }
  get configured() { return this.state().configured; }
  get protocol() { return this.state().protocol; }
  get leds() { return this.state().leds; }
}

// rp2040js's USBCDC (host side of a CDC device on the chip's USB port)
export class USBCDC {
  constructor(usbCtrl) {
    this.h = usbCtrl.emu.h;
    N.cdcCreate(this.h);
    this._onSerialData = null;
    this._onDeviceConnected = null;
    const h = this.h;
    this.txFIFO = { get itemCount() { return N.cdcTxCount(h); } };
  }
  get onSerialData() { return this._onSerialData; }
  set onSerialData(fn) { this._onSerialData = fn; N.cdcOn(this.h, 0, fn ?? undefined); }
  get onDeviceConnected() { return this._onDeviceConnected; }
  set onDeviceConnected(fn) { this._onDeviceConnected = fn; N.cdcOn(this.h, 1, fn ?? undefined); }
  sendSerialByte(b) {
    N.cdcSend(this.h, b);
  }
}

// not in rp2040js: the composite CDC host (test/emu/cdchost.mjs), natively
export class CdcHost {
  constructor(usbCtrl, nports = 2) {
    const h = usbCtrl.emu.h;
    this.h = h;
    N.cdcHostCreate(h, nports);
    this._onDeviceConnected = null;
    this.ports = Array.from({ length: nports }, (_, p) => {
      let fn = null;
      return {
        txFIFO: { get itemCount() { return N.cdcHostTxCount(h, p); } },
        get onSerialData() { return fn; },
        set onSerialData(f) { fn = f; N.cdcHostOn(h, 0, p, f ?? undefined); },
      };
    });
  }
  get onDeviceConnected() { return this._onDeviceConnected; }
  set onDeviceConnected(fn) { this._onDeviceConnected = fn; N.cdcHostOn(this.h, 1, 0, fn ?? undefined); }
  get portCount() { return N.cdcHostPorts(this.h); }
  setLines(p, value) { N.cdcHostLines(this.h, p, value); }
  open(p, on) { this.setLines(p, on ? 3 : 0); }
  sendSerialByte(b, p = 0) { N.cdcHostSend(this.h, p, b); }
}

// not in rp2040js: the storage card's microSD socket on SPI1 (SCK 14, MOSI 15,
// MISO 12, nCS 13, card detect 17) with an SD card model backed by an image
// file (emu/rp2040/harness/sdcard.h)
export class SdSocket {
  constructor(emu) {
    this.h = emu.h;
    N.sdCreate(this.h);
  }
  // opts: { highCapacity, writeProtect, initMs, readUs, writeMs, ncr }
  insert(image, opts = {}) {
    N.sdInsert(this.h, image, opts);
  }
  remove() {
    N.sdRemove(this.h);
  }
  // null (no card) or { initialised, busy, blocks, violations, stats }
  card() {
    return N.sdCard(this.h);
  }
}
