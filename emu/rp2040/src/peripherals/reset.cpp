// Port of rp2040js src/peripherals/reset.ts
#include "reset.h"

namespace rp2040js {

static constexpr uint32_t RESET = 0x0;       // Reset control.
static constexpr uint32_t WDSEL = 0x4;       // Watchdog select.
static constexpr uint32_t RESET_DONE = 0x8;  // Reset Done

uint32_t RPReset::readUint32(uint32_t offset) {
  switch (offset) {
    case RESET:
      return reset;
    case WDSEL:
      return wdsel;
    case RESET_DONE:
      return reset_done;
  }
  return BasePeripheral::readUint32(offset);
}

void RPReset::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case RESET:
      reset = value & 0x1ffffff;
      break;
    case WDSEL:
      wdsel = value & 0x1ffffff;
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
      break;
  }
}

}  // namespace rp2040js
