import { Machine } from '../emu/machinenative.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const withSysctl = process.env.CUPC8_SUBSET_SYSCTL !== '0';
const m = await Machine.create({ slots: {}, sysctl: withSysctl, threaded: false,
  rom: fs.readFileSync(process.env.CUPC8_SUBSET_ROM) });
async function command(...args) {
  const child = spawn('python3', ['tools/cupc8.py', '--port',
    `tcp:127.0.0.1:${m.sysctlPort}`, ...args],
  { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let output = '', code = null;
  child.stdout.on('data', data => output += data);
  child.stderr.on('data', data => output += data);
  child.on('exit', value => code = value);
  await m.runUntil(() => code !== null, 2e9);
  return { code, output };
}
try {
  m.powerOn();
  m.runFor(20e6);
  const boot = m.state();
  const ping = withSysctl ? await command('ping') : null;
  const status = withSysctl ? await command('status') : null;
  console.log(JSON.stringify({ boot: { pc: boot.pc, gpo: boot.gpo,
    nrst: boot.nrst, halted: boot.halted }, ping, status }));
} finally {
  m.stop();
}
