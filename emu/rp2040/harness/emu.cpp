// See emu.h. Follows test/emu/rp2040emu.mjs.
#include "emu.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>
#include <stdexcept>

#include "utils/js.h"
#include "utils/logging.h"

namespace rp2040js::harness {

const std::vector<uint32_t> &bootromB1() {
  static const std::vector<uint32_t> words = {
#include "bootrom_b1.inc"
  };
  return words;
}

static uint32_t readUInt32LE(const std::vector<uint8_t> &b, size_t at) {
  if (at + 4 > b.size()) throw std::range_error("ELF: read past the end of the file");
  return static_cast<uint32_t>(b[at]) | (static_cast<uint32_t>(b[at + 1]) << 8) |
         (static_cast<uint32_t>(b[at + 2]) << 16) | (static_cast<uint32_t>(b[at + 3]) << 24);
}

static uint32_t readUInt16LE(const std::vector<uint8_t> &b, size_t at) {
  if (at + 2 > b.size()) throw std::range_error("ELF: read past the end of the file");
  return static_cast<uint32_t>(b[at]) | (static_cast<uint32_t>(b[at + 1]) << 8);
}

void loadElf(const std::string &file, RP2040 &mcu) {
  std::ifstream in(file, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open " + file);
  const std::vector<uint8_t> b((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  const uint32_t phoff = readUInt32LE(b, 28), phentsize = readUInt16LE(b, 42), phnum = readUInt16LE(b, 44);
  for (uint32_t i = 0; i < phnum; i++) {
    const size_t h = phoff + static_cast<size_t>(i) * phentsize;
    if (readUInt32LE(b, h) != 1) continue;  // PT_LOAD
    const uint32_t offset = readUInt32LE(b, h + 4), paddr = readUInt32LE(b, h + 12),
                   filesz = readUInt32LE(b, h + 16);
    if (filesz && paddr >= 0x10000000 && paddr < 0x11000000) {
      // Buffer.subarray clamps to the file; Uint8Array.set throws past the flash
      const size_t begin = std::min<size_t>(offset, b.size());
      const size_t end = std::min<size_t>(static_cast<size_t>(offset) + filesz, b.size());
      const size_t dest = paddr - 0x10000000;
      if (dest + (end - begin) > mcu.flash.size()) throw std::range_error("RangeError: offset is out of bounds");
      std::copy(b.begin() + begin, b.begin() + end, mcu.flash.begin() + dest);
    }
  }
}

Emu::Emu(const std::string &elf, double mhz, double core1Slow) {
  mcu = std::make_unique<RP2040>(clock);
  mcu->logger = std::make_shared<ConsoleLogger>(LogLevel::Error);
  mcu->loadBootrom(bootromB1());
  loadElf(elf, *mcu);
  mcu->core0.setPC(0x10000000);  // boot stage 2, as the bootrom would
  nsPerCycle = 1000 / mhz;
  // PIO normally runs itself on setTimeout; we step it with the cores
  for (RPPIO &pio : mcu->pio) pio.run = [] {};
  mcu->uart[0].onByte = [this](uint32_t b) {
    uart += static_cast<char>(b);  // String.fromCharCode
    if (onUartByte) onUartByte(b);
  };
  if (core1Slow != 1) {
    CortexM0Core &core1 = mcu->core1;
    core1.executeInstructionOverride = [&core1, core1Slow, owed = 0.0]() mutable -> uint32_t {
      owed += core1.executeInstruction() * core1Slow;
      const double n = std::floor(owed);
      owed -= n;
      return static_cast<uint32_t>(n);
    };
  }
}

void Emu::step() {
  if (mcu->waiting()) {
    // both cores asleep: skip to the next timer alarm, but no further than
    // one microsecond so PIO and the test bench still see time pass
    const double ns = std::min(clock.nanosToNextAlarm(), 1000.0);
    const double n = std::max(1.0, jsMathRound(ns / nsPerCycle));
    mcu->idle(n);
    cycles(n);
    return;
  }
  const double n = mcu->step();  // 0 when the core that ran is still behind the other
  if (n) cycles(n);
}

void Emu::cycles(double n) {
  if (onCycle) {
    for (double i = 0; i < n; i++) {
      for (RPPIO &pio : mcu->pio)
        if (!pio.stopped) pio.step();
      onCycle();
    }
  } else {
    stepPIOs(mcu->pio, n);  // the same loop, with lazy PIO cycles in bulk
  }
  clock.tick(n * nsPerCycle);
}

}  // namespace rp2040js::harness
