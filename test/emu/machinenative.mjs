// The whole CUPC/8 machine on the native emulator (emu/machine, build/emu-
// machine/machine.node): the same machine and the same API as machine.mjs's
// Machine, cycle for cycle, with each RP2040 card on its own thread.
//
//   const m = await Machine.create({ slots: { 1: 'gpu', 2: 'io' } });
//   m.powerOn();  await m.runAsync(3e9);  m.screen()
//
// test_e2e.mjs uses it with CUPC8_EMU=native. CUPC8_EMU_THREADS=0 runs the
// cards serially (the same result, slower). Build:
//   tools/emu_build.sh && cmake -G Ninja -S emu/machine -B build/emu-machine && ninja -C build/emu-machine

import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { kernelRom, ROOT } from './romimage.mjs';

const native = createRequire(import.meta.url)(path.join(ROOT, 'build/emu-machine/machine.node'));
const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');

// The Wi-Fi card's QEMU, started exactly as machine.mjs's EspCard does; the
// native EspCard speaks the same $A6/$A5 protocol over these pipes.
function startEsp(image) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-esp-'));
  const fifo = path.join(dir, 'uart1');
  execFileSync('mkfifo', [fifo + '.in', fifo + '.out']);
  const flash = path.join(dir, 'flash.bin');
  fs.copyFileSync(image, flash);
  const qemu = fs.readdirSync(path.join(SDK, 'espressif/tools/qemu-riscv32'))
    .map((v) => path.join(SDK, 'espressif/tools/qemu-riscv32', v, 'qemu/bin/qemu-system-riscv32'))[0];
  const proc = spawn(qemu, ['-nographic', '-machine', 'esp32c3', '-monitor', 'none',
    '-drive', `file=${flash},if=mtd,format=raw`, '-nic', 'user,model=open_eth',
    '-serial', 'file:' + path.join(dir, 'uart0.log'), '-chardev', `pipe,id=frames,path=${fifo}`,
    '-serial', 'chardev:frames'], { stdio: 'ignore' });
  const tx = fs.openSync(fifo + '.in', 'w');
  const rx = fs.openSync(fifo + '.out', 'r');
  return { proc, tx, rx };
}

export class Machine {
  static async create({ slots = { 1: 'gpu', 2: 'io' }, rom = null, sysctl = false,
    threaded = process.env.CUPC8_EMU_THREADS !== '0', spiLog = false } = {}) {
    const m = new Machine();
    m.rom = rom ?? kernelRom();
    const wifi = Object.entries(slots).filter(([, k]) => k === 'wifi');
    if (wifi.length > 1) throw new Error('machinenative: one Wi-Fi card at most');
    if (wifi.length) m.esp = startEsp(path.join(ROOT, 'build/esp32c3-qemu/flash.bin'));
    m.h = native.create({ slots, rom: m.rom, sysctl, root: ROOT, threaded, spiLog,
      espTx: m.esp?.tx ?? -1, espRx: m.esp?.rx ?? -1 });
    m.kinds = { ...slots };
    if (sysctl) m.sysctlPort = await m.listen();
    if (Object.values(slots).includes('io')) {
      const h = m.h;
      m.keyboard = {
        press: (mods, ...keys) => native.press(h, mods, keys),
        get state() { return native.keyboard(h); },
      };
    }
    return m;
  }

  // the system card's USB CDC as a TCP port (machine.mjs SysctlCard.listen)
  listen() {
    return new Promise((resolve) => {
      this.server = net.createServer((sock) => {
        this.client = sock;
        sock.on('data', (d) => native.cdcWrite(this.h, d));
      });
      this.server.listen(0, '127.0.0.1', () => resolve(this.server.address().port));
    });
  }

  // what the card sent on its CDC while the machine ran (machine.mjs writes it
  // as it comes; the socket only sends it when the event loop runs anyway)
  flush() {
    const b = native.cdcRead(this.h);
    if (b) this.client?.write(b);
  }

  powerOn() {
    native.powerOn(this.h);
  }

  // run the machine for `ns` of emulated time
  runFor(ns) {
    native.runFor(this.h, ns);
    this.flush();
  }

  stop() {
    if (this.h) native.destroy(this.h);
    this.h = null;
    this.server?.close();
    this.client?.destroy();
    if (this.esp) {
      this.esp.proc.kill();
      fs.closeSync(this.esp.tx);
      fs.closeSync(this.esp.rx);
    }
  }

  // runFor, giving Node's event loop a turn every `slice` (the TCP port for
  // cupc8.py, child processes)
  async runAsync(ns, slice = 2e6) {
    const end = this.ns + ns;
    while (this.ns < end) {
      this.runFor(Math.min(slice, end - this.ns));
      await new Promise((r) => setImmediate(r));
    }
  }

  // run until cond() holds, yielding to the event loop; false after `ns`
  async runUntil(cond, ns, slice = 2e6) {
    const end = this.ns + ns;
    while (this.ns < end) {
      if (cond()) return true;
      await this.runAsync(Math.min(slice, end - this.ns), slice);
    }
    return cond();
  }

  get ns() {
    return native.ns(this.h);
  }

  state() {
    return native.state(this.h);
  }

  // a whole frame from the GPU's TMDS output: { rgb: Uint32Array(640*480) } or { error }
  frame() {
    const f = native.frame(this.h);
    this.flush();
    return f;
  }

  // the text on screen, 80x30: { text: [...] } or { error }
  screen() {
    const s = native.screen(this.h);
    this.flush();
    return s;
  }

  // the e-ink card's panel: the glass as of its last completed refresh,
  // { w, h, seq, grey: Uint8Array, refreshes, busy, errors, error, ... }, or null
  panel() {
    return native.panel(this.h);
  }

  // the text on the e-ink panel's glass, 80x30: { text: [...] } or { error }
  panelScreen() {
    return native.panelScreen(this.h);
  }

  // type on the USB keyboard: one report per key, then a release
  type(text) {
    native.type(this.h, text);
  }

  // not in machine.mjs: for comparing runs
  setThreaded(on) { native.setThreaded(this.h, on); }
  stats() { return native.stats(this.h); }
  cards() { return native.cards(this.h); }
  spiLog(slot) { return native.spiLog(this.h, slot); }
}
