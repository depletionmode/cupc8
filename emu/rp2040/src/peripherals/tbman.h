// Port of rp2040js src/peripherals/tbman.ts
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RPTBMAN : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
};

}  // namespace rp2040js
