// Port of rp2040js src/utils/timer32.ts
//
// Float math throughout, exactly as the JS numbers: ticks are
// ((nanos - baseNanos) / 1e9) * (baseFreq / prescaler), `%` is fmod,
// Math.round is jsMathRound.
#include "timer32.h"

#include <cmath>
#include <utility>

#include "js.h"

namespace rp2040js {

Timer32::Timer32(IClock &clock, double baseFreq)
    : clock(clock), baseFreq(baseFreq), tickRate(baseFreq / prescalerValue) {}

/** `x % m` (fmod) for integral x and m, without the library call where exact */
static inline double modIntegral(double x, double m) {
  if (x != 0 && std::fabs(x) < 4611686018427387904.0 && m >= 1 && m < 4611686018427387904.0) {
    const int64_t xi = static_cast<int64_t>(x), mi = static_cast<int64_t>(m);
    if (static_cast<double>(xi) == x && static_cast<double>(mi) == m) {
      // both integers below 2**62: C++'s % truncates like fmod, and its
      // result is exact; a zero result keeps x's sign, as fmod's does
      const int64_t r = xi % mi;
      return r ? static_cast<double>(r) : std::copysign(0.0, x);
    }
  }
  return std::fmod(x, m);
}

void Timer32::reset() {
  baseNanos = clock.nanos();
  baseValue = 0;
  updated();
}

void Timer32::set(double value, bool zigZagDown) {
  baseValue = zigZagDown ? topValue * 2 - value : value;
  baseNanos = clock.nanos();
  updated();
}

void Timer32::advance(double delta) { baseValue += delta; }

double Timer32::rawCounter() const {
  // const { baseFreq, prescalerValue, baseNanos, baseValue, enabled, timerMode } = this;
  if (!baseFreq || !prescalerValue || !enabled) {
    return baseValue;
  }
  const bool zigzag = timerMode == TimerMode::ZigZag;
  const double ticks = ((clock.nanos() - baseNanos) / 1e9) * tickRate;  // tickRate: baseFreq / prescalerValue
  const double topModulo = zigzag ? topValue * 2 : topValue + 1;
  const double delta =
      timerMode == TimerMode::Decrement ? topModulo - std::fmod(ticks, topModulo) : ticks;
  double currentValue = jsMathRound(baseValue + delta);
  if (topValue != 0xffffffff) {
    currentValue = modIntegral(currentValue, topModulo);  // std::fmod(currentValue, topModulo)
  }
  return currentValue;
}

uint32_t Timer32::counter() const {
  double currentValue = rawCounter();
  if (timerMode == TimerMode::ZigZag && currentValue > topValue) {
    currentValue = topValue * 2 - currentValue;
  }
  return toUint32(currentValue);
}

double Timer32::top() const { return topValue; }

void Timer32::setTop(double value) {
  const double counter = this->counter();
  topValue = value;
  set(counter <= topValue ? counter : 0);
}

double Timer32::frequency() const { return baseFreq; }

void Timer32::setFrequency(double value) {
  baseValue = counter();
  baseNanos = clock.nanos();
  baseFreq = value;
  tickRate = baseFreq / prescalerValue;
  updated();
}

double Timer32::prescaler() const { return prescalerValue; }

void Timer32::setPrescaler(double value) {
  baseValue = counter();
  baseNanos = clock.nanos();
  // TS bug (kept): tests the old prescaler value, before assigning the new one.
  enabled = prescalerValue != 0;
  prescalerValue = value;
  tickRate = baseFreq / prescalerValue;
  updated();
}

double Timer32::toNanos(double cycles) const {
  return (cycles * 1e9) / tickRate;  // tickRate: baseFreq / prescalerValue
}

bool Timer32::enable() const { return enabled; }

void Timer32::setEnable(bool value) {
  if (value != enabled) {
    if (value) {
      baseNanos = clock.nanos();
    } else {
      baseValue = counter();
    }
    enabled = value;
    updated();
  }
}

TimerMode Timer32::mode() const { return timerMode; }

void Timer32::setMode(TimerMode value) {
  if (timerMode != value) {
    const double counter = this->counter();
    timerMode = value;
    set(counter);
  }
}

void Timer32::updated() {
  // `for (const listener of this.listeners)`: listeners are only added at construction
  for (size_t i = 0; i < listeners.size(); i++) {
    listeners[i]();
  }
}

Timer32PeriodicAlarm::Timer32PeriodicAlarm(Timer32 &timer, std::function<void()> callback)
    : timer(timer), callback(std::move(callback)) {
  clockAlarm = timer.clock.createAlarm([this] { handleAlarm(); });
  timer.listeners.push_back([this] { update(); });
}

bool Timer32PeriodicAlarm::enable() const { return enabled; }

void Timer32PeriodicAlarm::setEnable(bool value) {
  if (value != enabled) {
    enabled = value;
    if (value && timer.enable()) {
      schedule();
    } else {
      cancel();
    }
  }
}

double Timer32PeriodicAlarm::target() const { return targetValue; }

void Timer32PeriodicAlarm::setTarget(double value) {
  if (value == targetValue) {
    return;
  }
  targetValue = value;
  if (enabled && timer.enable()) {
    cancel();
    schedule();
  }
}

void Timer32PeriodicAlarm::handleAlarm() {
  callback();
  if (enabled && timer.enable()) {
    schedule();
  }
}

void Timer32PeriodicAlarm::update() {
  cancel();
  if (enabled && timer.enable()) {
    schedule();
  }
}

void Timer32PeriodicAlarm::schedule() {
  const double top = timer.top();
  const TimerMode mode = timer.mode();
  const double rawCounter = timer.rawCounter();
  double cycleDelta = targetValue - rawCounter;
  if (mode == TimerMode::ZigZag && cycleDelta < 0) {
    if (cycleDelta < -top) {
      cycleDelta += 2 * top;
    } else {
      cycleDelta = top * 2 - targetValue - rawCounter;
    }
  }
  if (top != 0xffffffff) {
    if (cycleDelta <= 0) {
      cycleDelta += top + 1;
    }
    if (targetValue > top) {
      // Skip alarm
      return;
    }
  }
  if (mode == TimerMode::Decrement) {
    cycleDelta = top + 1 - cycleDelta;
  }
  const uint32_t cyclesToAlarm = toUint32(cycleDelta);
  const double nanosToAlarm = timer.toNanos(cyclesToAlarm);
  clockAlarm->schedule(nanosToAlarm);
}

void Timer32PeriodicAlarm::cancel() { clockAlarm->cancel(); }

}  // namespace rp2040js
