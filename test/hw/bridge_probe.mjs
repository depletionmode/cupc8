// MB-052: the netlist-generated main board (CUPC8_COSIM_TOP) with the system
// card: boot, then test/hw/bridge_exercise.py drives BRG-001/002 through
// sysctl, restores the kernel (CUPC8_SUBSET_ROM) and resets the machine; the
// CPU card model must boot again from the reprogrammed ROM.
import { Machine } from '../emu/machinenative.mjs';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const rom = process.env.CUPC8_SUBSET_ROM;
const m = await Machine.create({ slots: {}, sysctl: true, threaded: false, rom: fs.readFileSync(rom) });
const pick = (s) => ({ pc: s.pc, gpo: s.gpo, nrst: s.nrst, halted: Boolean(s.halted) });
try {
  m.powerOn();
  m.runFor(20e6);
  const boot = pick(m.state());
  const child = spawn('python3', ['test/hw/bridge_exercise.py', `tcp:127.0.0.1:${m.sysctlPort}`, rom],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let output = '', code = null;
  child.stdout.on('data', (d) => { output += d; process.stderr.write(d); });
  child.stderr.on('data', (d) => { output += d; process.stderr.write(d); });
  child.on('exit', (v) => { code = v; });
  await m.runUntil(() => code !== null, 1200e9);
  m.runFor(20e6);
  console.log(JSON.stringify({ boot, code, output: output.trim(), after: pick(m.state()) }));
} finally {
  m.stop();
}
