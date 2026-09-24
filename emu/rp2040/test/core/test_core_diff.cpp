// test_core_diff: the C++ side of the CortexM0Core / RPPPB differential test.
//
// Reads, on stdin, the operation stream that core-diff.mjs produces while it
// runs rp2040js, replays it on the C++ RP2040 and compares the core state after
// every instruction with the state rp2040js had. See core-diff.mjs.
//
//   N <seed>             new chip (RP2040 with a SimulationClock)
//   W <addr> <w>...      writeUint32 of consecutive words
//   P <addr> <v>         writeUint32
//   H <addr> <v>         writeUint16
//   R <i> <v>            core0.registers[i] = v
//   F <name> <v>         core0 field = v
//   I <irq> <0|1>        core0.setInterrupt(irq, v)
//   T <ns>               clock.tick(ns)
//   X <state>            core0.executeInstruction(), then compare the state
//   K <hash>             compare the FNV hash of the whole SRAM
//   E                    end
//
// After a mismatch the rest of that seed is skipped. Prints
// "steps=<n> mismatches=<m>" and exits 0 if m == 0.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "rp2040.h"
#include "utils/js.h"
#include "utils/logging.h"

using namespace rp2040js;

namespace {

class CaptureLogger : public Logger {
 public:
  std::vector<std::string> logs;
  void debug(const std::string &c, const std::string &m) override { logs.push_back("d:" + c + ":" + m); }
  void warn(const std::string &c, const std::string &m) override { logs.push_back("w:" + c + ":" + m); }
  void error(const std::string &c, const std::string &m) override { logs.push_back("e:" + c + ":" + m); }
  void info(const std::string &c, const std::string &m) override { logs.push_back("i:" + c + ":" + m); }
};

const char *const FIELD_NAMES[] = {
    "r0",        "r1",       "r2",        "r3",           "r4",           "r5",
    "r6",        "r7",       "r8",        "r9",           "r10",          "r11",
    "r12",       "r13",      "r14",       "r15",          "bankedSP",     "xPSR",
    "IPSR",      "PM",       "SPSEL",     "nPRIV",        "mode",         "cycles",
    "delta",     "pending",  "enabled",   "prio0",        "prio1",        "prio2",
    "prio3",     "pendNMI",  "pendPendSV", "pendSVCall",  "pendSystick",  "intsUpdated",
    "VTOR",      "SHPR2",    "SHPR3",     "eventRegistered", "waiting",   "waitingForEvent",
    "breakRewind", "NMIMask", "c1.event", "c1.waiting",   "c1.wfe",       "systickCountFlag",
    "systickClkSource", "systickIntEnable", "systickReload", "memhash", "blTaken", "breaks",
    "logs",
};

struct Hash {
  uint32_t h = 0x811c9dc5;
  void add(const std::vector<uint8_t> &mem, uint32_t lo, uint32_t hi) {
    for (uint32_t a = lo; a < hi; a += 4) {
      h = (h ^ loadLE32(&mem[a])) * 16777619u;
    }
  }
};

std::string hex(uint32_t v) {
  char b[16];
  snprintf(b, sizeof b, "%x", v);
  return b;
}

std::vector<std::string> split(const std::string &s, char sep) {
  std::vector<std::string> out;
  size_t start = 0;
  for (;;) {
    size_t e = s.find(sep, start);
    out.push_back(s.substr(start, e == std::string::npos ? std::string::npos : e - start));
    if (e == std::string::npos) break;
    start = e + 1;
  }
  return out;
}

uint32_t parseHex(const char *s, const char **end = nullptr) {
  char *e;
  unsigned long v = strtoul(s, &e, 16);
  if (end) *end = e;
  return static_cast<uint32_t>(v);
}

constexpr uint32_t RAM = 0x20000000;
const uint32_t HASH_RANGES[][2] = {
    {0x20000000, 0x20000200},
    {0x20010000, 0x20010400},
    {0x2001fc00, 0x20020000},
    {0x20030c00, 0x20031000},
};

struct Harness {
  std::unique_ptr<RP2040> mcu;
  std::shared_ptr<CaptureLogger> logger;
  std::vector<uint32_t> breaks;
  uint32_t blCount = 0;

  void newChip() {
    mcu = std::make_unique<RP2040>();
    logger = std::make_shared<CaptureLogger>();
    mcu->logger = logger;
    breaks.clear();
    blCount = 0;
    mcu->onBreak = [this](uint32_t code) { breaks.push_back(code); };
    mcu->core0.blTaken = [this](CortexM0Core &, bool) { blCount++; };
  }

  std::string state(const std::string &delta) {
    CortexM0Core &c = mcu->core0;
    CortexM0Core &c1 = mcu->core1;
    RPPPB &ppb = mcu->ppb;
    std::string s;
    auto add = [&s](const std::string &f) {
      if (!s.empty()) s += ' ';
      s += f;
    };
    auto b = [](bool v) { return std::string(v ? "1" : "0"); };
    for (uint32_t r : c.registers) add(hex(r));
    add(hex(c.bankedSP));
    add(hex(c.xPSR()));
    add(hex(c.IPSR));
    add(b(c.PM));
    add(std::to_string(static_cast<int>(c.SPSEL)));
    add(b(c.nPRIV));
    add(std::to_string(static_cast<int>(c.currentMode)));
    char cyc[64];
    snprintf(cyc, sizeof cyc, "%.0f", c.cycles);
    add(cyc);
    add(delta);
    add(hex(c.pendingInterrupts));
    add(hex(c.enabledInterrupts));
    for (uint32_t p : c.interruptPriorities) add(hex(p));
    add(b(c.pendingNMI));
    add(b(c.pendingPendSV));
    add(b(c.pendingSVCall));
    add(b(c.pendingSystick));
    add(b(c.interruptsUpdated));
    add(hex(c.VTOR));
    add(hex(c.SHPR2));
    add(hex(c.SHPR3));
    add(b(c.eventRegistered));
    add(b(c.waiting));
    add(b(c.waitingForEvent));
    add(std::to_string(c.breakRewind));
    add(hex(c.interruptNMIMask));
    add(b(c1.eventRegistered));
    add(b(c1.waiting));
    add(b(c1.waitingForEvent));
    add(b(ppb.systickCountFlag));
    add(b(ppb.systickClkSource));
    add(b(ppb.systickIntEnable));
    add(hex(ppb.systickReload));
    Hash h;
    for (const auto &r : HASH_RANGES) h.add(mcu->sram, r[0] - RAM, r[1] - RAM);
    add(hex(h.h));
    add(std::to_string(blCount));
    std::string br = "b";
    for (size_t i = 0; i < breaks.size(); i++) br += (i ? "," : "") + std::to_string(breaks[i]);
    add(br);
    std::string lg = "L";
    for (size_t i = 0; i < logger->logs.size(); i++) lg += (i ? "|" : "") + logger->logs[i];
    add(lg);
    logger->logs.clear();
    breaks.clear();
    blCount = 0;
    return s;
  }

  void setField(const std::string &name, uint32_t v) {
    CortexM0Core &c = mcu->core0;
    if (name == "N") c.N = v;
    else if (name == "Z") c.Z = v;
    else if (name == "C") c.C = v;
    else if (name == "V") c.V = v;
    else if (name == "PM") c.PM = v;
    else if (name == "SPSEL") c.SPSEL = static_cast<StackPointerBank>(v);
    else if (name == "nPRIV") c.nPRIV = v;
    else if (name == "mode") c.currentMode = static_cast<ExecutionMode>(v);
    else if (name == "IPSR") c.IPSR = v;
    else if (name == "bankedSP") c.bankedSP = v;
    else if (name == "VTOR") c.VTOR = v;
    else if (name == "SHPR2") c.SHPR2 = v;
    else if (name == "SHPR3") c.SHPR3 = v;
    else if (name == "pend") c.pendingInterrupts = v;
    else if (name == "en") c.enabledInterrupts = v;
    else if (name == "p0") c.interruptPriorities[0] = v;
    else if (name == "p1") c.interruptPriorities[1] = v;
    else if (name == "p2") c.interruptPriorities[2] = v;
    else if (name == "p3") c.interruptPriorities[3] = v;
    else if (name == "nmi") c.pendingNMI = v;
    else if (name == "pendsv") c.pendingPendSV = v;
    else if (name == "svc") c.pendingSVCall = v;
    else if (name == "systick") c.pendingSystick = v;
    else if (name == "upd") c.interruptsUpdated = v;
    else if (name == "evt") c.eventRegistered = v;
    else if (name == "wait") c.waiting = v;
    else if (name == "wfe") c.waitingForEvent = v;
    else if (name == "nmimask") c.interruptNMIMask = v;
    else {
      fprintf(stderr, "test_core_diff: unknown field %s\n", name.c_str());
      exit(2);
    }
  }
};

}  // namespace

int main() {
  std::ios::sync_with_stdio(false);
  Harness hx;
  std::string line;
  uint64_t steps = 0;
  int mismatches = 0;
  bool skip = false;
  int seed = 0;
  uint64_t seedStep = 0;
  std::vector<std::string> recent;  // the operations since the last compared instruction
  std::string prevState;

  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    const char op = line[0];
    if (op == 'E') break;
    if (op == 'N') {
      seed = atoi(line.c_str() + 2);
      seedStep = 0;
      skip = false;
      hx.newChip();
      recent.clear();
      prevState.clear();
      continue;
    }
    if (skip) {
      if (op == 'X') steps++;
      continue;
    }
    if (op != 'X' && op != 'K' && op != 'W') {
      recent.push_back(line);
    }
    try {
      switch (op) {
        case 'W': {
          const char *p = line.c_str() + 2;
          uint32_t addr = parseHex(p, &p);
          while (*p == ' ') {
            uint32_t v = parseHex(p, &p);
            hx.mcu->writeUint32(addr, v);
            addr += 4;
          }
          break;
        }
        case 'P': {
          const char *p = line.c_str() + 2;
          uint32_t addr = parseHex(p, &p);
          hx.mcu->writeUint32(addr, parseHex(p));
          break;
        }
        case 'H': {
          const char *p = line.c_str() + 2;
          uint32_t addr = parseHex(p, &p);
          hx.mcu->writeUint16(addr, parseHex(p));
          break;
        }
        case 'R': {
          const char *p = line.c_str() + 2;
          char *e;
          unsigned long i = strtoul(p, &e, 10);
          hx.mcu->core0.registers[i] = parseHex(e);
          break;
        }
        case 'F': {
          size_t sp = line.find(' ', 2);
          hx.setField(line.substr(2, sp - 2), parseHex(line.c_str() + sp + 1));
          break;
        }
        case 'I': {
          const char *p = line.c_str() + 2;
          char *e;
          unsigned long irq = strtoul(p, &e, 10);
          hx.mcu->core0.setInterrupt(static_cast<uint32_t>(irq), strtoul(e, nullptr, 10) != 0);
          break;
        }
        case 'T': {
          static_cast<SimulationClock &>(hx.mcu->clock).tick(strtod(line.c_str() + 2, nullptr));
          break;
        }
        case 'X': {
          steps++;
          seedStep++;
          std::string delta;
          try {
            delta = std::to_string(hx.mcu->core0.executeInstruction());
          } catch (const std::range_error &) {
            delta = "RangeError";  // as core-diff.mjs catches the JS RangeError
          }
          const std::string got = hx.state(delta);
          const std::string want = line.substr(2);
          if (got != want) {
            mismatches++;
            skip = true;
            printf("MISMATCH seed %d instruction %llu\n", seed, static_cast<unsigned long long>(seedStep));
            printf("  operations before it:\n");
            for (const auto &r : recent) printf("    %s\n", r.substr(0, 200).c_str());
            printf("  state before: %s\n", prevState.c_str());
            auto g = split(got, ' ');
            auto w = split(want, ' ');
            const size_t nf = sizeof FIELD_NAMES / sizeof FIELD_NAMES[0];
            for (size_t i = 0; i < std::max(g.size(), w.size()); i++) {
              const std::string gi = i < g.size() ? g[i] : "<none>";
              const std::string wi = i < w.size() ? w[i] : "<none>";
              if (gi != wi) {
                printf("  %-16s js=%s  c++=%s\n", i < nf ? FIELD_NAMES[i] : "?", wi.c_str(), gi.c_str());
              }
            }
          }
          prevState = want;
          recent.clear();
          break;
        }
        case 'K': {
          Hash h;
          h.add(hx.mcu->sram, 0, static_cast<uint32_t>(hx.mcu->sram.size()));
          if (hex(h.h) != line.substr(2)) {
            mismatches++;
            skip = true;
            printf("MISMATCH seed %d after instruction %llu: SRAM hash js=%s c++=%s\n", seed,
                   static_cast<unsigned long long>(seedStep), line.substr(2).c_str(), hex(h.h).c_str());
          }
          break;
        }
        default:
          fprintf(stderr, "test_core_diff: bad line: %s\n", line.substr(0, 80).c_str());
          return 2;
      }
    } catch (const std::exception &e) {
      mismatches++;
      skip = true;
      printf("MISMATCH seed %d instruction %llu: C++ threw %s (on: %s)\n", seed,
             static_cast<unsigned long long>(seedStep + 1), e.what(), line.substr(0, 120).c_str());
    }
  }
  printf("steps=%llu mismatches=%d\n", static_cast<unsigned long long>(steps), mismatches);
  return mismatches == 0 ? 0 : 1;
}
