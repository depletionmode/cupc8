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
  void tick(double deltaNanos);
  double nanosToNextAlarm() const;

 private:
  ClockAlarm *nextAlarm = nullptr;

  double nanosCounter = 0;
};

}  // namespace rp2040js
