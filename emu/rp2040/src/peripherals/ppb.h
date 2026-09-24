// Port of rp2040js src/peripherals/ppb.ts
#pragma once

#include <cstdint>
#include <string>

#include "../utils/timer32.h"
#include "peripheral.h"

namespace rp2040js {

// ppb.ts exports CPUID, ICSR, VTOR, SHPR2 and SHPR3, but only its tests
// import them; they are file-local in ppb.cpp so that they cannot clash with
// sio.cpp's CPUID or CortexM0Core::VTOR.

/** PPB stands for Private Periphral Bus.
 * These are peripherals that are part of the ARM Cortex Core, and there's one copy for each processor core.
 *
 * Included peripheral: NVIC, SysTick timer
 */
class RPPPB : public BasePeripheral {
 public:
  // Systick
  bool systickCountFlag = false;
  bool systickClkSource = false;
  bool systickIntEnable = false;
  uint32_t systickReload = 0;
  /** `new Timer32(this.rp2040.clock, this.rp2040.clkSys)` */
  Timer32 systickTimer;
  /** `new Timer32PeriodicAlarm(this.systickTimer, () => {...})` */
  Timer32PeriodicAlarm systickAlarm;

  RPPPB(RP2040 &rp2040, const std::string &name);

  void reset();

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
