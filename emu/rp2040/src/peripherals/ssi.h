// Port of rp2040js src/peripherals/ssi.ts
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RPSSI : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  uint32_t dr0 = 0;
  uint32_t txflr = 0;
  uint32_t rxflr = 0;
  uint32_t baudr = 0;
  uint32_t crtlr0 = 0;
  uint32_t crtlr1 = 0;
  uint32_t ssienr = 0;
  uint32_t spictlr0 = 0;
  uint32_t rxsampldly = 0;
  uint32_t txddriveedge = 0;
};

}  // namespace rp2040js
