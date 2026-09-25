// The PC's side of a composite USB device with CDC serial ports, on the
// emulated RP2040's device controller (rp2040js's RPUSBController): rp2040js's
// USBCDC (src/usb/cdc.ts), which knows one port, grown to every CDC function
// the configuration descriptor has. The system card has two (the sysctl
// protocol and the console, doc/proposals/usb-console.md).
//
// Enumeration is USBCDC's, step for step: address 1, the configuration
// descriptor (9 bytes, then all of it), configuration 1, then DTR|RTS on
// port 0's communication interface and onDeviceConnected. After that, a
// control request (setLines) waits for the previous one's status stage.
// Port p: its data comes to ports[p].onSerialData; sendSerialByte(b, p)
// queues bytes for it (512-byte FIFO each, as USBCDC's).
//
// The C++ port (emu/rp2040/src/usb/cdchost.cpp) behaves identically: the
// system card tests (SYS-006) compare the two (EMU-006).

import path from 'node:path';
import { SDK } from './rp2040emu.mjs';

const rp = await import(path.join(SDK, 'rp2040js/dist/esm/index.js'));
const { FIFO } = await import(path.join(SDK, 'rp2040js/dist/esm/utils/fifo.js'));

const CDC_REQUEST_SET_CONTROL_LINE_STATE = 0x22;
const CDC_DTR = 1, CDC_RTS = 2;
const CDC_COMM_CLASS = 2, CDC_DATA_CLASS = 10;
const ENDPOINT_BULK = 2;
const CONFIGURATION_DESCRIPTOR_SIZE = 9;

// [{ comm, in, out }] per CDC function, in descriptor order: a data interface
// with two bulk endpoints after its communication interface
export function extractPorts(d) {
  const ports = [];
  let comm = -1, data = null;
  for (let i = 0; i < d.length;) {
    const len = d[i];
    if (len < 2 || d.length < i + len) break;
    const type = d[i + 1];
    if (type === rp.DescriptorType.Interface && len === 9) {
      data = null;
      if (d[i + 5] === CDC_COMM_CLASS) comm = d[i + 2];
      else if (d[i + 5] === CDC_DATA_CLASS && d[i + 4] === 2) {
        data = { comm, in: -1, out: -1 };
        ports.push(data);
      }
    }
    if (data && type === rp.DescriptorType.Endpoint && len === 7 && (d[i + 3] & 3) === ENDPOINT_BULK) {
      if (d[i + 2] & 0x80) data.in = d[i + 2] & 0xf;
      else data.out = d[i + 2] & 0xf;
    }
    i += len;
  }
  return ports;
}

export class CdcHost {
  constructor(usb, nports = 2) {
    this.usb = usb;
    this.ports = Array.from({ length: nports }, () => ({ txFIFO: new FIFO(512), onSerialData: null, comm: -1, in: -1, out: -1 }));
    this.initialized = false;
    this.descriptorsSize = null;
    this.descriptors = [];
    this.pending = [];          // control requests waiting for the one in progress
    this.busy = false;
    this.onDeviceConnected = null;
    usb.onUSBEnabled = () => usb.resetDevice();
    usb.onResetReceived = () => usb.sendSetupPacket(rp.setDeviceAddressPacket(1));
    usb.onEndpointWrite = (ep, buf) => {
      if (ep === 0 && buf.length === 0) {
        if (this.descriptorsSize == null) {
          usb.sendSetupPacket(rp.getDescriptorPacket(rp.DescriptorType.Configration, CONFIGURATION_DESCRIPTOR_SIZE));
        } else if (!this.initialized) {
          // configured: port 0 opens, as USBCDC's one port does
          this.initialized = true;
          this.busy = false;
          this.setLines(0, CDC_DTR | CDC_RTS);
          this.onDeviceConnected?.();
        } else {
          // a control request's status stage: the next may go
          this.busy = false;
          this.next();
        }
      }
      if (ep === 0 && buf.length > 1) {
        if (buf.length === CONFIGURATION_DESCRIPTOR_SIZE && buf[1] === rp.DescriptorType.Configration &&
            this.descriptorsSize == null) {
          this.descriptorsSize = (buf[3] << 8) | buf[2];
          usb.sendSetupPacket(rp.getDescriptorPacket(rp.DescriptorType.Configration, this.descriptorsSize));
        } else if (this.descriptorsSize != null && this.descriptors.length < this.descriptorsSize) {
          this.descriptors.push(...buf);
        }
        if (this.descriptorsSize === this.descriptors.length) {
          extractPorts(this.descriptors).slice(0, this.ports.length).forEach((f, i) => Object.assign(this.ports[i], f));
          usb.sendSetupPacket(rp.setDeviceConfigurationPacket(1));
        }
      }
      if (ep !== 0) {
        const p = this.ports.find((q) => q.in === ep);
        p?.onSerialData?.(buf);
      }
    };
    usb.onEndpointRead = (ep, size) => {
      const p = this.ports.find((q) => q.out === ep);
      if (!p) return;
      const b = new Uint8Array(Math.min(size, p.txFIFO.itemCount));
      for (let i = 0; i < b.length; i++) b[i] = p.txFIFO.pull();
      usb.endpointReadDone(ep, b);
    };
  }

  // the number of CDC functions the device has (known once configured)
  get portCount() {
    return this.ports.filter((p) => p.in >= 0).length;
  }

  // SET_CONTROL_LINE_STATE on port p's communication interface: DTR is
  // "a terminal has the port open"
  setLines(p, value) {
    this.pending.push([p, value]);
    this.next();
  }

  open(p, on) {
    this.setLines(p, on ? CDC_DTR | CDC_RTS : 0);
  }

  next() {
    if (this.busy || !this.initialized || !this.pending.length) return;
    this.busy = true;
    const [p, value] = this.pending.shift();
    this.usb.sendSetupPacket(rp.createSetupPacket({
      dataDirection: rp.DataDirection.HostToDevice, type: rp.SetupType.Class, recipient: rp.SetupRecipient.Interface,
      bRequest: CDC_REQUEST_SET_CONTROL_LINE_STATE, wValue: value, wIndex: this.ports[p].comm, wLength: 0,
    }));
  }

  sendSerialByte(b, p = 0) {
    this.ports[p].txFIFO.push(b);
  }
}
