// test/emu/rp2040emu.mjs's Emu class on the native RP2040 (emu/rp2040): the
// B1 bootrom, the ELF's flash segments, core 0 started at 0x10000000, and the
// one step() loop that steps both cores, both PIO blocks and the clock
// together (the same loop as emu/rp2040/tools/rp2040run.cpp).
#pragma once

#include <memory>
#include <string>

#include "clock/simulation-clock.h"
#include "rp2040.h"
#include "utils/js.h"

namespace machine {

class Emu {
 public:
  rp2040js::SimulationClock clock;
  std::unique_ptr<rp2040js::RP2040> mcu;
  double nsPerCycle;
  std::string uart;  // UART0, one char per byte (String.fromCharCode)

  Emu(const std::string &elf, double mhz);
  Emu(const Emu &) = delete;
  Emu &operator=(const Emu &) = delete;

  double ns() const { return clock.nanos(); }

  // one step: an instruction on the core that is behind, and the PIO cycles
  // by which that moved the chip's time on
  void step() {
    if (mcu->waiting()) {
      // both cores asleep: skip to the next timer alarm, but no further than
      // one microsecond so PIO and the test bench still see time pass
      const double ns = std::min(clock.nanosToNextAlarm(), 1000.0);
      const double cycles = std::max(1.0, rp2040js::jsMathRound(ns / nsPerCycle));
      mcu->idle(cycles);
      this->cycles(cycles);
      return;
    }
    const double cycles = mcu->step();  // 0 when the core that ran is still behind the other
    if (cycles) this->cycles(cycles);
  }

  void cycles(double n) {
    for (double i = 0; i < n; i++) {
      for (rp2040js::RPPIO &pio : mcu->pio)
        if (!pio.stopped) pio.step();
    }
    clock.tick(n * nsPerCycle);
  }

  // Rp2040Card.advance: run until the chip's time reaches `ns`
  void advance(double ns) {
    while (clock.nanos() < ns) step();
  }
};

}  // namespace machine
