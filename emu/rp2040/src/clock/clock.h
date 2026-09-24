// Port of rp2040js src/clock/clock.ts
#pragma once

#include <functional>
#include <memory>

namespace rp2040js {

using AlarmCallback = std::function<void()>;

class IAlarm {
 public:
  virtual ~IAlarm() = default;
  virtual void schedule(double deltaNanos) = 0;
  virtual void cancel() = 0;
};

/**
 * The owner of an alarm (a peripheral) holds the unique_ptr; the clock only
 * links it. The clock must outlive every alarm it created.
 */
class IClock {
 public:
  virtual ~IClock() = default;
  /** `readonly nanos: number` */
  virtual double nanos() const = 0;

  virtual std::unique_ptr<IAlarm> createAlarm(AlarmCallback callback) = 0;
};

}  // namespace rp2040js
