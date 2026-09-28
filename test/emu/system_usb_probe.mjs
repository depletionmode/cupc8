// Prove the system card stays alive while its routed Type-C CDC host path is gated.
import { spawn } from 'node:child_process';
import { Machine } from './machinenative.mjs';

const orientation = process.argv[2];
if (!['A', 'B'].includes(orientation)) throw new Error('expected Type-C orientation A or B');
const machine = await Machine.create({ slots: {}, sysctl: true,
  usbOrientation: orientation, threaded: false });
try {
  machine.powerOn();
  machine.runFor(20e6);
  const port = Number.isInteger(machine.sysctlPort);
  let finished = false, exitCode = null, stdout = '';
  if (port) {
    const command = spawn('python3', ['tools/cupc8.py', '--port',
      `tcp:127.0.0.1:${machine.sysctlPort}`, 'ping'],
      { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
    command.stdout.on('data', data => { stdout += data; });
    command.on('exit', code => { exitCode = code; });
    finished = await machine.runUntil(() => exitCode !== null, 1e9, 0.2e6);
  }
  console.log(JSON.stringify({ orientation, port, finished, exitCode,
    ping: stdout.startsWith('CUPC8 sysctl'), state: machine.state() }));
} finally {
  machine.stop();
}
