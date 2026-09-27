// Compare a whole-machine TMDS frame to the independent host GPU core fed
// with the exact SPI transactions captured at the physical HDMI card slot.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ROOT } from './romimage.mjs';

export function compareGoldenHdmiFrame(machine) {
  const frames = machine.spiLog(1);
  if (!frames.length || frames.some(f => f.extra !== 0 || f.bytes.length > 8192))
    throw new Error('HDMI SPI traffic is empty or has an incomplete frame');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-e2e-hdmi-'));
  try {
    const input = path.join(dir, 'frames.bin');
    const output = path.join(dir, 'golden.rgb');
    const parts = [];
    for (const f of frames) parts.push(Buffer.from([f.bytes.length & 255, f.bytes.length >> 8]), Buffer.from(f.bytes));
    fs.writeFileSync(input, Buffer.concat(parts));
    execFileSync('make', ['-s', '-C', path.join(ROOT, 'fw'), 'gpu_golden']);
    const actual = machine.frame();
    if (actual.error || actual.rgb?.length !== 640 * 480)
      throw new Error(`TMDS capture failed: ${actual.error ?? 'wrong frame size'}`);
    const channel = x => Math.round(x / 85);
    const code = px => (channel((px >> 16) & 255) << 4) |
      (channel((px >> 8) & 255) << 2) | channel(px & 255);
    const comparisons = [];
    // The frame's cursor blink can lie in either half of its 30-vsync cycle.
    for (const phase of [0, 15]) {
      execFileSync(path.join(ROOT, 'build/fw/gpu_golden'), [input, String(phase), output]);
      const data = fs.readFileSync(output);
      if (data.length !== 640 * 480 * 4) throw new Error('gpu_golden produced an incomplete frame');
      const want = new Uint32Array(data.buffer, data.byteOffset, data.length / 4);
      let differences = 0, first = null;
      for (let i = 0; i < want.length; i++) {
        if (code(actual.rgb[i]) !== code(want[i])) {
          if (first === null) first = [i % 640, Math.floor(i / 640)];
          differences++;
        }
      }
      comparisons.push({phase, differences, first});
    }
    return {frames: frames.length, ...comparisons.sort((a, b) => a.differences - b.differences)[0]};
  } finally {
    fs.rmSync(dir, {recursive: true, force: true});
  }
}
