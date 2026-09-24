// test_runsteps: RP2040::runSteps (the Emu loop in one function, what
// Emu::runUntil and rp2040run use without an onCycle hook) against the plain
// loop of Emu::step() calls (EMU-005, `steps`).
//
//   test_runsteps <build/rp2040 dir> [--ns N] [--seed N]
//
// Each card image (gpu at 252 MHz, io, sysctl, the self-test; the gpu also
// with --core1-slow 1.15) runs on two chips: one by Emu::step(), one by
// runSteps in random-length runs (1..300 steps, some stopped by a time limit
// instead). After every run the chips must have the same time, the same
// state of both cores (registers, flags, cycles, sleep and interrupt state),
// the same PIO state and the same UART output.
//
// Prints one line, PASS or FAIL, and exits 0 on PASS.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "emu.h"

using namespace rp2040js;
using rp2040js::harness::Emu;

namespace {

uint32_t rngState = 7;
uint32_t rnd() {
  rngState ^= rngState << 13;
  rngState ^= rngState >> 17;
  rngState ^= rngState << 5;
  return rngState;
}

std::string state(Emu &e) {
  RP2040 &m = *e.mcu;
  m.syncPIO();
  std::string s;
  char b[128];
  snprintf(b, sizeof b, "ns=%.17g ", e.ns());
  s += b;
  for (CortexM0Core *c : m.cores) {
    for (uint32_t r : c->registers) {
      snprintf(b, sizeof b, "%x ", r);
      s += b;
    }
    snprintf(b, sizeof b, "%x %x %.0f %d%d%d %x %x %d ", c->xPSR(), c->bankedSP, c->cycles, c->waiting,
             c->waitingForEvent, c->eventRegistered, c->pendingInterrupts, c->enabledInterrupts, c->interruptsUpdated);
    s += b;
  }
  for (RPPIO &p : m.pio) {
    snprintf(b, sizeof b, "pio %x %x %x ", p.pinValues, p.pinDirections, p.irq);
    s += b;
    for (StateMachine &sm : p.machines) {
      snprintf(b, sizeof b, "%x %x %x %x ", sm.pc, sm.x, sm.y, sm.outputShiftCount);
      s += b;
    }
  }
  s += "uart=" + std::to_string(e.uart.size());
  return s;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: test_runsteps <build/rp2040 dir> [--ns N] [--seed N]\n");
    return 2;
  }
  const std::string dir = argv[1];
  double ns = 10e6;
  for (int i = 2; i + 1 < argc; i += 2) {
    if (!strcmp(argv[i], "--ns")) ns = strtod(argv[i + 1], nullptr);
    if (!strcmp(argv[i], "--seed")) rngState = static_cast<uint32_t>(strtoul(argv[i + 1], nullptr, 0)) | 1;
  }
  struct Case {
    const char *elf;
    double mhz, core1Slow;
  };
  const Case cases[] = {
      {"gpu.elf", 252, 1}, {"gpu.elf", 252, 1.15}, {"io.elf", 125, 1}, {"sysctl.elf", 125, 1}, {"emu_selftest.elf", 125, 1},
  };
  uint64_t runs = 0, steps = 0;
  for (const Case &c : cases) {
    Emu a(dir + "/" + c.elf, c.mhz, c.core1Slow), b(dir + "/" + c.elf, c.mhz, c.core1Slow);
    while (a.ns() < ns) {
      if (rnd() % 8 == 0) {
        // a time limit: `while (emu.ns() < t) emu.step()` on one, runTo(t) on the other
        const double t = a.ns() + static_cast<double>(rnd() % 3000);
        while (a.ns() < t) {
          a.step();
          steps++;
        }
        b.runTo(t);
      } else {
        const uint64_t k = 1 + rnd() % 300;
        for (uint64_t i = 0; i < k; i++) a.step();
        b.steps(k);
        steps += k;
      }
      runs++;
      const std::string sa = state(a), sb = state(b);
      if (sa != sb || a.uart != b.uart) {
        printf("MISMATCH %s (core1Slow %g) after %llu runs, %llu steps\n  step():   %s\n  runSteps: %s\n", c.elf,
               c.core1Slow, static_cast<unsigned long long>(runs), static_cast<unsigned long long>(steps),
               sa.c_str(), sb.c_str());
        printf("FAIL steps: runSteps differs from Emu::step()\n");
        return 1;
      }
    }
  }
  printf("PASS steps: %llu runs, %llu steps, runSteps = Emu::step() on every card image\n",
         static_cast<unsigned long long>(runs), static_cast<unsigned long long>(steps));
  return 0;
}
