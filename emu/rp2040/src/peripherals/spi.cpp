// Port of rp2040js src/peripherals/spi.ts
#include "spi.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t SSPCR0 = 0x000;    // Control register 0, SSPCR0 on page 3-4
static constexpr uint32_t SSPCR1 = 0x004;    // Control register 1, SSPCR1 on page 3-5
static constexpr uint32_t SSPDR = 0x008;     // Data register, SSPDR on page 3-6
static constexpr uint32_t SSPSR = 0x00c;     // Status register, SSPSR on page 3-7
static constexpr uint32_t SSPCPSR = 0x010;   // Clock prescale register, SSPCPSR on page 3-8
static constexpr uint32_t SSPIMSC = 0x014;   // Interrupt mask set or clear register, SSPIMSC on page 3-9
static constexpr uint32_t SSPRIS = 0x018;    // Raw interrupt status register, SSPRIS on page 3-10
static constexpr uint32_t SSPMIS = 0x01c;    // Masked interrupt status register, SSPMIS on page 3-11
static constexpr uint32_t SSPICR = 0x020;    // Interrupt clear register, SSPICR on page 3-11
static constexpr uint32_t SSPDMACR = 0x024;  // DMA control register, SSPDMACR on page 3-12
static constexpr uint32_t SSPPERIPHID0 = 0xfe0;  // Peripheral identification registers, SSPPeriphID0-3 on page 3-13
static constexpr uint32_t SSPPERIPHID1 = 0xfe4;  // Peripheral identification registers, SSPPeriphID0-3 on page 3-13
static constexpr uint32_t SSPPERIPHID2 = 0xfe8;  // Peripheral identification registers, SSPPeriphID0-3 on page 3-13
static constexpr uint32_t SSPPERIPHID3 = 0xfec;  // Peripheral identification registers, SSPPeriphID0-3 on page 3-13
static constexpr uint32_t SSPPCELLID0 = 0xff0;  // PrimeCell identification registers, SSPPCellID0-3 on page 3-16
static constexpr uint32_t SSPPCELLID1 = 0xff4;  // PrimeCell identification registers, SSPPCellID0-3 on page 3-16
static constexpr uint32_t SSPPCELLID2 = 0xff8;  // PrimeCell identification registers, SSPPCellID0-3 on page 3-16
static constexpr uint32_t SSPPCELLID3 = 0xffc;  // PrimeCell identification registers, SSPPCellID0-3 on page 3-16

// SSPCR0 bits:
static constexpr uint32_t SCR_MASK = 0xff;
static constexpr uint32_t SCR_SHIFT = 8;
static constexpr uint32_t SPH = 1 << 7;
static constexpr uint32_t SPO = 1 << 6;
static constexpr uint32_t FRF_MASK = 0x3;
static constexpr uint32_t FRF_SHIFT = 4;
static constexpr uint32_t DSS_MASK = 0xf;
static constexpr uint32_t DSS_SHIFT = 0;

// SSPCR1 bits:
static constexpr uint32_t SOD = 1 << 3;
static constexpr uint32_t MS = 1 << 2;
static constexpr uint32_t SSE = 1 << 1;
static constexpr uint32_t LBM = 1 << 0;

// SSPSR bits:
static constexpr uint32_t BSY = 1 << 4;
static constexpr uint32_t RFF = 1 << 3;
static constexpr uint32_t RNE = 1 << 2;
static constexpr uint32_t TNF = 1 << 1;
static constexpr uint32_t TFE = 1 << 0;

// SSPCPSR bits:
static constexpr uint32_t CPSDVSR_MASK = 0xfe;
static constexpr uint32_t CPSDVSR_SHIFT = 0;

// SSPDMACR bits:
static constexpr uint32_t TXDMAE = 1 << 1;
static constexpr uint32_t RXDMAE = 1 << 0;

// Interrupts:
static constexpr uint32_t SSPTXINTR = 1 << 3;
static constexpr uint32_t SSPRXINTR = 1 << 2;
static constexpr uint32_t SSPRTINTR = 1 << 1;
static constexpr uint32_t SSPRORINTR = 1 << 0;

// Unused in the TS too; referenced so -Wunused stays quiet.
[[maybe_unused]] static constexpr uint32_t UNUSED_SPI_CONSTS[] = {
    FRF_MASK, FRF_SHIFT, SOD, LBM, CPSDVSR_SHIFT, TXDMAE, RXDMAE};

RPSPI::RPSPI(RP2040 &rp2040, const std::string &name, uint32_t irq, ISPIDMAChannels dreq)
    : BasePeripheral(rp2040, name),
      onTransmit([this](uint32_t) { completeTransmit(0); }),
      irq(irq),
      dreq(dreq) {
  updateDMATx();
  updateDMARx();
}

uint32_t RPSPI::intStatus() const { return intRaw & intEnable; }

bool RPSPI::enabled() const { return !!(control1 & SSE); }

uint32_t RPSPI::dataBits() const { return ((control0 >> DSS_SHIFT) & DSS_MASK) + 1; }

// TS bug (kept): tests MS (an SSPCR1 bit) in control0.
bool RPSPI::masterMode() const { return !(control0 & MS); }

uint32_t RPSPI::spiMode() const {
  const uint32_t cpol = control0 & SPO;
  const uint32_t cpha = control0 & SPH;
  return cpol ? (cpha ? 2 : 3) : cpha ? 1 : 0;
}

double RPSPI::clockFrequency() const {
  if (!clockDivisor) {
    return 0;
  }

  const uint32_t scr = (control0 >> SCR_SHIFT) & SCR_MASK;
  return rp2040.clkPeri / (static_cast<double>(clockDivisor) * (1 + scr));
}

void RPSPI::updateDMATx() {
  if (txFIFO.full()) {
    rp2040.dma.clearDREQ(dreq.tx);
  } else {
    rp2040.dma.setDREQ(dreq.tx);
  }
}

void RPSPI::updateDMARx() {
  if (rxFIFO.empty()) {
    rp2040.dma.clearDREQ(dreq.rx);
  } else {
    rp2040.dma.setDREQ(dreq.rx);
  }
}

void RPSPI::doTX() {
  if (!busy && !txFIFO.empty()) {
    const uint32_t value = txFIFO.pull();
    busy = true;
    onTransmit(value);
    fifosUpdated();
  }
}

void RPSPI::completeTransmit(uint32_t rxValue) {
  busy = false;
  if (!rxFIFO.full()) {
    rxFIFO.push(rxValue);
  } else {
    intRaw |= SSPRORINTR;
  }
  fifosUpdated();
  doTX();
}

void RPSPI::checkInterrupts() { rp2040.setInterrupt(irq, !!intStatus()); }

void RPSPI::fifosUpdated() {
  const uint32_t prevStatus = intStatus();
  if (txFIFO.itemCount() <= txFIFO.size() / 2) {
    intRaw |= SSPTXINTR;
  } else {
    intRaw &= ~SSPTXINTR;
  }
  if (rxFIFO.itemCount() >= rxFIFO.size() / 2) {
    intRaw |= SSPRXINTR;
  } else {
    intRaw &= ~SSPRXINTR;
  }
  if (intStatus() != prevStatus) {
    checkInterrupts();
  }

  updateDMATx();
  updateDMARx();
}

uint32_t RPSPI::readUint32(uint32_t offset) {
  switch (offset) {
    case SSPCR0:
      return control0;
    case SSPCR1:
      return control1;
    case SSPDR:
      if (!rxFIFO.empty()) {
        const uint32_t value = rxFIFO.pull();
        fifosUpdated();
        return value;
      }
      return 0;
    case SSPSR:
      return (busy || !txFIFO.empty() ? BSY : 0) | (rxFIFO.full() ? RFF : 0) |
             (!rxFIFO.empty() ? RNE : 0) | (!txFIFO.full() ? TNF : 0) | (txFIFO.empty() ? TFE : 0);
    case SSPCPSR:
      return clockDivisor;
    case SSPIMSC:
      return intEnable;
    case SSPRIS:
      return intRaw;
    case SSPMIS:
      return intStatus();
    case SSPDMACR:
      return dmaControl;
    case SSPPERIPHID0:
      return 0x22;
    case SSPPERIPHID1:
      return 0x10;
    case SSPPERIPHID2:
      return 0x34;
    case SSPPERIPHID3:
      return 0x00;
    case SSPPCELLID0:
      return 0x0d;
    case SSPPCELLID1:
      return 0xf0;
    case SSPPCELLID2:
      return 0x05;
    case SSPPCELLID3:
      return 0xb1;
  }
  return BasePeripheral::readUint32(offset);
}

void RPSPI::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case SSPCR0:
      control0 = value;
      return;
    case SSPCR1:
      control1 = value;
      return;
    case SSPDR:
      if (!txFIFO.full()) {
        // decoded with respect to SSPCR0.DSS
        txFIFO.push(value & ((1u << dataBits()) - 1));
        doTX();
        fifosUpdated();
      }
      return;
    case SSPCPSR:
      clockDivisor = value & CPSDVSR_MASK;
      return;
    case SSPIMSC:
      intEnable = value;
      checkInterrupts();
      return;
    case SSPDMACR:
      dmaControl = value;
      return;
    case SSPICR:
      intRaw &= ~(value & (SSPRTINTR | SSPRORINTR));
      checkInterrupts();
      return;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
