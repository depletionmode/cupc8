// Port of rp2040js src/peripherals/sysinfo.ts
#include "sysinfo.h"

namespace rp2040js {

static constexpr uint32_t CHIP_ID = 0;
static constexpr uint32_t PLATFORM = 0x4;
static constexpr uint32_t GITREF_RP2040 = 0x40;

uint32_t RP2040SysInfo::readUint32(uint32_t offset) {
  // All the values here were verified against the silicon
  switch (offset) {
    case CHIP_ID:
      return 0x10002927;

    case PLATFORM:
      return 0x00000002;

    case GITREF_RP2040:
      return 0xe0c912e8;
  }
  return BasePeripheral::readUint32(offset);
}

}  // namespace rp2040js
