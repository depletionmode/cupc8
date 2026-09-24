// Port of rp2040js src/peripherals/adc.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "adc.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPADC::RPADC(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {
  // TODO(port): peripherals/adc.ts
  //   constructor(rp2040: RP2040, name: string) {
  //     super(rp2040, name);
  //     this.sampleAlarm = this.rp2040.clock.createAlarm(() =>
  //       this.completeADCRead(this.channelValues[this.currentChannel], false),
  //     );
  //     this.multiShotAlarm = this.rp2040.clock.createAlarm(() => {
  //       if (this.cs & CS_START_MANY) {
  //         this.startADCRead();
  //       }
  //     });
  //   }
  (void)rp2040;
  (void)name;
  // TODO(port): the onADCRead default
  //   onADCRead: (channel: number) => void = (channel) => {
  //     // Default implementation
  //     this.currentChannel = channel;
  //     this.sampleAlarm.schedule(this.sampleTime * 1000);
  //   };
}

uint32_t RPADC::temperatueEnable() const {
  // TODO(port): peripherals/adc.ts
  //   get temperatueEnable() {
  //     return this.cs & CS_TS_EN;
  //   }
  return 0;
}

uint32_t RPADC::enabled() const {
  // TODO(port): peripherals/adc.ts
  //   get enabled() {
  //     return this.cs & CS_EN;
  //   }
  return 0;
}

double RPADC::divider() const {
  // TODO(port): peripherals/adc.ts
  //   get divider() {
  //     return (
  //       1 +
  //       ((this.clockDiv >> DIV_INT_SHIFT) & DIV_INT_MASK) +
  //       ((this.clockDiv >> DIV_FRAC_SHIFT) & DIV_FRAC_MASK) / 256
  //     );
  //   }
  return 0;
}

uint32_t RPADC::intRaw() const {
  // TODO(port): peripherals/adc.ts
  //   get intRaw() {
  //     const thres = (this.fcs >> FCS_THRESH_SHIFT) & FCS_THRES_MASK;
  //     return this.fifo.itemCount >= thres ? FIFO_INT : 0;
  //   }
  return 0;
}

uint32_t RPADC::intStatus() const {
  // TODO(port): peripherals/adc.ts
  //   get intStatus() {
  //     return (this.intRaw & this.intEnable) | this.intForce;
  //   }
  return 0;
}

uint32_t RPADC::activeChannel() const {
  // TODO(port): peripherals/adc.ts
  //   private get activeChannel() {
  //     return (this.cs >> CS_AINSEL_SHIFT) & CS_AINSEL_MASK;
  //   }
  return 0;
}

void RPADC::setActiveChannel(uint32_t channel) {
  // TODO(port): peripherals/adc.ts
  //   private set activeChannel(channel: number) {
  //     this.cs &= ~(CS_AINSEL_MASK << CS_AINSEL_SHIFT);
  //     this.cs |= (channel & CS_AINSEL_SHIFT) << CS_AINSEL_SHIFT;
  //   }
  (void)channel;
}

void RPADC::checkInterrupts() {
  // TODO(port): peripherals/adc.ts
  //   checkInterrupts() {
  //     this.rp2040.setInterrupt(IRQ.ADC_FIFO, !!this.intStatus);
  //   }
}

void RPADC::startADCRead() {
  // TODO(port): peripherals/adc.ts
  //   startADCRead() {
  //     this.busy = true;
  //     this.onADCRead(this.activeChannel);
  //   }
}

void RPADC::updateDMA() {
  // TODO(port): peripherals/adc.ts
  //   private updateDMA() {
  //     if (this.fcs & FCS_DREQ_EN) {
  //       const thres = (this.fcs >> FCS_THRESH_SHIFT) & FCS_THRES_MASK;
  //       if (this.fifo.itemCount >= thres) {
  //         this.rp2040.dma.setDREQ(this.dreq);
  //       } else {
  //         this.rp2040.dma.clearDREQ(this.dreq);
  //       }
  //     }
  //   }
}

void RPADC::completeADCRead(uint32_t value, bool error) {
  // TODO(port): peripherals/adc.ts
  //   completeADCRead(value: number, error: boolean) {
  //     this.busy = false;
  //     this.result = value;
  //     if (error) {
  //       this.cs |= CS_ERR_STICKY | CS_ERR;
  //     } else {
  //       this.cs &= ~CS_ERR;
  //     }
  //
  //     // FIFO
  //     if (this.fcs & FCS_EN) {
  //       if (this.fifo.full) {
  //         this.fcs |= FCS_OVER;
  //       } else {
  //         value &= 0xfff; // 12 bits
  //         if (this.fcs & FCS_SHIFT) {
  //           value >>= 4;
  //         }
  //         if (error && this.fcs & FCS_ERR) {
  //           value |= FIFO_ERR;
  //         }
  //         this.fifo.push(value);
  //         this.updateDMA();
  //         this.checkInterrupts();
  //       }
  //     }
  //
  //     // Round-robin
  //     const round = (this.cs >> CS_RROBIN_SHIFT) & CS_RROBIN_MASK;
  //     if (round) {
  //       let channel = this.activeChannel + 1;
  //       while (!(round & (1 << channel))) {
  //         channel = (channel + 1) % this.numChannels;
  //       }
  //       this.activeChannel = channel;
  //     }
  //
  //     // Multi-shot conversions
  //     if (this.cs & CS_START_MANY) {
  //       const clockMHZ = 48;
  //       const sampleTicks = clockMHZ * this.sampleTime;
  //       if (this.divider > sampleTicks) {
  //         // clock runs at 48MHz, subtract 2uS
  //         const micros = (this.divider - sampleTicks) / clockMHZ;
  //         this.multiShotAlarm.schedule(micros * 1000);
  //       } else {
  //         this.startADCRead();
  //       }
  //     }
  //   }
  (void)value;
  (void)error;
}

uint32_t RPADC::readUint32(uint32_t offset) {
  // TODO(port): peripherals/adc.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case CS:
  //         return this.cs | (this.err ? CS_ERR : 0) | (this.busy ? 0 : CS_READY);
  //       case RESULT:
  //         return this.result;
  //       case FCS:
  //         return (
  //           this.fcs |
  //           ((this.fifo.itemCount & FCS_LEVEL_MASK) << FCS_LEVEL_SHIFT) |
  //           (this.fifo.full ? FCS_FULL : 0) |
  //           (this.fifo.empty ? FCS_EMPTY : 0)
  //         );
  //       case FIFO_REG:
  //         if (this.fifo.empty) {
  //           this.fcs |= FCS_UNDER;
  //           return 0;
  //         } else {
  //           const value = this.fifo.pull();
  //           this.updateDMA();
  //           return value;
  //         }
  //       case DIV:
  //         return this.clockDiv;
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
  TODO_PORT_ABORT("peripherals/adc.ts", "RPADC::readUint32");
}

void RPADC::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/adc.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case CS:
  //         this.fcs &= ~(value & CS_ERR_STICKY); // Write-clear bits
  //         this.cs = (this.cs & ~CS_WRITE_MASK) | (value & CS_WRITE_MASK);
  //         if (value & CS_EN && !this.busy && (value & CS_START_ONE || value & CS_START_MANY)) {
  //           this.startADCRead();
  //         }
  //         break;
  //       case FCS:
  //         this.fcs &= ~(value & (FCS_OVER | FCS_UNDER)); // Write-clear bits
  //         this.fcs = (this.fcs & ~FCS_WRITE_MASK) | (value & FCS_WRITE_MASK);
  //         this.checkInterrupts();
  //         break;
  //       case DIV:
  //         this.clockDiv = value;
  //         break;
  //       case INTE:
  //         this.intEnable = value & FIFO_INT;
  //         this.checkInterrupts();
  //         break;
  //       case INTF:
  //         this.intForce = value & FIFO_INT;
  //         this.checkInterrupts();
  //         break;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/adc.ts", "RPADC::writeUint32");
}

}  // namespace rp2040js
