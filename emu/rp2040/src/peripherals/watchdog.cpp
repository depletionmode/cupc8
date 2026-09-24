// Port of rp2040js src/peripherals/watchdog.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "watchdog.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPWatchdog::RPWatchdog(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {
  // TODO(port): peripherals/watchdog.ts
  //   constructor(rp2040: RP2040, name: string) {
  //     super(rp2040, name);
  //     this.timer = new Timer32(rp2040.clock, TICK_FREQUENCY);
  //     this.timer.mode = TimerMode.Decrement;
  //     this.timer.enable = false;
  //     this.alarm = new Timer32PeriodicAlarm(this.timer, () => {
  //       this.reason = TIMER;
  //       this.onWatchdogTrigger?.();
  //     });
  //     this.alarm.target = 0;
  //     this.alarm.enable = false;
  //   }
  (void)rp2040;
  (void)name;
  // TODO(port): the onWatchdogTrigger default
  //   onWatchdogTrigger = () => {
  //     this.rp2040.logger.warn(this.name, 'Watchdog triggered, but no reset handler provided');
  //   };
}

uint32_t RPWatchdog::readUint32(uint32_t offset) {
  // TODO(port): peripherals/watchdog.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case CTRL:
  //         return (
  //           (this.timer.enable ? ENABLE : 0) |
  //           (this.pauseDbg0 ? PAUSE_DBG0 : 0) |
  //           (this.pauseDbg1 ? PAUSE_DBG1 : 0) |
  //           (this.pauseJtag ? PAUSE_JTAG : 0) |
  //           ((this.timer.counter & TIME_MASK) << TIME_SHIFT)
  //         );
  //
  //       case REASON:
  //         return this.reason;
  //
  //       case SCRATCH0:
  //       case SCRATCH1:
  //       case SCRATCH2:
  //       case SCRATCH3:
  //       case SCRATCH4:
  //       case SCRATCH5:
  //       case SCRATCH6:
  //       case SCRATCH7:
  //         return this.scratchData[(offset - SCRATCH0) >> 2];
  //
  //       case TICK:
  //         // TODO COUNT bits
  //         return this.tickEnable ? RUNNING | TICK_ENABLE : 0;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/watchdog.ts", "RPWatchdog::readUint32");
}

void RPWatchdog::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/watchdog.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case CTRL:
  //         if (value & TRIGGER) {
  //           this.reason = FORCE;
  //           this.onWatchdogTrigger?.();
  //         }
  //         this.enable = !!(value & ENABLE);
  //         this.timer.enable = this.enable && this.tickEnable;
  //         this.alarm.enable = this.enable && this.tickEnable;
  //         this.pauseDbg0 = !!(value & PAUSE_DBG0);
  //         this.pauseDbg1 = !!(value & PAUSE_DBG1);
  //         this.pauseJtag = !!(value & PAUSE_JTAG);
  //         break;
  //
  //       case LOAD:
  //         this.timer.set((value >>> LOAD_SHIFT) & LOAD_MASK);
  //         break;
  //
  //       case SCRATCH0:
  //       case SCRATCH1:
  //       case SCRATCH2:
  //       case SCRATCH3:
  //       case SCRATCH4:
  //       case SCRATCH5:
  //       case SCRATCH6:
  //       case SCRATCH7:
  //         this.scratchData[(offset - SCRATCH0) >> 2] = value;
  //         break;
  //
  //       case TICK:
  //         this.tickEnable = !!(value & TICK_ENABLE);
  //         this.timer.enable = this.enable && this.tickEnable;
  //         this.alarm.enable = this.enable && this.tickEnable;
  //         // TODO - handle CYCLES (tick also affectes timer)
  //         break;
  //
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/watchdog.ts", "RPWatchdog::writeUint32");
}

}  // namespace rp2040js
