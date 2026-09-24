// Port of rp2040js src/peripherals/pwm.ts
#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <string>

#include "../clock/clock.h"
#include "../utils/timer32.h"
#include "peripheral.h"

namespace rp2040js {

class RPPWM;

enum class PWMDivMode {
  FreeRunning,
  BGated,
  BRisingEdge,
  BFallingEdge,
};

class PWMChannel {
 public:
  /** `new Timer32(this.clock, this.pwm.clockFreq)` */
  Timer32 timer;
  /** `() => { this.setA(false); }` */
  Timer32PeriodicAlarm alarmA;
  /** `() => { this.setB(false); }` */
  Timer32PeriodicAlarm alarmB;
  /** `() => this.wrap()` */
  Timer32PeriodicAlarm alarmBottom;

  uint32_t csr = 0;
  uint32_t div = 0;
  uint32_t cc = 0;
  uint32_t top = 0;
  bool lastBValue = false;
  bool countingUp = true;
  bool ccUpdated = false;
  bool topUpdated = false;
  double tickCounter = 0;  // `tickCounter -= timer.prescaler` makes it fractional
  PWMDivMode divMode = PWMDivMode::FreeRunning;

  IClock &clock;
  const uint32_t index;

  // GPIO pin indices: Table 525. Mapping of PWM channels to GPIO pins on RP2040
  const int32_t pinA1;
  const int32_t pinB1;
  const int32_t pinA2;  // -1 when none
  const int32_t pinB2;  // -1 when none

  PWMChannel(RPPWM &pwm, IClock &clock, uint32_t index);
  PWMChannel(const PWMChannel &) = delete;
  PWMChannel &operator=(const PWMChannel &) = delete;

  uint32_t readRegister(uint32_t offset);
  void writeRegister(uint32_t offset, uint32_t value);
  void reset();
  void setA(bool value);
  void setB(bool value);
  bool gpioBValue() const;
  void setBDirection(bool value);
  void gpioBChanged();
  void updateEnable();
  /** `set en(value)` (no getter in TS) */
  void setEn(uint32_t value);

 private:
  RPPWM &pwm;

  void updateDoubleBuffered();
  void wrap();
};

class RPPWM : public BasePeripheral {
 public:
  /** `[new PWMChannel(this, this.rp2040.clock, 0), ... 7]` (in the constructor's initialiser list) */
  std::array<PWMChannel, 8> channels;

  uint32_t gpioValue = 0;
  uint32_t gpioDirection = 0;

  RPPWM(RP2040 &rp2040, const std::string &name);

  uint32_t intStatus() const;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

  double clockFreq() const;

  void channelInterrupt(uint32_t index);
  void checkInterrupts();
  void gpioSet(uint32_t index, bool value);
  void gpioSetDir(uint32_t index, bool output);
  bool gpioRead(uint32_t index);
  void gpioOnInput(uint32_t index);
  void reset();

 private:
  uint32_t intRaw = 0;
  uint32_t intEnable = 0;
  uint32_t intForce = 0;
  /**
   * JS numbers: reset() stores the number 4294967295 in gpioDirection, while
   * gpioSetDir computes an int32 (`gpioDirection | bit` is -1). So the first
   * gpioSetDir after a reset sees `4294967295 != -1` and counts as a change
   * even when the bit is already set. True while gpioDirection holds that
   * non-int32 value.
   */
  bool gpioDirectionIsUint32 = false;
};

}  // namespace rp2040js
