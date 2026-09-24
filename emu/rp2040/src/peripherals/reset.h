// Port of rp2040js src/peripherals/reset.ts
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RPReset : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  uint32_t reset = 0;
  uint32_t wdsel = 0;
  uint32_t reset_done = 0x1ffffff;
};

}  // namespace rp2040js
