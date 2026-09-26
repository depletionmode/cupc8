// The whole CUPC/8 machine on the native emulator (emu/machine, build/emu-
// machine/machine.node): the same machine and the same API as machine.mjs's
// Machine, cycle for cycle, with each RP2040 card on its own thread.
//
//   const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage' } });
//   m.sd.insert('card.img', { writeMs: 5 });   // not in machine.mjs: the storage card's microSD
//   m.powerOn();  await m.runAsync(3e9);  m.screen()
//
// With sysctl: true, the system card's two USB serial ports: the first is a
// TCP port for cupc8.py (m.sysctlPort, as machine.mjs), the second is the
// console (doc/proposals/usb-console.md), m.console:
//   m.console.open()  m.console.write('list\r')  await m.runAsync(1e8)  m.console.read()
//   m.console.close()  await m.console.listen(port)   (a TCP client is the terminal)
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

// QEMU user networking's port forwards: 'tcp:8080:80' makes the PC's
// 127.0.0.1:8080 reach the card's port 80 (hostfwd)
function hostfwd(forward) {
  return forward.map((f) => {
    const m = /^(tcp|udp):(\d+):(\d+)$/.exec(f);
    if (!m) throw new Error(`machinenative: forward '${f}' is not tcp|udp:HOSTPORT:CARDPORT`);
    return `,hostfwd=${m[1]}:127.0.0.1:${m[2]}-:${m[3]}`;
  }).join('');
}

// The Wi-Fi card's QEMU (tools/qemu_build.sh: Espressif's, with the cupc8
// chardev), in step with the machine: icount (one instruction 8 ns, and an
// idle guest's clock jumps to its next timer), the guest's random numbers
// from a fixed seed, and UART1 the cupc8 chardev, whose FIFOs the native
// EspCard drives (emu/machine/README.md, "The Wi-Fi card").
// pcap: a file for the guest's network traffic (QEMU's filter-dump; guest
// times, plus a whole-seconds offset of the wall clock at start).
function startEsp(image, forward = [], pcap = null) {
  const qemu = path.join(ROOT, 'build/qemu-esp/bin/qemu-system-riscv32');
  if (!fs.existsSync(qemu)) throw new Error(`machinenative: no ${qemu}: run tools/qemu_build.sh`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-esp-'));
  const fifo = path.join(dir, 'uart1');
  execFileSync('mkfifo', [fifo + '.in', fifo + '.out']);
  const flash = path.join(dir, 'flash.bin');
  fs.copyFileSync(image, flash);
  const proc = spawn(qemu, ['-nographic', '-machine', 'esp32c3', '-monitor', 'none',
    '-icount', 'shift=3,sleep=off', '-seed', '1',
    '-drive', `file=${flash},if=mtd,format=raw`, '-nic', 'user,id=net0,model=open_eth' + hostfwd(forward),
    ...(pcap ? ['-object', `filter-dump,id=dump,netdev=net0,file=${pcap}`] : []),
    '-serial', 'file:' + path.join(dir, 'uart0.log'), '-chardev', `cupc8,id=frames,path=${fifo}`,
    '-serial', 'chardev:frames'], { stdio: 'ignore' });
  const tx = fs.openSync(fifo + '.in', 'w');
  const rx = fs.openSync(fifo + '.out', 'r');
  return { proc, tx, rx };
}

// The system card's console port, the PC's side: open() is a terminal
// opening it (DTR; the card then sets HOST and starts moving the rings), and
// what the card sends collects until read(). Like the protocol port, bytes
// move only between runs.
class Console {
  constructor(m) {
    this.m = m;
    this.isOpen = false;
    this.buf = [];
  }
  open() {
    native.consoleOpen(this.m.h, true);
    this.isOpen = true;
  }
  close() {
    native.consoleOpen(this.m.h, false);
    this.isOpen = false;
  }
  // bytes (a string, Buffer or array) typed on the PC
  write(data) {
    native.cdcWrite(this.m.h, Buffer.from(data), 1);
  }
  // everything the card sent since the last read(), as a Buffer
  read() {
    this.m.flush();
    const b = Buffer.concat(this.buf);
    this.buf = [];
    return b;
  }
  received(b) {
    if (this.client) this.client.write(b);
    else this.buf.push(b);
  }
  // a TCP port for a terminal (cupc8.py console --port tcp:127.0.0.1:N, or
  // nc): a connection opens the console, and its end closes it
  listen(port = 0) {
    return new Promise((resolve) => {
      this.server = net.createServer((sock) => {
        this.client?.destroy();
        this.client = sock;
        this.open();
        sock.on('data', (d) => this.write(d));
        sock.on('close', () => {
          if (this.client !== sock) return;
          this.client = null;
          this.close();
        });
        sock.on('error', () => {});
      });
      this.server.listen(port, '127.0.0.1', () => resolve(this.server.address().port));
    });
  }
}

export class Machine {
  // forward: port forwards to the Wi-Fi card, ['tcp:8080:80', 'udp:5353:53'];
  // pcap: a file for the Wi-Fi card's network traffic
  static async create({ slots = { 1: 'hdmi', 2: 'io' }, rom = null, sysctl = false,
    threaded = process.env.CUPC8_EMU_THREADS !== '0', spiLog = false, forward = [], pcap = null } = {}) {
    const m = new Machine();
    m.rom = rom ?? kernelRom();
    const wifi = Object.entries(slots).filter(([, k]) => k === 'wifi');
    if (wifi.length > 1) throw new Error('machinenative: one Wi-Fi card at most');
    if (forward.length && !wifi.length) throw new Error('machinenative: forward needs a Wi-Fi card');
    hostfwd(forward);                    // a bad entry throws before QEMU starts
    if (wifi.length) m.esp = startEsp(path.join(ROOT, 'build/esp32c3-qemu/flash.bin'), forward, pcap);
    m.h = native.create({ slots, rom: m.rom, sysctl, root: ROOT, threaded, spiLog,
      espTx: m.esp?.tx ?? -1, espRx: m.esp?.rx ?? -1 });
    m.kinds = { ...slots };
    if (sysctl) {
      m.sysctlPort = await m.listen();
      m.console = new Console(m);
    }
    if (Object.values(slots).includes('io')) {
      const h = m.h;
      m.keyboard = {
        press: (mods, ...keys) => native.press(h, mods, keys),
        get state() { return native.keyboard(h); },
      };
    }
    if (Object.values(slots).includes('storage')) {
      // the storage card's microSD socket (emu/rp2040/harness/sdcard.h): an
      // image file goes in (written through as blocks are programmed), comes out
      const h = m.h;
      m.sd = {
        insert: (image, opts = {}) => native.sdInsert(h, image, opts),
        remove: () => native.sdRemove(h),
        card: () => native.sdCard(h),
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
    const b = native.cdcRead(this.h, 0);
    if (b) this.client?.write(b);
    const c = this.console && native.cdcRead(this.h, 1);
    if (c) this.console.received(c);
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
    this.console?.server?.close();
    this.console?.client?.destroy();
    if (this.esp) {
      this.esp.proc.kill('SIGKILL');  // a lockstep QEMU waits on its FIFO and would not stop on SIGTERM
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
