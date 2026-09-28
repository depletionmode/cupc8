// Observe the system card's GPIO23 pulse at the main chipset reset input.
import { Machine } from './machinenative.mjs';
import { spawn } from 'node:child_process';

const machine = await Machine.create({ slots: {}, sysctl: true, threaded: false });
try {
  machine.powerOn();
  machine.runFor(20e6);
  const before = machine.state();
  const command = spawn('python3', ['tools/cupc8.py', '--port',
    `tcp:127.0.0.1:${machine.sysctlPort}`, 'reset'],
    { env: { ...process.env, CUPC8_TIMEOUT_SCALE: '300' } });
  let exitCode = null;
  let stderr = '';
  command.stderr.on('data', data => { stderr += data; });
  command.on('exit', code => { exitCode = code; });
  let duringReset = null;
  const finished = await machine.runUntil(() => {
    if (!duringReset && machine.state().nrst === 0) duringReset = machine.state();
    return exitCode !== null;
  }, 200e6, 0.2e6);
  console.log(JSON.stringify({ before, duringReset, after: machine.state(),
    finished, exitCode, stderr }));
} finally {
  machine.stop();
}
