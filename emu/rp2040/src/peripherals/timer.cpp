// Port of rp2040js src/peripherals/timer.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "timer.h"

#include <utility>
#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPTimerAlarm::RPTimerAlarm(uint32_t bitValue, std::unique_ptr<IAlarm> clockAlarm)
    : bitValue(bitValue), clockAlarm(std::move(clockAlarm)) {
  // TODO(port): peripherals/timer.ts
  //   constructor(
  //     readonly bitValue: number,
  //     readonly clockAlarm: IAlarm,
  //   ) {}
}

RPTimer::RPTimer(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      clock(rp2040.clock),
      alarms{{
          {1u << 0, clock.createAlarm([this] { fireAlarm(0); })},
          {1u << 1, clock.createAlarm([this] { fireAlarm(1); })},
          {1u << 2, clock.createAlarm([this] { fireAlarm(2); })},
          {1u << 3, clock.createAlarm([this] { fireAlarm(3); })},
      }} {
  // TODO(port): peripherals/timer.ts
  //   constructor(rp2040: RP2040, name: string) {
  //     super(rp2040, name);
  //     this.clock = rp2040.clock;
  //     this.alarms = [
  //       new RPTimerAlarm(
  //         ALARM_0,
  //         this.clock.createAlarm(() => this.fireAlarm(0)),
  //       ),
  //       new RPTimerAlarm(
  //         ALARM_1,
  //         this.clock.createAlarm(() => this.fireAlarm(1)),
  //       ),
  //       new RPTimerAlarm(
  //         ALARM_2,
  //         this.clock.createAlarm(() => this.fireAlarm(2)),
  //       ),
  //       new RPTimerAlarm(
  //         ALARM_3,
  //         this.clock.createAlarm(() => this.fireAlarm(3)),
  //       ),
  //     ];
  //   }
}

uint32_t RPTimer::intStatus() const {
  // TODO(port): peripherals/timer.ts
  //   get intStatus() {
  //     return (this.intRaw & this.intEnable) | this.intForce;
  //   }
  return 0;
}

uint32_t RPTimer::readUint32(uint32_t offset) {
  // TODO(port): peripherals/timer.ts
  //   readUint32(offset: number) {
  //     const time = this.clock.nanos / 1000;
  //
  //     switch (offset) {
  //       case TIMEHR:
  //         return this.latchedTimeHigh;
  //
  //       case TIMELR:
  //         this.latchedTimeHigh = Math.floor(time / 2 ** 32);
  //         return time >>> 0;
  //
  //       case TIMERAWH:
  //         return Math.floor(time / 2 ** 32);
  //
  //       case TIMERAWL:
  //         return time >>> 0;
  //
  //       case ALARM0:
  //         return this.alarms[0].targetMicros;
  //       case ALARM1:
  //         return this.alarms[1].targetMicros;
  //       case ALARM2:
  //         return this.alarms[2].targetMicros;
  //       case ALARM3:
  //         return this.alarms[3].targetMicros;
  //
  //       case PAUSE:
  //         return this.paused ? 1 : 0;
  //
  //       case INTR:
  //         return this.intRaw;
  //       case INTE:
  //         return this.intEnable;
  //       case INTF:
  //         return this.intForce;
  //       case INTS:
  //         return this.intStatus;
  //
  //       case ARMED:
  //         return (
  //           (this.alarms[0].armed ? this.alarms[0].bitValue : 0) |
  //           (this.alarms[1].armed ? this.alarms[1].bitValue : 0) |
  //           (this.alarms[2].armed ? this.alarms[2].bitValue : 0) |
  //           (this.alarms[3].armed ? this.alarms[3].bitValue : 0)
  //         );
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/timer.ts", "RPTimer::readUint32");
}

void RPTimer::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/timer.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case ALARM0:
  //       case ALARM1:
  //       case ALARM2:
  //       case ALARM3: {
  //         const alarmIndex = (offset - ALARM0) / 4;
  //         const alarm = this.alarms[alarmIndex];
  //         const deltaMicros = (value - this.clock.nanos / 1000) >>> 0;
  //         alarm.armed = true;
  //         alarm.targetMicros = value;
  //         alarm.clockAlarm.schedule(deltaMicros * 1000);
  //         break;
  //       }
  //       case ARMED:
  //         for (const alarm of this.alarms) {
  //           if (this.rawWriteValue & alarm.bitValue) {
  //             this.disarmAlarm(alarm);
  //           }
  //         }
  //         break;
  //       case PAUSE:
  //         this.paused = !!(value & 1);
  //         if (this.paused) {
  //           this.warn('Unimplemented Timer Pause');
  //         }
  //         // TODO actually pause the timer
  //         break;
  //       case INTR:
  //         this.intRaw &= ~this.rawWriteValue;
  //         this.checkInterrupts();
  //         break;
  //       case INTE:
  //         this.intEnable = value & 0xf;
  //         this.checkInterrupts();
  //         break;
  //       case INTF:
  //         this.intForce = value & 0xf;
  //         this.checkInterrupts();
  //         break;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/timer.ts", "RPTimer::writeUint32");
}

void RPTimer::fireAlarm(uint32_t index) {
  // TODO(port): peripherals/timer.ts
  //   private fireAlarm(index: number) {
  //     const alarm = this.alarms[index];
  //     this.disarmAlarm(alarm);
  //     this.intRaw |= alarm.bitValue;
  //     this.checkInterrupts();
  //   }
  (void)index;
}

void RPTimer::checkInterrupts() {
  // TODO(port): peripherals/timer.ts
  //   private checkInterrupts() {
  //     const { intStatus } = this;
  //     for (let i = 0; i < this.alarms.length; i++) {
  //       this.rp2040.setInterrupt(timerInterrupts[i], !!(intStatus & (1 << i)));
  //     }
  //   }
}

void RPTimer::disarmAlarm(RPTimerAlarm &alarm) {
  // TODO(port): peripherals/timer.ts
  //   private disarmAlarm(alarm: RPTimerAlarm) {
  //     alarm.clockAlarm.cancel();
  //     alarm.armed = false;
  //   }
  (void)alarm;
}

}  // namespace rp2040js
