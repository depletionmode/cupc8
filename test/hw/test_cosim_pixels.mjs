// Fast counterexample for the E2E-002 pixel-golden check, using a programmed
// ROM so the 5-minute blank-ROM upload is not repeated for this mutation.
import { Machine } from '../emu/machinenative.mjs';
import { compareGoldenHdmiFrame } from '../emu/hdmi_golden.mjs';

if (!process.env.CUPC8_COSIM_TOP) throw new Error('CUPC8_COSIM_TOP is required');
const m = await Machine.create({slots: {1: 'hdmi', 2: 'io'}, spiLog: true, threaded: false});
try {
  m.powerOn();
  const text = () => m.screen().text?.join('\n') ?? '';
  if (!await m.runUntil(() => text().includes('>>'), 6e9, 100e6)) throw new Error('no BASIC prompt');
  m.type('10 print 6*7\nrun\n');
  if (!await m.runUntil(() => text().includes('42'), 3e9, 100e6)) throw new Error('BASIC program failed');
  await m.runAsync(200e6);
  const good = compareGoldenHdmiFrame(m);
  if (good.differences) throw new Error(`untouched HDMI frame differs in ${good.differences} pixels`);
  const frames = m.spiLog(1).map(f => ({...f, bytes: [...f.bytes]}));
  const last = frames.findLast(f => f.bytes[0] === 0x10 && f.bytes.length === 2);
  if (!last) throw new Error('no PUTC SPI transaction to mutate');
  last.bytes[1] = last.bytes[1] === 0x41 ? 0x42 : 0x41;
  const changed = compareGoldenHdmiFrame({spiLog: () => frames, frame: () => m.frame()});
  if (!changed.differences) throw new Error('changed HDMI SPI character escaped pixel comparison');
  console.log(`golden HDMI: ${good.frames} SPI frames, 0 pixel differences; changed PUTC: ${changed.differences} differences`);
} finally {
  m.stop();
}
