// SYS-006: the real system card firmware (build/rp2040/sysctl.elf) on the
// emulated RP2040, driven over USB CDC exactly as cupc8.py drives it. Around
// it: the two W25Q configuration flashes on SPI1 (told apart by their CS
// pins), iCE40s that raise CDONE only when their flash starts with a
// bitstream's sync word, the two TCA9555 expanders, and the CC voltages.
//
//   node test/emu/test_sysctl.mjs
//   (CUPC8_EMU=native: on the C++ emulator, see emu_backend.mjs)

import path from 'node:path';
import { Emu, USBCDC } from './emu_backend.mjs';                     // CUPC8_EMU=native: the C++ emulator

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const emu = await Emu.load(path.join(ROOT, 'build/rp2040/sysctl.elf'), { mhz: 125 });
const gpio = emu.mcu.gpio;
const PIN = { FL0_NCS: 13, FL1_NCS: 9, CHIPSET_NCRESET: 6, CHIPSET_CDONE: 7, CPUCARD_NCRESET: 16, CPUCARD_CDONE: 17, SYS_NRST: 23 };
const MACHINE_PINS = [2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23];

let bad = 0, checks = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
}
const driven = (n) => gpio[n].outputEnable;
const drivenLow = (n) => gpio[n].outputEnable && !gpio[n].outputValue;

// ------------------------------------------------------------ W25Q16 models
class Flash {
  constructor(name) {
    this.name = name;
    this.mem = new Uint8Array(2 * 1024 * 1024).fill(0xff);
    this.wel = false;
    this.cmd = null;
    this.touched = 0;          // bytes clocked while this flash's FPGA was not held
  }
  begin() {
    this.cmd = [];
  }
  end() {
    this.cmd = null;
  }
  xfer(b) {
    const c = this.cmd;
    if (!c) return 0xff;
    c.push(b);
    const op = c[0], n = c.length, a = ((c[1] << 16) | (c[2] << 8) | c[3]) & 0x1fffff;
    if (op === 0x9f) return [0, 0xef, 0x40, 0x15][n - 1] ?? 0;
    if (op === 0x05) return n === 1 ? 0 : this.wel ? 0x02 : 0x00;  // never busy
    if (op === 0x06 && n === 1) this.wel = true;
    if (op === 0x04 && n === 1) this.wel = false;
    if (op === 0x03 && n > 4) return this.mem[(a + n - 5) & 0x1fffff];
    if (op === 0x20 && n === 4 && this.wel) {
      this.mem.fill(0xff, a & ~0xfff, (a & ~0xfff) + 4096);
      this.wel = false;
    }
    if (op === 0x02 && n > 4 && this.wel) {
      const at = (a & ~0xff) | ((a + n - 5) & 0xff);          // wraps within the page
      this.mem[at] &= b;
      if (n === 4 + 256) this.wel = false;
    }
    return 0;
  }
}
const flash = { [PIN.FL0_NCS]: new Flash('FL0'), [PIN.FL1_NCS]: new Flash('FL1') };
for (const cs of [PIN.FL0_NCS, PIN.FL1_NCS]) {
  gpio[cs].addListener(() => (drivenLow(cs) ? flash[cs].begin() : flash[cs].end()));
}
emu.mcu.spi[1].onTransmit = (b) => {
  let out = 0xff;
  for (const cs of [PIN.FL0_NCS, PIN.FL1_NCS]) if (drivenLow(cs)) out = flash[cs].xfer(b);
  emu.mcu.spi[1].completeTransmit(out);
};
emu.mcu.spi[0].onTransmit = () => emu.mcu.spi[0].completeTransmit(0);     // no chipset running

// ------------------------------------------------------------ the FPGAs
// CDONE (open drain, pulled up on the board) is high only once the FPGA has
// read a bitstream: sync word $7EAA997E at the start of its flash
const fpga = [
  { creset: PIN.CHIPSET_NCRESET, cdone: PIN.CHIPSET_CDONE, flash: flash[PIN.FL0_NCS], doneAt: 0 },
  { creset: PIN.CPUCARD_NCRESET, cdone: PIN.CPUCARD_CDONE, flash: flash[PIN.FL1_NCS], doneAt: 0 },
];
const hasBitstream = (f) => f.mem.subarray(0, 32).join().includes([0x7e, 0xaa, 0x99, 0x7e].join());
function fpgaTick() {
  for (const f of fpga) {
    if (drivenLow(f.creset)) {
      f.doneAt = 0;
      gpio[f.cdone].setInputValue(false);
    } else if (!f.doneAt) {
      f.doneAt = emu.ns + 200e6;            // an HX4K reads its image in ~0.2 s
    } else if (emu.ns >= f.doneAt) {
      gpio[f.cdone].setInputValue(hasBitstream(f.flash));
    }
  }
}
for (const f of fpga) gpio[f.cdone].setInputValue(hasBitstream(f.flash));

// ------------------------------------------------------------ TCA9555 expanders
const expander = { 0x20: new Uint8Array(8).fill(0xff), 0x21: new Uint8Array(8).fill(0xff) };
for (const e of Object.values(expander)) e.fill(0, 4, 6);  // polarity 0
let i2cAddr = -1, i2cReg = -1, i2cFirst = true;
const i2c = emu.mcu.i2c[0];
i2c.onConnect = (addr) => {
  i2cAddr = addr;
  i2cFirst = true;
  i2c.completeConnect(!!expander[addr]);
};
i2c.onWriteByte = (v) => {
  const e = expander[i2cAddr];
  if (i2cFirst) i2cReg = v & 7;
  else if (e) e[i2cReg++ & 7] = v;
  i2cFirst = false;
  i2c.completeWrite(!!e);
};
i2c.onReadByte = () => i2c.completeRead(expander[i2cAddr]?.[i2cReg++ & 7] ?? 0xff);
const cardHeld = (slot) => !((expander[0x20][6] >> slot) & 1) && !((expander[0x20][2] >> slot) & 1);

// ------------------------------------------------------------ USB CDC host
const cdc = new USBCDC(emu.mcu.usbCtrl);
let connected = false, rxBytes = [];
const pending = [];
cdc.onDeviceConnected = () => (connected = true);
cdc.onSerialData = (buf) => rxBytes.push(...buf);
emu.everyCycles(1000, () => {
  fpgaTick();
  while (pending.length && cdc.txFIFO.itemCount < 512) cdc.sendSerialByte(pending.shift());
});

function crc8(bytes) {
  let c = 0;
  for (const b of bytes) {
    c ^= b;
    for (let i = 0; i < 8; i++) c = c & 0x80 ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff;
  }
  return c;
}
function request(cmd, payload = [], timeoutNs = 5e9) {
  const body = [cmd, payload.length & 0xff, payload.length >> 8, ...payload];
  rxBytes = [];
  pending.push(0xc8, ...body, crc8(body));
  let reply = null;
  const done = () => {
    const i = rxBytes.indexOf(0xc8);
    if (i < 0 || rxBytes.length < i + 5) return false;
    const len = rxBytes[i + 2] | (rxBytes[i + 3] << 8);
    if (rxBytes.length < i + 5 + len) return false;
    const fr = rxBytes.slice(i, i + 5 + len);
    reply = { status: fr[1], data: fr.slice(4, 4 + len), crcOk: crc8(fr.slice(1, 4 + len)) === fr[4 + len] };
    return true;
  };
  emu.runUntil(done, timeoutNs);
  return reply;
}
const u24 = (v) => [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff];

// ------------------------------------------------------------ start-up
emu.runUntil(() => false, 50e6);
expect(MACHINE_PINS.every((n) => !driven(n)), `at start-up no machine pin is driven: ${MACHINE_PINS.filter(driven)}`);
emu.runUntil(() => connected, 3e9);
expect(connected, 'enumerates as a USB CDC device');

const ping = request(0x00);
expect(ping && ping.status === 0 && ping.crcOk && String.fromCharCode(...ping.data).startsWith('CUPC8 sysctl'),
  `PING: ${ping && String.fromCharCode(...ping.data)}`);
expect(MACHINE_PINS.every((n) => !driven(n)), 'still nothing driven after PING');
// the USB activity LEDs (GPIO0 TX, GPIO1 RX): lit by the exchange, dark ~30 ms later
const lit = (n) => gpio[n].outputEnable && gpio[n].outputValue;
emu.runUntil(() => false, 1e6);
expect(lit(0) && lit(1), 'the USB TX and RX LEDs light after a request and its reply');
emu.runUntil(() => false, 40e6);
expect(!lit(0) && !lit(1), 'and go dark ~30 ms later');

emu.mcu.adc.channelValues[0] = Math.round((900 / 3300) * 4095);    // CC1 0.9 V: a 1.5 A source
emu.mcu.adc.channelValues[1] = 0;
const pw = request(0x50);
expect(pw && pw.status === 0 && pw.data[0] === 2, `POWER: class 2 from 0.9 V on CC1 (${pw && pw.data})`);

const ram = request(0x10, [0, 0, 16, 0]);
expect(ram && ram.status === 7, `RAM_READ with no chipset answering: status 7 (${ram && ram.status})`);

// ------------------------------------------------------------ FPGA flash
const noHold = request(0x43, [0]);
expect(noHold && noHold.status === 6, `FLASH_ID before FPGA_HOLD is refused: status 6 (${noHold && noHold.status})`);
expect(!driven(PIN.FL0_NCS), 'and the chipset flash was not touched');

expect(request(0x44, [0]).status === 0 && drivenLow(PIN.CHIPSET_NCRESET), 'FPGA_HOLD 0 drives the chipset CRESET_n low');
const id = request(0x43, [0]);
expect(id && id.status === 0 && id.data.join() === [0xef, 0x40, 0x15].join(), `FLASH_ID 0: ${id && id.data}`);
expect(request(0x43, [1]).status === 6, 'FL1 is still refused: its FPGA is not held');

const image = [0xff, 0x00, 0x00, 0xff, 0x7e, 0xaa, 0x99, 0x7e];
for (let i = image.length; i < 1500; i++) image.push((i * 7) & 0xff);
expect(request(0x41, [0, ...u24(0), ...u24(image.length)]).status === 0, 'FLASH_ERASE');
expect(request(0x42, [0, ...u24(0), ...image]).status === 0, 'FLASH_PROGRAM 1500 bytes');
const back = request(0x40, [0, ...u24(0), image.length & 0xff, image.length >> 8]);
expect(back && back.data.join() === image.join(), 'FLASH_READ returns what was programmed');
expect(flash[PIN.FL0_NCS].mem.subarray(0, image.length).join() === image.join(), 'and it is in the chipset flash');
expect(flash[PIN.FL1_NCS].mem.every((b) => b === 0xff), 'the CPU card flash is untouched');

const boot = request(0x45, [0]);
expect(boot && boot.status === 0 && !driven(PIN.CHIPSET_NCRESET), `FPGA_BOOT 0: released, CDONE seen (status ${boot && boot.status})`);
expect(![10, 11, 12, 13].some(driven), 'FL0 lines released once the chipset owns its flash again');

// a CPU card flash with no bitstream: its FPGA never raises CDONE
request(0x44, [1]);
request(0x41, [1, ...u24(0), ...u24(4096)]);
const noImage = request(0x45, [1], 5e9);
expect(noImage && noImage.status === 4, `FPGA_BOOT with no bitstream: timeout (status ${noImage && noImage.status})`);

// ------------------------------------------------------------ cards
expect(request(0x52, [2, 1]).status === 0 && cardHeld(2), 'CARD_RESET 2 hold: slot 3 CARD_RST_n driven low');
expect([0, 1, 3, 4, 5].every((s) => !cardHeld(s)), 'and no other slot');
expect(request(0x52, [2, 0]).status === 0 && !cardHeld(2), 'CARD_RESET 2 release');

// ------------------------------------------------------------ framing
rxBytes = [];
pending.push(0xc8, 0x00, 0, 0, 0x55);                             // PING with a wrong CRC
emu.runUntil(() => rxBytes.length >= 5, 1e9);
expect(rxBytes[0] === 0xc8 && rxBytes[1] === 1, `a bad CRC is answered with status 1 (${rxBytes.slice(0, 5)})`);

// ------------------------------------------------------------ programming port
const MUX = [20, 21, 22], CLK = 18, IO = 19;
const muxSlot = () => (MUX.every((n) => !driven(n)) ? -1 : MUX.reduce((v, n, i) => v | ((gpio[n].outputValue ? 1 : 0) << i), 0));
expect(muxSlot() === -1, 'the mux is released (channel 7) until a slot is selected');
expect(request(0x53, [5]).status === 0 && muxSlot() === 5, `PROG_SELECT 5 drives MUX_SEL = 5 (${muxSlot()})`);
expect(request(0x53, [0xff]).status === 0 && muxSlot() === -1, 'PROG_SELECT $FF releases it');

// UART: PROG_CLK (TX) wired back to PROG_IO (RX)
const loop = () => gpio[IO].setInputValue(driven(CLK) ? gpio[CLK].outputValue : true);
const unloop = gpio[CLK].addListener(loop);
loop();
expect(request(0x56, [0x00, 0xc2, 0x01, 0x00]).status === 0, 'UART_OPEN 115200');
const first = request(0x57, [...Buffer.from('\xc0hello esp\xc0', 'latin1')]);   // returns what came back so far
emu.runUntil(() => false, 2e6);                                     // 12 bytes at 115200: ~1 ms
const rest = request(0x57, []);
const echo = Buffer.from([...(first?.data ?? []), ...(rest?.data ?? [])]).toString('latin1');
expect(echo === '\xc0hello esp\xc0', `UART loopback across two UART_XFERs: ${JSON.stringify(echo)}`);
request(0x56, [0, 0, 0, 0]);
unloop();

// SWD at pin level: a minimal SW-DP (wake-up, line reset, TARGETSEL, DPIDR)
// sampling SWDIO on SWCLK's rising edge and driving its bits after it
const alert = [0x92, 0xf3, 0x09, 0x62, 0x95, 0x2d, 0x85, 0x86, 0xe9, 0xaf, 0xdd, 0xe3, 0xa2, 0x0e, 0xbc, 0x19];
const alertBits = alert.flatMap((b) => [0, 1, 2, 3, 4, 5, 6, 7].map((i) => (b >> i) & 1)).join('');
const dp = { hist: '', awake: false, ones: 0, selected: false, phase: 0, bits: [], out: [], lastClk: false, dpidrReads: 0 };
function dpBit(b) {
  dp.hist = (dp.hist + b).slice(-160);
  dp.ones = b ? dp.ones + 1 : 0;
  if (!dp.awake) {
    const i = dp.hist.lastIndexOf(alertBits);
    if (i >= 0 && dp.hist.length - i - 128 === 12 && dp.hist.slice(i + 128, i + 132) === '0000' && dp.hist.slice(i + 132) === '01011000') dp.awake = true;
    return;
  }
  if (dp.ones >= 50) { dp.phase = 0; dp.selected = false; return; }
  dp.bits.push(b);
  if (dp.phase === 0) { if (!b) dp.bits = []; else dp.phase = 1; return; }
  if (dp.phase === 1 && dp.bits.length === 8) {
    const r = dp.bits.reduce((v, x, i) => v | (x << i), 0);
    dp.bits = [];
    dp.phase = 0;
    if (r === 0x99) { dp.phase = 3; return; }                          // TARGETSEL: 5 undriven, then 33 bits
    if (r === 0xa5 && dp.selected) {                                  // DPIDR read
      const v = 0x0bc12477, bits = [1, 0, 0];
      for (let i = 0; i < 32; i++) bits.push((v >>> i) & 1);
      bits.push([...v.toString(2)].filter((c) => c === '1').length & 1);
      dp.out = bits;
      dp.dpidrReads++;
    }
    return;
  }
  if (dp.phase === 3 && dp.bits.length === 33) {
    const v = dp.bits.slice(0, 32).reduce((a, x, i) => a + x * 2 ** i, 0);
    dp.selected = v === 0x01002927;
    dp.bits = [];
    dp.phase = 0;
  }
}
gpio[CLK].addListener(() => {
  const clk = driven(CLK) && gpio[CLK].outputValue;
  if (clk && !dp.lastClk) {
    if (driven(IO)) {
      dpBit(gpio[IO].outputValue ? 1 : 0);
      gpio[IO].setInputValue(true);
    } else {
      gpio[IO].setInputValue(dp.out.length ? dp.out.shift() === 1 : true);   // our next bit, or released
    }
  }
  dp.lastClk = clk;
});
gpio[IO].setInputValue(true);
request(0x53, [1]);
const bitsOf = (bytes, n) => [n & 0xff, n >> 8, ...bytes];
request(0x54, bitsOf([0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00], 64));
request(0x54, bitsOf([0xff, ...alert, 0xa0, 0x01], 148));
request(0x54, bitsOf([0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00], 64));
expect(dp.awake, 'the dormant-to-SWD sequence arrives bit-exact on the pins');
const ts = request(0x55, [0x99, 0x27, 0x29, 0x00, 0x01]);
expect(ts && ts.data[0] === 1 && dp.selected, `TARGETSEL core 0 selects the DP (${ts && ts.data})`);
const idr = request(0x55, [0xa5]);
const v = idr && idr.data.length === 5 ? (idr.data[1] | (idr.data[2] << 8) | (idr.data[3] << 16) | (idr.data[4] << 24)) >>> 0 : 0;
expect(idr && idr.data[0] === 1 && v === 0x0bc12477, `DPIDR read at pin level: ack ${idr && idr.data[0]}, ${v.toString(16)}`);
request(0x53, [0xff]);

console.log(`SYS-006: real sysctl.elf on the emulated RP2040 over USB, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
