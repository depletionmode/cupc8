// EMU-001: the emulator runs the dual-core features the card firmware needs
// (fw/rp2040/selftest/selftest.c prints the verdict).
import { Emu } from './rp2040emu.mjs';

const emu = await Emu.load(process.argv[2] ?? 'build/rp2040/emu_selftest.elf');
const done = emu.runUntil(() => /EMU (PASS|FAIL)[^\n]*\n/.test(emu.uart), 200e6);
process.stdout.write(emu.uart);
if (!done) console.log(`EMU-001: no verdict after ${(emu.ns / 1e6).toFixed(1)} ms emulated`);
process.exit(done && emu.uart.includes('EMU PASS') ? 0 : 1);
