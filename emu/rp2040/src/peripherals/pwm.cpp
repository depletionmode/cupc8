// Port of rp2040js src/peripherals/pwm.ts
#include "pwm.h"

#include <cmath>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

/** Control and status register */
static constexpr uint32_t CHn_CSR = 0x00;
/**
 * INT and FRAC form a fixed-point fractional number.
 * Counting rate is system clock frequency divided by this number.
 * Fractional division uses simple 1st-order sigma-delta.
 */
static constexpr uint32_t CHn_DIV = 0x04;
/** Direct access to the PWM counter */
static constexpr uint32_t CHn_CTR = 0x08;
/** Counter compare values */
static constexpr uint32_t CHn_CC = 0x0c;
/** Counter wrap value */
static constexpr uint32_t CHn_TOP = 0x10;

/**
 * This register aliases the CSR_EN bits for all channels.
 * Writing to this register allows multiple channels to be enabled
 * or disabled simultaneously, so they can run in perfect sync.
 * For each channel, there is only one physical EN register bit,
 * which can be accessed through here or CHx_CSR.
 */
static constexpr uint32_t EN = 0xa0;
/** Raw Interrupts */
static constexpr uint32_t INTR = 0xa4;
/** Interrupt Enable */
static constexpr uint32_t INTE = 0xa8;
/** Interrupt Force */
static constexpr uint32_t INTF = 0xac;
/** Interrupt status after masking & forcing */
static constexpr uint32_t INTS = 0xb0;

static constexpr uint32_t INT_MASK = 0xff;

/* CHn_CSR bits */
static constexpr uint32_t CSR_PH_ADV = 1 << 7;
static constexpr uint32_t CSR_PH_RET = 1 << 6;
static constexpr uint32_t CSR_DIVMODE_SHIFT = 4;
static constexpr uint32_t CSR_DIVMODE_MASK = 0x3;
static constexpr uint32_t CSR_B_INV = 1 << 3;
static constexpr uint32_t CSR_A_INV = 1 << 2;
static constexpr uint32_t CSR_PH_CORRECT = 1 << 1;
static constexpr uint32_t CSR_EN = 1 << 0;

PWMChannel::PWMChannel(RPPWM &pwm, IClock &clock, uint32_t index)
    : timer(clock, pwm.clockFreq()),
      alarmA(timer, [this] { setA(false); }),
      alarmB(timer, [this] { setB(false); }),
      alarmBottom(timer, [this] { wrap(); }),
      clock(clock),
      index(index),
      pinA1(static_cast<int32_t>(index * 2)),
      pinB1(static_cast<int32_t>(index * 2 + 1)),
      pinA2(index < 7 ? static_cast<int32_t>(16 + index * 2) : -1),
      pinB2(index < 7 ? static_cast<int32_t>(16 + index * 2 + 1) : -1),
      pwm(pwm) {
  alarmA.setEnable(true);
  alarmB.setEnable(true);
  alarmBottom.setEnable(true);
}

uint32_t PWMChannel::readRegister(uint32_t offset) {
  switch (offset) {
    case CHn_CSR:
      return csr;
    case CHn_DIV:
      return div;
    case CHn_CTR:
      return timer.counter();
    case CHn_CC:
      return cc;
    case CHn_TOP:
      return top;
  }
  /* Shouldn't get here */
  return 0;
}

void PWMChannel::writeRegister(uint32_t offset, uint32_t value) {
  switch (offset) {
    case CHn_CSR:
      if (value & CSR_EN && !(csr & CSR_EN)) {
        updateDoubleBuffered();
      }
      csr = value & ~(CSR_PH_ADV | CSR_PH_RET);
      // TS bug (kept): PH_ADV / PH_RET were just masked out, so these never fire.
      if (csr & CSR_PH_ADV) {
        timer.advance(1);
      }
      if (csr & CSR_PH_RET) {
        timer.advance(-1);
      }
      divMode = static_cast<PWMDivMode>((csr >> CSR_DIVMODE_SHIFT) & CSR_DIVMODE_MASK);
      setBDirection(divMode == PWMDivMode::FreeRunning);
      updateEnable();
      lastBValue = gpioBValue();
      timer.setMode(value & CSR_PH_CORRECT ? TimerMode::ZigZag : TimerMode::Increment);
      break;
    case CHn_DIV: {
      div = value & 0x000fffff;
      const uint32_t intValue = (value >> 4) & 0xff;
      const uint32_t fracValue = value & 0xf;
      timer.setPrescaler((intValue ? intValue : 256) + fracValue / 16.0);
      break;
    }
    case CHn_CTR:
      timer.set(value & 0xffff);
      break;
    case CHn_CC:
      cc = value;
      ccUpdated = true;
      break;
    case CHn_TOP:
      top = value & 0xffff;
      topUpdated = true;
      break;
  }
}

void PWMChannel::reset() {
  writeRegister(CHn_CSR, 0);
  writeRegister(CHn_DIV, 0x01 << 4);
  writeRegister(CHn_CTR, 0);
  writeRegister(CHn_CC, 0);
  writeRegister(CHn_TOP, 0xffff);
  countingUp = true;
  timer.setEnable(false);
  timer.reset();
}

void PWMChannel::updateDoubleBuffered() {
  if (ccUpdated) {
    alarmB.setTarget(cc >> 16);
    alarmA.setTarget(cc & 0xffff);
    ccUpdated = false;
  }
  if (topUpdated) {
    timer.setTop(top);
    topUpdated = false;
  }
}

void PWMChannel::wrap() {
  pwm.channelInterrupt(index);
  updateDoubleBuffered();
  if (!(csr & CSR_PH_CORRECT)) {
    setA(alarmA.target() > 0);
    setB(alarmB.target() > 0);
  }
}

void PWMChannel::setA(bool value) {
  if (csr & CSR_A_INV) {
    value = !value;
  }
  pwm.gpioSet(pinA1, value);
  if (pinA2 >= 0) {
    pwm.gpioSet(pinA2, value);
  }
}

void PWMChannel::setB(bool value) {
  if (csr & CSR_B_INV) {
    value = !value;
  }
  pwm.gpioSet(pinB1, value);
  if (pinB2 >= 0) {
    pwm.gpioSet(pinB2, value);
  }
}

bool PWMChannel::gpioBValue() const {
  return pwm.gpioRead(pinB1) || (pinB2 > 0 ? pwm.gpioRead(pinB2) : false);
}

void PWMChannel::setBDirection(bool value) {
  pwm.gpioSetDir(pinB1, value);
  if (pinB2 >= 0) {
    pwm.gpioSetDir(pinB2, value);
  }
}

void PWMChannel::gpioBChanged() {
  const bool value = gpioBValue();
  if (value == lastBValue) {
    return;
  }
  lastBValue = value;
  switch (divMode) {
    case PWMDivMode::BGated:
      updateEnable();
      break;

    case PWMDivMode::BRisingEdge:
      if (value) {
        tickCounter++;
      }
      break;

    case PWMDivMode::BFallingEdge:
      if (!value) {
        tickCounter++;
      }
      break;

    default:
      break;
  }

  if (tickCounter >= timer.prescaler()) {
    timer.advance(1);
    tickCounter -= timer.prescaler();
  }
}

void PWMChannel::updateEnable() {
  const bool enable = !!(csr & CSR_EN);
  timer.setEnable(enable && (divMode == PWMDivMode::FreeRunning ||
                             (divMode == PWMDivMode::BGated && gpioBValue())));
}

void PWMChannel::setEn(uint32_t value) {
  if (value && !(csr & CSR_EN)) {
    updateDoubleBuffered();
  }
  if (value) {
    csr |= CSR_EN;
  } else {
    csr &= ~CSR_EN;
  }
  updateEnable();
}

RPPWM::RPPWM(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      channels{{
          {*this, rp2040.clock, 0},
          {*this, rp2040.clock, 1},
          {*this, rp2040.clock, 2},
          {*this, rp2040.clock, 3},
          {*this, rp2040.clock, 4},
          {*this, rp2040.clock, 5},
          {*this, rp2040.clock, 6},
          {*this, rp2040.clock, 7},
      }} {}

uint32_t RPPWM::intStatus() const { return (intRaw & intEnable) | intForce; }

uint32_t RPPWM::readUint32(uint32_t offset) {
  if (offset < EN) {
    const uint32_t channel = offset / 0x14;  // Math.floor(offset / 0x14)
    return channels[channel].readRegister(offset % 0x14);
  }
  switch (offset) {
    case EN:
      // TS bug (kept): PWMChannel has a setter for `en` but no getter, so each
      // `channels[n].en` is undefined and `undefined << n` is 0: EN reads as 0.
      return 0;
    case INTR:
      return intRaw;
    case INTE:
      return intEnable;
    case INTF:
      return intForce;
    case INTS:
      return intStatus();
  }
  return BasePeripheral::readUint32(offset);
}

void RPPWM::writeUint32(uint32_t offset, uint32_t value) {
  if (offset < EN) {
    const uint32_t channel = offset / 0x14;  // Math.floor(offset / 0x14)
    return channels[channel].writeRegister(offset % 0x14, value);
  }

  switch (offset) {
    case EN:
      channels[7].setEn(value & (1 << 7));
      channels[6].setEn(value & (1 << 6));
      channels[5].setEn(value & (1 << 5));
      channels[4].setEn(value & (1 << 4));
      channels[3].setEn(value & (1 << 3));
      channels[2].setEn(value & (1 << 2));
      channels[1].setEn(value & (1 << 1));
      channels[0].setEn(value & (1 << 0));
      break;
    case INTR:
      intRaw &= ~(value & INT_MASK);
      checkInterrupts();
      break;
    case INTE:
      intEnable = value & INT_MASK;
      checkInterrupts();
      break;
    case INTF:
      intForce = value & INT_MASK;
      checkInterrupts();
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

double RPPWM::clockFreq() const { return rp2040.clkSys; }

void RPPWM::channelInterrupt(uint32_t index) {
  intRaw |= 1 << index;
  checkInterrupts();

  // We also set the DMA Request (DREQ) for the channel
  rp2040.dma.setDREQ(static_cast<DREQChannel>(DREQ_PWM_WRAP0 + index));
}

void RPPWM::checkInterrupts() { rp2040.setInterrupt(IRQ::PWM_WRAP, !!intStatus()); }

void RPPWM::gpioSet(uint32_t index, bool value) {
  const uint32_t bit = static_cast<uint32_t>(jsShl(1, index));
  const uint32_t newGpioValue = value ? gpioValue | bit : gpioValue & ~bit;
  if (gpioValue != newGpioValue) {
    gpioValue = newGpioValue;
    rp2040.gpio[index].checkForUpdates();
  }
}

void RPPWM::gpioSetDir(uint32_t index, bool output) {
  const uint32_t bit = static_cast<uint32_t>(jsShl(1, index));
  const uint32_t newGpioDirection = output ? gpioDirection | bit : gpioDirection & ~bit;
  if (gpioDirection != newGpioDirection) {
    gpioDirection = newGpioDirection;
    rp2040.gpio[index].checkForUpdates();
  }
}

bool RPPWM::gpioRead(uint32_t index) { return rp2040.gpio[index].inputValue(); }

void RPPWM::gpioOnInput(uint32_t index) {
  // TS bug (kept): `this.gpioDirection && 1 << index` (logical, not bitwise
  // and): returns whenever any PWM pin is an output.
  if (gpioDirection && jsShl(1, index)) {
    return;
  }
  for (PWMChannel &channel : channels) {
    if (channel.pinB1 == static_cast<int32_t>(index) ||
        channel.pinB2 == static_cast<int32_t>(index)) {
      channel.gpioBChanged();
    }
  }
}

void RPPWM::reset() {
  gpioDirection = 0xffffffff;
  for (PWMChannel &channel : channels) {
    channel.reset();
  }
}

}  // namespace rp2040js
