// WIFI-006: Machine.create({ forward }) on the native emulator hands QEMU its
// hostfwd entries: the Wi-Fi card's QEMU holds the forwarded host ports (a
// TCP connect is accepted, the UDP port is taken), and bad entries are
// refused before QEMU starts. What arrives through a forward is WIFI-003's
// (test_wifi_qemu.py, the same -nic line) and the kernel's E2E tests'.
//
//   tools/fw_esp32c3.sh qemu && tools/emu_machine_build.sh && node test/emu/test_wifi_forward.mjs

import dgram from 'node:dgram';
import net from 'node:net';
import { Machine } from './machinenative.mjs';

let checks = 0, bad = 0;
function expect(cond, what) {
  checks++;
  if (!cond) {
    bad++;
    console.log('FAIL', what);
  }
}

async function freePort() {
  const s = net.createServer();
  await new Promise((r) => s.listen(0, '127.0.0.1', r));
  const port = s.address().port;
  await new Promise((r) => s.close(r));
  return port;
}

async function refused(opts, what) {
  try {
    const m = await Machine.create(opts);
    m.stop();
    expect(false, what);
  } catch {
    expect(true, what);
  }
}

await refused({ slots: { 1: 'hdmi', 2: 'wifi' }, forward: ['tcp:8080'] }, "'tcp:8080' is refused");
await refused({ slots: { 1: 'hdmi', 2: 'wifi' }, forward: ['icmp:1:2'] }, "'icmp:1:2' is refused");
await refused({ slots: { 1: 'hdmi', 2: 'io' }, forward: ['tcp:8080:80'] }, 'a forward with no Wi-Fi card is refused');

const tcpPort = await freePort(), udpPort = await freePort();
const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'wifi' },
  forward: [`tcp:${tcpPort}:80`, `udp:${udpPort}:53`] });
try {
  // QEMU opens the forwards as it starts: give it a moment
  let connected = false;
  for (let i = 0; i < 50 && !connected; i++) {
    connected = await new Promise((resolve) => {
      const c = net.connect(tcpPort, '127.0.0.1', () => { c.destroy(); resolve(true); });
      c.on('error', () => resolve(false));
    });
    if (!connected) await new Promise((r) => setTimeout(r, 100));
  }
  expect(connected, `QEMU accepts TCP on the forwarded 127.0.0.1:${tcpPort}`);
  const taken = await new Promise((resolve) => {
    const u = dgram.createSocket('udp4');
    u.on('error', () => { u.close(); resolve(true); });
    u.bind(udpPort, '127.0.0.1', () => { u.close(); resolve(false); });
  });
  expect(taken, `QEMU holds the forwarded UDP port ${udpPort}`);
} finally {
  m.stop();
}

console.log(`WIFI-006: port forwards to the Wi-Fi card's QEMU, ${checks} checks, ${bad} failures`);
process.exit(bad ? 1 : 0);
