// machinerun: the native whole machine from the command line, for speed
// measurements and the serial-vs-threaded determinism check.
//
//   machinerun --root DIR --rom FILE [--slots 1:gpu,2:io] [--mode serial|threaded|both]
//              [--spi-log] STEP...
//
// STEPs run in order, as test/emu/test_e2e.mjs does them:
//   --until TEXT NS     run until the screen shows TEXT (checked every 100 ms
//                       of emulated time, each check capturing a frame, like
//                       test_e2e.mjs's waitFor); fails after NS
//   --type TEXT         type on the USB keyboard (\n is Enter)
//   --run NS            run for NS
// Then it prints the screen, the machine's digest (board clocks, CPU state,
// RAM, every card's clock and UART, the per-iteration trace, the SPI logs)
// and the speed. --mode both runs the scenario serially and threaded and
// exits 1 unless the two digests are identical.
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

#include "../../soc/emu/board.h"
#include "machine.h"

using namespace machine;

struct Step {
  std::string kind, text;
  double ns = 0;
};

static uint64_t fnv(const void *p, size_t n, uint64_t h = 0xcbf29ce484222325ull) {
  const uint8_t *b = static_cast<const uint8_t *>(p);
  for (size_t i = 0; i < n; i++) {
    h ^= b[i];
    h *= 0x100000001b3ull;
  }
  return h;
}

static std::string screenText(Machine &m) {
  std::string err;
  auto rows = m.screen(&err);
  if (!err.empty()) return "(no picture: " + err + ")";
  std::string t;
  for (auto &r : rows) t += r + "\n";
  while (!t.empty() && t.back() == '\n') t.pop_back();
  return t;
}

struct Result {
  std::string digest, screen;
  double ns, secs;
  bool ok;
  Machine::Stats stats;
};

static Result run(const Machine::Options &o, const std::vector<Step> &steps) {
  Machine m(o);
  m.stats.traceOn = true;
  const auto t0 = std::chrono::steady_clock::now();
  m.powerOn();
  bool ok = true;
  for (const Step &s : steps) {
    if (s.kind == "run") {
      m.runFor(s.ns);
    } else if (s.kind == "type") {
      m.type(s.text);
    } else if (s.kind == "until") {
      // test_e2e.mjs waitFor: runUntil(cond, ns, 100e6)
      const double end = m.ns() + s.ns;
      bool found = false;
      while (m.ns() < end) {
        if (screenText(m).find(s.text) != std::string::npos) {
          found = true;
          break;
        }
        m.runFor(std::min(100e6, end - m.ns()));
      }
      if (!found) found = screenText(m).find(s.text) != std::string::npos;
      std::fprintf(stderr, "  until '%s': %s at %.3f s emulated\n", s.text.c_str(), found ? "found" : "NOT FOUND",
                   m.ns() / 1e9);
      ok &= found;
    }
  }
  Result r;
  r.screen = screenText(m);
  const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
  std::ostringstream d;
  const auto st = m.state();
  d << "board clocks " << m.board->clocks << " pc " << std::hex << st.pc << " sp " << st.sp << " gpo " << st.gpo
    << std::dec << "\n";
  d << "ram " << std::hex << fnv(m.board->ram, 65536) << " rom " << fnv(m.board->rom.mem, sizeof m.board->rom.mem)
    << std::dec << "\n";
  d << "trace " << std::hex << m.stats.trace << std::dec << " idle windows " << m.stats.idleWindows << " busy "
    << m.stats.busyIterations << "\n";
  char buf[64];
  if (m.sysctl) {
    std::snprintf(buf, sizeof buf, "%.17g", m.sysctl->e.ns());
    d << "sysctl ns " << buf << " uart " << std::hex << fnv(m.sysctl->e.uart.data(), m.sysctl->e.uart.size())
      << std::dec << "\n";
  }
  for (auto &[slot, c] : m.cards) {
    if (!c->emu()) continue;
    std::snprintf(buf, sizeof buf, "%.17g", c->emu()->ns());
    d << "slot " << slot << " " << c->kind << " ns " << buf << " uart " << std::hex
      << fnv(c->emu()->uart.data(), c->emu()->uart.size()) << std::dec;
    auto *rc = static_cast<Rp2040Card *>(c.get());
    uint64_t h = 0xcbf29ce484222325ull;
    for (auto &f : rc->log) {
      h = fnv(&f.start, 8, h);
      h = fnv(&f.ns, 8, h);
      h = fnv(f.bytes.data(), f.bytes.size(), h);
      h = fnv(f.miso.data(), f.miso.size(), h);
      h = fnv(&f.extra, 4, h);
    }
    d << " spi frames " << rc->log.size() << " log " << std::hex << h << std::dec << "\n";
  }
  d << "screen " << std::hex << fnv(r.screen.data(), r.screen.size()) << std::dec << "\n";
  r.digest = d.str();
  r.ns = m.ns();
  r.secs = secs;
  r.ok = ok;
  r.stats = m.stats;
  return r;
}

static std::string unescape(const std::string &s) {
  std::string o;
  for (size_t i = 0; i < s.size(); i++) {
    if (s[i] == '\\' && i + 1 < s.size() && s[i + 1] == 'n') {
      o += '\n';
      i++;
    } else {
      o += s[i];
    }
  }
  return o;
}

int main(int argc, char **argv) {
  Machine::Options o;
  std::string mode = "threaded", romFile;
  std::vector<Step> steps;
  o.slots = {{1, "gpu"}, {2, "io"}};
  for (int i = 1; i < argc; i++) {
    const std::string a = argv[i];
    auto next = [&]() -> std::string {
      if (i + 1 >= argc) {
        std::fprintf(stderr, "machinerun: %s needs a value\n", a.c_str());
        std::exit(2);
      }
      return argv[++i];
    };
    if (a == "--root") o.root = next();
    else if (a == "--rom") romFile = next();
    else if (a == "--mode") mode = next();
    else if (a == "--spi-log") o.spiLog = true;
    else if (a == "--slots") {
      o.slots.clear();
      std::stringstream ss(next());
      std::string item;
      while (std::getline(ss, item, ',')) o.slots[std::stoi(item.substr(0, item.find(':')))] = item.substr(item.find(':') + 1);
    } else if (a == "--until") {
      Step s{"until", next()};
      s.ns = std::stod(next());
      steps.push_back(s);
    } else if (a == "--type") {
      steps.push_back({"type", unescape(next())});
    } else if (a == "--run") {
      Step s{"run", ""};
      s.ns = std::stod(next());
      steps.push_back(s);
    } else {
      std::fprintf(stderr, "machinerun: unknown argument %s\n", a.c_str());
      return 2;
    }
  }
  std::ifstream in(romFile, std::ios::binary);
  if (o.root.empty() || !in) {
    std::fprintf(stderr, "machinerun: --root and a readable --rom are required\n");
    return 2;
  }
  o.rom.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
  std::vector<Result> results;
  for (const std::string &md : {std::string("serial"), std::string("threaded")}) {
    if (mode != "both" && mode != md) continue;
    o.threaded = md == "threaded";
    std::fprintf(stderr, "%s:\n", md.c_str());
    Result r = run(o, steps);
    std::printf("==== %s\n%s\n---- digest\n%s", md.c_str(), r.screen.c_str(), r.digest.c_str());
    std::printf("---- speed: %.3f s emulated in %.1f s: %.2fx slower than real time (%llu idle windows, %llu busy clocks)\n",
                r.ns / 1e9, r.secs, r.secs / (r.ns / 1e9), static_cast<unsigned long long>(r.stats.idleWindows),
                static_cast<unsigned long long>(r.stats.busyClocks));
    std::fflush(stdout);
    results.push_back(r);
  }
  bool ok = true;
  for (auto &r : results) ok &= r.ok;
  if (results.size() == 2) {
    const bool same = results[0].digest == results[1].digest && results[0].screen == results[1].screen;
    std::printf("serial and threaded: %s\n", same ? "IDENTICAL" : "DIFFERENT");
    ok &= same;
  }
  return ok ? 0 : 1;
}
