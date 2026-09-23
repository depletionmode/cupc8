// A USB HID boot keyboard for the emulated RP2040's host port (the patched
// rp2040js USBHostController): control transfers on EP0, reports on EP1 IN.
// It records what the host did to it (address, configuration, protocol,
// LED output reports) so tests can check the card drove it correctly.

const BOOT_KEYBOARD_REPORT = [
  0x05, 0x01, 0x09, 0x06, 0xa1, 0x01, 0x05, 0x07, 0x19, 0xe0, 0x29, 0xe7, 0x15, 0x00, 0x25, 0x01,
  0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01, 0x75, 0x08, 0x81, 0x01, 0x95, 0x05, 0x75, 0x01,
  0x05, 0x08, 0x19, 0x01, 0x29, 0x05, 0x91, 0x02, 0x95, 0x01, 0x75, 0x03, 0x91, 0x01, 0x95, 0x06,
  0x75, 0x08, 0x15, 0x00, 0x25, 0x65, 0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xc0,
];

export class UsbKeyboard {
  // speed 1 = low speed (most keyboards; 8-byte EP0), 2 = full speed
  constructor({ speed = 1, interval = 10 } = {}) {
    this.speed = speed;
    this.mps0 = speed === 1 ? 8 : 64;
    this.device = [18, 1, 0x10, 0x01, 0, 0, 0, this.mps0, 0x09, 0x12, 0x01, 0x00, 0x00, 0x01, 0, 0, 0, 1];
    const report = BOOT_KEYBOARD_REPORT;
    this.reportDesc = report;
    this.config = [
      9, 2, 34, 0, 1, 1, 0, 0xa0, 50,
      9, 4, 0, 0, 1, 3, 1, 1, 0,                               // HID, boot, keyboard
      9, 0x21, 0x11, 0x01, 0, 1, 0x22, report.length, 0,
      7, 5, 0x81, 3, 8, 0, interval,
    ];
    this.busReset();
    this.leds = [];          // every LED output report, in order
    this.protocol = 1;       // 1 report, 0 boot
    this.reports = [];
    this.log = [];
  }

  busReset() {
    this.addr = 0;
    this.pendingAddr = null;
    this.configured = 0;
    this.ctrl = null;
  }

  // queue HID boot reports: [mods, 0, k1..k6]
  press(mods, ...keys) {
    const r = [mods, 0, ...keys, 0, 0, 0, 0, 0, 0].slice(0, 8);
    this.reports.push(Uint8Array.from(r));
  }

  setup(addr, p) {
    if (addr !== this.addr) return 'ack';               // not us: nothing answers
    const type = p[0], req = p[1], value = p[2] | (p[3] << 8), length = p[6] | (p[7] << 8);
    this.log.push({ type, req, value, length });
    const reply = (bytes) => ({ in: Uint8Array.from(bytes.slice(0, length)), pos: 0 });
    this.ctrl = null;
    if (type === 0x80 && req === 6) {                     // GET_DESCRIPTOR
      const kind = value >> 8;
      if (kind === 1) this.ctrl = reply(this.device);
      else if (kind === 2) this.ctrl = reply(this.config);
      else return 'stall';                              // no strings
    } else if (type === 0x81 && req === 6 && value >> 8 === 0x22) {
      this.ctrl = reply(this.reportDesc);
    } else if (type === 0x00 && req === 5) {              // SET_ADDRESS (after status)
      this.ctrl = { status: () => (this.addr = value & 0x7f) };
    } else if (type === 0x00 && req === 9) {              // SET_CONFIGURATION
      this.ctrl = { status: () => (this.configured = value) };
    } else if (type === 0x21 && req === 0x0a) {           // SET_IDLE
      this.ctrl = { status: () => {} };
    } else if (type === 0x21 && req === 0x0b) {           // SET_PROTOCOL
      this.ctrl = { status: () => (this.protocol = value) };
    } else if (type === 0x21 && req === 0x09) {           // SET_REPORT: the LEDs
      const c = { out: [], length };
      c.status = () => this.leds.push(c.out[0]);
      this.ctrl = c;
    } else {
      return 'stall';
    }
    return 'ack';
  }

  in(addr, ep, maxLen) {
    if (addr !== this.addr) return 'nak';
    if (ep === 0) {
      const c = this.ctrl;
      if (!c) return 'stall';
      if (c.in) {
        const chunk = c.in.subarray(c.pos, c.pos + Math.min(this.mps0, maxLen));
        c.pos += chunk.length;
        return chunk;
      }
      // status stage of a no-data or OUT-data request
      const status = c.status;
      this.ctrl = null;
      status();
      return new Uint8Array(0);
    }
    if (ep === 1 && this.configured) return this.reports.shift() ?? 'nak';
    return 'stall';
  }

  out(addr, ep, data) {
    if (addr !== this.addr || ep !== 0 || !this.ctrl) return 'stall';
    if (this.ctrl.out && this.ctrl.out.length < this.ctrl.length) {
      this.ctrl.out.push(...data);                        // data stage
      return 'ack';
    }
    this.ctrl = null;                                     // status stage after IN data
    return 'ack';
  }
}
