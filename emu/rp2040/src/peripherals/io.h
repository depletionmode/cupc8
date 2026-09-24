// Port of rp2040js src/peripherals/io.ts
#pragma once

#include <cstdint>
#include <string>

#include "peripheral.h"

namespace rp2040js {

class GPIOPin;

class RPIO : public BasePeripheral {
 public:
  RPIO(RP2040 &rp2040, const std::string &name);

  struct PinFromOffset {
    GPIOPin &gpio;
    bool isCtrl;
  };
  PinFromOffset getPinFromOffset(uint32_t offset);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
