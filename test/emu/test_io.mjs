// IOC-004: the real IO card firmware (build/rp2040/io.elf) on the emulated
// RP2040: a USB keyboard model on its native port (TinyUSB host enumerates
// it for real), the CPU side through its slot pins with CUPC/8 SPI timing.
//
//   node test/emu/test_io.mjs
//   (CUPC8_EMU=native: on the C++ emulator, see emu_backend.mjs)

import path from 'node:path';
import { Emu, SlotHost, UsbKeyboard } from './emu_backend.mjs';     // CUPC8_EMU=native: the C++ emulator

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const emu = await Emu.load(path.join(ROOT, 'build/rp2040/io.elf'), { mhz: 125 });
const host = new SlotHost(emu, { clkDiv: 2 });
const VBUS_NFAULT = 8, NIRQ = 6;
emu.mcu.gpio[VBUS_NFAULT].setInputValue(true);        // the power switch is fine

let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
}
function run(script, ns = 5e9) {
  host.run(script);
  let done;
  try {
    done = emu.runUntil(() => host.done, ns);
  } catch (e) {
    console.log(`FAIL the card crashed at ${(emu.ns / 1e6).toFixed(3)} ms: ${e.message}`);
    process.exit(1);
  }
  if (!done) {
    console.log('FAIL the card stopped answering (host script timed out)');
    process.exit(1);
  }
  return host.result;
}
const wait = (ns) => run(function* () { yield ns; });
const status = () => run(function* () { return (yield* this.frame([0x02]))[0]; });
const cmd = (bytes) => run(function* () { yield* this.frame(bytes); return yield* this.read(); });
const keys = () => {
  const r = cmd([0x01, 16]);
  return r ? String.fromCharCode(...r.data.filter((b) => b !== 0xff)) : null;
};
const CONNECTED = 0x20, FAULT = 0x10;
const irqAsserted = () => {
  const p = emu.mcu.gpio[NIRQ];
  return p.outputEnable && !p.outputValue;
};

// usages: a=4 .. z=29, Enter 40, Caps 57; LShift = mods bit 1
const usage = (c) => 4 + c.toLowerCase().charCodeAt(0) - 97;
function type(kbd, text) {
  for (const c of text) {
    const shift = c >= 'A' && c <= 'Z' ? 0x02 : 0;
    kbd.press(shift, usage(c));
    kbd.press(0);
  }
}

// ---------------------------------------------------------------- no keyboard
const s0 = run(function* () {
  for (let i = 0; i < 200; i++) {
    const m = yield* this.frame([0x02]);
    if (m[0] !== 0xff) return m[0];
    yield 1e6;
  }
  return 0xff;
});
expect(s0 !== 0xff, 'the card answers within 200 ms of power-on');
expect(!(s0 & CONNECTED), `no keyboard: KBD_CONNECTED clear (status ${s0?.toString(16)})`);
const ident = cmd([0xf0]);
expect(ident && ident.data[0] === 0x02 && ident.data[3] === 0xc8, `IDENT says IO card: ${JSON.stringify(ident)}`);

// ------------------------------------------------- a low-speed keyboard arrives
for (const speed of [1, 2]) {
  const kbd = new UsbKeyboard({ speed });
  emu.mcu.usbCtrl.attachDevice(kbd);
  let st = 0;
  for (let i = 0; i < 100 && !(st & CONNECTED); i++) {
    wait(10e6);
    st = status();
  }
  const name = speed === 1 ? 'low-speed' : 'full-speed';
  expect(st & CONNECTED, `${name}: enumerated within 1 s (status ${st.toString(16)})`);
  expect(kbd.addr !== 0 && kbd.configured === 1, `${name}: address ${kbd.addr}, configuration ${kbd.configured}`);
  expect(kbd.protocol === 0, `${name}: SET_PROTOCOL(boot) sent`);
  expect(kbd.leds.length >= 1 && kbd.leds.at(-1) === 1, `${name}: Num Lock LED on at connect (${kbd.leds})`);

  cmd([0x05]);                                          // FLUSH
  run(function* () { yield* this.frame([0xf2, 1]); });  // IRQ_EN
  type(kbd, 'Hello');
  kbd.press(0, 40);
  kbd.press(0);
  wait(300e6);
  expect(irqAsserted(), `${name}: IRQ_n asserted while keys are waiting`);
  expect((status() & 0x0f) === 6, `${name}: FIFO count 6 in the status byte (${status() & 0x0f})`);
  const n0 = host.log.length;
  const got = keys();
  if (process.env.DEBUG) for (const f of host.log.slice(n0)) console.log('mosi', f.mosi.map((b) => b.toString(16)).join(' '), 'miso', f.miso.map((b) => b.toString(16)).join(' '));
  expect(got === 'Hello\r', `${name}: typed "Hello" + Enter, got ${JSON.stringify(got)}`);
  wait(20e6);
  expect(!irqAsserted(), `${name}: IRQ_n released once the FIFO is empty`);

  // Caps Lock: handled on the card, which lights the keyboard's LED
  kbd.press(0, 57);
  kbd.press(0);
  type(kbd, 'ab');
  wait(200e6);
  expect(kbd.leds.at(-1) === 3, `${name}: Caps Lock LED on (${kbd.leds})`);
  expect(keys() === 'AB', `${name}: Caps Lock gives capitals`);
  kbd.press(0, 57);
  kbd.press(0);
  wait(100e6);
  expect(kbd.leds.at(-1) === 1, `${name}: Caps Lock LED off again (${kbd.leds})`);

  // typematic repeat: 500 ms delay, then every 30 ms
  cmd([0x05]);
  kbd.press(0, usage('x'));
  wait(700e6);
  kbd.press(0);
  wait(50e6);
  const rep = keys();
  expect(rep && rep.length >= 6 && rep.length <= 9 && /^x+$/.test(rep), `${name}: held 700 ms gives 1 + ~7 repeats, got ${JSON.stringify(rep)}`);

  emu.mcu.usbCtrl.detachDevice();
  wait(50e6);
  expect(!(status() & CONNECTED), `${name}: unplugged, KBD_CONNECTED clear`);
}

// ------------------------------------- CS_n falling while the card refreshes
// The main loop swaps the MISO preload (slotspi_refresh) whenever the status
// changes, e.g. a key arrives. A frame whose CS_n falls inside that swap once
// began with the old status byte AND the new one, so the host read the
// second status byte as RESP_LEN (it showed up only on a full-speed keyboard,
// by the timing of that build). Hit the window on purpose: the swap starts by
// masking IO_IRQ_BANK0 (an NVIC ICER write, bit 13); drop CS_n k cycles
// after that write, for k across the swap, and check every READ is framed.
{
  const kbd = new UsbKeyboard({ speed: 2, interval: 1 });
  emu.mcu.usbCtrl.attachDevice(kbd);
  let st = 0;
  for (let i = 0; i < 100 && !(st & CONNECTED); i++) {
    wait(10e6);
    st = status();
  }
  expect(st & CONNECTED, 'race sweep: keyboard enumerated');
  const trap = emu.ppbWriteTrap(0x180, 1 << 13);
  const bareRead = (t) =>
    host.run(function* () {               // a bare READ, CS_n falling now
      yield* this.select();
      const s0 = yield* this.byte(0xfe);
      yield this.byteGapNs;
      const len = yield* this.byte(0);
      for (let i = 0; i < len && i < 16; i++) { yield this.byteGapNs; yield* this.byte(0); }
      yield* this.deselect();
      t.got = { s0, len };
      return t;
    });
  let framed = 0;
  const odd = [];
  for (let k = 0; k <= 120; k += 3) {
    cmd([0x05]);                          // FLUSH: the FIFO is empty
    cmd([0x00]);                          // GETKEY: a 1-byte response is pending
    wait(2e6);
    const t = { k, got: null };
    trap.arm(k, () => bareRead(t));
    kbd.press(0, usage('q'));
    kbd.press(0);
    emu.runUntil(() => t.got !== null, 100e6);
    if (!t.got) { odd.push(`k=${k}: no refresh seen`); trap.disarm(); continue; }
    if (t.got.len === 1) framed++;
    else odd.push(`k=${k}: status $${t.got.s0.toString(16)} then RESP_LEN $${t.got.len.toString(16)}`);
    wait(2e6);
  }
  trap.remove();
  expect(odd.length === 0, `race sweep: every READ framed as status, RESP_LEN 1 (${framed} ok${odd.length ? '; ' + odd.join('; ') : ''})`);
  emu.mcu.usbCtrl.detachDevice();
  wait(50e6);
}

// ------------------------------------------------------------ VBUS fault
emu.mcu.gpio[VBUS_NFAULT].setInputValue(false);
wait(10e6);
expect(status() & FAULT, 'the power switch fault shows as VBUS_FAULT');
emu.mcu.gpio[VBUS_NFAULT].setInputValue(true);
wait(10e6);
expect(!(status() & FAULT), 'VBUS_FAULT clears with the fault');

console.log(`IOC-004: real io.elf on the emulated RP2040 with a USB keyboard model, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
