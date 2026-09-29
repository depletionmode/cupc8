// The rail indicator LEDs of a netlist-generated machine (CUPC8_COSIM_TOP):
// Machine.powerLeds() for a machine with the system card and four slot cards
// (the Wi-Fi card, which needs QEMU, is checked in the manifest only).
import { Machine } from '../emu/machinenative.mjs';

const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage', 4: 'eink' }, sysctl: true,
  threaded: false });
try {
  console.log(JSON.stringify(m.powerLeds()));
} finally {
  m.stop();
}
