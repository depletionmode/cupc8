// Port of rp2040js src/peripherals/spi.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "spi.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPSPI::RPSPI(RP2040 &rp2040, const std::string &name, uint32_t irq, ISPIDMAChannels dreq)
    : BasePeripheral(rp2040, name), irq(irq), dreq(dreq) {
  // TODO(port): peripherals/spi.ts
  //   constructor(
  //     rp2040: RP2040,
  //     name: string,
  //     readonly irq: number,
  //     readonly dreq: ISPIDMAChannels,
  //   ) {
  //     super(rp2040, name);
  //     this.updateDMATx();
  //     this.updateDMARx();
  //   }
  (void)rp2040;
  (void)name;
  (void)irq;
  (void)dreq;
  // TODO(port): the onTransmit default
  //   onTransmit: (value: number) => void = () => this.completeTransmit(0);
}

uint32_t RPSPI::intStatus() const {
  // TODO(port): peripherals/spi.ts
  //   get intStatus() {
  //     return this.intRaw & this.intEnable;
  //   }
  return 0;
}

bool RPSPI::enabled() const {
  // TODO(port): peripherals/spi.ts
  //   get enabled() {
  //     return !!(this.control1 & SSE);
  //   }
  return false;
}

uint32_t RPSPI::dataBits() const {
  // TODO(port): peripherals/spi.ts
  //   get dataBits() {
  //     return ((this.control0 >> DSS_SHIFT) & DSS_MASK) + 1;
  //   }
  return 0;
}

bool RPSPI::masterMode() const {
  // TODO(port): peripherals/spi.ts
  //   get masterMode() {
  //     return !(this.control0 & MS);
  //   }
  return false;
}

uint32_t RPSPI::spiMode() const {
  // TODO(port): peripherals/spi.ts
  //   get spiMode() {
  //     const cpol = this.control0 & SPO;
  //     const cpha = this.control0 & SPH;
  //     return cpol ? (cpha ? 2 : 3) : cpha ? 1 : 0;
  //   }
  return 0;
}

double RPSPI::clockFrequency() const {
  // TODO(port): peripherals/spi.ts
  //   get clockFrequency() {
  //     if (!this.clockDivisor) {
  //       return 0;
  //     }
  //
  //     const scr = (this.control0 >> SCR_SHIFT) & SCR_MASK;
  //     return this.rp2040.clkPeri / (this.clockDivisor * (1 + scr));
  //   }
  return 0;
}

void RPSPI::updateDMATx() {
  // TODO(port): peripherals/spi.ts
  //   private updateDMATx() {
  //     if (this.txFIFO.full) {
  //       this.rp2040.dma.clearDREQ(this.dreq.tx);
  //     } else {
  //       this.rp2040.dma.setDREQ(this.dreq.tx);
  //     }
  //   }
}

void RPSPI::updateDMARx() {
  // TODO(port): peripherals/spi.ts
  //   private updateDMARx() {
  //     if (this.rxFIFO.empty) {
  //       this.rp2040.dma.clearDREQ(this.dreq.rx);
  //     } else {
  //       this.rp2040.dma.setDREQ(this.dreq.rx);
  //     }
  //   }
}

void RPSPI::doTX() {
  // TODO(port): peripherals/spi.ts
  //   private doTX() {
  //     if (!this.busy && !this.txFIFO.empty) {
  //       const value = this.txFIFO.pull();
  //       this.busy = true;
  //       this.onTransmit(value);
  //       this.fifosUpdated();
  //     }
  //   }
}

void RPSPI::completeTransmit(uint32_t rxValue) {
  // TODO(port): peripherals/spi.ts
  //   completeTransmit(rxValue: number) {
  //     this.busy = false;
  //     if (!this.rxFIFO.full) {
  //       this.rxFIFO.push(rxValue);
  //     } else {
  //       this.intRaw |= SSPRORINTR;
  //     }
  //     this.fifosUpdated();
  //     this.doTX();
  //   }
  (void)rxValue;
}

void RPSPI::checkInterrupts() {
  // TODO(port): peripherals/spi.ts
  //   checkInterrupts() {
  //     this.rp2040.setInterrupt(this.irq, !!this.intStatus);
  //   }
}

void RPSPI::fifosUpdated() {
  // TODO(port): peripherals/spi.ts
  //   private fifosUpdated() {
  //     const prevStatus = this.intStatus;
  //     if (this.txFIFO.itemCount <= this.txFIFO.size / 2) {
  //       this.intRaw |= SSPTXINTR;
  //     } else {
  //       this.intRaw &= ~SSPTXINTR;
  //     }
  //     if (this.rxFIFO.itemCount >= this.rxFIFO.size / 2) {
  //       this.intRaw |= SSPRXINTR;
  //     } else {
  //       this.intRaw &= ~SSPRXINTR;
  //     }
  //     if (this.intStatus !== prevStatus) {
  //       this.checkInterrupts();
  //     }
  //
  //     this.updateDMATx();
  //     this.updateDMARx();
  //   }
}

uint32_t RPSPI::readUint32(uint32_t offset) {
  // TODO(port): peripherals/spi.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case SSPCR0:
  //         return this.control0;
  //       case SSPCR1:
  //         return this.control1;
  //       case SSPDR:
  //         if (!this.rxFIFO.empty) {
  //           const value = this.rxFIFO.pull();
  //           this.fifosUpdated();
  //           return value;
  //         }
  //         return 0;
  //       case SSPSR:
  //         return (
  //           (this.busy || !this.txFIFO.empty ? BSY : 0) |
  //           (this.rxFIFO.full ? RFF : 0) |
  //           (!this.rxFIFO.empty ? RNE : 0) |
  //           (!this.txFIFO.full ? TNF : 0) |
  //           (this.txFIFO.empty ? TFE : 0)
  //         );
  //       case SSPCPSR:
  //         return this.clockDivisor;
  //       case SSPIMSC:
  //         return this.intEnable;
  //       case SSPRIS:
  //         return this.intRaw;
  //       case SSPMIS:
  //         return this.intStatus;
  //       case SSPDMACR:
  //         return this.dmaControl;
  //       case SSPPERIPHID0:
  //         return 0x22;
  //       case SSPPERIPHID1:
  //         return 0x10;
  //       case SSPPERIPHID2:
  //         return 0x34;
  //       case SSPPERIPHID3:
  //         return 0x00;
  //       case SSPPCELLID0:
  //         return 0x0d;
  //       case SSPPCELLID1:
  //         return 0xf0;
  //       case SSPPCELLID2:
  //         return 0x05;
  //       case SSPPCELLID3:
  //         return 0xb1;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/spi.ts", "RPSPI::readUint32");
}

void RPSPI::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/spi.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case SSPCR0:
  //         this.control0 = value;
  //         return;
  //       case SSPCR1:
  //         this.control1 = value;
  //         return;
  //       case SSPDR:
  //         if (!this.txFIFO.full) {
  //           // decoded with respect to SSPCR0.DSS
  //           this.txFIFO.push(value & ((1 << this.dataBits) - 1));
  //           this.doTX();
  //           this.fifosUpdated();
  //         }
  //         return;
  //       case SSPCPSR:
  //         this.clockDivisor = value & CPSDVSR_MASK;
  //         return;
  //       case SSPIMSC:
  //         this.intEnable = value;
  //         this.checkInterrupts();
  //         return;
  //       case SSPDMACR:
  //         this.dmaControl = value;
  //         return;
  //       case SSPICR:
  //         this.intRaw &= ~(value & (SSPRTINTR | SSPRORINTR));
  //         this.checkInterrupts();
  //         return;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/spi.ts", "RPSPI::writeUint32");
}

}  // namespace rp2040js
