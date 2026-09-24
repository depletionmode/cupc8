// Port of rp2040js src/clock/simulation-clock.ts
#include "simulation-clock.h"

#include <utility>

namespace rp2040js {

ClockAlarm::ClockAlarm(SimulationClock &clock, AlarmCallback callback)
    : callback(std::move(callback)), clock(clock) {}

ClockAlarm::~ClockAlarm() { clock.unlinkAlarm(this); }

void ClockAlarm::schedule(double deltaNanos) {
  if (scheduled) {
    cancel();
  }
  clock.linkAlarm(deltaNanos, this);
}

void ClockAlarm::cancel() {
  clock.unlinkAlarm(this);
  scheduled = false;
}

SimulationClock::SimulationClock(double frequency) : frequency(frequency) {}

std::unique_ptr<IAlarm> SimulationClock::createAlarm(ClockEventCallback callback) {
  return std::make_unique<ClockAlarm>(*this, std::move(callback));
}

ClockAlarm *SimulationClock::linkAlarm(double nanos, ClockAlarm *alarm) {
  alarm->nanos = this->nanos() + nanos;
  ClockAlarm *alarmListItem = nextAlarm;
  ClockAlarm *lastItem = nullptr;
  while (alarmListItem && alarmListItem->nanos < alarm->nanos) {
    lastItem = alarmListItem;
    alarmListItem = alarmListItem->next;
  }
  if (lastItem) {
    lastItem->next = alarm;
    alarm->next = alarmListItem;
  } else {
    nextAlarm = alarm;
    alarm->next = alarmListItem;
  }
  alarm->scheduled = true;
  alarm->linked = true;
  return alarm;
}

bool SimulationClock::unlinkAlarm(ClockAlarm *alarm) {
  if (!alarm->linked) {
    return false;  // (the search below would not find it)
  }
  alarm->linked = false;
  ClockAlarm *alarmListItem = nextAlarm;
  if (!alarmListItem) {
    return false;
  }
  ClockAlarm *lastItem = nullptr;
  while (alarmListItem) {
    if (alarmListItem == alarm) {
      if (lastItem) {
        lastItem->next = alarmListItem->next;
      } else {
        nextAlarm = alarmListItem->next;
      }
      return true;
    }
    lastItem = alarmListItem;
    alarmListItem = alarmListItem->next;
  }
  return false;
}

void SimulationClock::fireAlarms(double targetNanos) {
  // tick(deltaNanos): `const targetNanos = this.nanosCounter + deltaNanos` (in the header)
  ClockAlarm *alarm = nextAlarm;
  while (alarm && alarm->nanos <= targetNanos) {
    nextAlarm = alarm->next;
    alarm->linked = false;
    nanosCounter = alarm->nanos;
    alarm->callback();
    alarm = nextAlarm;
  }
  nanosCounter = targetNanos;
}

double SimulationClock::nanosToNextAlarm() const {
  if (nextAlarm) {
    return nextAlarm->nanos - nanos();
  }
  return 0;
}

}  // namespace rp2040js
