// Hold the main-board reset switch during startup; report the chipset state.
import { Machine } from './machinenative.mjs';

const machine = await Machine.create({ slots: {}, sysctl: false,
  resetButtonPressed: true, threaded: false });
try {
  machine.powerOn();
  machine.runFor(20e6);
  console.log(JSON.stringify(machine.state()));
} finally {
  machine.stop();
}
