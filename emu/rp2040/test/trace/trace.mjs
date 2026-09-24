// The same run as build/emu-native/rp2040run, on rp2040js (test/emu/rp2040emu.mjs),
// printing the same trace: "<ns> <pc0> <pc1>" after every Nth step(), to stderr,
// and the UART0 text to stdout. Diffing the two traces checks that the native
// port is cycle-identical to rp2040js on a real firmware image.
//
//   node emu/rp2040/test/trace/trace.mjs <elf> --until <regex> --max-ns <ns>
//        [--mhz N] [--toggle-gpio PIN:EVERY_N_CYCLES]... [--trace-every N]

import { Emu } from '../../../../test/emu/rp2040emu.mjs';

const args = process.argv.slice(2);
const elf = args.shift();
const opt = {};
const toggles = [];
while (args.length) {
  const k = args.shift();
  if (k === '--toggle-gpio') toggles.push(args.shift().split(':').map(Number));
  else opt[k.replace(/^--/, '')] = args.shift();
}
const until = new RegExp(opt.until ?? '$^');
const maxNs = Number(opt['max-ns'] ?? 1e9);
const every = Number(opt['trace-every'] ?? 0);
const emu = await Emu.load(elf, { mhz: Number(opt.mhz ?? 125) });
const hex8 = (v) => (v >>> 0).toString(16).padStart(8, '0');

if (toggles.length) {
  // every Nth cycle, flip the pin's input (each option its own count, applied in order)
  let c = 0;
  emu.onCycle = () => {
    c++;
    for (const [pin, n] of toggles) {
      if (c % n === 0) emu.mcu.gpio[pin].setInputValue(!emu.mcu.gpio[pin].inputValue);
    }
  };
}
let lines = [];
if (every) {
  const step = emu.step.bind(emu);
  let steps = 0;
  emu.step = () => {
    step();
    if (++steps % every === 0) {
      lines.push(`${emu.ns} ${hex8(emu.mcu.core0.PC)} ${hex8(emu.mcu.core1.PC)}\n`);
      if (lines.length >= 4096) {
        process.stderr.write(lines.join(''));
        lines = [];
      }
    }
  };
}
const done = emu.runUntil(() => until.test(emu.uart), maxNs);
process.stderr.write(lines.join(''));
process.stdout.write(emu.uart);
process.exit(done ? 0 : 1);
