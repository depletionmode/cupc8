// Port of rp2040js src/peripherals/psm.ts (cupc8 dual-core patch)
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

/** Power-on state machine: only what multicore_reset_core1() needs. */
class RPPSM : public BasePeripheral {
 public:
  uint32_t frceOn = 0;
  uint32_t frceOff = 0;
  uint32_t wdsel = 0;

  using BasePeripheral::BasePeripheral;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
