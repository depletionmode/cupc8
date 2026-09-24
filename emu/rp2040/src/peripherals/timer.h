// Port of rp2040js src/peripherals/timer.ts
#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <string>

#include "../clock/clock.h"
#include "peripheral.h"

namespace rp2040js {

class RPTimerAlarm {
 public:
  bool armed = false;
  uint32_t targetMicros = 0;

  const uint32_t bitValue;
  const std::unique_ptr<IAlarm> clockAlarm;

  RPTimerAlarm(uint32_t bitValue, std::unique_ptr<IAlarm> clockAlarm);
};

class RPTimer : public BasePeripheral {
 public:
  RPTimer(RP2040 &rp2040, const std::string &name);

  uint32_t intStatus() const;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  IClock &clock;
  uint32_t latchedTimeHigh = 0;
  /** Four alarms (constructor initialiser list; each clock alarm captures `this`). */
  std::array<RPTimerAlarm, 4> alarms;
  uint32_t intRaw = 0;
  uint32_t intEnable = 0;
  uint32_t intForce = 0;
  bool paused = false;

  void fireAlarm(uint32_t index);
  void checkInterrupts();
  void disarmAlarm(RPTimerAlarm &alarm);
};

}  // namespace rp2040js
