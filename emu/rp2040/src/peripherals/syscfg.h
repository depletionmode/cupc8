// Port of rp2040js src/peripherals/syscfg.ts
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RP2040SysCfg : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
