// Port of rp2040js src/peripherals/sysinfo.ts
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RP2040SysInfo : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
};

}  // namespace rp2040js
