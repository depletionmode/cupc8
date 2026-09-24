// Port of rp2040js src/simulator.ts (cupc8 patch: both cores, rp2040.idle()).
//
// Not needed by the chip; kept for parity. There is no event loop, so
// execute() runs one batch (up to 1000000 iterations) and returns instead of
// re-arming itself with setTimeout; call it again while executing().
// IGDBTarget (gdb/*) is not ported.
#pragma once

#include <memory>

#include "clock/simulation-clock.h"
#include "rp2040.h"

namespace rp2040js {

class Simulator {
 public:
  /** `constructor(readonly clock = new SimulationClock())` */
  std::unique_ptr<SimulationClock> ownedClock;
  SimulationClock &clock;
  std::unique_ptr<RP2040> rp2040;
  bool stopped = true;

  Simulator();
  explicit Simulator(SimulationClock &clock);

  void execute();
  void stop();
  bool executing() const { return !stopped; }
};

}  // namespace rp2040js
