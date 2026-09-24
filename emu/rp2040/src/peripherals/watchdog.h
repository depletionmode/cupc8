// Port of rp2040js src/peripherals/watchdog.ts
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

#include "../utils/timer32.h"
#include "peripheral.h"

namespace rp2040js {

class RPWatchdog : public BasePeripheral {
 public:
  /** `readonly timer;` assigned in the constructor (mode and enable set before the alarm exists) */
  std::unique_ptr<Timer32> timer;
  std::unique_ptr<Timer32PeriodicAlarm> alarm;
  std::array<uint32_t, 8> scratchData{};  // `new Uint32Array(8)`

  /** Called when the watchdog triggers - override with your own soft reset implementation */
  std::function<void()> onWatchdogTrigger;

  // User provided
  RPWatchdog(RP2040 &rp2040, const std::string &name);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  bool enable = false;
  bool tickEnable = true;
  uint32_t reason = 0;
  bool pauseDbg0 = true;
  bool pauseDbg1 = true;
  bool pauseJtag = true;
};

}  // namespace rp2040js
