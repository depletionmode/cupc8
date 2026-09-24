// Port of rp2040js src/utils/timer32.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "timer32.h"

#include <utility>
#include "js.h"

namespace rp2040js {

Timer32::Timer32(IClock &clock, double baseFreq) : clock(clock), baseFreq(baseFreq) {
  // TODO(port): utils/timer32.ts
  //   constructor(
  //     readonly clock: IClock,
  //     private baseFreq: number,
  //   ) {}
}

void Timer32::reset() {
  // TODO(port): utils/timer32.ts
  //   reset() {
  //     this.baseNanos = this.clock.nanos;
  //     this.baseValue = 0;
  //     this.updated();
  //   }
}

void Timer32::set(double value, bool zigZagDown) {
  // TODO(port): utils/timer32.ts
  //   set(value: number, zigZagDown = false) {
  //     this.baseValue = zigZagDown ? this.topValue * 2 - value : value;
  //     this.baseNanos = this.clock.nanos;
  //     this.updated();
  //   }
  (void)value;
  (void)zigZagDown;
}

void Timer32::advance(double delta) {
  // TODO(port): utils/timer32.ts
  //   advance(delta: number) {
  //     this.baseValue += delta;
  //   }
  (void)delta;
}

double Timer32::rawCounter() const {
  // TODO(port): utils/timer32.ts
  //   get rawCounter() {
  //     const { baseFreq, prescalerValue, baseNanos, baseValue, enabled, timerMode } = this;
  //     if (!baseFreq || !prescalerValue || !enabled) {
  //       return this.baseValue;
  //     }
  //     const zigzag = timerMode == TimerMode.ZigZag;
  //     const ticks = ((this.clock.nanos - baseNanos) / 1e9) * (baseFreq / prescalerValue);
  //     const topModulo = zigzag ? this.topValue * 2 : this.topValue + 1;
  //     const delta = timerMode == TimerMode.Decrement ? topModulo - (ticks % topModulo) : ticks;
  //     let currentValue = Math.round(baseValue + delta);
  //     if (this.topValue != 0xffffffff) {
  //       currentValue %= topModulo;
  //     }
  //     return currentValue;
  //   }
  return 0;
}

uint32_t Timer32::counter() const {
  // TODO(port): utils/timer32.ts
  //   get counter() {
  //     let currentValue = this.rawCounter;
  //     if (this.timerMode == TimerMode.ZigZag && currentValue > this.topValue) {
  //       currentValue = this.topValue * 2 - currentValue;
  //     }
  //     return currentValue >>> 0;
  //   }
  return 0;
}

double Timer32::top() const {
  // TODO(port): utils/timer32.ts
  //   get top() {
  //     return this.topValue;
  //   }
  return 0;
}

void Timer32::setTop(double value) {
  // TODO(port): utils/timer32.ts
  //   set top(value: number) {
  //     const { counter } = this;
  //     this.topValue = value;
  //     this.set(counter <= this.topValue ? counter : 0);
  //   }
  (void)value;
}

double Timer32::frequency() const {
  // TODO(port): utils/timer32.ts
  //   get frequency() {
  //     return this.baseFreq;
  //   }
  return 0;
}

void Timer32::setFrequency(double value) {
  // TODO(port): utils/timer32.ts
  //   set frequency(value: number) {
  //     this.baseValue = this.counter;
  //     this.baseNanos = this.clock.nanos;
  //     this.baseFreq = value;
  //     this.updated();
  //   }
  (void)value;
}

double Timer32::prescaler() const {
  // TODO(port): utils/timer32.ts
  //   get prescaler() {
  //     return this.prescalerValue;
  //   }
  return 0;
}

void Timer32::setPrescaler(double value) {
  // TODO(port): utils/timer32.ts
  //   set prescaler(value: number) {
  //     this.baseValue = this.counter;
  //     this.baseNanos = this.clock.nanos;
  //     this.enabled = this.prescalerValue !== 0;
  //     this.prescalerValue = value;
  //     this.updated();
  //   }
  (void)value;
}

double Timer32::toNanos(double cycles) const {
  // TODO(port): utils/timer32.ts
  //   toNanos(cycles: number) {
  //     const { baseFreq, prescalerValue } = this;
  //     return (cycles * 1e9) / (baseFreq / prescalerValue);
  //   }
  (void)cycles;
  return 0;
}

bool Timer32::enable() const {
  // TODO(port): utils/timer32.ts
  //   get enable() {
  //     return this.enabled;
  //   }
  return false;
}

void Timer32::setEnable(bool value) {
  // TODO(port): utils/timer32.ts
  //   set enable(value: boolean) {
  //     if (value !== this.enabled) {
  //       if (value) {
  //         this.baseNanos = this.clock.nanos;
  //       } else {
  //         this.baseValue = this.counter;
  //       }
  //       this.enabled = value;
  //       this.updated();
  //     }
  //   }
  (void)value;
}

TimerMode Timer32::mode() const {
  // TODO(port): utils/timer32.ts
  //   get mode() {
  //     return this.timerMode;
  //   }
  return TimerMode::Increment;
}

void Timer32::setMode(TimerMode value) {
  // TODO(port): utils/timer32.ts
  //   set mode(value: TimerMode) {
  //     if (this.timerMode !== value) {
  //       const { counter } = this;
  //       this.timerMode = value;
  //       this.set(counter);
  //     }
  //   }
  (void)value;
}

void Timer32::updated() {
  // TODO(port): utils/timer32.ts
  //   private updated() {
  //     for (const listener of this.listeners) {
  //       listener();
  //     }
  //   }
}

Timer32PeriodicAlarm::Timer32PeriodicAlarm(Timer32 &timer, std::function<void()> callback)
    : timer(timer), callback(std::move(callback)) {
  // TODO(port): utils/timer32.ts
  //   constructor(
  //     readonly timer: Timer32,
  //     readonly callback: () => void,
  //   ) {
  //     this.clockAlarm = this.timer.clock.createAlarm(this.handleAlarm);
  //     timer.listeners.push(this.update);
  //   }
}

bool Timer32PeriodicAlarm::enable() const {
  // TODO(port): utils/timer32.ts
  //   get enable() {
  //     return this.enabled;
  //   }
  return false;
}

void Timer32PeriodicAlarm::setEnable(bool value) {
  // TODO(port): utils/timer32.ts
  //   set enable(value: boolean) {
  //     if (value !== this.enabled) {
  //       this.enabled = value;
  //       if (value && this.timer.enable) {
  //         this.schedule();
  //       } else {
  //         this.cancel();
  //       }
  //     }
  //   }
  (void)value;
}

double Timer32PeriodicAlarm::target() const {
  // TODO(port): utils/timer32.ts
  //   get target() {
  //     return this.targetValue;
  //   }
  return 0;
}

void Timer32PeriodicAlarm::setTarget(double value) {
  // TODO(port): utils/timer32.ts
  //   set target(value: number) {
  //     if (value === this.targetValue) {
  //       return;
  //     }
  //     this.targetValue = value;
  //     if (this.enabled && this.timer.enable) {
  //       this.cancel();
  //       this.schedule();
  //     }
  //   }
  (void)value;
}

void Timer32PeriodicAlarm::handleAlarm() {
  // TODO(port): utils/timer32.ts
  //   handleAlarm = () => {
  //     this.callback();
  //     if (this.enabled && this.timer.enable) {
  //       this.schedule();
  //     }
  //   };
}

void Timer32PeriodicAlarm::update() {
  // TODO(port): utils/timer32.ts
  //   update = () => {
  //     this.cancel();
  //     if (this.enabled && this.timer.enable) {
  //       this.schedule();
  //     }
  //   };
}

void Timer32PeriodicAlarm::schedule() {
  // TODO(port): utils/timer32.ts
  //   private schedule() {
  //     const { timer, targetValue } = this;
  //     const { top, mode, rawCounter } = timer;
  //     let cycleDelta = targetValue - rawCounter;
  //     if (mode === TimerMode.ZigZag && cycleDelta < 0) {
  //       if (cycleDelta < -top) {
  //         cycleDelta += 2 * top;
  //       } else {
  //         cycleDelta = top * 2 - targetValue - rawCounter;
  //       }
  //     }
  //     if (top != 0xffffffff) {
  //       if (cycleDelta <= 0) {
  //         cycleDelta += top + 1;
  //       }
  //       if (targetValue > top) {
  //         // Skip alarm
  //         return;
  //       }
  //     }
  //     if (mode === TimerMode.Decrement) {
  //       cycleDelta = top + 1 - cycleDelta;
  //     }
  //     const cyclesToAlarm = cycleDelta >>> 0;
  //     const nanosToAlarm = timer.toNanos(cyclesToAlarm);
  //     this.clockAlarm.schedule(nanosToAlarm);
  //   }
}

void Timer32PeriodicAlarm::cancel() {
  // TODO(port): utils/timer32.ts
  //   private cancel() {
  //     this.clockAlarm.cancel();
  //   }
}

}  // namespace rp2040js
