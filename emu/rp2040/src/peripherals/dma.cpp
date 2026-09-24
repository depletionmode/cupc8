// Port of rp2040js src/peripherals/dma.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "dma.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPDMAChannel::RPDMAChannel(RPDMA &dma, RP2040 &rp2040, uint32_t index)
    : dma(dma), rp2040(rp2040), index(index) {
  // TODO(port): peripherals/dma.ts
  //   constructor(
  //     readonly dma: RPDMA,
  //     readonly rp2040: RP2040,
  //     readonly index: number,
  //   ) {
  //     this.transferAlarm = rp2040.clock.createAlarm(this.transfer);
  //     this.reset();
  //   }
}

void RPDMAChannel::start() {
  // TODO(port): peripherals/dma.ts
  //   start() {
  //     if (!(this.ctrl & EN) || this.ctrl & BUSY) {
  //       return;
  //     }
  //     this.ctrl |= BUSY;
  //     this.transCount = this.transCountReload;
  //     if (this.transCount) {
  //       this.scheduleTransfer();
  //     }
  //   }
}

uint32_t RPDMAChannel::treq() const {
  // TODO(port): peripherals/dma.ts
  //   get treq() {
  //     return this.treqValue;
  //   }
  return 0;
}

uint32_t RPDMAChannel::active() const {
  // TODO(port): peripherals/dma.ts
  //   get active() {
  //     return this.ctrl & EN && this.ctrl & BUSY;
  //   }
  return 0;
}

void RPDMAChannel::transfer8() {
  // TODO(port): peripherals/dma.ts
  //   transfer8 = () => {
  //     const { rp2040 } = this;
  //     rp2040.writeUint8(this.writeAddr, rp2040.readUint8(this.readAddr));
  //   };
}

void RPDMAChannel::transfer16() {
  // TODO(port): peripherals/dma.ts
  //   transfer16 = () => {
  //     const { rp2040 } = this;
  //     rp2040.writeUint16(this.writeAddr, rp2040.readUint16(this.readAddr));
  //   };
}

void RPDMAChannel::transferSwap16() {
  // TODO(port): peripherals/dma.ts
  //   transferSwap16 = () => {
  //     const { rp2040 } = this;
  //     const input = rp2040.readUint16(this.readAddr);
  //     rp2040.writeUint16(this.writeAddr, ((input & 0xff) << 8) | (input >> 8));
  //   };
}

void RPDMAChannel::transfer32() {
  // TODO(port): peripherals/dma.ts
  //   transfer32 = () => {
  //     const { rp2040 } = this;
  //     rp2040.writeUint32(this.writeAddr, rp2040.readUint32(this.readAddr));
  //   };
}

void RPDMAChannel::transferSwap32() {
  // TODO(port): peripherals/dma.ts
  //   transferSwap32 = () => {
  //     const { rp2040 } = this;
  //     const input = rp2040.readUint32(this.readAddr);
  //     rp2040.writeUint32(
  //       this.writeAddr,
  //       ((input & 0x000000ff) << 24) |
  //         ((input & 0x0000ff00) << 8) |
  //         ((input & 0x00ff0000) >> 8) |
  //         ((input >> 24) & 0xff),
  //     );
  //   };
}

void RPDMAChannel::transfer() {
  // TODO(port): peripherals/dma.ts
  //   transfer = () => {
  //     const { ctrl, dataSize, ringMask } = this;
  //     this.transferFn();
  //     if (ctrl & INCR_READ) {
  //       if (ringMask && !(ctrl & RING_SEL)) {
  //         this.readAddr = (this.readAddr & ~ringMask) | ((this.readAddr + dataSize) & ringMask);
  //       } else {
  //         this.readAddr += dataSize;
  //       }
  //     }
  //     if (ctrl & INCR_WRITE) {
  //       if (ringMask && ctrl & RING_SEL) {
  //         this.writeAddr = (this.writeAddr & ~ringMask) | ((this.writeAddr + dataSize) & ringMask);
  //       } else {
  //         this.writeAddr += dataSize;
  //       }
  //     }
  //     this.transCount--;
  //     if (this.transCount > 0) {
  //       this.scheduleTransfer();
  //     } else {
  //       this.ctrl &= ~BUSY;
  //       if (!(this.ctrl & IRQ_QUIET)) {
  //         this.dma.intRaw |= 1 << this.index;
  //         this.dma.checkInterrupts();
  //       }
  //       if (this.chainTo !== this.index) {
  //         this.dma.channels[this.chainTo]?.start();
  //       }
  //     }
  //   };
}

void RPDMAChannel::scheduleTransfer() {
  // TODO(port): peripherals/dma.ts
  //   scheduleTransfer() {
  //     if (this.dma.dreq[this.treqValue] || this.treqValue === TREQ.Permanent) {
  //       this.transferAlarm.schedule(0);
  //     } else {
  //       const delay = this.dma.getTimer(this.treqValue);
  //       if (delay) {
  //         this.transferAlarm.schedule(delay * 1000);
  //       }
  //     }
  //   }
}

void RPDMAChannel::abort() {
  // TODO(port): peripherals/dma.ts
  //   abort() {
  //     this.ctrl &= ~BUSY;
  //     this.transferAlarm.cancel();
  //   }
}

uint32_t RPDMAChannel::readUint32(uint32_t offset) {
  // TODO(port): peripherals/dma.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case CHn_READ_ADDR:
  //       case CHn_AL1_READ_ADDR:
  //       case CHn_AL2_READ_ADDR:
  //       case CHn_AL3_READ_ADDR_TRIG:
  //         return this.readAddr;
  //
  //       case CHn_WRITE_ADDR:
  //       case CHn_AL1_WRITE_ADDR:
  //       case CHn_AL2_WRITE_ADDR_TRIG:
  //       case CHn_AL3_WRITE_ADDR:
  //         return this.writeAddr;
  //
  //       case CHn_TRANS_COUNT:
  //       case CHn_AL1_TRANS_COUNT_TRIG:
  //       case CHn_AL2_TRANS_COUNT:
  //       case CHn_AL3_TRANS_COUNT:
  //         return this.transCount;
  //
  //       case CHn_CTRL_TRIG:
  //       case CHn_AL1_CTRL:
  //       case CHn_AL2_CTRL:
  //       case CHn_AL3_CTRL:
  //         return this.ctrl;
  //
  //       case CHn_DBG_CTDREQ:
  //         return this.dreqCounter;
  //
  //       case CHn_DBG_TCR:
  //         return this.transCountReload;
  //     }
  //
  //     return 0;
  //   }
  (void)offset;
  return 0;
}

void RPDMAChannel::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/dma.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case CHn_READ_ADDR:
  //       case CHn_AL1_READ_ADDR:
  //       case CHn_AL2_READ_ADDR:
  //       case CHn_AL3_READ_ADDR_TRIG:
  //         this.readAddr = value;
  //         break;
  //
  //       case CHn_WRITE_ADDR:
  //       case CHn_AL1_WRITE_ADDR:
  //       case CHn_AL2_WRITE_ADDR_TRIG:
  //       case CHn_AL3_WRITE_ADDR:
  //         this.writeAddr = value;
  //         break;
  //
  //       case CHn_TRANS_COUNT:
  //       case CHn_AL1_TRANS_COUNT_TRIG:
  //       case CHn_AL2_TRANS_COUNT:
  //       case CHn_AL3_TRANS_COUNT:
  //         this.transCountReload = value;
  //         break;
  //
  //       case CHn_CTRL_TRIG:
  //       case CHn_AL1_CTRL:
  //       case CHn_AL2_CTRL:
  //       case CHn_AL3_CTRL: {
  //         this.ctrl = (this.ctrl & ~CHn_CTRL_TRIG_WRITE_MASK) | (value & CHn_CTRL_TRIG_WRITE_MASK);
  //         this.ctrl &= ~(value & CHn_CTRL_TRIG_WC_MASK); // Handle write-clear (WC) bits
  //         this.treqValue = (this.ctrl >> TREQ_SEL_SHIFT) & TREQ_SEL_MASK;
  //         this.chainTo = (this.ctrl >> CHAIN_TO_SHIFT) & CHAIN_TO_MASK;
  //         const ringSize = (this.ctrl >> RING_SIZE_SHIFT) & RING_SIZE_MASK;
  //         this.ringMask = ringSize ? (1 << ringSize) - 1 : 0;
  //         switch ((this.ctrl >> DATA_SIZE_SHIFT) & DATA_SIZE_MASK) {
  //           case 1:
  //             this.dataSize = 2;
  //             this.transferFn = this.ctrl & BSWAP ? this.transferSwap16 : this.transfer16;
  //             break;
  //           case 2:
  //             this.dataSize = 4;
  //             this.transferFn = this.ctrl & BSWAP ? this.transferSwap32 : this.transfer32;
  //             break;
  //           case 0:
  //           default:
  //             this.transferFn = this.transfer8;
  //             this.dataSize = 1;
  //         }
  //         if (this.ctrl & EN && this.ctrl & BUSY) {
  //           this.scheduleTransfer();
  //         }
  //         if (!(this.ctrl & EN)) {
  //           this.transferAlarm.cancel();
  //         }
  //         break;
  //       }
  //
  //       case CHn_DBG_CTDREQ:
  //         this.dreqCounter = 0;
  //         break;
  //     }
  //
  //     if (
  //       offset === CHn_AL3_READ_ADDR_TRIG ||
  //       offset === CHn_AL2_WRITE_ADDR_TRIG ||
  //       offset === CHn_AL1_TRANS_COUNT_TRIG ||
  //       offset === CHn_CTRL_TRIG
  //     ) {
  //       if (value) {
  //         this.start();
  //       } else if (this.ctrl & IRQ_QUIET) {
  //         // Null trigger interrupts
  //         this.dma.intRaw |= 1 << this.index;
  //         this.dma.checkInterrupts();
  //       }
  //     }
  //   }
  (void)offset;
  (void)value;
}

void RPDMAChannel::reset() {
  // TODO(port): peripherals/dma.ts
  //   reset() {
  //     this.writeUint32(CHn_CTRL_TRIG, this.index << CHAIN_TO_SHIFT);
  //   }
}

RPDMA::RPDMA(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      channels{{
          {*this, rp2040, 0},
          {*this, rp2040, 1},
          {*this, rp2040, 2},
          {*this, rp2040, 3},
          {*this, rp2040, 4},
          {*this, rp2040, 5},
          {*this, rp2040, 6},
          {*this, rp2040, 7},
          {*this, rp2040, 8},
          {*this, rp2040, 9},
          {*this, rp2040, 10},
          {*this, rp2040, 11},
      }} {
  // TODO(port): peripherals/dma.ts
  //   readonly channels = [
  //     new RPDMAChannel(this, this.rp2040, 0),
}

uint32_t RPDMA::intStatus0() const {
  // TODO(port): peripherals/dma.ts
  //   get intStatus0() {
  //     return (this.intRaw & this.intEnable0) | this.intForce0;
  //   }
  return 0;
}

uint32_t RPDMA::intStatus1() const {
  // TODO(port): peripherals/dma.ts
  //   get intStatus1() {
  //     return (this.intRaw & this.intEnable1) | this.intForce1;
  //   }
  return 0;
}

uint32_t RPDMA::readUint32(uint32_t offset) {
  // TODO(port): peripherals/dma.ts
  //   readUint32(offset: number) {
  //     if ((offset & 0x7ff) <= CHANNEL_REGISTERS_SIZE) {
  //       const channelIndex = (offset & 0x7ff) >> 6;
  //       return this.channels[channelIndex].readUint32(offset & CHANNEL_REGISTERS_MASK);
  //     }
  //     switch (offset) {
  //       case TIMER0:
  //         return this.timer0;
  //       case TIMER1:
  //         return this.timer1;
  //       case TIMER2:
  //         return this.timer2;
  //       case TIMER3:
  //         return this.timer3;
  //       case INTR:
  //         return this.intRaw;
  //       case INTE0:
  //         return this.intEnable0;
  //       case INTF0:
  //         return this.intForce0;
  //       case INTS0:
  //         return this.intStatus0;
  //       case INTE1:
  //         return this.intEnable1;
  //       case INTF1:
  //         return this.intForce1;
  //       case INTS1:
  //         return this.intStatus1;
  //       case N_CHANNELS:
  //         return this.channels.length;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/dma.ts", "RPDMA::readUint32");
}

void RPDMA::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/dma.ts
  //   writeUint32(offset: number, value: number) {
  //     if ((offset & 0x7ff) <= CHANNEL_REGISTERS_SIZE) {
  //       const channelIndex = (offset & 0x7ff) >> 6;
  //       this.channels[channelIndex].writeUint32(offset & CHANNEL_REGISTERS_MASK, value);
  //       return;
  //     }
  //     switch (offset) {
  //       case TIMER0:
  //         this.timer0 = value;
  //         return;
  //       case TIMER1:
  //         this.timer1 = value;
  //         return;
  //       case TIMER2:
  //         this.timer2 = value;
  //         return;
  //       case TIMER3:
  //         this.timer3 = value;
  //         return;
  //       case INTR:
  //       case INTS0:
  //       case INTS1:
  //         this.intRaw &= ~this.rawWriteValue;
  //         this.checkInterrupts();
  //         return;
  //       case INTE0:
  //         this.intEnable0 = value & 0xffff;
  //         this.checkInterrupts();
  //         return;
  //       case INTF0:
  //         this.intForce0 = value & 0xffff;
  //         this.checkInterrupts();
  //         return;
  //       case INTE1:
  //         this.intEnable1 = value & 0xffff;
  //         this.checkInterrupts();
  //         return;
  //       case INTF1:
  //         this.intForce1 = value & 0xffff;
  //         this.checkInterrupts();
  //         return;
  //       case MULTI_CHAN_TRIGGER:
  //         for (const chan of this.channels) {
  //           if (value & (1 << chan.index)) {
  //             chan.start();
  //           }
  //         }
  //         return;
  //       case CHAN_ABORT:
  //         for (const chan of this.channels) {
  //           if (value & (1 << chan.index)) {
  //             chan.abort();
  //           }
  //         }
  //         return;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/dma.ts", "RPDMA::writeUint32");
}

void RPDMA::setDREQ(DREQChannel dreqChannel) {
  // TODO(port): peripherals/dma.ts
  //   setDREQ(dreqChannel: DREQChannel) {
  //     const { dreq } = this;
  //     if (!dreq[dreqChannel]) {
  //       dreq[dreqChannel] = true;
  //       for (const channel of this.channels) {
  //         if (channel.treq === dreqChannel && channel.active) {
  //           channel.scheduleTransfer();
  //         }
  //       }
  //     }
  //   }
  (void)dreqChannel;
}

void RPDMA::clearDREQ(DREQChannel dreqChannel) {
  // TODO(port): peripherals/dma.ts
  //   clearDREQ(dreqChannel: DREQChannel) {
  //     this.dreq[dreqChannel] = false;
  //   }
  (void)dreqChannel;
}

double RPDMA::getTimer(TREQ treq) const {
  // TODO(port): peripherals/dma.ts
  //   getTimer(treq: TREQ) {
  //     let dividend = 0,
  //       divisor = 1;
  //     switch (treq) {
  //       case TREQ.Permanent:
  //         dividend = 1;
  //         divisor = 1;
  //         break;
  //       case TREQ.Timer0:
  //         dividend = this.timer0 >>> 16;
  //         divisor = this.timer0 & 0xffff;
  //         break;
  //       case TREQ.Timer1:
  //         dividend = this.timer1 >>> 16;
  //         divisor = this.timer1 & 0xffff;
  //         break;
  //       case TREQ.Timer2:
  //         dividend = this.timer2 >>> 16;
  //         divisor = this.timer2 & 0xffff;
  //         break;
  //       case TREQ.Timer3:
  //         dividend = this.timer3 >>> 36;
  //         divisor = this.timer3 & 0xffff;
  //         break;
  //     }
  //     if (divisor === 0) {
  //       return 0;
  //     }
  //     return ((dividend / divisor) * 1e6) / this.rp2040.clkSys;
  //   }
  (void)treq;
  return 0;
}

void RPDMA::checkInterrupts() {
  // TODO(port): peripherals/dma.ts
  //   checkInterrupts() {
  //     this.rp2040.setInterrupt(IRQ.DMA_IRQ0, !!this.intStatus0);
  //     this.rp2040.setInterrupt(IRQ.DMA_IRQ1, !!this.intStatus1);
  //   }
}

}  // namespace rp2040js
