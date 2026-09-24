// Port of rp2040js src/peripherals/rtc.ts
//
// TS keeps `baseline` as a JS Date and reads it back with the LOCAL-time
// getters (getFullYear, getMonth, getDate, getDay, getHours, ...), so the
// result depends on the host time zone. The port keeps the Date as its
// time value (ms since the epoch, double) and must use local time too.
#pragma once

#include <cstdint>

#include "peripheral.h"

namespace rp2040js {

class RP2040RTC : public BasePeripheral {
 public:
  uint32_t setup0 = 0;
  uint32_t setup1 = 0;
  uint32_t ctrl = 0;
  /** `new Date(2021, 0, 1)` (local time) as Date.getTime(); set in the constructor */
  double baseline = 0;
  double baselineNanos = 0;

  RP2040RTC(RP2040 &rp2040, const std::string &name);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
