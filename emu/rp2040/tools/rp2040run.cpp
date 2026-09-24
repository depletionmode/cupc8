// rp2040run: the native counterpart of test/emu/rp2040emu.mjs (the Emu class)
// plus the per-cycle GPIO toggle of test/emu/run_nested.mjs.
//
//   rp2040run <elf> --until <regex> --max-ns <ns> [--mhz N] [--core1-slow F]
//             [--toggle-gpio PIN:EVERY_N_CYCLES] [--trace-every N]
//
// Loads the B1 bootrom and the ELF's flash segments, starts core 0 at
// 0x10000000 (boot stage 2, as the bootrom would), runs until the UART0 text
// matches <regex> (ECMAScript syntax, searched like RegExp.test) or <ns> of
// emulated time pass, prints the UART0 text to stdout and exits 0 on a match,
// 1 otherwise. --trace-every N prints "<ns> <pc0> <pc1>" to stderr after every
// Nth step() (ns as JS prints the number, pcs as 8 lowercase hex digits).
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <fstream>
#include <functional>
#include <iterator>
#include <memory>
#include <regex>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "rp2040.h"
#include "utils/js.h"
#include "utils/logging.h"

using namespace rp2040js;

// the B1 bootrom ships with rp2040js as TypeScript source in its demo;
// CMake extracts its words the way rp2040emu.mjs's bootrom() does.
static const std::vector<uint32_t> &bootrom() {
  static const std::vector<uint32_t> words = {
#include "bootrom_b1.inc"
  };
  return words;
}

static uint32_t readUInt32LE(const std::vector<uint8_t> &b, size_t at) {
  if (at + 4 > b.size()) {
    throw std::range_error("ELF: read past the end of the file");
  }
  return static_cast<uint32_t>(b[at]) | (static_cast<uint32_t>(b[at + 1]) << 8) |
         (static_cast<uint32_t>(b[at + 2]) << 16) | (static_cast<uint32_t>(b[at + 3]) << 24);
}

static uint32_t readUInt16LE(const std::vector<uint8_t> &b, size_t at) {
  if (at + 2 > b.size()) {
    throw std::range_error("ELF: read past the end of the file");
  }
  return static_cast<uint32_t>(b[at]) | (static_cast<uint32_t>(b[at + 1]) << 8);
}

// copy an ELF's loadable segments into flash (by their physical address)
static void loadElf(const std::string &file, RP2040 &mcu) {
  std::ifstream in(file, std::ios::binary);
  if (!in) {
    throw std::runtime_error("cannot open " + file);
  }
  const std::vector<uint8_t> b((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  const uint32_t phoff = readUInt32LE(b, 28), phentsize = readUInt16LE(b, 42),
                 phnum = readUInt16LE(b, 44);
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
      if (dest + (end - begin) > mcu.flash.size()) {
        throw std::range_error("RangeError: offset is out of bounds");
      }
      std::copy(b.begin() + begin, b.begin() + end, mcu.flash.begin() + dest);
    }
  }
}

// `${n}` for a JS number (fixed notation, shortest round trip; exact for the
// range a run's nanosecond clock can reach).
static std::string jsNumber(double n) {
  char buf[64];
  auto r = std::to_chars(buf, buf + sizeof buf, n, std::chars_format::fixed);
  return std::string(buf, r.ptr);
}

class Emu {
 public:
  SimulationClock clock;
  std::unique_ptr<RP2040> mcu;
  double nsPerCycle;
  std::string uart;
  /** per-cycle hook: (emu) => void (pin-level test benches) */
  std::function<void(Emu &)> onCycle;

  // core1Slow: charge core 1 this many times the cycles each instruction
  // takes, to show real-time code has margin (bus contention, cycle-count
  // error) rather than just fitting in the emulator
  Emu(const std::string &elf, double mhz, double core1Slow) {
    mcu = std::make_unique<RP2040>(clock);
    mcu->logger = std::make_shared<ConsoleLogger>(LogLevel::Error);
    mcu->loadBootrom(bootrom());
    loadElf(elf, *mcu);
    mcu->core0.setPC(0x10000000);  // boot stage 2, as the bootrom would
    nsPerCycle = 1000 / mhz;
    // PIO normally runs itself on setTimeout; we step it with the cores
    for (RPPIO &pio : mcu->pio) pio.run = [] {};
    mcu->uart[0].onByte = [this](uint32_t b) { uart += static_cast<char>(b); };  // String.fromCharCode
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

  double ns() const { return clock.nanos(); }

  // one step: an instruction on the core that is behind, and the PIO cycles
  // by which that moved the chip's time on
  void step() {
    if (mcu->waiting()) {
      // both cores asleep: skip to the next timer alarm, but no further than
      // one microsecond so PIO and the test bench still see time pass
      const double ns = std::min(clock.nanosToNextAlarm(), 1000.0);
      const double cycles = std::max(1.0, jsMathRound(ns / nsPerCycle));
      mcu->idle(cycles);
      this->cycles(cycles);
      return;
    }
    const double cycles = mcu->step();  // 0 when the core that ran is still behind the other
    if (cycles) this->cycles(cycles);
  }

  void cycles(double n) {
    for (double i = 0; i < n; i++) {
      for (RPPIO &pio : mcu->pio)
        if (!pio.stopped) pio.step();
      if (onCycle) onCycle(*this);
    }
    clock.tick(n * nsPerCycle);
  }

  // run until cond() is true; false if `ns` of emulated time pass first
  bool runUntil(const std::function<bool()> &cond, double ns) {
    const double end = clock.nanos() + ns;
    while (clock.nanos() < end) {
      if (cond()) return true;
      for (int i = 0; i < 64; i++) {
        step();
        afterStep();
      }
    }
    return cond();
  }

  // --trace-every
  uint64_t traceEvery = 0;
  uint64_t steps = 0;

 private:
  void afterStep() {
    if (traceEvery && ++steps % traceEvery == 0) {
      std::fprintf(stderr, "%s %08x %08x\n", jsNumber(clock.nanos()).c_str(), mcu->core0.PC(),
                   mcu->core1.PC());
    }
  }
};

// process.stdout.write(string): the UART text is one UTF-16 unit per byte
// (String.fromCharCode), which node writes as UTF-8.
static void writeUart(const std::string &uart) {
  std::string out;
  out.reserve(uart.size());
  for (unsigned char c : uart) {
    if (c < 0x80) {
      out += static_cast<char>(c);
    } else {
      out += static_cast<char>(0xc0 | (c >> 6));
      out += static_cast<char>(0x80 | (c & 0x3f));
    }
  }
  std::fwrite(out.data(), 1, out.size(), stdout);
  std::fflush(stdout);
}

static void usage() {
  std::fprintf(stderr,
               "usage: rp2040run <elf> --until <regex> --max-ns <ns> [--mhz N] [--core1-slow F]\n"
               "                 [--toggle-gpio PIN:EVERY_N_CYCLES] [--trace-every N]\n");
  std::exit(2);
}

static double number(const char *s) {
  char *end = nullptr;
  const double v = std::strtod(s, &end);
  if (!end || *end || end == s) {
    std::fprintf(stderr, "rp2040run: not a number: %s\n", s);
    std::exit(2);
  }
  return v;
}

int main(int argc, char **argv) {
  std::string elf, until;
  bool haveUntil = false;
  double maxNs = -1, mhz = 125, core1Slow = 1;
  int togglePin = -1;
  double toggleEvery = 0;
  double traceEvery = 0;
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    auto next = [&]() -> const char * {
      if (i + 1 >= argc) usage();
      return argv[++i];
    };
    if (a == "--until") {
      until = next();
      haveUntil = true;
    } else if (a == "--max-ns") {
      maxNs = number(next());
    } else if (a == "--mhz") {
      mhz = number(next());
    } else if (a == "--core1-slow") {
      core1Slow = number(next());
    } else if (a == "--toggle-gpio") {
      const std::string v = next();
      const size_t colon = v.find(':');
      if (colon == std::string::npos) usage();
      togglePin = static_cast<int>(number(v.substr(0, colon).c_str()));
      toggleEvery = number(v.substr(colon + 1).c_str());
      if (togglePin < 0 || togglePin > 29 || toggleEvery < 1) usage();
    } else if (a == "--trace-every") {
      traceEvery = number(next());
    } else if (a.size() > 1 && a[0] == '-') {
      usage();
    } else if (elf.empty()) {
      elf = a;
    } else {
      usage();
    }
  }
  if (elf.empty() || !haveUntil || maxNs < 0) usage();

  std::regex re;
  try {
    re = std::regex(until, std::regex::ECMAScript);
  } catch (const std::regex_error &e) {
    std::fprintf(stderr, "rp2040run: bad --until regex: %s\n", e.what());
    return 2;
  }

  std::unique_ptr<Emu> emu;
  bool done = false;
  try {
    emu = std::make_unique<Emu>(elf, mhz, core1Slow);
    emu->traceEvery = static_cast<uint64_t>(traceEvery);
    if (togglePin >= 0) {
      // run_nested.mjs: every Nth cycle, flip the pin's input
      emu->onCycle = [pin = togglePin, every = toggleEvery, n = 0.0](Emu &e) mutable {
        if (std::fmod(++n, every) == 0) {
          GPIOPin &gpio = e.mcu->gpio[pin];
          gpio.setInputValue(!gpio.inputValue());
        }
      };
    }
    // `/re/.test(emu.uart)`, re-tested only when the text has changed
    size_t tested = std::string::npos;
    bool matched = false;
    auto cond = [&]() {
      if (emu->uart.size() != tested) {
        tested = emu->uart.size();
        matched = std::regex_search(emu->uart, re);
      }
      return matched;
    };
    done = emu->runUntil(cond, maxNs);
  } catch (const std::exception &e) {
    if (emu) writeUart(emu->uart);
    std::fprintf(stderr, "rp2040run: %s\n", e.what());
    return 1;
  }
  writeUart(emu->uart);
  return done ? 0 : 1;
}
