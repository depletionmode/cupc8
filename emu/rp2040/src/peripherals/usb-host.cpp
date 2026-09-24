// Port of rp2040js src/peripherals/usb-host.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "usb-host.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

USBHostController::USBHostController(RP2040 &rp2040, USBHostRegs &regs) : rp2040(rp2040), regs(regs) {
  // TODO(port): peripherals/usb-host.ts
  //   constructor(
  //     private readonly rp2040: RP2040,
  //     private readonly regs: {
  //       get addrEndp(): number;
  //       sieStatus: number;
  //       buffStatus: number;
  //       update(): void;
  //     },
  //   ) {
  //     this.epxAlarm = rp2040.clock.createAlarm(() => this.epxService());
  //     this.setupAlarm = rp2040.clock.createAlarm(() => {
  //       const done = this.setupDone;
  //       this.setupDone = null;
  //       done?.();
  //     });
  //     this.frameAlarm = rp2040.clock.createAlarm(() => this.frame());
  //   }
}

uint8_t *USBHostController::dpram() {
  // TODO(port): peripherals/usb-host.ts
  //   private get dpram() {
  //     return this.rp2040.usbDPRAMView;
  //   }
  return rp2040.usbDPRAM.data();
}

void USBHostController::attach(USBHostDevice *device) {
  // TODO(port): peripherals/usb-host.ts
  //   attach(device: USBHostDevice) {
  //     this.device = device;
  //     this.setSpeed(device.speed);
  //     this.frameAlarm.schedule(FRAME_NANOS);
  //   }
  (void)device;
}

void USBHostController::detach() {
  // TODO(port): peripherals/usb-host.ts
  //   detach() {
  //     this.device = null;
  //     this.epxActive = false;
  //     this.setSpeed(0);
  //   }
}

void USBHostController::setSpeed(uint32_t speed) {
  // TODO(port): peripherals/usb-host.ts
  //   private setSpeed(speed: number) {
  //     this.regs.sieStatus =
  //       (this.regs.sieStatus & ~SIE_STATUS_SPEED_MASK) | (speed << SIE_STATUS_SPEED_SHIFT);
  //     this.connChanged = true;
  //     this.regs.update();
  //   }
  (void)speed;
}

uint32_t USBHostController::intRaw() const {
  // TODO(port): peripherals/usb-host.ts
  //   get intRaw() {
  //     const s = this.regs.sieStatus;
  //     return (
  //       (this.connChanged ? INTR_HOST_CONN_DIS : 0) |
  //       (s & SIE_STATUS_TRANS_COMPLETE ? INTR_TRANS_COMPLETE : 0) |
  //       (this.regs.buffStatus ? INTR_BUFF_STATUS : 0) |
  //       (s & (1 << 31) ? INTR_ERROR_DATA_SEQ : 0) |
  //       (s & SIE_STATUS_RX_TIMEOUT ? INTR_ERROR_RX_TIMEOUT : 0) |
  //       (s & SIE_STATUS_STALL_REC ? INTR_STALL : 0)
  //     );
  //   }
  return 0;
}

uint32_t USBHostController::sieCtrlWritten(uint32_t value) {
  // TODO(port): peripherals/usb-host.ts
  //   sieCtrlWritten(value: number) {
  //     if (value & SIE_CTRL_RESET_BUS) {
  //       this.device?.busReset();
  //     }
  //     if (value & SIE_CTRL_START_TRANS) {
  //       const addr = this.regs.addrEndp & 0x7f;
  //       const ep = (this.regs.addrEndp >> 16) & 0xf;
  //       if (value & SIE_CTRL_SEND_SETUP) {
  //         this.epxActive = false;
  //         const packet = this.rp2040.usbDPRAM.slice(SETUP_PACKET, SETUP_PACKET + 8);
  //         this.later(() => {
  //           if (!this.device) {
  //             this.status(SIE_STATUS_RX_TIMEOUT);
  //           } else if (this.device.setup(addr, packet) === 'stall') {
  //             this.status(SIE_STATUS_STALL_REC);
  //           } else {
  //             this.status(SIE_STATUS_TRANS_COMPLETE | SIE_STATUS_ACK_REC);
  //           }
  //         });
  //       } else {
  //         this.epxActive = true;
  //         this.epxIn = !!(value & SIE_CTRL_RECEIVE_DATA);
  //         this.epxBuf = 0;
  //         this.epxAddr = addr;
  //         this.epxEp = ep;
  //         this.epxAlarm.schedule(PACKET_NANOS);
  //       }
  //     }
  //     return value & ~(SIE_CTRL_START_TRANS | SIE_CTRL_RESET_BUS);
  //   }
  return value;
}

void USBHostController::dpramWritten(uint32_t offset) {
  // TODO(port): peripherals/usb-host.ts
  //   dpramWritten(offset: number) {
  //     if (offset === EPX_BUF_CTRL && this.epxActive) {
  //       this.epxAlarm.schedule(PACKET_NANOS);
  //     }
  //   }
  (void)offset;
}

void USBHostController::later(std::function<void()> fn) {
  // TODO(port): peripherals/usb-host.ts
  //   private later(fn: () => void) {
  //     this.setupDone = fn;
  //     this.setupAlarm.schedule(PACKET_NANOS);
  //   }
  (void)fn;
}

void USBHostController::status(uint32_t bits) {
  // TODO(port): peripherals/usb-host.ts
  //   private status(bits: number) {
  //     this.regs.sieStatus |= bits;
  //     this.regs.update();
  //   }
  (void)bits;
}

void USBHostController::bufferDone(uint32_t bit) {
  // TODO(port): peripherals/usb-host.ts
  //   private bufferDone(bit: number) {
  //     this.regs.buffStatus |= bit;
  //     this.regs.update();
  //   }
  (void)bit;
}

void USBHostController::epxService() {
  // TODO(port): peripherals/usb-host.ts
  //   private epxService() {
  //     if (!this.epxActive || !this.device) {
  //       return;
  //     }
  //     const ctrl = this.dpram.getUint32(EPX_CTRL, true);
  //     const double = !!(ctrl & EP_DOUBLE_BUF);
  //     const half = double ? this.epxBuf : 0;
  //     const shift = half ? 16 : 0;
  //     const all = this.dpram.getUint32(EPX_BUF_CTRL, true);
  //     let buf = (all >>> shift) & 0xffff;
  //     if (!(buf & BUF_AVAILABLE)) {
  //       return; // wait for the CPU to hand over the buffer
  //     }
  //     const len = buf & BUF_LEN_MASK;
  //     const data = (ctrl & EP_BUF_ADDR_MASK) + half * 64;
  //     let short = false;
  //     if (this.epxIn) {
  //       const r = this.device.in(this.epxAddr, this.epxEp, len);
  //       if (r === 'nak') {
  //         this.epxAlarm.schedule(NAK_RETRY_NANOS);
  //         return;
  //       }
  //       if (r === 'stall') {
  //         this.epxActive = false;
  //         this.status(SIE_STATUS_STALL_REC);
  //         return;
  //       }
  //       this.rp2040.usbDPRAM.set(r.subarray(0, len), data);
  //       short = r.length < len;
  //       buf = (buf & ~(BUF_AVAILABLE | BUF_LEN_MASK)) | BUF_FULL | Math.min(r.length, len);
  //     } else {
  //       const r = this.device.out(
  //         this.epxAddr,
  //         this.epxEp,
  //         this.rp2040.usbDPRAM.slice(data, data + len),
  //       );
  //       if (r === 'nak') {
  //         this.epxAlarm.schedule(NAK_RETRY_NANOS);
  //         return;
  //       }
  //       if (r === 'stall') {
  //         this.epxActive = false;
  //         this.status(SIE_STATUS_STALL_REC);
  //         return;
  //       }
  //       buf &= ~(BUF_AVAILABLE | BUF_FULL);
  //     }
  //     const last = !!(buf & BUF_LAST) || short;
  //     const mask = 0xffff << shift;
  //     this.dpram.setUint32(EPX_BUF_CTRL, ((all & ~mask) | (buf << shift)) >>> 0, true);
  //     if (last) {
  //       this.epxActive = false;
  //     }
  //     // per double buffer: one BUFF_STATUS after both halves (or a short/last first half)
  //     const perDouble = double && !!(ctrl & EP_INT_PER_DOUBLE_BUF) && !(ctrl & EP_INT_PER_BUF);
  //     if (!perDouble || half === 1 || last) {
  //       this.bufferDone(1);
  //     }
  //     if (last) {
  //       this.status(SIE_STATUS_TRANS_COMPLETE);
  //       return;
  //     }
  //     if (double) {
  //       this.epxBuf ^= 1;
  //     }
  //     this.epxAlarm.schedule(PACKET_NANOS);
  //   }
}

void USBHostController::frame() {
  // TODO(port): peripherals/usb-host.ts
  //   private frame() {
  //     if (!this.device) {
  //       return;
  //     }
  //     this.sofNumber = (this.sofNumber + 1) & 0x7ff;
  //     for (let n = 0; n < 15; n++) {
  //       if (!(this.intEpCtrl & (1 << (n + 1)))) {
  //         continue;
  //       }
  //       const ctrl = this.dpram.getUint32(INT_EP_CTRL + 8 * n, true);
  //       const interval = ((ctrl >>> EP_INTERVAL_SHIFT) & EP_INTERVAL_MASK) + 1;
  //       if (++this.intEpPollDue[n] < interval) {
  //         continue;
  //       }
  //       this.intEpPollDue[n] = 0;
  //       let buf = this.dpram.getUint32(INT_EP_BUF_CTRL + 8 * n, true);
  //       if (!(buf & BUF_AVAILABLE)) {
  //         continue;
  //       }
  //       const addr = this.intEpAddr[n] & 0x7f;
  //       const ep = (this.intEpAddr[n] >> 16) & 0xf;
  //       const out = !!(this.intEpAddr[n] & (1 << 25));
  //       const len = buf & BUF_LEN_MASK;
  //       const data = ctrl & EP_BUF_ADDR_MASK;
  //       if (out) {
  //         const r = this.device.out(addr, ep, this.rp2040.usbDPRAM.slice(data, data + len));
  //         if (r !== 'ack') continue;
  //         buf &= ~(BUF_AVAILABLE | BUF_FULL);
  //         this.dpram.setUint32(INT_EP_BUF_CTRL + 8 * n, buf, true);
  //         this.bufferDone(1 << (2 * (n + 1) + 1));
  //       } else {
  //         const r = this.device.in(addr, ep, len);
  //         if (r === 'nak' || r === 'stall') continue;
  //         this.rp2040.usbDPRAM.set(r.subarray(0, len), data);
  //         buf = (buf & ~(BUF_AVAILABLE | BUF_LEN_MASK)) | BUF_FULL | Math.min(r.length, len);
  //         this.dpram.setUint32(INT_EP_BUF_CTRL + 8 * n, buf, true);
  //         this.bufferDone(1 << (2 * (n + 1)));
  //       }
  //     }
  //     this.frameAlarm.schedule(FRAME_NANOS);
  //   }
}

}  // namespace rp2040js
