// Port of rp2040js src/peripherals/timer.ts
#include "timer.h"

#include <cmath>
#include <utility>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t TIMEHR = 0x08;
static constexpr uint32_t TIMELR = 0x0c;
static constexpr uint32_t TIMERAWH = 0x24;
static constexpr uint32_t TIMERAWL = 0x28;
static constexpr uint32_t ALARM0 = 0x10;
static constexpr uint32_t ALARM1 = 0x14;
static constexpr uint32_t ALARM2 = 0x18;
static constexpr uint32_t ALARM3 = 0x1c;
static constexpr uint32_t ARMED = 0x20;
static constexpr uint32_t PAUSE = 0x30;
static constexpr uint32_t INTR = 0x34;
static constexpr uint32_t INTE = 0x38;
static constexpr uint32_t INTF = 0x3c;
static constexpr uint32_t INTS = 0x40;

static constexpr uint32_t ALARM_0 = 1 << 0;
static constexpr uint32_t ALARM_1 = 1 << 1;
static constexpr uint32_t ALARM_2 = 1 << 2;
static constexpr uint32_t ALARM_3 = 1 << 3;

static constexpr uint32_t timerInterrupts[] = {IRQ::TIMER_0, IRQ::TIMER_1, IRQ::TIMER_2,
                                               IRQ::TIMER_3};

RPTimerAlarm::RPTimerAlarm(uint32_t bitValue, std::unique_ptr<IAlarm> clockAlarm)
    : bitValue(bitValue), clockAlarm(std::move(clockAlarm)) {}

RPTimer::RPTimer(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      clock(rp2040.clock),
      alarms{{
          {ALARM_0, clock.createAlarm([this] { fireAlarm(0); })},
          {ALARM_1, clock.createAlarm([this] { fireAlarm(1); })},
          {ALARM_2, clock.createAlarm([this] { fireAlarm(2); })},
          {ALARM_3, clock.createAlarm([this] { fireAlarm(3); })},
      }} {}

uint32_t RPTimer::intStatus() const { return (intRaw & intEnable) | intForce; }

uint32_t RPTimer::readUint32(uint32_t offset) {
  const double time = clock.nanos() / 1000;

  switch (offset) {
    case TIMEHR:
      return latchedTimeHigh;

    case TIMELR:
      latchedTimeHigh = static_cast<uint32_t>(std::floor(time / 4294967296.0));
      return toUint32(time);  // `time >>> 0` truncates the fractional microseconds

    case TIMERAWH:
      return static_cast<uint32_t>(std::floor(time / 4294967296.0));

    case TIMERAWL:
      return toUint32(time);

    case ALARM0:
      return alarms[0].targetMicros;
    case ALARM1:
      return alarms[1].targetMicros;
    case ALARM2:
      return alarms[2].targetMicros;
    case ALARM3:
      return alarms[3].targetMicros;

    case PAUSE:
      return paused ? 1 : 0;

    case INTR:
      return intRaw;
    case INTE:
      return intEnable;
    case INTF:
      return intForce;
    case INTS:
      return intStatus();

    case ARMED:
      return (alarms[0].armed ? alarms[0].bitValue : 0) | (alarms[1].armed ? alarms[1].bitValue : 0) |
             (alarms[2].armed ? alarms[2].bitValue : 0) | (alarms[3].armed ? alarms[3].bitValue : 0);
  }
  return BasePeripheral::readUint32(offset);
}

void RPTimer::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case ALARM0:
    case ALARM1:
    case ALARM2:
    case ALARM3: {
      const uint32_t alarmIndex = (offset - ALARM0) / 4;
      RPTimerAlarm &alarm = alarms[alarmIndex];
      // `(value - this.clock.nanos / 1000) >>> 0`: float subtraction, then
      // ToUint32 truncates the fraction (towards zero).
      // JS-SIGN: for a negative int32 `value` (writeUint8/16 byte replication,
      // an atomic alias write with bit 31 set) the difference is negative in TS
      // and truncates the other way: one microsecond more than here when the
      // clock is at a fractional microsecond.
      const uint32_t deltaMicros = toUint32(static_cast<double>(value) - clock.nanos() / 1000);
      alarm.armed = true;
      alarm.targetMicros = value;
      alarm.clockAlarm->schedule(deltaMicros * 1000.0);
      break;
    }
    case ARMED:
      for (RPTimerAlarm &alarm : alarms) {
        if (rawWriteValue & alarm.bitValue) {
          disarmAlarm(alarm);
        }
      }
      break;
    case PAUSE:
      paused = !!(value & 1);
      if (paused) {
        warn("Unimplemented Timer Pause");
      }
      // TODO actually pause the timer
      break;
    case INTR:
      intRaw &= ~rawWriteValue;
      checkInterrupts();
      break;
    case INTE:
      intEnable = value & 0xf;
      checkInterrupts();
      break;
    case INTF:
      intForce = value & 0xf;
      checkInterrupts();
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

void RPTimer::fireAlarm(uint32_t index) {
  RPTimerAlarm &alarm = alarms[index];
  disarmAlarm(alarm);
  intRaw |= alarm.bitValue;
  checkInterrupts();
}

void RPTimer::checkInterrupts() {
  const uint32_t intStatus = this->intStatus();
  for (uint32_t i = 0; i < alarms.size(); i++) {
    rp2040.setInterrupt(timerInterrupts[i], !!(intStatus & (1 << i)));
  }
}

void RPTimer::disarmAlarm(RPTimerAlarm &alarm) {
  alarm.clockAlarm->cancel();
  alarm.armed = false;
}

}  // namespace rp2040js
