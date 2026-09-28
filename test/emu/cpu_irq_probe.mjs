// Exercise each chipset-to-CPU IRQ input with a real firmware stimulus.
// The fixture is assembled into the ROM's fixed $e000 window at run time.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Machine } from './machinenative.mjs';
import { kernelRom, ROOT } from './romimage.mjs';

const bit = Number(process.argv[2]);
if (!Number.isInteger(bit) || bit < 0 || bit > 3) throw new Error('expected IRQ bit 0..3');

const spiEnable = `
card_boot_wait:
  ld r0, $f206
  lt r0, #3
  bzf card_boot_wait
  mov r0, #1
  st $f104, r0
  mov r0, #0xf2
  st $f100, r0
  mov r0, #1
  st $f102, r0
spi_wait0:
  ld r0, $f103
  eq r0, #0
  bzf spi_wait0
  mov r0, #1
  st $f100, r0
  mov r0, #1
  st $f102, r0
spi_wait1:
  ld r0, $f103
  eq r0, #0
  bzf spi_wait1
  mov r0, #0
  st $f104, r0
`;

const assembly = `
main:
  mov r0, #<handler
  st $${(0x10 + bit * 2).toString(16)}, r0
  mov r0, #>handler
  st $${(0x11 + bit * 2).toString(16)}, r0
${bit === 0 ? spiEnable : ''}
  mov r0, #0x11
  st $f000, r0
  mov r0, #${bit === 3 ? 16 : 1 << bit}
  st $f201, r0
  sti
${bit === 1 ? '  tmr0 #12' : bit === 2 ? '  tmr1 #12' : ''}
  wai
idle:
  b idle
handler:
  mov r0, #${0xa0 + bit}
  st $f000, r0
  halt
`;

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-cpu-irq-'));
try {
  const source = path.join(dir, 'probe.s');
  const image = path.join(dir, 'probe.bin');
  fs.writeFileSync(source, assembly);
  execFileSync('python3', [path.join(ROOT, 'tools/as.py'), source, image,
    '0xe000,0xe600,0x0f00'], { stdio: 'pipe' });
  const rom = kernelRom();
  const fixture = fs.readFileSync(image);
  if (fixture.length > 2048) throw new Error('IRQ fixture exceeds fixed ROM window');
  rom.set(fixture, 0);
  const machine = await Machine.create({ slots: bit === 0 ? { 1: 'io' } : {},
    rom, threaded: false });
  try {
    machine.powerOn();
    machine.runFor(bit === 0 ? 1e9 : bit === 3 ? 80e6 : 2e6);
    if (bit === 0) {
      if (machine.keyboard) machine.type('x');
      machine.runFor(100e6);
    }
    console.log(JSON.stringify({ bit, state: machine.state() }));
  } finally {
    machine.stop();
  }
} finally {
  fs.rmSync(dir, { recursive: true, force: true });
}
