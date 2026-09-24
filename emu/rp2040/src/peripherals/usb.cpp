// Port of rp2040js src/peripherals/usb.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "usb.h"

#include <utility>
#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

USBEndpointAlarm::USBEndpointAlarm(std::unique_ptr<IAlarm> alarm) : alarm(std::move(alarm)) {
  // TODO(port): peripherals/usb.ts
  //   constructor(readonly alarm: IAlarm) {}
}

void USBEndpointAlarm::schedule(std::vector<uint8_t> buffer, double delayNanos) {
  // TODO(port): peripherals/usb.ts
  //   schedule(buffer: Uint8Array, delayNanos: number) {
  //     this.buffers.push(buffer);
  //     this.alarm.schedule(delayNanos);
  //   }
  (void)buffer;
  (void)delayNanos;
}

RPUSBController::RPUSBController(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {
  // TODO(port): peripherals/usb.ts
  //   constructor(rp2040: RP2040, name: string) {
  //     super(rp2040, name);
  //     // eslint-disable-next-line @typescript-eslint/no-this-alias
  //     const ctl = this;
  //     this.host = new USBHostController(rp2040, {
  //       get addrEndp() {
  //         return ctl.addrEndp;
  //       },
  //       get sieStatus() {
  //         return ctl.sieStatus;
  //       },
  //       set sieStatus(v: number) {
  //         ctl.sieStatus = v;
  //       },
  //       get buffStatus() {
  //         return ctl.buffStatus;
  //       },
  //       set buffStatus(v: number) {
  //         ctl.buffStatus = v;
  //       },
  //       update() {
  //         ctl.checkInterrupts();
  //       },
  //     });
  //     const clock = rp2040.clock;
  //     this.endpointReadAlarms = [];
  //     this.endpointWriteAlarms = [];
  //     for (let i = 0; i < ENDPOINT_COUNT; ++i) {
  //       this.endpointReadAlarms.push(
  //         new USBEndpointAlarm(
  //           clock.createAlarm(() => {
  //             const buffer = this.endpointReadAlarms[i].buffers.shift();
  //             if (buffer) {
  //               this.finishRead(i, buffer);
  //             }
  //           }),
  //         ),
  //       );
  //       this.endpointWriteAlarms.push(
  //         new USBEndpointAlarm(
  //           clock.createAlarm(() => {
  //             for (const buffer of this.endpointWriteAlarms[i].buffers) {
  //               this.onEndpointWrite?.(i, buffer);
  //             }
  //             this.endpointWriteAlarms[i].buffers = [];
  //           }),
  //         ),
  //       );
  //     }
  //     this.resetAlarm = clock.createAlarm(() => {
  //       this.sieStatus |= SIE_BUS_RESET;
  //       this.sieStatusUpdated();
  //     });
  //   }
}

bool RPUSBController::isHost() const {
  // TODO(port): peripherals/usb.ts
  //   get isHost() {
  //     return !!(this.mainCtrl & HOST_NDEVICE);
  //   }
  return false;
}

uint32_t RPUSBController::intStatus() const {
  // TODO(port): peripherals/usb.ts
  //   get intStatus() {
  //     const raw = this.isHost ? this.host.intRaw : this.intRaw;
  //     return (raw & this.intEnable) | this.intForce;
  //   }
  return 0;
}

void RPUSBController::attachDevice(USBHostDevice *device) {
  // TODO(port): peripherals/usb.ts
  //   attachDevice(device: USBHostDevice) {
  //     this.host.attach(device);
  //   }
  (void)device;
}

void RPUSBController::detachDevice() {
  // TODO(port): peripherals/usb.ts
  //   detachDevice() {
  //     this.host.detach();
  //   }
}

uint32_t RPUSBController::readUint32(uint32_t offset) {
  // TODO(port): peripherals/usb.ts
  //   readUint32(offset: number) {
  //     if (offset >= 0x04 && offset <= 0x3c) {
  //       return this.host.intEpAddr[(offset >> 2) - 1];
  //     }
  //     switch (offset) {
  //       case SOF_RD:
  //         return this.host.sofNumber;
  //       case SIE_CTRL:
  //         return this.sieCtrl;
  //       case INT_EP_CTRL:
  //         return this.host.intEpCtrl;
  //       case USB_PWR:
  //         return this.usbPwr;
  //       case ADDR_ENDP:
  //         return this.addrEndp & 0b1111000000001111111;
  //       case MAIN_CTRL:
  //         return this.mainCtrl;
  //       case SIE_STATUS:
  //         return this.sieStatus;
  //       case BUFF_STATUS:
  //         return this.buffStatus;
  //       case BUFF_CPU_SHOULD_HANDLE:
  //         return 0;
  //       case INTR:
  //         return this.intRaw;
  //       case INTE:
  //         return this.intEnable;
  //       case INTF:
  //         return this.intForce;
  //       case INTS:
  //         return this.intStatus;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/usb.ts", "RPUSBController::readUint32");
}

void RPUSBController::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/usb.ts
  //   writeUint32(offset: number, value: number) {
  //     if (offset >= 0x04 && offset <= 0x3c) {
  //       this.host.intEpAddr[(offset >> 2) - 1] = value;
  //       return;
  //     }
  //     switch (offset) {
  //       case SIE_CTRL:
  //         this.sieCtrl = this.isHost ? this.host.sieCtrlWritten(value) : value;
  //         break;
  //       case INT_EP_CTRL:
  //         this.host.intEpCtrl = value & 0xfffe;
  //         break;
  //       case USB_PWR:
  //         this.usbPwr = value;
  //         break;
  //       case ADDR_ENDP:
  //         this.addrEndp = value;
  //         break;
  //       case MAIN_CTRL:
  //         this.mainCtrl = value & (SIM_TIMING | CONTROLLER_EN | HOST_NDEVICE);
  //         if (value & CONTROLLER_EN && !(value & HOST_NDEVICE)) {
  //           this.onUSBEnabled?.();
  //         }
  //         break;
  //       case BUFF_STATUS:
  //         this.buffStatus &= ~this.rawWriteValue;
  //         this.buffStatusUpdated();
  //         break;
  //       case USB_MUXING:
  //         // Workaround for busy wait in hw_enumeration_fix_force_ls_j() / hw_enumeration_fix_finish():
  //         if (value & TO_DIGITAL_PAD && !(value & TO_PHY)) {
  //           this.sieStatus |= SIE_CONNECTED;
  //         }
  //         break;
  //       case SIE_STATUS:
  //         if (this.isHost) {
  //           // writing the SPEED bits acknowledges a connect/disconnect
  //           if (this.rawWriteValue & SIE_STATUS_SPEED_MASK) {
  //             this.host.connChanged = false;
  //           }
  //           this.sieStatus &= ~(this.rawWriteValue & SIE_WRITECLEAR_MASK & ~SIE_CONNECTED);
  //           this.checkInterrupts();
  //           break;
  //         }
  //         this.sieStatus &= ~(this.rawWriteValue & SIE_WRITECLEAR_MASK);
  //         if (this.rawWriteValue & SIE_BUS_RESET) {
  //           this.onResetReceived?.();
  //           this.sieStatus &= ~(SIE_LINE_STATE_MASK << SIE_LINE_STATE_SHIFT);
  //           this.sieStatus |= (SIELineState.J << SIE_LINE_STATE_SHIFT) | SIE_CONNECTED;
  //         }
  //         this.sieStatusUpdated();
  //         break;
  //       case INTE:
  //         this.intEnable = value & 0xfffff;
  //         this.checkInterrupts();
  //         break;
  //       case INTF:
  //         this.intForce = value & 0xfffff;
  //         this.checkInterrupts();
  //         break;
  //
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/usb.ts", "RPUSBController::writeUint32");
}

uint32_t RPUSBController::readEndpointControlReg(uint32_t endpoint, bool out) {
  // TODO(port): peripherals/usb.ts
  //   private readEndpointControlReg(endpoint: number, out: boolean) {
  //     const controlRegOffset = EP1_IN_CONTROL + 8 * (endpoint - 1) + (out ? 4 : 0);
  //     return this.rp2040.usbDPRAMView.getUint32(controlRegOffset, true);
  //   }
  (void)endpoint;
  (void)out;
  return 0;
}

uint32_t RPUSBController::getEndpointBufferOffset(uint32_t endpoint, bool out) {
  // TODO(port): peripherals/usb.ts
  //   private getEndpointBufferOffset(endpoint: number, out: boolean) {
  //     if (endpoint === 0) {
  //       return 0x100;
  //     }
  //     return this.readEndpointControlReg(endpoint, out) & 0xffc0;
  //   }
  (void)endpoint;
  (void)out;
  return 0;
}

void RPUSBController::DPRAMUpdated(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/usb.ts
  //   DPRAMUpdated(offset: number, value: number) {
  //     if (this.isHost) {
  //       this.host.dpramWritten(offset);
  //       return;
  //     }
  //     if (
  //       value & USB_BUF_CTRL_AVAILABLE &&
  //       offset >= EP0_IN_BUFFER_CONTROL &&
  //       offset <= EP15_OUT_BUFFER_CONTROL
  //     ) {
  //       const endpoint = (offset - EP0_IN_BUFFER_CONTROL) >> 3;
  //       const bufferOut = offset & 4 ? true : false;
  //       let doubleBuffer = false;
  //       let interrupt = true;
  //       if (endpoint != 0) {
  //         const control = this.readEndpointControlReg(endpoint, bufferOut);
  //         doubleBuffer = !!(control & USB_CTRL_DOUBLE_BUF);
  //         interrupt = !!(control & USB_CTRL_INTERRUPT_PER_TRANSFER);
  //       }
  //
  //       if (doubleBuffer && (value >> USB_BUF1_SHIFT) & USB_BUF_CTRL_AVAILABLE) {
  //         const bufferLength = (value >> USB_BUF1_SHIFT) & USB_BUF_CTRL_LEN_MASK;
  //         const bufferOffset = this.getEndpointBufferOffset(endpoint, bufferOut) + USB_BUF1_OFFSET;
  //         this.debug(
  //           `Start USB transfer, endPoint=${endpoint}, direction=${
  //             bufferOut ? 'out' : 'in'
  //           } buffer=${bufferOffset.toString(16)} length=${bufferLength}`,
  //         );
  //         value &= ~(USB_BUF_CTRL_AVAILABLE << USB_BUF1_SHIFT);
  //         this.rp2040.usbDPRAMView.setUint32(offset, value, true);
  //         if (bufferOut) {
  //           this.onEndpointRead?.(endpoint, bufferLength);
  //         } else {
  //           value &= ~(USB_BUF_CTRL_FULL << USB_BUF1_SHIFT);
  //           this.rp2040.usbDPRAMView.setUint32(offset, value, true);
  //           const buffer = this.rp2040.usbDPRAM.slice(bufferOffset, bufferOffset + bufferLength);
  //           this.indicateBufferReady(endpoint, false);
  //           this.endpointWriteAlarms[endpoint].schedule(buffer, this.writeDelayMicroseconds * 1000);
  //         }
  //       }
  //
  //       const bufferLength = value & USB_BUF_CTRL_LEN_MASK;
  //       const bufferOffset = this.getEndpointBufferOffset(endpoint, bufferOut);
  //       this.debug(
  //         `Start USB transfer, endPoint=${endpoint}, direction=${
  //           bufferOut ? 'out' : 'in'
  //         } buffer=${bufferOffset.toString(16)} length=${bufferLength}`,
  //       );
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/usb.ts", "RPUSBController::DPRAMUpdated");
}

void RPUSBController::endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer) {
  // TODO(port): peripherals/usb.ts
  //   endpointReadDone(endpoint: number, buffer: Uint8Array, delay = this.readDelayMicroseconds) {
  //     this.endpointReadAlarms[endpoint].schedule(buffer, delay * 1000);
  //   }
  endpointReadDone(endpoint, std::move(buffer), readDelayMicroseconds);
}

void RPUSBController::endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer, double delay) {
  // TODO(port): peripherals/usb.ts
  //   endpointReadDone(endpoint: number, buffer: Uint8Array, delay = this.readDelayMicroseconds) {
  //     this.endpointReadAlarms[endpoint].schedule(buffer, delay * 1000);
  //   }
  (void)endpoint;
  (void)buffer;
  (void)delay;
}

void RPUSBController::finishRead(uint32_t endpoint, const std::vector<uint8_t> &buffer) {
  // TODO(port): peripherals/usb.ts
  //   private finishRead(endpoint: number, buffer: Uint8Array) {
  //     const bufferOffset = this.getEndpointBufferOffset(endpoint, true);
  //     const bufControlReg = EP0_OUT_BUFFER_CONTROL + endpoint * 8;
  //     let bufControl = this.rp2040.usbDPRAMView.getUint32(bufControlReg, true);
  //     const requestedLength = bufControl & USB_BUF_CTRL_LEN_MASK;
  //     const newLength = Math.min(buffer.length, requestedLength);
  //     bufControl |= USB_BUF_CTRL_FULL;
  //     bufControl = (bufControl & ~USB_BUF_CTRL_LEN_MASK) | (newLength & USB_BUF_CTRL_LEN_MASK);
  //     this.rp2040.usbDPRAMView.setUint32(bufControlReg, bufControl, true);
  //     this.rp2040.usbDPRAM.set(buffer.subarray(0, newLength), bufferOffset);
  //     this.indicateBufferReady(endpoint, true);
  //   }
  (void)endpoint;
  (void)buffer;
}

void RPUSBController::checkInterrupts() {
  // TODO(port): peripherals/usb.ts
  //   checkInterrupts() {
  //     const { intStatus } = this;
  //     this.rp2040.setInterrupt(IRQ.USBCTRL, !!intStatus);
  //   }
}

void RPUSBController::resetDevice() {
  // TODO(port): peripherals/usb.ts
  //   resetDevice() {
  //     this.resetAlarm.schedule(10_000_000); // USB reset takes ~10ms
  //   }
}

void RPUSBController::sendSetupPacket(const std::vector<uint8_t> &setupPacket) {
  // TODO(port): peripherals/usb.ts
  //   sendSetupPacket(setupPacket: Uint8Array) {
  //     this.rp2040.usbDPRAM.set(setupPacket);
  //     this.sieStatus |= SIE_SETUP_REC;
  //     this.sieStatusUpdated();
  //   }
  (void)setupPacket;
}

void RPUSBController::indicateBufferReady(uint32_t endpoint, bool out) {
  // TODO(port): peripherals/usb.ts
  //   private indicateBufferReady(endpoint: number, out: boolean) {
  //     this.buffStatus |= 1 << (endpoint * 2 + (out ? 1 : 0));
  //     this.buffStatusUpdated();
  //   }
  (void)endpoint;
  (void)out;
}

void RPUSBController::buffStatusUpdated() {
  // TODO(port): peripherals/usb.ts
  //   private buffStatusUpdated() {
  //     if (this.buffStatus) {
  //       this.intRaw |= INTR_BUFF_STATUS;
  //     } else {
  //       this.intRaw &= ~INTR_BUFF_STATUS;
  //     }
  //     this.checkInterrupts();
  //   }
}

void RPUSBController::sieStatusUpdated() {
  // TODO(port): peripherals/usb.ts
  //   private sieStatusUpdated() {
  //     const intRegisterMap = [
  //       [SIE_SETUP_REC, 1 << 16],
  //       [SIE_RESUME, 1 << 15],
  //       [SIE_SUSPENDED, 1 << 14],
  //       [SIE_CONNECTED, 1 << 13],
  //       [SIE_BUS_RESET, 1 << 12],
  //       [SIE_VBUS_DETECTED, 1 << 11],
  //       [SIE_STALL_REC, 1 << 10],
  //       [SIE_CRC_ERROR, 1 << 9],
  //       [SIE_BIT_STUFF_ERROR, 1 << 8],
  //       [SIE_RX_OVERFLOW, 1 << 7],
  //       [SIE_RX_TIMEOUT, 1 << 6],
  //       [SIE_DATA_SEQ_ERROR, 1 << 5],
  //     ];
  //     for (const [sieBit, intRawBit] of intRegisterMap) {
  //       if (this.sieStatus & sieBit) {
  //         this.intRaw |= intRawBit;
  //       } else {
  //         this.intRaw &= ~intRawBit;
  //       }
  //     }
  //     this.checkInterrupts();
  //   }
}

}  // namespace rp2040js
