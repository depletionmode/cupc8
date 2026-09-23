// EMU-002: nested interrupts on the emulated RP2040 (fw/rp2040/selftest/nested.c).
import { Emu } from './rp2040emu.mjs';

const emu = await Emu.load(process.argv[2] ?? 'build/rp2040/emu_nested.elf');
let n = 0;
emu.onCycle = () => {
  if (++n % 997 === 0) emu.mcu.gpio[2].setInputValue(!emu.mcu.gpio[2].inputValue);   // a GPIO IRQ every ~8 us
};
const done = emu.runUntil(() => /NEST (PASS|FAIL)[^\n]*\n/.test(emu.uart), 500e6);
process.stdout.write(emu.uart);
const m = /NEST PASS (\d+)/.exec(emu.uart);
const ok = done && m && Number(m[1]) > 100;
if (!ok) console.log('EMU-002: failed', done ? '' : '(no verdict)');
process.exit(ok ? 0 : 1);
