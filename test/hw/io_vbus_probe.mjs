// The IO card's VBUS switch on the netlist-generated top (CUPC8_COSIM_TOP):
// the real kernel boots to BASIC (HDMI card in slot 1) with the IO card in slot 2; the slot SPI frames'
// status bytes carry VBUS_FAULT (bit 4, GPIO8 read low by the firmware), and
// the USB keyboard model exists only while the card's VBUS is on.
import { Machine } from '../emu/machinenative.mjs';
import { kernelRom } from '../emu/romimage.mjs';

const text = (m) => { const s = m.screen(); return s.error ? '' : s.text.join('\n'); };
const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io' }, rom: kernelRom(), threaded: false, spiLog: true });
try {
  m.powerOn();
  await m.runUntil(() => text(m).includes('>>'), 8e9, 100e6);
  m.runFor(100e6);
  const frames = m.spiLog(2);
  const statuses = frames.filter((f) => f.miso.length).map((f) => f.miso[0]);
  console.log(JSON.stringify({
    frames: frames.length,
    faults: statuses.filter((s) => s & 0x10).length,
    keyboard: Boolean(m.keyboard),
  }));
} finally {
  m.stop();
}
