// The whole CUPC/8 machine, emulated (doc/milestone-1.md, "Whole-machine
// emulator"): the main board's CPU and chipset from their RTL (build/emu/
// core.node, tools/emu_build.sh), the SRAM and the SST39 ROM chip, and the
// cards running their real firmware in their own emulators, wired to the
// chipset's slot SPI and IRQ pins. Everything steps in lockstep: one 12 MHz
// clock at a time while any slot or the bridge is selected, 10 us at a time
// otherwise.
//
//   const m = await Machine.create({ slots: { 1: 'gpu', 2: 'io' } });
//   m.powerOn();  m.runFor(3e9);  m.screen()   // 80x30 text read off the HDMI output

import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { Emu, SDK } from './rp2040emu.mjs';
import { kernelRom, ROOT } from './romimage.mjs';
import { TmdsCapture } from './tmds.mjs';
import { UsbKeyboard } from './usbkbd.mjs';

const core = createRequire(import.meta.url)(path.join(ROOT, 'build/emu/core.node'));
const NS_PER_CLOCK = 1000 / 12;
const IDLE_CLOCKS = 120;                      // 10 us between syncs while no slot is selected

// the RP2040 cards' slot pins (hw/pins.yaml)
const P = { SCK: 2, MOSI: 3, MISO: 4, NCS: 5, NIRQ: 6 };

class Rp2040Card {
  constructor(kind, emu) {
    this.kind = kind;
    this.emu = emu;
    const g = emu.mcu.gpio;
    g[P.NCS].setInputValue(true);
    g[P.SCK].setInputValue(false);
    g[P.MOSI].setInputValue(false);
  }
  advance(ns) {
    const e = this.emu;
    while (e.ns < ns) e.step();
  }
  drive(sck, mosi, selected) {
    if (this.log) {
      // record every frame: its MOSI bytes, and the time it ended
      if (selected && !this.sel) { this.bits = []; this.rbits = []; this.t0 = this.emu.ns; }
      if (selected && sck && !this.sck) { this.bits.push(mosi); this.rbits.push(this.miso()); }
      if (!selected && this.sel && this.bits.length) {
        const bytes = [];
        for (let i = 0; i + 8 <= this.bits.length; i += 8) bytes.push(this.bits.slice(i, i + 8).reduce((v, b) => (v << 1) | b, 0));
        const pack = (bits) => { const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(bits.slice(i, i + 8).reduce((v, b) => (v << 1) | b, 0)); return out; };
        this.log.push({ start: this.t0, ns: this.emu.ns, bytes, miso: pack(this.rbits), extra: this.bits.length % 8 });
      }
      this.sel = selected;
      this.sck = sck;
    }
    const g = this.emu.mcu.gpio;
    g[P.MOSI].setInputValue(!!mosi);
    g[P.SCK].setInputValue(!!sck);
    g[P.NCS].setInputValue(!selected);
  }
  miso() {
    const p = this.emu.mcu.gpio[P.MISO];
    return p.outputEnable ? (p.outputValue ? 1 : 0) : 1;   // released: the main board's pull-up
  }
  irq() {
    const p = this.emu.mcu.gpio[P.NIRQ];
    return p.outputEnable && !p.outputValue;                // open drain, active low
  }
}

// The Wi-Fi card: its ESP-IDF image in Espressif's QEMU (the QEMU build: no
// radio, frames over UART1, test/emu/test_wifi_qemu.py). QEMU has no SPI
// slave, so this class is one: at CS_n falling it asks the card for its
// preload ($A6) and shifts it out on MISO bit by bit, collects MOSI, and
// hands the whole frame over ($A5) when CS_n rises. That is exactly what the
// card's SPI slave does with a preloaded transaction. The card's IRQ_n is not
// modelled (QEMU has no pin for it): the kernel polls the Wi-Fi card.
class EspCard {
  constructor(image) {
    this.kind = 'wifi';
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-esp-'));
    const fifo = path.join(dir, 'uart1');
    execFileSync('mkfifo', [fifo + '.in', fifo + '.out']);
    const flash = path.join(dir, 'flash.bin');
    fs.copyFileSync(image, flash);
    const qemu = fs.readdirSync(path.join(SDK, 'espressif/tools/qemu-riscv32'))
      .map((v) => path.join(SDK, 'espressif/tools/qemu-riscv32', v, 'qemu/bin/qemu-system-riscv32'))[0];
    this.proc = spawn(qemu, ['-nographic', '-machine', 'esp32c3', '-monitor', 'none',
      '-drive', `file=${flash},if=mtd,format=raw`, '-nic', 'user,model=open_eth',
      '-serial', 'file:' + path.join(dir, 'uart0.log'), '-chardev', `pipe,id=frames,path=${fifo}`,
      '-serial', 'chardev:frames'], { stdio: 'ignore' });
    this.tx = fs.openSync(fifo + '.in', 'w');
    this.rx = fs.openSync(fifo + '.out', 'r');
    this.selected = false;
    this.bits = [];
    this.mosi = [];
    this.lastSck = 0;
  }
  read(n) {
    const b = Buffer.alloc(n);
    for (let got = 0; got < n;) got += fs.readSync(this.rx, b, got, n - got, null);
    return b;
  }
  advance() {}
  drive(sck, mosi, selected) {
    if (selected && !this.selected) {
      fs.writeSync(this.tx, Buffer.from([0xa6]));
      const h = this.read(3);
      const pre = this.read(h[1] | (h[2] << 8));
      this.bits = [...pre].flatMap((b) => [7, 6, 5, 4, 3, 2, 1, 0].map((i) => (b >> i) & 1));
      this.mosi = [];
      this.bit = 0;
    } else if (!selected && this.selected) {
      const bytes = [];
      for (let i = 0; i + 8 <= this.mosi.length; i += 8) bytes.push(this.mosi.slice(i, i + 8).reduce((v, b) => (v << 1) | b, 0));
      if (bytes.length) {
        fs.writeSync(this.tx, Buffer.from([0xa5, bytes.length & 0xff, bytes.length >> 8, ...bytes]));
        this.read(3 + bytes.length);
      }
    }
    if (selected && sck && !this.lastSck) {                    // mode 0: sampled on the rising edge
      this.mosi.push(mosi);
      this.bit++;
    }
    this.selected = selected;
    this.lastSck = sck;
  }
  miso() {
    return this.selected ? (this.bits[this.bit] ?? 0) : 1;
  }
  irq() {
    return false;
  }
  stop() {
    this.proc.kill();
  }
}

// The system card: sysctl.elf on its own emulated RP2040. Its bridge SPI
// (SPI0, a master at 1 MHz) meets the chipset's bridge at pin level: each
// byte it sends is clocked into the chipset's BR_* pins at 1 MHz by the
// machine, and the transfer completes with the bits BR_MISO gave back. Its
// USB CDC is a TCP port for cupc8.py (--port tcp:127.0.0.1:N).
const BR_NCS = 5, SYS_NRST = 23, CHIPSET_CDONE = 7, CPUCARD_CDONE = 17;
class SysctlCard {
  constructor(emu, rp) {
    this.kind = 'sysctl';
    this.emu = emu;
    const g = emu.mcu.gpio;
    g[CHIPSET_CDONE].setInputValue(true);                     // both FPGAs configured
    g[CPUCARD_CDONE].setInputValue(true);
    g[8].setInputValue(true);
    this.pending = null;                                      // the byte being clocked into the bridge
    emu.mcu.spi[0].onTransmit = (b) => {
      this.pending = { out: b, bit: 0, got: 0, half: 0 };
    };
    this.cdc = new rp.USBCDC(emu.mcu.usbCtrl);
    this.toCard = [];
    this.cdc.onSerialData = (buf) => this.client?.write(Buffer.from(buf));
  }
  listen() {
    return new Promise((resolve) => {
      this.server = net.createServer((sock) => {
        this.client = sock;
        sock.on('data', (d) => this.toCard.push(...d));
      });
      this.server.listen(0, '127.0.0.1', () => resolve(this.server.address().port));
    });
  }
  advance(ns) {
    const e = this.emu;
    while (this.toCard.length && this.cdc.txFIFO.itemCount < 256) this.cdc.sendSerialByte(this.toCard.shift());
    while (e.ns < ns) e.step();
  }
  // the bridge pins, as they are this clock (called once per core clock while busy)
  bridgePins(brMiso) {
    const g = this.emu.mcu.gpio;
    const ncs = g[BR_NCS].outputEnable ? g[BR_NCS].outputValue : 1;
    const p = this.pending;
    if (!p) return { sck: 0, mosi: 0, ncs };
    // 1 MHz: 6 core clocks a half period; sample MISO as SCK rises (mode 0)
    const phase = Math.floor(p.half / 6);
    const bit = phase >> 1, high = phase & 1;
    if (high && p.half % 6 === 0) p.got = (p.got << 1) | brMiso;
    p.half++;
    if (bit >= 8) {
      this.pending = null;
      this.emu.mcu.spi[0].completeTransmit(p.got & 0xff);
      return { sck: 0, mosi: 0, ncs };
    }
    return { sck: high, mosi: (p.out >> (7 - bit)) & 1, ncs };
  }
  sysReset() {
    const p = this.emu.mcu.gpio[SYS_NRST];
    return p.outputEnable && !p.outputValue;                 // driven low: the supervisor resets the board
  }
  drive() {}
  miso() { return 1; }
  irq() { return false; }
  stop() {
    this.server?.close();
    this.client?.destroy();
  }
}

// the 8x16 text font: font8x8_cp437 with each row doubled (gpu.c)
function loadFont() {
  const src = fs.readFileSync(path.join(ROOT, 'fw/common/font8x8_cp437.c'), 'utf8');
  const bytes = src.slice(src.indexOf('{')).match(/0x[0-9a-fA-F]{2}/g).map((h) => parseInt(h, 16));
  return Array.from({ length: 256 }, (_, c) => Array.from({ length: 16 }, (_, r) => bytes[c * 8 + (r >> 1)]));
}

export class Machine {
  static async create({ slots = { 1: 'gpu', 2: 'io' }, rom = null, sysctl = false } = {}) {
    const m = new Machine();
    m.rom = rom ?? kernelRom();
    m.cards = {};
    if (sysctl) {
      const rp = await import(path.join(SDK, 'rp2040js/dist/esm/index.js'));
      m.sysctl = new SysctlCard(await Emu.load(path.join(ROOT, 'build/rp2040/sysctl.elf'), { mhz: 125 }), rp);
      m.sysctlPort = await m.sysctl.listen();
    }
    for (const [slot, kind] of Object.entries(slots)) {
      if (kind === 'wifi') {
        m.cards[slot] = new EspCard(path.join(ROOT, 'build/esp32c3-qemu/flash.bin'));
        continue;
      }
      const elf = path.join(ROOT, 'build/rp2040', kind + '.elf');
      const emu = await Emu.load(elf, { mhz: kind === 'gpu' ? 252 : 125 });
      m.cards[slot] = new Rp2040Card(kind, emu);
      if (kind === 'gpu') m.tmds = new TmdsCapture(emu);
      if (kind === 'io') {
        emu.mcu.gpio[8].setInputValue(true);                 // VBUS switch: no fault
        m.keyboard = new UsbKeyboard({ speed: 1 });
      }
    }
    m.pwrHi = true;
    return m;
  }

  powerOn() {
    core.init(this.rom);
    core.run(12, this.inputs(false));                         // the supervisor holds nPOR a moment
    if (this.keyboard) this.cards[Object.keys(this.cards).find((s) => this.cards[s].kind === 'io')].emu.mcu.usbCtrl.attachDevice(this.keyboard);
  }

  inputs(por = true) {
    const out = core.outputs();
    const cs = (out >> 2) & 0x7f;
    let miso = 1, nirq = 0x3f;
    for (const [slot, card] of Object.entries(this.cards)) {
      const dev = slot - 1;
      if (!((cs >> dev) & 1)) miso &= card.miso();
      if (card.irq()) nirq &= ~(1 << dev);
    }
    const br = this.br ?? { sck: 0, mosi: 0, ncs: 1 };
    const reset = this.sysctl?.sysReset();
    return miso | (nirq << 1) | (br.sck << 7) | (br.mosi << 8) | (br.ncs << 9) | ((this.pwrHi ? 1 : 0) << 10) |
      (1 << 11) | ((por && !reset ? 1 : 0) << 12);
  }

  // run the machine for `ns` of emulated time
  runFor(ns) {
    const end = core.ns() + ns;
    while (core.ns() < end) {
      const out = core.outputs();
      const cs = (out >> 2) & 0x7f;
      if (this.sysctl) this.br = this.sysctl.bridgePins((out >> 9) & 1);
      const busy = cs !== 0x7f || (this.br && (!this.br.ncs || this.sysctl.pending));
      // A card reacts to the pins it was given at the last clock during the
      // clock that follows, so it runs up to the next edge before the core
      // samples MISO there. (Advancing it only afterwards gave it no time at
      // all: at SCK = 6 MHz, one clock per half period, every MISO bit came
      // a whole bit late.)
      if (cs !== 0x7f) for (const card of Object.values(this.cards)) card.advance(core.ns() + NS_PER_CLOCK);
      core.run(busy ? 1 : IDLE_CLOCKS, this.inputs());
      const t = core.ns();
      this.sysctl?.advance(t);
      const now = core.outputs();
      const sck = now & 1, mosi = (now >> 1) & 1, ncs = (now >> 2) & 0x7f;
      for (const [slot, card] of Object.entries(this.cards)) {
        card.advance(t);
        card.drive(sck, mosi, !((ncs >> (slot - 1)) & 1));
      }
    }
  }

  stop() {
    for (const c of Object.values(this.cards)) c.stop?.();
    this.sysctl?.stop();
  }

  // runFor, giving Node's event loop a turn every `slice` (the TCP port for
  // cupc8.py, child processes)
  async runAsync(ns, slice = 2e6) {
    const end = core.ns() + ns;
    while (core.ns() < end) {
      this.runFor(Math.min(slice, end - core.ns()));
      await new Promise((r) => setImmediate(r));
    }
  }

  // run until cond() holds, yielding to the event loop; false after `ns`
  async runUntil(cond, ns, slice = 2e6) {
    const end = core.ns() + ns;
    while (core.ns() < end) {
      if (cond()) return true;
      await this.runAsync(Math.min(slice, end - core.ns()), slice);
    }
    return cond();
  }

  get ns() {
    return core.ns();
  }

  state() {
    return core.state();
  }

  // ----------------------------------------------------------- the screen
  // capture a whole frame from the GPU's TMDS output (about two frame times)
  frame() {
    this.tmds.start();
    this.runFor(40e6);
    this.tmds.stop();
    return this.tmds.frame(this.tmds.analyse());
  }

  // the text on screen: each 8x16 cell matched against the font (either polarity,
  // so the cursor's inverted cell reads as its character)
  screen() {
    const f = this.frame();
    if (f.error) return { error: f.error };
    const font = (this.font ??= loadFont());
    const rows = [];
    for (let row = 0; row < 30; row++) {
      let line = '';
      for (let col = 0; col < 80; col++) {
        const px = (x, y) => f.rgb[(row * 16 + y) * 640 + col * 8 + x] & 0xc0c0c0;   // RGB222 levels
        const bg = px(0, 0);
        const bits = [];
        for (let y = 0; y < 16; y++) {
          let b = 0;
          for (let x = 0; x < 8; x++) if (px(x, y) !== bg) b |= 0x80 >> x;
          bits.push(b);
        }
        let ch = ' ';
        if (bits.some((b) => b)) {
          const inv = bits.map((b) => ~b & 0xff);
          const c = font.findIndex((g) => g.every((r, i) => r === bits[i]) || g.every((r, i) => r === inv[i]));
          ch = c >= 32 && c < 127 ? String.fromCharCode(c) : c < 0 ? '?' : '.';
        }
        line += ch;
      }
      rows.push(line.trimEnd());
    }
    return { text: rows };
  }

  // type on the USB keyboard: one report per key, then a release
  type(text) {
    const shifted = '~!@#$%^&*()_+{}|:"<>?';
    const plain = "`1234567890-=[]\\;',./";
    for (const c of text) {
      let mods = 0, u;
      if (c >= 'a' && c <= 'z') u = 4 + c.charCodeAt(0) - 97;
      else if (c >= 'A' && c <= 'Z') { u = 4 + c.charCodeAt(0) - 65; mods = 2; }
      else if (c >= '1' && c <= '9') u = 30 + c.charCodeAt(0) - 49;
      else if (c === '0') u = 39;
      else if (c === '\n') u = 40;
      else if (c === ' ') u = 44;
      else {
        const k = plain.indexOf(c) >= 0 ? plain.indexOf(c) : shifted.indexOf(c);
        if (shifted.indexOf(c) >= 0) mods = 2;
        u = [53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 47, 48, 49, 51, 52, 54, 55, 56][k];
      }
      this.keyboard.press(mods, u);
      this.keyboard.press(0);
    }
  }
}
