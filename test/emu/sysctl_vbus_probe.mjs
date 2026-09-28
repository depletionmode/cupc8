// Sysctl USB VBUS sense on the routed top, without a host TCP socket.
import { createRequire } from 'node:module';
import path from 'node:path';
import { Machine } from './machinenative.mjs';
import { ROOT } from './romimage.mjs';

const native = createRequire(import.meta.url)(path.join(ROOT, 'build/emu-machine/machine.node'));
const orientation = process.argv.find(arg => arg === 'A' || arg === 'B') ?? 'A';
const hostVbus = !process.argv.includes('--no-host-vbus');
const m = await Machine.create({slots: {}, sysctl: true, hostVbus, hostPort: false,
  usbOrientation: orientation,
  threaded: false, rom: Buffer.alloc(512 * 1024, 0xff)});
try {
  m.powerOn();
  native.runFor(m.h, 20e6);
  // PING: C8, command 00, length 0000, CRC8 00.
  native.cdcWrite(m.h, Buffer.from([0xc8, 0, 0, 0, 0]), 0);
  let reply = Buffer.alloc(0);
  for (let i = 0; i < 1000; i++) {
    native.runFor(m.h, 1e6);
    const chunk = native.cdcRead(m.h, 0);
    if (chunk) reply = Buffer.concat([reply, chunk]);
    if (reply.length >= 5) break;
  }
  console.log(JSON.stringify({orientation, hostVbus, reply: [...reply],
    ping: reply.length >= 5 && reply[0] === 0xc8 && reply[1] === 0,
    state: native.state(m.h)}));
} finally {
  m.stop();
}
