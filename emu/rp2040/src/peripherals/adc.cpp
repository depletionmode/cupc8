// Port of rp2040js src/peripherals/adc.ts
#include "adc.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t CS = 0x00;        // ADC Control and Status
static constexpr uint32_t RESULT = 0x04;    // Result of most recent ADC conversion
static constexpr uint32_t FCS = 0x08;       // FIFO control and status
static constexpr uint32_t FIFO_REG = 0x0c;  // Conversion result FIFO
static constexpr uint32_t DIV = 0x10;       // Clock divider.0x14 INTR Raw Interrupts
static constexpr uint32_t INTR = 0x14;      // Raw Interrupts
static constexpr uint32_t INTE = 0x18;      // Interrupt Enable
static constexpr uint32_t INTF = 0x1c;      // Interrupt Force
static constexpr uint32_t INTS = 0x20;      // Interrupt status after masking & forcing

// CS bits
static constexpr uint32_t CS_RROBIN_MASK = 0x1f;
static constexpr uint32_t CS_RROBIN_SHIFT = 16;
static constexpr uint32_t CS_AINSEL_MASK = 0x7;
static constexpr uint32_t CS_AINSEL_SHIFT = 12;
static constexpr uint32_t CS_ERR_STICKY = 1 << 10;
static constexpr uint32_t CS_ERR = 1 << 9;
static constexpr uint32_t CS_READY = 1 << 8;
static constexpr uint32_t CS_START_MANY = 1 << 3;
static constexpr uint32_t CS_START_ONE = 1 << 2;
static constexpr uint32_t CS_TS_EN = 1 << 1;
static constexpr uint32_t CS_EN = 1 << 0;
static constexpr uint32_t CS_WRITE_MASK = (CS_RROBIN_MASK << CS_RROBIN_SHIFT) |
                                          (CS_AINSEL_MASK << CS_AINSEL_SHIFT) | CS_START_MANY |
                                          CS_START_ONE | CS_TS_EN | CS_EN;

// FCS bits
static constexpr uint32_t FCS_THRES_MASK = 0xf;
static constexpr uint32_t FCS_THRESH_SHIFT = 24;
static constexpr uint32_t FCS_LEVEL_MASK = 0xf;
static constexpr uint32_t FCS_LEVEL_SHIFT = 16;
static constexpr uint32_t FCS_OVER = 1 << 11;
static constexpr uint32_t FCS_UNDER = 1 << 10;
static constexpr uint32_t FCS_FULL = 1 << 9;
static constexpr uint32_t FCS_EMPTY = 1 << 8;
static constexpr uint32_t FCS_DREQ_EN = 1 << 3;
static constexpr uint32_t FCS_ERR = 1 << 2;
static constexpr uint32_t FCS_SHIFT = 1 << 1;
static constexpr uint32_t FCS_EN = 1 << 0;
static constexpr uint32_t FCS_WRITE_MASK =
    (FCS_THRES_MASK << FCS_THRESH_SHIFT) | FCS_DREQ_EN | FCS_ERR | FCS_SHIFT | FCS_EN;

// FIFO_REG bits
static constexpr uint32_t FIFO_ERR = 1 << 15;

// DIV bits
static constexpr uint32_t DIV_INT_MASK = 0xffff;
static constexpr uint32_t DIV_INT_SHIFT = 8;
static constexpr uint32_t DIV_FRAC_MASK = 0xff;
static constexpr uint32_t DIV_FRAC_SHIFT = 0;

// Interrupt bits
static constexpr uint32_t FIFO_INT = 1 << 0;

RPADC::RPADC(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      onADCRead([this](uint32_t channel) {
        // Default implementation
        currentChannel = channel;
        sampleAlarm->schedule(sampleTime * 1000);
      }) {
  sampleAlarm = this->rp2040.clock.createAlarm([this] {
    // `this.channelValues[this.currentChannel]`: currentChannel comes from
    // AINSEL (0..7), and channelValues[5..7] is undefined, which the TS then
    // stores as `result` (reads back as 0 on the bus) and pushes as
    // `undefined & 0xfff` = 0: both are 0 here.
    completeADCRead(currentChannel < channelValues.size() ? channelValues[currentChannel] : 0,
                    false);
  });
  multiShotAlarm = this->rp2040.clock.createAlarm([this] {
    if (cs & CS_START_MANY) {
      startADCRead();
    }
  });
}

uint32_t RPADC::temperatueEnable() const { return cs & CS_TS_EN; }

uint32_t RPADC::enabled() const { return cs & CS_EN; }

double RPADC::divider() const {
  return 1 + ((clockDiv >> DIV_INT_SHIFT) & DIV_INT_MASK) +
         ((clockDiv >> DIV_FRAC_SHIFT) & DIV_FRAC_MASK) / 256.0;
}

uint32_t RPADC::intRaw() const {
  const uint32_t thres = (fcs >> FCS_THRESH_SHIFT) & FCS_THRES_MASK;
  return fifo.itemCount() >= thres ? FIFO_INT : 0;
}

uint32_t RPADC::intStatus() const { return (intRaw() & intEnable) | intForce; }

uint32_t RPADC::activeChannel() const { return (cs >> CS_AINSEL_SHIFT) & CS_AINSEL_MASK; }

void RPADC::setActiveChannel(uint32_t channel) {
  cs &= ~(CS_AINSEL_MASK << CS_AINSEL_SHIFT);
  // TS bug (kept): masks with CS_AINSEL_SHIFT (12) instead of CS_AINSEL_MASK.
  cs |= (channel & CS_AINSEL_SHIFT) << CS_AINSEL_SHIFT;
}

void RPADC::checkInterrupts() { rp2040.setInterrupt(IRQ::ADC_FIFO, !!intStatus()); }

void RPADC::startADCRead() {
  busy = true;
  onADCRead(activeChannel());
}

void RPADC::updateDMA() {
  if (fcs & FCS_DREQ_EN) {
    const uint32_t thres = (fcs >> FCS_THRESH_SHIFT) & FCS_THRES_MASK;
    if (fifo.itemCount() >= thres) {
      rp2040.dma.setDREQ(dreq);
    } else {
      rp2040.dma.clearDREQ(dreq);
    }
  }
}

void RPADC::completeADCRead(uint32_t value, bool error) {
  busy = false;
  result = value;
  if (error) {
    cs |= CS_ERR_STICKY | CS_ERR;
  } else {
    cs &= ~CS_ERR;
  }

  // FIFO
  if (fcs & FCS_EN) {
    if (fifo.full()) {
      fcs |= FCS_OVER;
    } else {
      value &= 0xfff;  // 12 bits
      if (fcs & FCS_SHIFT) {
        value >>= 4;
      }
      if (error && fcs & FCS_ERR) {
        value |= FIFO_ERR;
      }
      fifo.push(value);
      updateDMA();
      checkInterrupts();
    }
  }

  // Round-robin
  const uint32_t round = (cs >> CS_RROBIN_SHIFT) & CS_RROBIN_MASK;
  if (round) {
    uint32_t channel = activeChannel() + 1;
    while (!(round & (1u << channel))) {
      channel = (channel + 1) % numChannels;
    }
    setActiveChannel(channel);
  }

  // Multi-shot conversions
  if (cs & CS_START_MANY) {
    const double clockMHZ = 48;
    const double sampleTicks = clockMHZ * sampleTime;
    if (divider() > sampleTicks) {
      // clock runs at 48MHz, subtract 2uS
      const double micros = (divider() - sampleTicks) / clockMHZ;
      multiShotAlarm->schedule(micros * 1000);
    } else {
      startADCRead();
    }
  }
}

uint32_t RPADC::readUint32(uint32_t offset) {
  switch (offset) {
    case CS:
      return cs | (err ? CS_ERR : 0) | (busy ? 0 : CS_READY);
    case RESULT:
      return result;
    case FCS:
      return fcs | ((fifo.itemCount() & FCS_LEVEL_MASK) << FCS_LEVEL_SHIFT) |
             (fifo.full() ? FCS_FULL : 0) | (fifo.empty() ? FCS_EMPTY : 0);
    case FIFO_REG:
      if (fifo.empty()) {
        fcs |= FCS_UNDER;
        return 0;
      } else {
        const uint32_t value = fifo.pull();
        updateDMA();
        return value;
      }
    case DIV:
      return clockDiv;
    case INTR:
      return intRaw();
    case INTE:
      return intEnable;
    case INTF:
      return intForce;
    case INTS:
      return intStatus();
  }
  return BasePeripheral::readUint32(offset);
}

void RPADC::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case CS:
      fcs &= ~(value & CS_ERR_STICKY);  // Write-clear bits
      cs = (cs & ~CS_WRITE_MASK) | (value & CS_WRITE_MASK);
      if (value & CS_EN && !busy && (value & CS_START_ONE || value & CS_START_MANY)) {
        startADCRead();
      }
      break;
    case FCS:
      fcs &= ~(value & (FCS_OVER | FCS_UNDER));  // Write-clear bits
      fcs = (fcs & ~FCS_WRITE_MASK) | (value & FCS_WRITE_MASK);
      checkInterrupts();
      break;
    case DIV:
      clockDiv = value;
      break;
    case INTE:
      intEnable = value & FIFO_INT;
      checkInterrupts();
      break;
    case INTF:
      intForce = value & FIFO_INT;
      checkInterrupts();
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
