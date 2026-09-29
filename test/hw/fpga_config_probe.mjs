// The FPGA configuration chain on the native machine (emu/machine/fpgaconfig.h)
// with the netlist-generated top in CUPC8_COSIM_TOP: power on, then run the
// cupc8.py commands given as a JSON list of argument lists (argv[2]), and
// print the machine state after power-on and after each command.
// A command's argument "@FILE" is replaced by a file path written from the
// hex bytes that follow (e.g. "@7eaa997e" writes those four bytes).
import { Machine } from '../emu/machinenative.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const commands = JSON.parse(process.argv[2] ?? '[]');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cupc8-fpga-'));
// CUPC8_PROBE_OPTS: more Machine.create options, as JSON (e.g. {"pwrHi": false})
const extra = JSON.parse(process.env.CUPC8_PROBE_OPTS ?? '{}');
const m = await Machine.create({ slots: {}, sysctl: true, threaded: false, ...extra });
const pick = (s) => ({ pc: s.pc, gpo: s.gpo, nrst: s.nrst, chipsetConfigured: s.chipsetConfigured,
  cpuConfigured: s.cpuConfigured, cdoneLed: s.cdoneLed });
async function command(args) {
  args = args.map((a, i) => {
    if (typeof a !== 'string' || !a.startsWith('@')) return a;
    const file = path.join(dir, `arg${i}.bin`);
    const hex = a.slice(1);
    // "@<hex>*<n>": the hex bytes repeated n times
    const [bytes, times] = hex.split('*');
    fs.writeFileSync(file, Buffer.from(bytes.repeat(Number(times ?? 1)), 'hex'));
    return file;
  });
  const child = spawn('python3', ['tools/cupc8.py', '--port', `tcp:127.0.0.1:${m.sysctlPort}`, ...args],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let output = '', code = null;
  child.stdout.on('data', (d) => { output += d; });
  child.stderr.on('data', (d) => { output += d; });
  child.on('exit', (v) => { code = v; });
  await m.runUntil(() => code !== null, 30e9);
  m.runFor(5e6);
  return { args: args.map(String), code, output: output.trim(), state: pick(m.state()) };
}
try {
  m.powerOn();
  m.runFor(20e6);
  const result = { boot: pick(m.state()), commands: [] };
  for (const args of commands) result.commands.push(await command(args));
  console.log(JSON.stringify(result));
} finally {
  m.stop();
  fs.rmSync(dir, { recursive: true, force: true });
}
