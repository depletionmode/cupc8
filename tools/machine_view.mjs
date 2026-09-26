// Watch the whole-machine emulator (test/emu/machine.mjs) in a browser: the
// real boot ROM and kernel on the CPU/chipset RTL, the cards on their real
// firmware, the GPU's HDMI (TMDS) output decoded to pixels, and the browser's
// keyboard on the IO card's USB keyboard.
//
//   node tools/machine_view.mjs [--port 8640] [--slots hdmi,io[,wifi]] [--every 250] [--native]
//   node tools/machine_view.mjs --native --slots hdmi,io,wifi --forward tcp:8080:80,udp:5353:53
//   node tools/machine_view.mjs --native --slots eink,io      (the e-ink card: 5.83", or eink750)
//
// then open http://127.0.0.1:8640. --every is the emulated time between
// captured frames, in ms. --native (or CUPC8_EMU=native) runs the native
// emulator (emu/machine, built by tools/emu_machine_build.sh; about 8x slower
// than real time) instead of test/emu/machine.mjs (~100x slower): the same
// machine, cycle for cycle (EMU-007), just faster.
//
// --console (native only) fits the system card and opens its console port
// (doc/proposals/usb-console.md): a pane under the screen shows what the
// kernel's terminal prints, and text typed (or pasted) in its box is typed
// into the machine. --console-port N instead serves that port on TCP N for a
// terminal: `cupc8.py console tcp:127.0.0.1:N` (or nc); connecting opens it.
//
// With an e-ink card (slot kind eink or eink750, native only) the page shows
// the panel's glass instead of HDMI: the UC8179 model's picture, which
// changes only when a refresh completes, as on the real panel (a partial
// refresh about 0.3 s after the typing stops; CUPC8_EINK_SCALE scales the
// panel's busy times).

import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log(`Watch the CUPC/8 machine emulator in a browser.

usage: node tools/machine_view.mjs [options]

  --native         run the native emulator (emu/machine; build it with
                   tools/emu_machine_build.sh). Also CUPC8_EMU=native.
                   Without it: the legacy JS emulator (test/emu/machine.mjs).
  --slots LIST     the cards in slots 1, 2, ... (default hdmi,io). Kinds:
                   hdmi, io, wifi, storage, and (native only) eink (5.83")
                   or eink750 in place of hdmi.
  --forward LIST   port forwards to the Wi-Fi card (native only), comma
                   separated PROTO:HOSTPORT:CARDPORT: tcp:8080:80 makes the
                   PC's 127.0.0.1:8080 reach port 80 on the card (QEMU's
                   hostfwd). The card reaches the PC as 10.0.2.2.
  --every MS       emulated time between captured frames (default 250)
  --sd IMAGE       with a storage card (native only): put this card image in
                   its microSD socket; a missing file is made first, a 16 MB
                   FAT16 card as a PC would format it (test/emu/fatimg.py)
  --console        (native only) fit the system card and open its console
                   port: the page shows the kernel's terminal text and
                   types what you enter in its box (a BASIC program can be
                   pasted there)
  --console-port N (native only) fit the system card and serve its console
                   port on TCP N instead: cupc8.py console tcp:127.0.0.1:N
  --port N         the web page's port (default 8640)
  -h, --help       this text

Then open http://127.0.0.1:<port>, click the screen and type.

examples:
  node tools/machine_view.mjs --native
  node tools/machine_view.mjs --native --slots hdmi,io,wifi
  node tools/machine_view.mjs --native --slots hdmi,io,wifi --forward tcp:8080:80,udp:5353:53
  node tools/machine_view.mjs --native --slots eink,io,storage --sd card.img
  node tools/machine_view.mjs --native --console

environment:
  CUPC8_EINK_SCALE   scale the e-ink panel's busy times
  CUPC8_EMU_THREADS  0 runs the native emulator single-threaded`);
  process.exit(0);
}

const native = process.argv.includes('--native') || process.env.CUPC8_EMU === 'native';
const { Machine } = await import(native ? '../test/emu/machinenative.mjs' : '../test/emu/machine.mjs');

const arg = (name, dflt) => {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 ? process.argv[i + 1] : dflt;
};
const port = Number(arg('port', 8640));
const every = Number(arg('every', 250)) * 1e6;
const kinds = arg('slots', 'hdmi,io').split(',');
const slots = Object.fromEntries(kinds.map((k, i) => [i + 1, k]));

const forward = arg('forward', '').split(',').filter(Boolean);

const eink = kinds.some((k) => k.startsWith('eink'));
if (eink && !native) throw new Error('the e-ink card runs on the native emulator only: add --native');
if (forward.length && !native) throw new Error('--forward is for the native emulator only: add --native');
const sd = arg('sd', null);
if (sd && !(native && kinds.includes('storage'))) throw new Error('--sd needs --native and a storage card in --slots');
const consolePane = process.argv.includes('--console');
const consolePort = arg('console-port', null);
if ((consolePane || consolePort) && !native) throw new Error('the console is for the native emulator only: add --native');
if (consolePane && consolePort) throw new Error('--console or --console-port, not both');
const m = await Machine.create({ slots, forward, sysctl: !!(consolePane || consolePort) });
let consoleText = '';             // the console's output so far (the pane)
if (consolePane) m.console.open();
if (consolePort) {
  const p = await m.console.listen(Number(consolePort));
  console.log(`console: cupc8.py console tcp:127.0.0.1:${p}`);
}
if (sd) {
  if (!fs.existsSync(sd)) {
    const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
    const root = path.dirname(path.dirname(new URL(import.meta.url).pathname));
    execFileSync(path.join(SDK, 'pyfat/bin/python'), [path.join(root, 'test/emu/fatimg.py'), 'mkfs', sd, '16', '16']);
    console.log(`made ${sd}: a 16 MB FAT16 card`);
  }
  m.sd.insert(sd, { highCapacity: false });  // a 16 MB card is standard capacity, as in E2E-007
}
let frame = null;                 // the last good frame, RGB888
let fw = 640, fh = 480;           // its size (the e-ink panel's is its own)
let frames = 0, note = 'powering on', started = Date.now();
let keyAt = null;                 // emulated time of the first key not yet shown

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
  #leds { margin-top: 10px; display: flex; gap: 14px; align-items: flex-end; }
  .led { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 11px; color: #888; }
  .led i { width: 16px; height: 16px; border-radius: 50%; background: #2a1a0a; border: 1px solid #444; }
  .led i.on { background: #ffb020; border-color: #ffd070; box-shadow: 0 0 10px #ffb020; }
  #con { display: none; width: 960px; max-width: 100%; margin-top: 12px; }
  #con pre { height: 240px; overflow-y: auto; margin: 0; padding: 6px; background: #000; color: #9c9;
             border: 1px solid #333; white-space: pre-wrap; }
  #con textarea { width: 100%; box-sizing: border-box; margin-top: 4px; background: #181818; color: #ccc;
                  border: 1px solid #333; font: inherit; }
</style></head><body>
<canvas id="c" width="640" height="480" tabindex="0"></canvas>
<div id="leds" title="the main board's GPO LEDs D1-D8 ($f000), bit 7 on the left"></div>
<div id="status">connecting...</div>
<div id="help">click the screen, then type: keys go to the IO card's USB keyboard</div>
<div id="con"><div>the USB console (the system card's second serial port)</div><pre id="cout"></pre>
<textarea id="cin" rows="2" placeholder="type here: Enter sends the line; paste a BASIC program and press Enter"></textarea></div>
<script>
const c = document.getElementById('c'), g = c.getContext('2d');
let img = g.createImageData(640, 480);
const status = document.getElementById('status');
// the GPO LEDs D8..D1 ($f000 bits 7..0), as on the main board
const leds = document.getElementById('leds');
for (let b = 7; b >= 0; b--) leds.insertAdjacentHTML('beforeend', '<span class="led"><i id="led' + b + '"></i>D' + (b + 1) + '</span>');
c.focus();
async function tick() {
  try {
    const s = await (await fetch('/state')).json();
    status.textContent = s.line;
    for (let b = 0; b < 8; b++) document.getElementById('led' + b).className = (s.gpo >> b) & 1 ? 'on' : '';
    if (s.frames !== window.seen) {
      window.seen = s.frames;
      if (c.width !== s.w || c.height !== s.h) {
        c.width = s.w; c.height = s.h;
        img = g.createImageData(s.w, s.h);
        c.style.background = s.eink ? '#fff' : '#000';
      }
      const rgb = new Uint8Array(await (await fetch('/frame')).arrayBuffer());
      if (rgb.length === s.w * s.h * 3) {
        for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
          img.data[j] = rgb[i]; img.data[j + 1] = rgb[i + 1]; img.data[j + 2] = rgb[i + 2]; img.data[j + 3] = 255;
        }
        g.putImageData(img, 0, 0);
      }
    }
  } catch (e) { status.textContent = 'emulator not reachable: ' + e; }
  setTimeout(tick, 100);
}
tick();
// the console pane
const con = document.getElementById('con'), cout = document.getElementById('cout'), cin = document.getElementById('cin');
let conAt = 0;
async function conTick() {
  try {
    const r = await (await fetch('/console?from=' + conAt)).json();
    if (r.on) con.style.display = 'block';
    if (r.text) {
      const end = cout.scrollTop + cout.clientHeight >= cout.scrollHeight - 4;
      cout.textContent += r.text;
      if (end) cout.scrollTop = cout.scrollHeight;
    }
    conAt = r.to;
  } catch (e) {}
  setTimeout(conTick, 200);
}
conTick();
cin.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || e.shiftKey) return;
  e.preventDefault();
  fetch('/console', { method: 'POST', body: cin.value + '\\r' });
  cin.value = '';
});
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
    res.end(JSON.stringify({ line, frames, w: fw, h: fh, eink, gpo: s.gpo }));
  } else if (url.pathname === '/frame') {
    res.writeHead(200, { 'Content-Type': 'application/octet-stream' });
    res.end(frame ?? Buffer.alloc(0));
  } else if (url.pathname === '/console' && req.method === 'POST') {
    // typed into the console pane: to the machine as the PC's bytes
    let body = '';
    req.on('data', (d) => (body += d));
    req.on('end', () => {
      if (consolePane) m.console.write(body);
      res.writeHead(204);
      res.end();
    });
  } else if (url.pathname === '/console') {
    // the console's text from offset `from` (a terminal's CR LF shown as a newline)
    const from = Math.min(Number(url.searchParams.get('from') ?? 0), consoleText.length);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ on: consolePane, text: consoleText.slice(from), to: consoleText.length }));
  } else if (url.pathname === '/key' && req.method === 'POST') {
    keyAt ??= m.ns;
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
  console.log(`CUPC/8 emulator (${native ? 'native' : 'machine.mjs'}, slots: ${kinds.join(', ')}): open http://127.0.0.1:${port}`);
});

// ------------------------------------------------------------- the emulator
m.powerOn();
started = Date.now();
let seq = -1, shot = 0;
for (;;) {
  // capture every `every`, or 5 ms after a key (the echo takes ~2 ms): not at
  // the end of the chunk, which at ~8x slower than real time is seconds away
  await m.runAsync(5e6);
  if (consolePane) {
    // a terminal's rendering, roughly: CR LF a newline, backspace takes a character back
    for (const ch of m.console.read().toString('latin1').replace(/\r\n/g, '\n').replace(/\r/g, '')) {
      consoleText = ch === '\b' ? consoleText.slice(0, -1) : consoleText + ch;
    }
  }
  if (!(keyAt !== null && m.ns - keyAt >= 5e6) && m.ns - shot < every) continue;
  keyAt = null;
  shot = m.ns;
  if (eink) {
    // the panel's glass: it changes when a refresh completes
    const p = m.panel();
    const busy = { 0: '', 4: 'powering on', 2: 'powering off', 18: 'REFRESHING' }[p.busy] ?? `busy $${p.busy.toString(16)}`;
    note = `e-paper ${p.w}x${p.h}: ${p.refreshes[0]} clean, ${p.refreshes[1]} fast, ${p.refreshes[2]} grey, ` +
      `${p.refreshes[3]} partial refreshes ${busy}${p.errors ? `   PANEL ERRORS ${p.errors}: ${p.error}` : ''}`;
    if (p.seq !== seq) {
      seq = p.seq;
      const rgb = Buffer.alloc(p.w * p.h * 3);
      for (let i = 0; i < p.w * p.h; i++) rgb[i * 3] = rgb[i * 3 + 1] = rgb[i * 3 + 2] = p.grey[i];
      fw = p.w;
      fh = p.h;
      frame = rgb;
      frames++;
    }
    continue;
  }
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
