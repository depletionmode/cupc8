// EMU-003: the whole-machine emulator boots: the CPU and chipset RTL run the
// real boot ROM and kernel from the ROM chip, the graphics card (its real
// firmware) is probed over the slot SPI and shows the kernel's banner, read
// back off its TMDS output.
//
//   node test/emu/test_machine.mjs
import { Machine } from './machine.mjs';

const m = await Machine.create({ slots: { 1: 'gpu' } });
m.powerOn();
let text = '';
for (let t = 0; t < 30 && !text.includes('CUPC/8 BASIC'); t++) {
  m.runFor(100e6);
  if (t >= 8) {
    const s = m.screen();
    text = s.error ? '' : s.text.join('\n');
    if (s.error) console.log(`${((t + 1) * 0.1).toFixed(1)} s: ${s.error}`);
  }
}
const ok = text.includes('CUPC/8 BASIC') && text.includes('>>');
if (!ok) console.log('FAIL the BASIC banner and prompt are not on the screen:\n' + text);
console.log(`EMU-003: the machine boots to BASIC on HDMI, ${ok ? 0 : 1} failures`);
process.exit(ok ? 0 : 1);
