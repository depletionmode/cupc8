// Port of rp2040js src/peripherals/uart.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "uart.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPUART::RPUART(RP2040 &rp2040, const std::string &name, uint32_t irq, IUARTDMAChannels dreq)
    : BasePeripheral(rp2040, name), irq(irq), dreq(dreq), ctrlRegister((1 << 9) | (1 << 8) /* RXE | TXE */) {
  // TODO(port): peripherals/uart.ts
  //   constructor(
  //     rp2040: RP2040,
  //     name: string,
  //     readonly irq: number,
  //     readonly dreq: IUARTDMAChannels,
  //   ) {
  //     super(rp2040, name);
  //   }
}

bool RPUART::enabled() const {
  // TODO(port): peripherals/uart.ts
  //   get enabled() {
  //     return !!(this.ctrlRegister & UARTEN);
  //   }
  return false;
}

bool RPUART::txEnabled() const {
  // TODO(port): peripherals/uart.ts
  //   get txEnabled() {
  //     return !!(this.ctrlRegister & TXE);
  //   }
  return false;
}

bool RPUART::rxEnabled() const {
  // TODO(port): peripherals/uart.ts
  //   get rxEnabled() {
  //     return !!(this.ctrlRegister & RXE);
  //   }
  return false;
}

bool RPUART::fifosEnabled() const {
  // TODO(port): peripherals/uart.ts
  //   get fifosEnabled() {
  //     return !!(this.lineCtrlRegister & FEN);
  //   }
  return false;
}

uint32_t RPUART::wordLength() const {
  // TODO(port): peripherals/uart.ts
  //   get wordLength() {
  //     switch ((this.lineCtrlRegister >>> 5) & 0x3) {
  //       case 0b00:
  //         return 5;
  //       case 0b01:
  //         return 6;
  //       case 0b10:
  //         return 7;
  //       case 0b11:
  //         return 8;
  //     }
  //   }
  return 0;
}

double RPUART::baudDivider() const {
  // TODO(port): peripherals/uart.ts
  //   get baudDivider() {
  //     return this.intDivisor + this.fracDivisor / 64;
  //   }
  return 0;
}

double RPUART::baudRate() const {
  // TODO(port): peripherals/uart.ts
  //   get baudRate() {
  //     return Math.round(this.rp2040.clkPeri / (this.baudDivider * 16));
  //   }
  return 0;
}

uint32_t RPUART::flags() const {
  // TODO(port): peripherals/uart.ts
  //   get flags() {
  //     return (this.rxFIFO.full ? RXFF : 0) | (this.rxFIFO.empty ? RXFE : 0) | TXFE;
  //   }
  return 0;
}

void RPUART::checkInterrupts() {
  // TODO(port): peripherals/uart.ts
  //   checkInterrupts() {
  //     // TODO We should actually implement a proper FIFO for TX
  //     this.interruptStatus |= UARTTXINTR;
  //     this.rp2040.setInterrupt(this.irq, !!(this.interruptStatus & this.interruptMask));
  //   }
}

void RPUART::feedByte(uint32_t value) {
  // TODO(port): peripherals/uart.ts
  //   feedByte(value: number) {
  //     this.rxFIFO.push(value);
  //     // TODO check if the FIFO has reached the threshold level
  //     this.interruptStatus |= UARTRXINTR;
  //     this.checkInterrupts();
  //   }
  (void)value;
}

uint32_t RPUART::readUint32(uint32_t offset) {
  // TODO(port): peripherals/uart.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case UARTDR: {
  //         const value = this.rxFIFO.pull();
  //         if (!this.rxFIFO.empty) {
  //           this.interruptStatus |= UARTRXINTR;
  //         } else {
  //           this.interruptStatus &= ~UARTRXINTR;
  //         }
  //         this.checkInterrupts();
  //         return value;
  //       }
  //       case UARTFR:
  //         return this.flags;
  //       case UARTIBRD:
  //         return this.intDivisor;
  //       case UARTFBRD:
  //         return this.fracDivisor;
  //       case UARTLCR_H:
  //         return this.lineCtrlRegister;
  //       case UARTCR:
  //         return this.ctrlRegister;
  //       case UARTIMSC:
  //         return this.interruptMask;
  //       case UARTIRIS:
  //         return this.interruptStatus;
  //       case UARTIMIS:
  //         return this.interruptStatus & this.interruptMask;
  //       case UARTPERIPHID0:
  //         return 0x11;
  //       case UARTPERIPHID1:
  //         return 0x10;
  //       case UARTPERIPHID2:
  //         return 0x34;
  //       case UARTPERIPHID3:
  //         return 0x00;
  //       case UARTPCELLID0:
  //         return 0x0d;
  //       case UARTPCELLID1:
  //         return 0xf0;
  //       case UARTPCELLID2:
  //         return 0x05;
  //       case UARTPCELLID3:
  //         return 0xb1;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/uart.ts", "RPUART::readUint32");
}

void RPUART::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/uart.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case UARTDR:
  //         this.onByte?.(value & 0xff);
  //         break;
  //
  //       case UARTIBRD:
  //         this.intDivisor = value & 0xffff;
  //         this.onBaudRateChange?.(this.baudRate);
  //         break;
  //
  //       case UARTFBRD:
  //         this.fracDivisor = value & 0x3f;
  //         this.onBaudRateChange?.(this.baudRate);
  //         break;
  //
  //       case UARTLCR_H:
  //         this.lineCtrlRegister = value;
  //         break;
  //
  //       case UARTCR:
  //         this.ctrlRegister = value;
  //         if (this.enabled) {
  //           this.rp2040.dma.setDREQ(this.dreq.tx);
  //         } else {
  //           this.rp2040.dma.clearDREQ(this.dreq.tx);
  //         }
  //         break;
  //
  //       case UARTIMSC:
  //         this.interruptMask = value & 0x7ff;
  //         this.checkInterrupts();
  //         break;
  //
  //       case UARTICR:
  //         this.interruptStatus &= ~this.rawWriteValue;
  //         this.checkInterrupts();
  //         break;
  //
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/uart.ts", "RPUART::writeUint32");
}

}  // namespace rp2040js
