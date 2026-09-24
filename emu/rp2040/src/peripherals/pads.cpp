// Port of rp2040js src/peripherals/pads.ts
#include "pads.h"

#include "../gpio-pin.h"
#include "../rp2040.h"

namespace rp2040js {

static constexpr uint32_t VOLTAGE_SELECT = 0;
static constexpr uint32_t GPIO_FIRST = 0x4;
static constexpr uint32_t GPIO_LAST = 0x78;

static constexpr uint32_t QSPI_FIRST = 0x4;
static constexpr uint32_t QSPI_LAST = 0x18;

RPPADS::RPPADS(RP2040 &rp2040, const std::string &name, IIOBank bank)
    : BasePeripheral(rp2040, name),
      bank(bank),
      firstPadRegister(bank == IIOBank::qspi ? QSPI_FIRST : GPIO_FIRST),
      lastPadRegister(bank == IIOBank::qspi ? QSPI_LAST : GPIO_LAST) {}

GPIOPin &RPPADS::getPinFromOffset(uint32_t offset) {
  const uint32_t gpioIndex = (offset - firstPadRegister) >> 2;
  if (bank == IIOBank::qspi) {
    return rp2040.qspi[gpioIndex];
  } else {
    return rp2040.gpio[gpioIndex];
  }
}

uint32_t RPPADS::readUint32(uint32_t offset) {
  if (offset >= firstPadRegister && offset <= lastPadRegister) {
    const GPIOPin &gpio = getPinFromOffset(offset);
    return gpio.padValue;
  }
  switch (offset) {
    case VOLTAGE_SELECT:
      return voltageSelect;
  }
  return BasePeripheral::readUint32(offset);
}

void RPPADS::writeUint32(uint32_t offset, uint32_t value) {
  if (offset >= firstPadRegister && offset <= lastPadRegister) {
    rp2040.syncPIO();  // PIO fast path: the pad sets the pin's value and input
    GPIOPin &gpio = getPinFromOffset(offset);
    const bool oldInputEnable = gpio.inputEnable();
    gpio.padValue = value;
    gpio.checkForUpdates();
    if (oldInputEnable != gpio.inputEnable()) {
      gpio.refreshInput();
    }
    return;
  }
  switch (offset) {
    case VOLTAGE_SELECT:
      voltageSelect = value & 1;
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
