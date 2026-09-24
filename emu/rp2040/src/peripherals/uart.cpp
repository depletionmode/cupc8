// Port of rp2040js src/peripherals/uart.ts
#include "uart.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t UARTDR = 0x0;
static constexpr uint32_t UARTFR = 0x18;
static constexpr uint32_t UARTIBRD = 0x24;
static constexpr uint32_t UARTFBRD = 0x28;
static constexpr uint32_t UARTLCR_H = 0x2c;
static constexpr uint32_t UARTCR = 0x30;
static constexpr uint32_t UARTIMSC = 0x38;
static constexpr uint32_t UARTIRIS = 0x3c;
static constexpr uint32_t UARTIMIS = 0x40;
static constexpr uint32_t UARTICR = 0x44;
static constexpr uint32_t UARTPERIPHID0 = 0xfe0;
static constexpr uint32_t UARTPERIPHID1 = 0xfe4;
static constexpr uint32_t UARTPERIPHID2 = 0xfe8;
static constexpr uint32_t UARTPERIPHID3 = 0xfec;
static constexpr uint32_t UARTPCELLID0 = 0xff0;
static constexpr uint32_t UARTPCELLID1 = 0xff4;
static constexpr uint32_t UARTPCELLID2 = 0xff8;
static constexpr uint32_t UARTPCELLID3 = 0xffc;

// UARTFR bits:
static constexpr uint32_t TXFE = 1 << 7;
static constexpr uint32_t RXFF = 1 << 6;
static constexpr uint32_t RXFE = 1 << 4;

// UARTLCR_H bits:
static constexpr uint32_t FEN = 1 << 4;

// UARTCR bits:
static constexpr uint32_t RXE = 1 << 9;
static constexpr uint32_t TXE = 1 << 8;
static constexpr uint32_t UARTEN = 1 << 0;

// Interrupt bits
static constexpr uint32_t UARTTXINTR = 1 << 5;
static constexpr uint32_t UARTRXINTR = 1 << 4;

RPUART::RPUART(RP2040 &rp2040, const std::string &name, uint32_t irq, IUARTDMAChannels dreq)
    : BasePeripheral(rp2040, name), irq(irq), dreq(dreq), ctrlRegister(RXE | TXE) {}

bool RPUART::enabled() const { return !!(ctrlRegister & UARTEN); }

bool RPUART::txEnabled() const { return !!(ctrlRegister & TXE); }

bool RPUART::rxEnabled() const { return !!(ctrlRegister & RXE); }

bool RPUART::fifosEnabled() const { return !!(lineCtrlRegister & FEN); }

uint32_t RPUART::wordLength() const {
  switch ((lineCtrlRegister >> 5) & 0x3) {
    case 0b00:
      return 5;
    case 0b01:
      return 6;
    case 0b10:
      return 7;
    case 0b11:
    default:
      return 8;
  }
}

double RPUART::baudDivider() const { return intDivisor + fracDivisor / 64.0; }

double RPUART::baudRate() const { return jsMathRound(rp2040.clkPeri / (baudDivider() * 16)); }

uint32_t RPUART::flags() const {
  return (rxFIFO.full() ? RXFF : 0) | (rxFIFO.empty() ? RXFE : 0) | TXFE;
}

void RPUART::checkInterrupts() {
  // TODO We should actually implement a proper FIFO for TX
  interruptStatus |= UARTTXINTR;
  rp2040.setInterrupt(irq, !!(interruptStatus & interruptMask));
}

void RPUART::feedByte(uint32_t value) {
  rxFIFO.push(value);
  // TODO check if the FIFO has reached the threshold level
  interruptStatus |= UARTRXINTR;
  checkInterrupts();
}

uint32_t RPUART::readUint32(uint32_t offset) {
  switch (offset) {
    case UARTDR: {
      const uint32_t value = rxFIFO.pull();
      if (!rxFIFO.empty()) {
        interruptStatus |= UARTRXINTR;
      } else {
        interruptStatus &= ~UARTRXINTR;
      }
      checkInterrupts();
      return value;
    }
    case UARTFR:
      return flags();
    case UARTIBRD:
      return intDivisor;
    case UARTFBRD:
      return fracDivisor;
    case UARTLCR_H:
      return lineCtrlRegister;
    case UARTCR:
      return ctrlRegister;
    case UARTIMSC:
      return interruptMask;
    case UARTIRIS:
      return interruptStatus;
    case UARTIMIS:
      return interruptStatus & interruptMask;
    case UARTPERIPHID0:
      return 0x11;
    case UARTPERIPHID1:
      return 0x10;
    case UARTPERIPHID2:
      return 0x34;
    case UARTPERIPHID3:
      return 0x00;
    case UARTPCELLID0:
      return 0x0d;
    case UARTPCELLID1:
      return 0xf0;
    case UARTPCELLID2:
      return 0x05;
    case UARTPCELLID3:
      return 0xb1;
  }
  return BasePeripheral::readUint32(offset);
}

void RPUART::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case UARTDR:
      if (onByte) {
        onByte(value & 0xff);
      }
      break;

    case UARTIBRD:
      intDivisor = value & 0xffff;
      if (onBaudRateChange) {
        onBaudRateChange(baudRate());
      }
      break;

    case UARTFBRD:
      fracDivisor = value & 0x3f;
      if (onBaudRateChange) {
        onBaudRateChange(baudRate());
      }
      break;

    case UARTLCR_H:
      lineCtrlRegister = value;
      break;

    case UARTCR:
      ctrlRegister = value;
      if (enabled()) {
        rp2040.dma.setDREQ(dreq.tx);
      } else {
        rp2040.dma.clearDREQ(dreq.tx);
      }
      break;

    case UARTIMSC:
      interruptMask = value & 0x7ff;
      checkInterrupts();
      break;

    case UARTICR:
      interruptStatus &= ~rawWriteValue;
      checkInterrupts();
      break;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
