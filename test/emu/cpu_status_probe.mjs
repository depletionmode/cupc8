// Run a tiny HALT or STI; WAI ROM and read the real bridge status register.
import { Machine } from './machinenative.mjs';
import { kernelRom } from './romimage.mjs';
import { spawn } from 'node:child_process';

const mode = process.argv[2];
if (!['halted', 'waiting'].includes(mode)) throw new Error('expected halted or waiting');
const rom = kernelRom();
if (mode === 'halted') rom[0] = 0xf8;
else { rom[0] = 0xc8; rom[1] = 0xf0; }
const machine = await Machine.create({ slots: {}, sysctl: true, rom, threaded: false });
try {
  machine.powerOn();
  machine.runFor(20e6);
  const state = machine.state();
  const command = spawn('python3', ['tools/cupc8.py', '--port',
    `tcp:127.0.0.1:${machine.sysctlPort}`, 'status'],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let exitCode = null;
  let stdout = '', stderr = '';
  command.stdout.on('data', data => { stdout += data; });
  command.stderr.on('data', data => { stderr += data; });
  command.on('exit', code => { exitCode = code; });
  const finished = await machine.runUntil(() => exitCode !== null, 100e6, 0.2e6);
  const match = /bridge status \$([0-9a-f]+)/i.exec(stdout);
  console.log(JSON.stringify({ mode, state, finished, exitCode,
    bridgeStatus: match ? parseInt(match[1], 16) : null, stderr }));
} finally {
  machine.stop();
}
