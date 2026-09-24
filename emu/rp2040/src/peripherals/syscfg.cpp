// Port of rp2040js src/peripherals/syscfg.ts
#include "syscfg.h"

#include "../rp2040.h"

namespace rp2040js {

static constexpr uint32_t PROC0_NMI_MASK = 0;
[[maybe_unused]] static constexpr uint32_t PROC1_NMI_MASK = 4;

uint32_t RP2040SysCfg::readUint32(uint32_t offset) {
  switch (offset) {
    case PROC0_NMI_MASK:
      return rp2040.core().interruptNMIMask;
  }
  return BasePeripheral::readUint32(offset);
}

void RP2040SysCfg::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case PROC0_NMI_MASK:
      rp2040.core().interruptNMIMask = value;
      break;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
