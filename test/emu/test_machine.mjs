// EMU-003: the whole-machine emulator boots: the CPU and chipset RTL run the
// real boot ROM and kernel from the ROM chip, the graphics card (its real
// firmware) is probed over the slot SPI and shows the kernel's banner, read
// back off its TMDS output.
//
//   node test/emu/test_machine.mjs
import { Machine } from './machine.mjs';

const m = await Machine.create({ slots: { 1: 'hdmi' } });
m.cards[1].log = [];                    // every frame the GPU sees (Rp2040Card.drive)
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
let bad = 0;
if (!(text.includes('CUPC/8 BASIC') && text.includes('>>'))) {
  bad++;
  console.log('FAIL the BASIC banner and prompt are not on the screen:\n' + text);
}
// slot.md, probe sequence: READ no sooner than 5 ms after IDENT's CS_n rise
const log = m.cards[1].log;
const ident = log.findIndex((f) => f.bytes[0] === 0xf0);
const read = ident >= 0 ? log[ident + 1] : undefined;
const gap = read && read.bytes[0] === 0xfe ? (read.start - log[ident].ns) / 1e6 : NaN;
if (!(gap >= 5)) {
  bad++;
  console.log(`FAIL the boot ROM's probe READ came ${gap.toFixed(2)} ms after IDENT (slot.md: at least 5 ms)`);
}
console.log(`EMU-003: the machine boots to BASIC on HDMI, ${bad} failures`);
process.exit(bad ? 1 : 0);
