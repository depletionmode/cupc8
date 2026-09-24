// The card-test Emu loop in C++: test/emu/rp2040emu.mjs's Emu class, line for
// line (tools/rp2040run.cpp has its own copy of the same loop). Loads the B1
// bootrom and an ELF's flash segments, starts core 0 at boot stage 2 and runs
// both cores, both PIO blocks and the clock together. A test bench hooks in
// with onCycle, called once per PIO cycle exactly where the JS calls
// emu.onCycle (after the PIO steps, before the clock ticks for the batch).
//
//   rp2040js::harness::Emu emu("build/rp2040/gpu.elf", 252, 1.15);
//   emu.runUntil([&] { return done; }, 1e9);            // ns of emulated time
#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "rp2040.h"

namespace rp2040js::harness {

/** the B1 bootrom words (extracted from rp2040js demo/bootrom.ts at build time) */
const std::vector<uint32_t> &bootromB1();

/** copy an ELF's loadable segments into flash (by their physical address) */
void loadElf(const std::string &file, RP2040 &mcu);

class Emu {
 public:
  SimulationClock clock;
  std::unique_ptr<RP2040> mcu;
  double nsPerCycle;
  /** UART0's bytes (String.fromCharCode each) */
  std::string uart;
  /** called after each UART0 byte is appended (optional) */
  std::function<void(uint32_t)> onUartByte;
  /** per-cycle hook (pin-level test benches); empty = none */
  std::function<void()> onCycle;

  // core1Slow: charge core 1 this many times the cycles each instruction
  // takes, to show real-time code has margin (bus contention, cycle-count
  // error) rather than just fitting in the emulator
  Emu(const std::string &elf, double mhz = 125, double core1Slow = 1);
  Emu(const Emu &) = delete;
  Emu &operator=(const Emu &) = delete;

  double ns() const { return clock.nanos(); }

  // one step: an instruction on the core that is behind, and the PIO cycles
  // by which that moved the chip's time on
  void step() {
    if (mcu->waiting()) {
      stepIdle();
      return;
    }
    const double n = mcu->step();  // 0 when the core that ran is still behind the other
    if (n) cycles(n);
  }
  void cycles(double n) {
    if (onCycle) {
      cyclesHooked(n);
    } else {
      stepPIOs(mcu->pio, n);  // the same loop, with lazy PIO cycles in bulk
    }
    clock.tick(n * nsPerCycle);
  }

  // run until cond() is true; false if `ns` of emulated time pass first
  template <class Cond>
  bool runUntil(Cond &&cond, double ns) {
    const double end = clock.nanos() + ns;
    while (clock.nanos() < end) {
      if (cond()) return true;
      for (int i = 0; i < 64; i++) step();
    }
    return cond();
  }

 private:
  /** step() with both cores asleep */
  void stepIdle();
  /** cycles()' PIO loop with the onCycle hook */
  void cyclesHooked(double n);
};

}  // namespace rp2040js::harness
