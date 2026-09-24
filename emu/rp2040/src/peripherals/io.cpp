// Port of rp2040js src/peripherals/io.ts
#include "io.h"

#include "../gpio-pin.h"
#include "../rp2040.h"

namespace rp2040js {

static constexpr uint32_t GPIO_CTRL_LAST = 0x0ec;
static constexpr uint32_t INTR0 = 0xf0;
static constexpr uint32_t PROC0_INTE0 = 0x100;
static constexpr uint32_t PROC0_INTF0 = 0x110;
static constexpr uint32_t PROC0_INTS0 = 0x120;
static constexpr uint32_t PROC0_INTS3 = 0x12c;

RPIO::RPIO(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {}

RPIO::PinFromOffset RPIO::getPinFromOffset(uint32_t offset) {
  const uint32_t gpioIndex = offset >> 3;
  return {
      rp2040.gpio[gpioIndex],
      !!(offset & 0x4),
  };
}

uint32_t RPIO::readUint32(uint32_t offset) {
  if (offset <= GPIO_CTRL_LAST) {
    const PinFromOffset pin = getPinFromOffset(offset);
    return pin.isCtrl ? pin.gpio.ctrl : pin.gpio.status();
  }
  if (offset >= INTR0 && offset <= PROC0_INTS3) {
    const uint32_t startIndex = (offset & 0xf) * 2;
    const uint32_t register_ = offset & ~0xfu;
    auto &gpio = rp2040.gpio;
    uint32_t result = 0;
    for (int index = 7; index >= 0; index--) {
      // `gpio[index + startIndex]` is undefined past the last pin
      if (index + startIndex >= gpio.size()) {
        continue;
      }
      const GPIOPin &pin = gpio[index + startIndex];
      result <<= 4;
      switch (register_) {
        case INTR0:
          result |= pin.irqStatus;
          break;
        case PROC0_INTE0:
          result |= pin.irqEnableMask;
          break;
        case PROC0_INTF0:
          result |= pin.irqForceMask;
          break;
        case PROC0_INTS0:
          result |= (pin.irqStatus & pin.irqEnableMask) | pin.irqForceMask;
          break;
      }
    }
    return result;
  }
  return BasePeripheral::readUint32(offset);
}

void RPIO::writeUint32(uint32_t offset, uint32_t value) {
  if (offset <= GPIO_CTRL_LAST) {
    const PinFromOffset pin = getPinFromOffset(offset);
    if (pin.isCtrl) {
      pin.gpio.ctrl = value;
      pin.gpio.checkForUpdates();
    }
    return;
  }
  if (offset >= INTR0 && offset <= PROC0_INTS3) {
    const uint32_t startIndex = (offset & 0xf) * 2;
    const uint32_t register_ = offset & ~0xfu;
    auto &gpio = rp2040.gpio;
    for (uint32_t index = 0; index < 8; index++) {
      if (index + startIndex >= gpio.size()) {
        continue;
      }
      GPIOPin &pin = gpio[index + startIndex];
      const uint32_t pinValue = (value >> (index * 4)) & 0xf;
      const uint32_t pinRawWriteValue = (rawWriteValue >> (index * 4)) & 0xf;
      switch (register_) {
        case INTR0:
          pin.updateIRQValue(pinRawWriteValue);
          break;
        case PROC0_INTE0:
          if (pin.irqEnableMask != pinValue) {
            pin.irqEnableMask = pinValue;
            rp2040.updateIOInterrupt();
          }
          break;
        case PROC0_INTF0:
          if (pin.irqForceMask != pinValue) {
            pin.irqForceMask = pinValue;
            rp2040.updateIOInterrupt();
          }
          break;
      }
    }
    return;
  }

  BasePeripheral::writeUint32(offset, value);
}

}  // namespace rp2040js
