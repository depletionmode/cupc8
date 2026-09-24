// The RP2040 emulator the card tests (GPU-004/005, IOC-004, SYS-006) run on:
// rp2040js (rp2040emu.mjs and friends; the default) or, with
// CUPC8_EMU=native, the cycle-identical C++ port (rp2040native.mjs, needs
// build/emu-native/rp2040emu.node). Both give the same classes:
//
//   import { Emu, SlotHost, TmdsCapture, UsbKeyboard, USBCDC } from './emu_backend.mjs';
//
// CUPC8_EMU_TRACE=1 prints, on stderr, one line per runUntil() (its result
// and the emulated ns), every slot-host frame (MOSI and MISO) and a digest of
// every TMDS capture, so that a test's run on the two backends can be diffed.

import path from 'node:path';
import { createHash } from 'node:crypto';

export const NATIVE = process.env.CUPC8_EMU === 'native';
if (process.env.CUPC8_EMU && !['native', 'js'].includes(process.env.CUPC8_EMU)) {
  throw new Error(`CUPC8_EMU=${process.env.CUPC8_EMU}: use native or js`);
}

let m;
if (NATIVE) {
  m = await import('./rp2040native.mjs');
} else {
  const { Emu, SDK } = await import('./rp2040emu.mjs');
  const { SlotHost } = await import('./slothost.mjs');
  const { TmdsCapture } = await import('./tmds.mjs');
  const { UsbKeyboard } = await import('./usbkbd.mjs');
  const rp = await import(path.join(SDK, 'rp2040js/dist/esm/index.js'));
  m = { Emu, SlotHost, TmdsCapture, UsbKeyboard, USBCDC: rp.USBCDC };
}

let { Emu, SlotHost, TmdsCapture, UsbKeyboard, USBCDC } = m;

if (process.env.CUPC8_EMU_TRACE) {
  const hosts = [];
  const out = (s) => process.stderr.write(s + '\n');
  const hex = (a) => Array.from(a, (b) => b.toString(16)).join(' ');
  const flush = () => {
    for (const [i, host] of hosts.entries()) {
      for (; host.traced < host.log.length; host.traced++) {
        const f = host.log[host.traced];
        out(`host${i} mosi ${f.mosi.length > 24 ? `${f.mosi.length} bytes` : hex(f.mosi)} miso ${hex(f.miso)}`);
      }
    }
  };
  const runUntil = Emu.prototype.runUntil;
  Emu.prototype.runUntil = function (cond, ns) {
    const r = runUntil.call(this, cond, ns);
    flush();
    out(`runUntil ${r} ns ${this.ns}`);
    return r;
  };
  const Host = SlotHost;
  SlotHost = class extends Host {
    constructor(...a) {
      super(...a);
      this.traced = 0;
      hosts.push(this);
    }
  };
  const stop = TmdsCapture.prototype.stop;
  TmdsCapture.prototype.stop = function () {
    stop.call(this);
    const h = createHash('sha256');
    for (const l of this.lanes) h.update(Uint16Array.from(l));
    h.update(Float64Array.from(this.times));
    out(`tmds ${this.lanes.map((l) => l.length)} words ${this.times.length} t ${this.times[0]}..${this.times.at(-1)} sha256 ${h.digest('hex').slice(0, 16)}`);
  };
}

export { Emu, SlotHost, TmdsCapture, UsbKeyboard, USBCDC };
