// Read the chipset's real trace flags after firmware executes CPU cycles.
import { Machine } from './machinenative.mjs';
import { spawn } from 'node:child_process';

const machine = await Machine.create({ slots: {}, sysctl: true, threaded: false });
try {
  machine.powerOn();
  machine.runFor(20e6);
  const state = machine.state();
  const command = spawn('python3', ['tools/cupc8.py', '--port',
    `tcp:127.0.0.1:${machine.sysctlPort}`, 'trace'],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let exitCode = null;
  let stdout = '', stderr = '';
  command.stdout.on('data', data => { stdout += data; });
  command.stderr.on('data', data => { stderr += data; });
  command.on('exit', code => { exitCode = code; });
  const finished = await machine.runUntil(() => exitCode !== null, 200e6, 0.2e6);
  const entries = stdout.split('\n').filter(line => /^[0-9a-f]{4} [RW] [0-9a-f]{2}/.test(line));
  const syncEntries = entries.filter(line => line.endsWith(' sync'));
  console.log(JSON.stringify({ state, finished, exitCode, entries: entries.length,
    syncEntries: syncEntries.length, stderr }));
} finally {
  machine.stop();
}
