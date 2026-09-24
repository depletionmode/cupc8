// Port of rp2040js src/clock/simulation-clock.ts
#pragma once

#include <memory>

#include "clock.h"

namespace rp2040js {

class SimulationClock;

using ClockEventCallback = std::function<void()>;

class ClockAlarm : public IAlarm {
 public:
  ClockAlarm *next = nullptr;
  double nanos = 0;
  bool scheduled = false;
  /** Not in TS: whether the alarm is in the clock's list (a fired alarm is
   * not, but keeps `scheduled`), so that unlinking one that is not in the
   * list skips the search that would not find it. */
  bool linked = false;

  ClockAlarm(SimulationClock &clock, AlarmCallback callback);
  /** Not in TS (GC): unlinks the alarm so the clock never holds a dangling pointer. */
  ~ClockAlarm() override;
  ClockAlarm(const ClockAlarm &) = delete;
  ClockAlarm &operator=(const ClockAlarm &) = delete;

  void schedule(double deltaNanos) override;
  void cancel() override;

  const AlarmCallback callback;

 private:
  SimulationClock &clock;
};

class SimulationClock : public IClock {
 public:
  const double frequency;

  explicit SimulationClock(double frequency = 125e6);

  double nanos() const override { return nanosCounter; }
  double micros() const { return nanos() / 1000; }

  std::unique_ptr<IAlarm> createAlarm(ClockEventCallback callback) override;

  ClockAlarm *linkAlarm(double nanos, ClockAlarm *alarm);
  bool unlinkAlarm(ClockAlarm *alarm);
  void tick(double deltaNanos) {
    // (the loop below, inline for the common case of no alarm due)
    const double targetNanos = nanosCounter + deltaNanos;
    if (!nextAlarm || nextAlarm->nanos > targetNanos) {
      nanosCounter = targetNanos;
      return;
    }
    fireAlarms(targetNanos);
  }
  double nanosToNextAlarm() const;

 private:
  /** tick()'s loop: fire the alarms due by targetNanos, then move to it */
  void fireAlarms(double targetNanos);
  ClockAlarm *nextAlarm = nullptr;

  double nanosCounter = 0;
};

}  // namespace rp2040js
