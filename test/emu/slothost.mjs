// The CUPC/8 side of a card slot, at pin level: an SPI master in mode 0 with
// the chipset's clock divider (SCK = 12 MHz / (2 x clk_div)) and the host
// timing rules of doc/hardware/slot.md, driving an emulated card's pins.
//
// Scripts are generators that yield nanoseconds to wait:
//   host.run(function* () { const miso = yield* host.frame([0xf0]); ... });
//   emu.runUntil(() => host.done, 1e9);

const SCK = 2, MOSI = 3, MISO = 4, CS = 5;

export class SlotHost {
  constructor(emu, { clkDiv = 2, csSetupNs = 2000, byteGapNs = 1000, frameGapNs = 20000 } = {}) {
    Object.assign(this, { emu, clkDiv, csSetupNs, byteGapNs, frameGapNs });
    this.pin = (n) => emu.mcu.gpio[n];
    this.pin(CS).setInputValue(true);
    this.pin(SCK).setInputValue(false);
    this.pin(MOSI).setInputValue(false);
    this.done = true;
    this.wakeAt = 0;
    this.gen = null;
    this.log = [];
    const prev = emu.onCycle;
    emu.onCycle = (e) => {
      if (prev) prev(e);
      this.tick();
    };
  }

  get halfNs() {
    return (Math.max(1, this.clkDiv) * 1000) / 12;
  }

  // MISO has a pull-up on the main board: an undriven line reads 1
  miso() {
    const p = this.pin(MISO);
    return p.outputEnable ? (p.outputValue ? 1 : 0) : 1;
  }

  run(script) {
    this.gen = script.call(this);
    this.done = false;
    this.wakeAt = this.emu.ns;
    this.result = undefined;
  }

  tick() {
    if (this.done || this.emu.ns < this.wakeAt) return;
    const r = this.gen.next();
    if (r.done) {
      this.done = true;
      this.result = r.value;
    } else {
      this.wakeAt = this.emu.ns + r.value;
    }
  }

  // one byte on the wire; returns the MISO byte (sampled at each rising edge)
  *byte(out) {
    let got = 0;
    for (let bit = 7; bit >= 0; bit--) {
      this.pin(MOSI).setInputValue(!!((out >> bit) & 1));
      yield this.halfNs;
      this.pin(SCK).setInputValue(true);
      got = (got << 1) | this.miso();
      yield this.halfNs;
      this.pin(SCK).setInputValue(false);
    }
    return got;
  }

  *select() {
    this.pin(CS).setInputValue(false);
    yield this.csSetupNs;
  }

  *deselect() {
    this.pin(CS).setInputValue(true);
    yield this.frameGapNs;
  }

  // a whole frame; returns the MISO bytes
  *frame(bytes) {
    yield* this.select();
    const miso = [];
    for (let i = 0; i < bytes.length; i++) {
      if (i) yield this.byteGapNs;
      miso.push(yield* this.byte(bytes[i]));
    }
    yield* this.deselect();
    this.log.push({ mosi: bytes, miso });
    return miso;
  }

  // READ frame: $FE, RESP_LEN, then that many bytes. Retries while RESP_LEN is
  // 0, as the host protocol says. Returns { status, data } or null.
  *read({ tries = 200, retryNs = 50000 } = {}) {
    for (let t = 0; t < tries; t++) {
      yield* this.select();
      const status = yield* this.byte(0xfe);
      yield this.byteGapNs;
      const len = yield* this.byte(0);
      const data = [];
      if (len !== 0 && len !== 0xff) {
        for (let i = 0; i < len; i++) {
          yield this.byteGapNs;
          data.push(yield* this.byte(0));
        }
      }
      yield* this.deselect();
      this.log.push({ mosi: [0xfe], miso: [status, len, ...data] });
      if (len === 0xff) return null;                  // empty slot
      if (len) return { status, data };
      yield retryNs;
    }
    return null;
  }

  *wait(ns) {
    yield ns;
  }
}
