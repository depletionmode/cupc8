// Port of rp2040js src/utils/timer32.ts
//
// All counter/frequency arithmetic here is floating point in TS
// (ticks = elapsed ns / 1e9 * freq, Math.round, %), so every numeric field
// and getter is a double; `counter` is the only `>>> 0` result.
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

#include "../clock/clock.h"

namespace rp2040js {

enum class TimerMode {
  Increment,
  Decrement,
  ZigZag,
};

class Timer32 {
 public:
  IClock &clock;
  std::vector<std::function<void()>> listeners;

  Timer32(IClock &clock, double baseFreq);
  Timer32(const Timer32 &) = delete;
  Timer32 &operator=(const Timer32 &) = delete;

  void reset();
  void set(double value, bool zigZagDown = false);

  /**
   * Advances the counter by the given amount. Note that this will
   * decrease the counter if the timer is running in Decrement mode.
   *
   * @param delta The value to add to the counter. Can be negative.
   */
  void advance(double delta);

  double rawCounter() const;
  uint32_t counter() const;

  double top() const;
  void setTop(double value);

  double frequency() const;
  void setFrequency(double value);

  double prescaler() const;
  void setPrescaler(double value);

  double toNanos(double cycles) const;

  bool enable() const;
  void setEnable(bool value);

  TimerMode mode() const;
  void setMode(TimerMode value);

 private:
  double baseValue = 0;
  double baseNanos = 0;
  double topValue = 0xffffffff;
  double prescalerValue = 1;
  TimerMode timerMode = TimerMode::Increment;
  bool enabled = true;
  double baseFreq;

  void updated();
};

class Timer32PeriodicAlarm {
 public:
  Timer32 &timer;
  const std::function<void()> callback;

  /** Pushes a listener capturing `this` onto timer.listeners: never move or copy. */
  Timer32PeriodicAlarm(Timer32 &timer, std::function<void()> callback);
  Timer32PeriodicAlarm(const Timer32PeriodicAlarm &) = delete;
  Timer32PeriodicAlarm &operator=(const Timer32PeriodicAlarm &) = delete;

  bool enable() const;
  void setEnable(bool value);

  double target() const;
  void setTarget(double value);

  /** `handleAlarm = () => {...}` (the clock alarm's callback) */
  void handleAlarm();
  /** `update = () => {...}` (the timer listener) */
  void update();

 private:
  double targetValue = 0;
  bool enabled = false;
  std::unique_ptr<IAlarm> clockAlarm;

  void schedule();
  void cancel();
};

}  // namespace rp2040js
