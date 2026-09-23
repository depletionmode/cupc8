// A deterministic RP2040 for the card firmware tests: rp2040js (with our
// dual-core patch, tools/patches/) driven by one loop that steps both cores,
// both PIO blocks and the clock together, so a run is repeatable.
//
//   const emu = await Emu.load('build/rp2040/gpu.elf');
//   emu.runUntil(() => emu.uart.includes('ready'), 1e9);   // ns of emulated time

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
const rp = await import(path.join(SDK, 'rp2040js/dist/esm/index.js'));
const { SimulationClock } = await import(path.join(SDK, 'rp2040js/dist/esm/clock/simulation-clock.js'));

// the B1 bootrom ships with rp2040js as TypeScript source in its demo
function bootrom() {
  const src = fs.readFileSync(path.join(SDK, 'rp2040js/demo/bootrom.ts'), 'utf8');
  const body = src.slice(src.indexOf('bootromB1'));
  const words = body.slice(body.indexOf('[') + 1, body.indexOf(']')).match(/0x[0-9a-f]+/gi);
  return new Uint32Array(words.map((w) => parseInt(w, 16)));
}

// copy an ELF's loadable segments into flash (by their physical address)
function loadElf(file, mcu) {
  const b = fs.readFileSync(file);
  const phoff = b.readUInt32LE(28), phentsize = b.readUInt16LE(42), phnum = b.readUInt16LE(44);
  for (let i = 0; i < phnum; i++) {
    const h = phoff + i * phentsize;
    if (b.readUInt32LE(h) !== 1) continue; // PT_LOAD
    const offset = b.readUInt32LE(h + 4), paddr = b.readUInt32LE(h + 12), filesz = b.readUInt32LE(h + 16);
    if (filesz && paddr >= 0x10000000 && paddr < 0x11000000) {
      mcu.flash.set(b.subarray(offset, offset + filesz), paddr - 0x10000000);
    }
  }
}

export class Emu {
  static async load(elf, { mhz = 125 } = {}) {
    return new Emu(elf, mhz);
  }

  constructor(elf, mhz) {
    this.clock = new SimulationClock();
    this.mcu = new rp.RP2040(this.clock);
    this.mcu.logger = new rp.ConsoleLogger(rp.LogLevel.Error);
    this.mcu.loadBootrom(bootrom());
    loadElf(elf, this.mcu);
    this.mcu.core0.PC = 0x10000000; // boot stage 2, as the bootrom would
    this.nsPerCycle = 1000 / mhz;
    // PIO normally runs itself on setTimeout; we step it with the cores
    for (const pio of this.mcu.pio) pio.run = () => {};
    this.uart = '';
    this.mcu.uart[0].onByte = (b) => (this.uart += String.fromCharCode(b));
    this.onCycle = null; // per-cycle hook: (emu) => void (pin-level test benches)
  }

  get ns() {
    return this.clock.nanos;
  }

  // one step: an instruction on each running core, and the PIO cycles it took
  step() {
    const { mcu, clock } = this;
    if (mcu.waiting) {
      // both cores asleep: skip to the next timer alarm, but no further than
      // one microsecond so PIO and the test bench still see time pass
      const ns = Math.min(clock.nanosToNextAlarm, 1000);
      const cycles = Math.max(1, Math.round(ns / this.nsPerCycle));
      this.cycles(cycles);
      return;
    }
    this.cycles(mcu.step() || 1);
  }

  cycles(n) {
    const { mcu, clock } = this;
    for (let i = 0; i < n; i++) {
      for (const pio of mcu.pio) if (!pio.stopped) pio.step();
      if (this.onCycle) this.onCycle(this);
    }
    clock.tick(n * this.nsPerCycle);
  }

  // run until cond() is true; false if `ns` of emulated time pass first
  runUntil(cond, ns) {
    const end = this.clock.nanos + ns;
    while (this.clock.nanos < end) {
      if (cond()) return true;
      for (let i = 0; i < 64; i++) this.step();
    }
    return cond();
  }
}
