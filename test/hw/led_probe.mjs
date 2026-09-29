// The cards' firmware-driven indicator LEDs on the native machine with the
// netlist-generated top (CUPC8_COSIM_TOP): Machine.leds() after real use.
// A: HDMI, IO, storage (a FAT microSD) and the system card: the BASIC
//    prompt, DIR (storage ACT/CARD), a typed line (IO KEY/KBD), cupc8.py
//    ping (system USB TX/RX). B: the e-ink card as the display (REFRESH).
// Prints {net: {lit, rises}} per card kind.
import { Machine } from '../emu/machinenative.mjs';
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const SDK = process.env.CUPC8_SDK ?? path.join(os.homedir(), '.local/share/cupc8-sdk');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-leds-'));
const img = path.join(dir, 'card.img');
execFileSync(path.join(SDK, 'pyfat/bin/python'), [path.join(ROOT, 'test/emu/fatimg.py'), 'mkfs', img, '16', '16']);

const text = (m) => { const s = m.screen(); return s.error ? '' : s.text.join('\n').replace(/\n+$/, ''); };
const result = {};
function collect(m) {
  for (const l of m.leds()) {
    result[l.kind] ??= {};
    const r = result[l.kind][l.net ?? `GPIO${l.gpio}`] ??= { lit: false, rises: 0 };
    r.lit ||= l.lit;
    r.rises += l.rises;
  }
}
async function prompt(m, ns = 8e9) {
  return m.runUntil(() => text(m).includes('>>'), ns, 100e6);
}

try {
  let m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage' }, sysctl: true, threaded: false });
  m.sd.insert(img, { highCapacity: false });
  m.powerOn();
  result.promptA = await prompt(m);
  m.type('dir\n');
  await m.runAsync(1500e6);
  const child = spawn('python3', ['tools/cupc8.py', '--port', `tcp:127.0.0.1:${m.sysctlPort}`, 'ping'],
    { cwd: ROOT, env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let code = null;
  child.on('exit', (v) => { code = v; });
  await m.runUntil(() => code !== null, 5e9);
  result.ping = code;
  collect(m);
  m.stop();

  m = await Machine.create({ slots: { 1: 'eink', 2: 'io' }, threaded: false });
  m.powerOn();
  await m.runAsync(4e9);
  collect(m);
  m.stop();
  console.log(JSON.stringify(result));
} finally {
  fs.rmSync(dir, { recursive: true, force: true });
}
