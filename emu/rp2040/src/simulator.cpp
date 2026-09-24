// Port of rp2040js src/simulator.ts
#include "simulator.h"

namespace rp2040js {

Simulator::Simulator() : ownedClock(std::make_unique<SimulationClock>()), clock(*ownedClock) {
  rp2040 = std::make_unique<RP2040>(clock);
  rp2040->onBreak = [this](uint32_t) { stop(); };
}

Simulator::Simulator(SimulationClock &clock) : clock(clock) {
  rp2040 = std::make_unique<RP2040>(clock);
  rp2040->onBreak = [this](uint32_t) { stop(); };
}

void Simulator::execute() {
  RP2040 &rp2040 = *this->rp2040;

  stopped = false;
  const double cycleNanos = 1e9 / 125000000;  // 125 MHz
  for (double i = 0; i < 1000000 && !stopped; i++) {
    if (rp2040.waiting()) {
      const double nanosToNextAlarm = clock.nanosToNextAlarm();
      clock.tick(nanosToNextAlarm);
      rp2040.idle(nanosToNextAlarm / cycleNanos);
      i += nanosToNextAlarm / cycleNanos;
    } else {
      const double cycles = rp2040.step();
      clock.tick(cycles * cycleNanos);
    }
  }
  // (TS: if (!this.stopped) this.executeTimer = setTimeout(() => this.execute(), 0);)
}

void Simulator::stop() { stopped = true; }

}  // namespace rp2040js
