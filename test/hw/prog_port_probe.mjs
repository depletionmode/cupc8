// The card programming port on the netlist-generated top (CUPC8_COSIM_TOP): the
// system card programs the RP2040 cards named by the plan (argv[2], JSON
// [{slot, seed}]) over SWD with cupc8.py's own flash routine, through the
// muxes and the routed copper. Prints the script's output and, per slot with
// an SWD target, the SHA-256 of the first 8 KB of the target's flash and its
// reset count (test_cosim_prog_port.py compares them with the images).
import { Machine } from '../emu/machinenative.mjs';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

const plan = process.argv[2];
const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage', 4: 'eink' }, sysctl: true,
  threaded: false });
try {
  m.powerOn();
  m.runFor(20e6);
  const child = spawn('python3', ['test/hw/prog_port_exercise.py', `tcp:127.0.0.1:${m.sysctlPort}`, plan],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let output = '', code = null;
  child.stdout.on('data', (d) => { output += d; });
  child.stderr.on('data', (d) => { output += d; });
  child.on('exit', (v) => { code = v; });
  await m.runUntil(() => code !== null, 3000e9);
  const targets = {};
  for (let slot = 1; slot <= 6; slot++) {
    const t = m.progTarget(slot);
    targets[slot] = t && { sha: createHash('sha256').update(t.flash.subarray(0, 8192)).digest('hex'), resets: t.resets };
  }
  console.log(JSON.stringify({ code, output: output.trim(), targets, ns: m.ns }));
} finally {
  m.stop();
}
