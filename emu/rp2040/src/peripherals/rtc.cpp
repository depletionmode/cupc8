// Port of rp2040js src/peripherals/rtc.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "rtc.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RP2040RTC::RP2040RTC(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {
  // TODO(port): peripherals/rtc.ts
  //   baseline = new Date(2021, 0, 1);
}

uint32_t RP2040RTC::readUint32(uint32_t offset) {
  // TODO(port): peripherals/rtc.ts
  //   readUint32(offset: number) {
  //     const date = new Date(
  //       this.baseline.getTime() + (this.rp2040.clock.nanos - this.baselineNanos) / 1_000_000,
  //     );
  //     switch (offset) {
  //       case RTC_SETUP0:
  //         return this.setup0;
  //       case RTC_SETUP1:
  //         return this.setup1;
  //       case RTC_CTRL:
  //         return this.ctrl;
  //       case IRQ_SETUP_0:
  //         return 0;
  //       case RTC_RTC1:
  //         return (
  //           ((date.getFullYear() & RTC_0_YEAR_MASK) << RTC_0_YEAR_SHIFT) |
  //           (((date.getMonth() + 1) & RTC_0_MONTH_MASK) << RTC_0_MONTH_SHIFT) |
  //           ((date.getDate() & RTC_0_DAY_MASK) << RTC_0_DAY_SHIFT)
  //         );
  //       case RTC_RTC0:
  //         return (
  //           ((date.getDay() & RTC_1_DOTW_MASK) << RTC_1_DOTW_SHIFT) |
  //           ((date.getHours() & RTC_1_HOUR_MASK) << RTC_1_HOUR_SHIFT) |
  //           ((date.getMinutes() & RTC_1_MIN_MASK) << RTC_1_MIN_SHIFT) |
  //           ((date.getSeconds() & RTC_1_SEC_MASK) << RTC_1_SEC_SHIFT)
  //         );
  //       default:
  //         break;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/rtc.ts", "RP2040RTC::readUint32");
}

void RP2040RTC::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/rtc.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case RTC_SETUP0:
  //         this.setup0 = value;
  //         break;
  //       case RTC_SETUP1:
  //         this.setup1 = value;
  //         break;
  //       case RTC_CTRL:
  //         // Though RTC_LOAD_BITS is type SC and should be cleared on next cycle, pico-sdk write
  //         // RTC_LOAD_BITS & RTC_ENABLE_BITS seperatly.
  //         // https://github.com/raspberrypi/pico-sdk/blob/master/src/rp2_common/hardware_rtc/rtc.c#L76-L80
  //         if (value & RTC_LOAD_BITS) {
  //           this.ctrl |= RTC_LOAD_BITS;
  //         }
  //         if (value & RTC_ENABLE_BITS) {
  //           this.ctrl |= RTC_ENABLE_BITS;
  //           this.ctrl |= RTC_ACTIVE_BITS;
  //           if (this.ctrl & RTC_LOAD_BITS) {
  //             const year = (this.setup0 >> SETUP_0_YEAR_SHIFT) & SETUP_0_YEAR_MASK;
  //             const month = (this.setup0 >> SETUP_0_MONTH_SHIFT) & SETUP_0_MONTH_MASK;
  //             const day = (this.setup0 >> SETUP_0_DAY_SHIFT) & SETUP_0_DAY_MASK;
  //             const hour = (this.setup1 >> SETUP_1_HOUR_SHIFT) & SETUP_1_HOUR_MASK;
  //             const min = (this.setup1 >> SETUP_1_MIN_SHIFT) & SETUP_1_MIN_MASK;
  //             const sec = (this.setup1 >> SETUP_1_SEC_SHIFT) & SETUP_1_SEC_MASK;
  //             this.baseline = new Date(year, month - 1, day, hour, min, sec);
  //             this.baselineNanos = this.rp2040.clock.nanos;
  //             this.ctrl &= ~RTC_LOAD_BITS;
  //           }
  //         } else {
  //           this.ctrl &= ~RTC_ENABLE_BITS;
  //           this.ctrl &= ~RTC_ACTIVE_BITS;
  //         }
  //         break;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/rtc.ts", "RP2040RTC::writeUint32");
}

}  // namespace rp2040js
