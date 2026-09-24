// Port of rp2040js src/peripherals/psm.ts
#include "psm.h"

#include "../rp2040.h"

namespace rp2040js {

static constexpr uint32_t FRCE_ON = 0x0;
static constexpr uint32_t FRCE_OFF = 0x4;
static constexpr uint32_t WDSEL = 0x8;
static constexpr uint32_t DONE = 0xc;

static constexpr uint32_t PROC1 = 1 << 16;

uint32_t RPPSM::readUint32(uint32_t offset) {
  switch (offset) {
    case FRCE_ON:
      return frceOn;
    case FRCE_OFF:
      return frceOff;
    case WDSEL:
      return wdsel;
    case DONE:
      return 0x1ffff & ~frceOff;
  }
  return BasePeripheral::readUint32(offset);
}

void RPPSM::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case FRCE_ON:
      frceOn = value & 0x1ffff;
      return;
    case FRCE_OFF: {
      const bool released = (frceOff & PROC1) && !(value & PROC1);
      frceOff = value & 0x1ffff;
      rp2040.core1Held = !!(frceOff & PROC1);
      if (released) {
        rp2040.resetCore1();
      }
      return;
    }
    case WDSEL:
      wdsel = value & 0x1ffff;
      return;
  }
  BasePeripheral::writeUint32(offset, value);
}

}  // namespace rp2040js
