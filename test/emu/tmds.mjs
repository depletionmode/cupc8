// Capture and decode the DVI output of the graphics card: the 10-bit TMDS
// symbols the three serialiser state machines (PIO0 SM0-2: blue, green, red)
// pull from their TX FIFOs, two symbols per word, first in bits 9:0.

// control tokens: (C1 = vsync, C0 = hsync)
const CTRL = new Map([[0b1101010100, 0], [0b0010101011, 1], [0b0101010100, 2], [0b1010101011, 3]]);

export function decodeData(sym) {
  let q = sym & 0xff;
  if (sym & 0x200) q = ~q & 0xff;
  let d = q & 1;
  for (let i = 1; i < 8; i++) {
    const bit = ((q >> i) ^ (q >> (i - 1))) & 1;
    d |= (sym & 0x100 ? bit : bit ^ 1) << i;
  }
  return d;
}

export class TmdsCapture {
  constructor(emu) {
    this.emu = emu;
    this.lanes = [[], [], []];
    this.times = []; // emulated ns of each lane-0 word
    this.on = false;
    const sms = emu.mcu.pio[0].machines;
    for (let lane = 0; lane < 3; lane++) {
      const fifo = sms[lane].txFIFO;
      const pull = fifo.pull.bind(fifo);
      fifo.pull = () => {
        const w = pull();
        if (this.on) {
          this.lanes[lane].push(w & 0x3ff, (w >> 10) & 0x3ff);
          if (lane === 0) this.times.push(emu.ns);
        }
        return w;
      };
    }
  }

  start() {
    this.lanes = [[], [], []];
    this.times = [];
    this.on = true;
  }

  stop() {
    this.on = false;
  }

  // Split the capture into frames by the sync on lane 0 (blue). Returns
  // { frames: [{ lines: [{ start, hsyncAt, hsyncLen, dataStart, dataLen }], vsyncLine, vsyncLines, t0 }], errors }
  analyse() {
    const blue = this.lanes[0];
    const n = Math.min(...this.lanes.map((l) => l.length));
    const ctrl = (i) => CTRL.get(blue[i]); // undefined for data symbols
    // hsync is active low: C0 = 0 during the pulse
    const hs = (i) => ctrl(i) !== undefined && (ctrl(i) & 1) === 0;
    const vs = (i) => ctrl(i) !== undefined && (ctrl(i) & 2) === 0;
    const lines = [];
    for (let i = 1; i < n; i++) {
      if (hs(i) && !hs(i - 1)) lines.push(i);
    }
    const out = [];
    for (let l = 0; l + 1 < lines.length; l++) {
      const a = lines[l], b = lines[l + 1];
      let hsLen = 0;
      while (hs(a + hsLen)) hsLen++;
      let ds = -1, dl = 0;
      for (let i = a; i < b; i++) {
        if (ctrl(i) === undefined) {
          if (ds < 0) ds = i;
          dl++;
        }
      }
      out.push({ start: a, total: b - a, hsyncLen: hsLen, dataStart: ds, dataLen: dl, vsync: vs(a), t: this.times[a >> 1] });
    }
    return out;
  }

  // the 480 active lines of the first complete frame after `fromLine`
  // (index into analyse()): 640x480 RGB888, or an error string
  frame(lines) {
    // a frame starts at the first line after a vsync run
    let k = 1;
    while (k < lines.length && !(lines[k - 1].vsync && !lines[k].vsync)) k++;
    const active = [];
    for (let l = k; l < lines.length && active.length < 480; l++) {
      if (lines[l].vsync) return { error: `vsync after ${active.length} active lines` };
      if (lines[l].dataLen) active.push(lines[l]);
    }
    if (active.length < 480) return { error: `only ${active.length} active lines captured` };
    const rgb = new Uint32Array(640 * 480);
    for (let y = 0; y < 480; y++) {
      const { dataStart, dataLen } = active[y];
      if (dataLen !== 640) return { error: `line ${y} has ${dataLen} data symbols` };
      for (let x = 0; x < 640; x++) {
        const i = dataStart + x;
        rgb[y * 640 + x] =
          (decodeData(this.lanes[2][i]) << 16) | (decodeData(this.lanes[1][i]) << 8) | decodeData(this.lanes[0][i]);
      }
    }
    return { rgb, firstLine: k };
  }
}
