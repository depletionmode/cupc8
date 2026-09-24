// Port of rp2040js src/peripherals/pads.ts
#pragma once

#include <cstdint>
#include <string>

#include "peripheral.h"

namespace rp2040js {

class GPIOPin;

/** `type IIOBank = 'qspi' | 'bank0'` */
enum class IIOBank {
  qspi,
  bank0,
};

class RPPADS : public BasePeripheral {
 public:
  uint32_t voltageSelect = 0;
  const IIOBank bank;

  RPPADS(RP2040 &rp2040, const std::string &name, IIOBank bank);

  GPIOPin &getPinFromOffset(uint32_t offset);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  const uint32_t firstPadRegister;
  const uint32_t lastPadRegister;
};

}  // namespace rp2040js
