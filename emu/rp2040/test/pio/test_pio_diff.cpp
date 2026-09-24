// test_pio_diff: the C++ half of the PIO differential test (see pio_diff.mjs).
//
//   test_pio_diff <scenario> hash <K>     print "h <cycle> <hash>" every K cycles
//   test_pio_diff <scenario> dump <A> <B> print the full state after cycles A..B-1
//   test_pio_diff <scenario> bench        run without observing, print speed
//
// A scenario is a text file written by pio_diff.mjs: "C <cycles>" and then
// events "<cycle> <op> <a> <b>" (hex a/b) applied before that cycle's steps:
//   w addr value   rp2040.writeUint32       r addr   rp2040.readUint32 (observed)
//   g pin value    gpio[pin].setInputValue  t n value TXF write if SM n's TX FIFO is not full
//   x n            RXF read if SM n's RX FIFO is not empty (observed)
// Each cycle is then pio[0].step(); pio[1].step(). Both halves compute the
// same state vector (stateVector in pio_diff.mjs) and hash it identically.
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "rp2040.h"
#include "utils/js.h"

using namespace rp2040js;

namespace {

struct Event {
  uint32_t cycle;
  char op;
  uint32_t a, b;
};

struct Hash {
  uint32_t h = 0x811c9dc5;
  void mix(uint32_t v) {
    h = (h ^ v) * 0x01000193u;
    h ^= h >> 15;
  }
};

constexpr uint32_t PIO_BASE[2] = {0x50200000, 0x50300000};

void smState(const StateMachine &sm, std::vector<uint32_t> &out) {
  out.push_back(sm.enabled ? 1 : 0);
  out.push_back(sm.x);
  out.push_back(sm.y);
  out.push_back(sm.pc);
  out.push_back(sm.inputShiftReg);
  out.push_back(sm.inputShiftCount);
  out.push_back(sm.outputShiftReg);
  out.push_back(sm.outputShiftCount);
  out.push_back(toUint32(sm.cycles));
  out.push_back(toUint32(std::floor(sm.cycles / 4294967296.0)));
  out.push_back(sm.execOpcode);
  out.push_back(sm.execValid ? 1 : 0);
  out.push_back(sm.updatePC ? 1 : 0);
  out.push_back(sm.clockDivInt);
  out.push_back(sm.clockDivFrac);
  out.push_back(sm.debugDivPhase());
  out.push_back(static_cast<uint32_t>(sm.debugDelayLeft()));
  out.push_back(sm.execCtrl);
  out.push_back(sm.shiftCtrl);
  out.push_back(sm.pinCtrl);
  out.push_back(sm.outPinValues);
  out.push_back(sm.outPinDirection);
  out.push_back(sm.waiting ? 1 : 0);
  out.push_back(static_cast<uint32_t>(sm.waitType));
  out.push_back(sm.waitIndex);
  out.push_back(sm.waitPolarity ? 1 : 0);
  out.push_back(static_cast<uint32_t>(sm.waitDelay));
  for (const FIFO *f : {&sm.txFIFO, &sm.rxFIFO}) {
    out.push_back(f->size());
    out.push_back(f->itemCount());
    std::vector<uint32_t> items = f->items();
    for (size_t i = 0; i < 8; i++) {
      out.push_back(i < items.size() ? items[i] : 0);
    }
  }
}

void pioState(const RPPIO &pio, std::vector<uint32_t> &out) {
  for (const StateMachine &sm : pio.machines) {
    smState(sm, out);
  }
  out.push_back(pio.stopped ? 1 : 0);
  out.push_back(pio.fdebug);
  out.push_back(pio.txStall);
  out.push_back(pio.rxStall);
  out.push_back(pio.inputSyncBypass);
  out.push_back(pio.irq);
  out.push_back(pio.pinValues);
  out.push_back(pio.pinDirections);
  out.push_back(pio.oldPinValues);
  out.push_back(pio.oldPinDirections);
  out.push_back(pio.irq0IntEnable);
  out.push_back(pio.irq0IntForce);
  out.push_back(pio.irq1IntEnable);
  out.push_back(pio.irq1IntForce);
  out.push_back(pio.intRaw());
  out.push_back(pio.irq0IntStatus());
  out.push_back(pio.irq1IntStatus());
}

void stateVector(const RP2040 &mcu, bool irqLines, std::vector<uint32_t> &out) {
  out.clear();
  pioState(mcu.pio[0], out);
  pioState(mcu.pio[1], out);
  if (irqLines) {
    out.push_back((mcu.core0.pendingInterrupts >> 7) & 0xf);
  }
}

[[noreturn]] void usage() {
  std::fprintf(stderr, "usage: test_pio_diff <scenario> (hash K | dump A B | bench)\n");
  std::exit(2);
}

}  // namespace

int main(int argc, char **argv) {
  if (argc < 3) {
    usage();
  }
  const std::string mode = argv[2];
  uint32_t hashEvery = 0, dumpFrom = 0, dumpTo = 0;
  if (mode == "hash" && argc == 4) {
    hashEvery = static_cast<uint32_t>(std::stoul(argv[3]));
  } else if (mode == "dump" && argc == 5) {
    dumpFrom = static_cast<uint32_t>(std::stoul(argv[3]));
    dumpTo = static_cast<uint32_t>(std::stoul(argv[4]));
  } else if (mode != "bench") {
    usage();
  }

  std::ifstream in(argv[1]);
  if (!in) {
    std::fprintf(stderr, "cannot read %s\n", argv[1]);
    return 2;
  }
  uint32_t cycles = 0;
  std::vector<Event> events;
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty() || line[0] == '#') {
      continue;
    }
    std::istringstream ls(line);
    if (line[0] == 'C') {
      char c;
      ls >> c >> cycles;
      continue;
    }
    Event e{};
    std::string a, b;
    ls >> e.cycle >> e.op >> a >> b;
    e.a = static_cast<uint32_t>(std::stoul(a, nullptr, 16));
    e.b = b.empty() ? 0 : static_cast<uint32_t>(std::stoul(b, nullptr, 16));
    events.push_back(e);
  }

  RP2040 mcu;
  mcu.pio[0].run = [] {};
  mcu.pio[1].run = [] {};

  // The PIO IRQ lines are observed through core0.pendingInterrupts, but only
  // once cortex-m0-core's setInterrupt is ported (pio_diff.mjs asks us).
  mcu.core0.setInterrupt(31, true);
  const bool irqLines = (mcu.core0.pendingInterrupts >> 31) & 1;
  mcu.core0.setInterrupt(31, false);
  if (mode != "bench") {
    std::printf("irqlines %d\n", irqLines ? 1 : 0);
  }

  const bool dump = mode == "dump";
  const bool bench = mode == "bench";
  Hash hash;
  uint32_t cycle = 0;
  auto observe = [&](const char *what, uint32_t a, uint32_t v) {
    if (bench) {
      return;
    }
    if (dump) {
      if (cycle >= dumpFrom && cycle < dumpTo) {
        std::printf("%s %u %x %x\n", what, cycle, a, v);
      }
    } else {
      hash.mix(0xa5a50000u ^ a);
      hash.mix(v);
    }
  };
  for (uint32_t pin = 0; pin < mcu.gpio.size(); pin++) {
    mcu.gpio[pin].addListener([&, pin](GPIOPinState state, GPIOPinState) {
      observe("gpio", pin, static_cast<uint32_t>(state));
    });
  }

  std::vector<uint32_t> state;
  size_t next = 0;
  const auto t0 = std::chrono::steady_clock::now();
  for (cycle = 0; cycle < cycles; cycle++) {
    for (; next < events.size() && events[next].cycle == cycle; next++) {
      const Event &e = events[next];
      switch (e.op) {
        case 'w':
          mcu.writeUint32(e.a, e.b);
          break;
        case 'r':
          observe("r", e.a, mcu.readUint32(e.a));
          break;
        case 'g':
          mcu.gpio[e.a].setInputValue(e.b != 0);
          break;
        case 't':
          if (!mcu.pio[e.a >> 2].machines[e.a & 3].txFIFO.full()) {
            mcu.writeUint32(PIO_BASE[e.a >> 2] + 0x10 + 4 * (e.a & 3), e.b);
          }
          break;
        case 'x':
          if (!mcu.pio[e.a >> 2].machines[e.a & 3].rxFIFO.empty()) {
            const uint32_t addr = PIO_BASE[e.a >> 2] + 0x20 + 4 * (e.a & 3);
            observe("r", addr, mcu.readUint32(addr));
          }
          break;
        default:
          std::fprintf(stderr, "bad event op %c\n", e.op);
          return 2;
      }
    }
    mcu.pio[0].step();
    mcu.pio[1].step();
    if (bench) {
      continue;
    }
    if (dump) {
      if (cycle >= dumpFrom && cycle < dumpTo) {
        stateVector(mcu, irqLines, state);
        std::printf("s %u", cycle);
        for (uint32_t v : state) {
          std::printf(" %x", v);
        }
        std::printf("\n");
      }
      if (cycle + 1 >= dumpTo) {
        break;
      }
      continue;
    }
    stateVector(mcu, irqLines, state);
    for (uint32_t v : state) {
      hash.mix(v);
    }
    if ((cycle + 1) % hashEvery == 0 || cycle + 1 == cycles) {
      for (const RPPIO &pio : mcu.pio) {
        for (uint32_t v : pio.instructions) {
          hash.mix(v);
        }
      }
      std::printf("h %u %08x\n", cycle, hash.h);
    }
  }
  if (bench) {
    const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("bench %u cycles in %.3f s: %.1f M PIO cycles/s, %.1f M machine-steps/s (8 machines)\n", cycles, s,
                cycles / s / 1e6, cycles * 8.0 / s / 1e6);
  }
  return 0;
}
