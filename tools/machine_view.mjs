// Watch the whole-machine emulator (test/emu/machine.mjs) in a browser: the
// real boot ROM and kernel on the CPU/chipset RTL, the cards on their real
// firmware, the GPU's HDMI (TMDS) output decoded to pixels, and the browser's
// keyboard on the IO card's USB keyboard.
//
//   node tools/machine_view.mjs [--port 8640] [--slots gpu,io[,wifi]] [--every 250]
//
// then open http://127.0.0.1:8640. --every is the emulated time between
// captured frames, in ms; the emulator runs ~50x slower than real time, so
// the boot to the BASIC prompt takes about a minute of wall time.

import http from 'node:http';
import { Machine } from '../test/emu/machine.mjs';

const arg = (name, dflt) => {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 ? process.argv[i + 1] : dflt;
};
const port = Number(arg('port', 8640));
const every = Number(arg('every', 250)) * 1e6;
const kinds = arg('slots', 'gpu,io').split(',');
const slots = Object.fromEntries(kinds.map((k, i) => [i + 1, k]));

const m = await Machine.create({ slots });
let frame = null;                 // the last good frame, 640x480 RGB888
let frames = 0, note = 'powering on', started = Date.now();

// ------------------------------------------------------------------- the page
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>CUPC/8 emulator</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; background: #111; color: #ccc; font: 14px ui-monospace, monospace;
         display: flex; flex-direction: column; align-items: center; padding: 16px; }
  canvas { width: 960px; max-width: 100%; image-rendering: pixelated; border: 1px solid #333;
           background: #000; outline: none; }
  canvas:focus { border-color: #6a6; }
  #status { margin-top: 8px; white-space: pre; }
  #help { margin-top: 4px; color: #777; }
</style></head><body>
<canvas id="c" width="640" height="480" tabindex="0"></canvas>
<div id="status">connecting...</div>
<div id="help">click the screen, then type: keys go to the IO card's USB keyboard</div>
<script>
const c = document.getElementById('c'), g = c.getContext('2d'), img = g.createImageData(640, 480);
const status = document.getElementById('status');
c.focus();
async function tick() {
  try {
    const s = await (await fetch('/state')).json();
    status.textContent = s.line;
    if (s.frames !== window.seen) {
      window.seen = s.frames;
      const rgb = new Uint8Array(await (await fetch('/frame')).arrayBuffer());
      if (rgb.length === 640 * 480 * 3) {
        for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
          img.data[j] = rgb[i]; img.data[j + 1] = rgb[i + 1]; img.data[j + 2] = rgb[i + 2]; img.data[j + 3] = 255;
        }
        g.putImageData(img, 0, 0);
      }
    }
  } catch (e) { status.textContent = 'emulator not reachable: ' + e; }
  setTimeout(tick, 300);
}
tick();
// USB HID usages for the keys typed text can't carry
const USAGE = { Enter: 40, Escape: 41, Backspace: 42, Tab: 43, ArrowRight: 79, ArrowLeft: 80,
                ArrowDown: 81, ArrowUp: 82, Delete: 76, Home: 74, End: 77 };
c.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  let q = null;
  if (e.key.length === 1) q = 'text=' + encodeURIComponent(e.key);
  else if (USAGE[e.key]) q = 'usage=' + USAGE[e.key];
  if (q) { e.preventDefault(); fetch('/key?' + q, { method: 'POST' }); }
});
</script></body></html>`;

// ----------------------------------------------------------------- the server
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(PAGE);
  } else if (url.pathname === '/state') {
    const s = m.state();
    const emu = m.ns / 1e9, wall = (Date.now() - started) / 1000;
    const line = `emulated ${emu.toFixed(2)} s (${(wall / Math.max(emu, 1e-9)).toFixed(0)}x slower than real time)` +
      `   POST $${s.gpo.toString(16).padStart(2, '0')}   PC $${s.pc.toString(16).padStart(4, '0')}` +
      `${s.halted ? '   HALTED' : ''}   frames ${frames}   ${note}`;
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ line, frames }));
  } else if (url.pathname === '/frame') {
    res.writeHead(200, { 'Content-Type': 'application/octet-stream' });
    res.end(frame ?? Buffer.alloc(0));
  } else if (url.pathname === '/key' && req.method === 'POST') {
    if (!m.keyboard) note = 'no IO card fitted: keys go nowhere';
    else if (url.searchParams.has('text')) m.type(url.searchParams.get('text'));
    else if (url.searchParams.has('usage')) {
      m.keyboard.press(0, Number(url.searchParams.get('usage')));
      m.keyboard.press(0);
    }
    res.writeHead(204);
    res.end();
  } else {
    res.writeHead(404);
    res.end();
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`CUPC/8 emulator (slots: ${kinds.join(', ')}): open http://127.0.0.1:${port}`);
});

// ------------------------------------------------------------- the emulator
m.powerOn();
started = Date.now();
for (;;) {
  await m.runAsync(every);
  const f = m.frame();                       // ~2 frame times of TMDS, decoded
  if (f.error) {
    note = 'no picture yet: ' + f.error;     // the GPU has not started its output
    continue;
  }
  const rgb = Buffer.alloc(640 * 480 * 3);
  for (let i = 0; i < 640 * 480; i++) {
    const p = f.rgb[i];
    rgb[i * 3] = p >> 16;
    rgb[i * 3 + 1] = (p >> 8) & 0xff;
    rgb[i * 3 + 2] = p & 0xff;
  }
  frame = rgb;
  frames++;
  note = '';
}
