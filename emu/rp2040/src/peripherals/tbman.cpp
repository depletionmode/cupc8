// Port of rp2040js src/peripherals/tbman.ts
#include "tbman.h"

namespace rp2040js {

static constexpr uint32_t PLATFORM = 0;
static constexpr uint32_t ASIC = 1;

uint32_t RPTBMAN::readUint32(uint32_t offset) {
  switch (offset) {
    case PLATFORM:
      return ASIC;
    default:
      return BasePeripheral::readUint32(offset);
  }
}

}  // namespace rp2040js
