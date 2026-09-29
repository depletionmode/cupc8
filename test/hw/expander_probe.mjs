// sysctl's I2C expanders on the netlist-generated top (CUPC8_COSIM_TOP): the
// pin levels the model presents for a machine with the system card and the
// cards in slots 1, 2, 3 and 5 (the Wi-Fi card, which needs QEMU, is not
// fitted). Prints {u14: [port0, port1], u13: [port0, port1]}.
import { Machine } from '../emu/machinenative.mjs';

const m = await Machine.create({ slots: { 1: 'hdmi', 2: 'io', 3: 'storage', 5: 'eink' }, sysctl: true,
  threaded: false });
try {
  m.powerOn();
  m.runFor(20e6);
  const pins = Object.fromEntries(m.expanders().map((x) => [x.address === 0x21 ? 'u14' : 'u13', x.pins]));
  console.log(JSON.stringify(pins));
} finally {
  m.stop();
}
