// test_periph_diff: the C++ half of the peripheral differential test (see
// periph_diff.mjs, which writes the scenarios, runs the same scenario through
// rp2040js and compares the traces).
//
//   test_periph_diff <scenario>      prints the trace to stdout
//
// Scenario ops (one per line; integers hex, doubles as the 16 hex digits of
// their IEEE-754 bits):
//   S seed              seed of the callback-decision PRNG (xorshift32)
//   FILL seed           fill SRAM[0..16K) and flash[0..8K) from xorshift32(seed)
//   W/W8/W16 addr v     rp2040.writeUint32 / writeUint8 / writeUint16
//   R/R8/R16 addr       rp2040.readUint32 / readUint8 / readUint16 (traced)
//   T delta             clock.tick(delta)
//   U n byte            uart[n].feedByte(byte)
//   SM n mode           SPI n onTransmit: 0 library default, 1 answer at once, 2 answer later
//   SC n v              spi[n].completeTransmit(v)
//   IM n mode           I2C n callbacks: 0 library defaults, 1 answer at once, 2 answer later
//   IS/IC/IW/IR/IP/IA   i2c[n].completeStart / completeConnect(ack, nackByte) /
//                       completeWrite(ack) / completeRead(v) / completeStop / arbitrationLost
//   D n / DC n          dma.setDREQ(n) / dma.clearDREQ(n)
//   G pin v             gpio[pin].setInputValue(v)
//   AV ch v             adc.channelValues[ch] = v
//   PR                  pwm.reset()
//   CK / CKALL          FNV-1a of SRAM[0..2K) / of all SRAM and flash[0..16K)
// After every op: "N <nanosToNextAlarm> <nanos>".
//
// RP2040::setInterrupt calls are traced by linking with
// -Wl,--wrap=<RP2040::setInterrupt> (every call from the peripherals is an
// external reference to it), so no shared source needs a hook.
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "peripherals/watchdog.h"
#include "rp2040.h"
#include "utils/js.h"

using namespace rp2040js;

namespace {

std::string out;

void line(const std::string &s) {
  out += s;
  out += '\n';
  if (out.size() > (1u << 22)) {
    fwrite(out.data(), 1, out.size(), stdout);
    out.clear();
  }
}

std::string hex8(uint32_t v) {
  char buf[16];
  snprintf(buf, sizeof buf, "%" PRIx32, v);
  return buf;
}

std::string hexd(double x) {
  uint64_t bits;
  std::memcpy(&bits, &x, 8);
  char buf[24];
  snprintf(buf, sizeof buf, "%016" PRIx64, bits);
  return buf;
}

double unhexd(const std::string &s) {
  const uint64_t bits = std::stoull(s, nullptr, 16);
  double x;
  std::memcpy(&x, &bits, 8);
  return x;
}

/** xorshift32, as in periph_diff.mjs */
struct Rng {
  uint32_t s;
  explicit Rng(uint32_t seed) : s(seed ? seed : 0x9e3779b9) {}
  uint32_t next() {
    uint32_t x = s;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    s = x;
    return s;
  }
  uint32_t below(uint32_t n) { return next() % n; }
};

struct Runaway {};
constexpr uint32_t ALARM_BUDGET = 500000;

class TestClock : public SimulationClock {
 public:
  uint32_t nextId = 0;
  uint32_t fired = 0;

  struct State {
    int64_t id = -1;
  };

  class TestAlarm : public IAlarm {
   public:
    TestAlarm(TestClock &clock, std::shared_ptr<State> st, std::unique_ptr<IAlarm> inner)
        : clock(clock), st(std::move(st)), inner(std::move(inner)) {}
    void schedule(double deltaNanos) override {
      if (st->id < 0) {
        st->id = clock.nextId++;
      }
      inner->schedule(deltaNanos);
    }
    void cancel() override { inner->cancel(); }

   private:
    TestClock &clock;
    std::shared_ptr<State> st;
    std::unique_ptr<IAlarm> inner;
  };

  std::unique_ptr<IAlarm> createAlarm(ClockEventCallback callback) override {
    auto st = std::make_shared<State>();
    auto inner = SimulationClock::createAlarm([this, st, callback] {
      if (++fired > ALARM_BUDGET) {
        throw Runaway{};
      }
      line("A " + std::to_string(st->id) + " " + hexd(nanos()));
      callback();
    });
    return std::make_unique<TestAlarm>(*this, st, std::move(inner));
  }
};

TestClock *theClock = nullptr;

class RecordingLogger : public Logger {
 public:
  void debug(const std::string &c, const std::string &m) override { line("L D " + c + " " + m); }
  void warn(const std::string &c, const std::string &m) override { line("L W " + c + " " + m); }
  void error(const std::string &c, const std::string &m) override { line("L E " + c + " " + m); }
  void info(const std::string &c, const std::string &m) override { line("L I " + c + " " + m); }
};

uint32_t fnv(const std::vector<uint8_t> &bytes, size_t start, size_t end) {
  uint32_t h = 0x811c9dc5;
  for (size_t i = start; i < end; i++) {
    h ^= bytes[i];
    h *= 0x01000193u;
  }
  return h;
}

}  // namespace

// --wrap target: every RP2040::setInterrupt call from another object file.
extern "C" void __real__ZN8rp2040js6RP204012setInterruptEjb(RP2040 *self, uint32_t irq, bool value);
extern "C" void __wrap__ZN8rp2040js6RP204012setInterruptEjb(RP2040 *self, uint32_t irq, bool value) {
  if (irq != IRQ::IO_BANK0) {
    line("I " + std::to_string(irq) + " " + (value ? "1" : "0") + " " + hexd(theClock->nanos()));
  }
  __real__ZN8rp2040js6RP204012setInterruptEjb(self, irq, value);
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: test_periph_diff <scenario>\n");
    return 2;
  }
  std::ifstream in(argv[1]);
  if (!in) {
    fprintf(stderr, "cannot open %s\n", argv[1]);
    return 2;
  }
  std::vector<std::string> ops;
  for (std::string l; std::getline(in, l);) {
    if (!l.empty()) {
      ops.push_back(l);
    }
  }

  TestClock clock;
  theClock = &clock;
  auto mcuPtr = std::make_unique<RP2040>(clock);
  RP2040 &mcu = *mcuPtr;
  Rng cb(1);

  mcu.logger = std::make_shared<RecordingLogger>();
  for (uint32_t u = 0; u < 2; u++) {
    mcu.uart[u].onByte = [u](uint32_t b) { line("B " + std::to_string(u) + " " + hex8(b)); };
    mcu.uart[u].onBaudRateChange = [u](double b) {
      line("BR " + std::to_string(u) + " " + hexd(b));
    };
  }
  uint32_t spiMode[2] = {0, 0};
  std::function<void(uint32_t)> spiDefault[2] = {mcu.spi[0].onTransmit, mcu.spi[1].onTransmit};
  for (uint32_t s = 0; s < 2; s++) {
    mcu.spi[s].onTransmit = [&, s](uint32_t v) {
      line("X " + std::to_string(s) + " " + hex8(v));
      if (spiMode[s] == 0) {
        spiDefault[s](v);
      } else if (spiMode[s] == 1) {
        mcu.spi[s].completeTransmit(cb.next() & 0xff);
      }
    };
  }
  struct I2CCallbacks {
    std::function<void(bool)> onStart;
    std::function<void(uint32_t, I2CMode)> onConnect;
    std::function<void(uint32_t)> onWriteByte;
    std::function<void(bool)> onReadByte;
    std::function<void()> onStop;
  };
  I2CCallbacks i2cDefaults[2];
  for (uint32_t n = 0; n < 2; n++) {
    RPI2C &i = mcu.i2c[n];
    i2cDefaults[n] = {i.onStart, i.onConnect, i.onWriteByte, i.onReadByte, i.onStop};
  }
  auto setI2CMode = [&](uint32_t n, uint32_t mode) {
    RPI2C &i = mcu.i2c[n];
    if (mode == 0) {
      i.onStart = i2cDefaults[n].onStart;
      i.onConnect = i2cDefaults[n].onConnect;
      i.onWriteByte = i2cDefaults[n].onWriteByte;
      i.onReadByte = i2cDefaults[n].onReadByte;
      i.onStop = i2cDefaults[n].onStop;
      return;
    }
    const bool sync = mode == 1;
    const std::string ns = std::to_string(n);
    i.onStart = [&i, sync, ns](bool rs) {
      line("IS " + ns + " " + (rs ? "1" : "0"));
      if (sync) i.completeStart();
    };
    i.onConnect = [&i, &cb, sync, ns](uint32_t addr, I2CMode m) {
      line("IC " + ns + " " + hex8(addr) + " " + std::to_string(static_cast<int>(m)));
      if (sync) {
        const bool ack = cb.below(4) != 0;
        i.completeConnect(ack, cb.below(2));
      }
    };
    i.onWriteByte = [&i, &cb, sync, ns](uint32_t v) {
      line("IW " + ns + " " + hex8(v));
      if (sync) i.completeWrite(cb.below(5) != 0);
    };
    i.onReadByte = [&i, &cb, sync, ns](bool ack) {
      line("IR " + ns + " " + (ack ? "1" : "0"));
      if (sync) i.completeRead(cb.next() & 0xff);
    };
    i.onStop = [&i, sync, ns] {
      line("IP " + ns);
      if (sync) i.completeStop();
    };
  };
  std::function<void(uint32_t)> adcRead = mcu.adc.onADCRead;
  mcu.adc.onADCRead = [&adcRead](uint32_t ch) {
    line("AR " + std::to_string(ch));
    adcRead(ch);
  };
  auto *wd = dynamic_cast<RPWatchdog *>(mcu.peripherals.at(0x40058));
  // Once the watchdog counter has expired, TS's alarm re-fires at the same
  // instant forever (a real reset handler never returns); the "handler" here
  // either disables the watchdog or reloads it (as periph_diff.mjs).
  wd->onWatchdogTrigger = [&clock, &mcu, &cb] {
    line("WD " + hexd(clock.nanos()));
    if (cb.below(2)) {
      mcu.writeUint32(0x40058000, 0);
    } else {
      mcu.writeUint32(0x40058004, 1 + cb.below(0x1000));
    }
  };
  for (uint32_t pin = 0; pin < 30; pin++) {
    mcu.gpio[pin].addListener([pin, &clock](GPIOPinState state, GPIOPinState old) {
      line("G " + std::to_string(pin) + " " + std::to_string(static_cast<int>(state)) + " " +
           std::to_string(static_cast<int>(old)) + " " + hexd(clock.nanos()));
    });
  }

  try {
    for (const std::string &l : ops) {
      clock.fired = 0;
      std::istringstream ss(l);
      std::vector<std::string> f;
      for (std::string w; ss >> w;) {
        f.push_back(w);
      }
      auto a = [&f](size_t k) { return static_cast<uint32_t>(std::stoul(f.at(k), nullptr, 16)); };
      const std::string &op = f[0];
      if (op == "S") {
        cb.s = a(1) ? a(1) : 1;
      } else if (op == "FILL") {
        Rng fr(a(1));
        for (size_t i = 0; i < 0x4000; i++) mcu.sram[i] = fr.next() & 0xff;
        for (size_t i = 0; i < 0x2000; i++) mcu.flash[i] = fr.next() & 0xff;
      } else if (op == "W") {
        mcu.writeUint32(a(1), a(2));
      } else if (op == "W8") {
        mcu.writeUint8(a(1), a(2));
      } else if (op == "W16") {
        mcu.writeUint16(a(1), a(2));
      } else if (op == "R") {
        line("r " + f[1] + " " + hex8(mcu.readUint32(a(1))));
      } else if (op == "R8") {
        line("r " + f[1] + " " + hex8(mcu.readUint8(a(1))));
      } else if (op == "R16") {
        line("r " + f[1] + " " + hex8(mcu.readUint16(a(1))));
      } else if (op == "T") {
        clock.tick(unhexd(f[1]));
      } else if (op == "U") {
        mcu.uart[a(1)].feedByte(a(2));
      } else if (op == "SM") {
        spiMode[a(1)] = a(2);
      } else if (op == "SC") {
        mcu.spi[a(1)].completeTransmit(a(2));
      } else if (op == "IM") {
        setI2CMode(a(1), a(2));
      } else if (op == "IS") {
        mcu.i2c[a(1)].completeStart();
      } else if (op == "IC") {
        mcu.i2c[a(1)].completeConnect(a(2) != 0, a(3));
      } else if (op == "IW") {
        mcu.i2c[a(1)].completeWrite(a(2) != 0);
      } else if (op == "IR") {
        mcu.i2c[a(1)].completeRead(a(2));
      } else if (op == "IP") {
        mcu.i2c[a(1)].completeStop();
      } else if (op == "IA") {
        mcu.i2c[a(1)].arbitrationLost();
      } else if (op == "D") {
        mcu.dma.setDREQ(static_cast<DREQChannel>(a(1)));
      } else if (op == "DC") {
        mcu.dma.clearDREQ(static_cast<DREQChannel>(a(1)));
      } else if (op == "G") {
        mcu.gpio[a(1)].setInputValue(a(2) != 0);
      } else if (op == "AV") {
        mcu.adc.channelValues[a(1)] = a(2);
      } else if (op == "PR") {
        mcu.pwm.reset();
      } else if (op == "CK") {
        line("CK " + hex8(fnv(mcu.sram, 0, 0x800)));
      } else if (op == "CKALL") {
        line("CKALL " + hex8(fnv(mcu.sram, 0, mcu.sram.size())) + " " + hex8(fnv(mcu.flash, 0, 0x4000)));
      } else {
        fprintf(stderr, "bad op %s\n", l.c_str());
        return 2;
      }
      line("N " + hexd(clock.nanosToNextAlarm()) + " " + hexd(clock.nanos()));
    }
  } catch (const Runaway &) {
    line("RUNAWAY");
  } catch (const std::exception &e) {
    line(std::string("EXCEPTION ") + e.what());
  }
  fwrite(out.data(), 1, out.size(), stdout);
  fflush(stdout);
  // The chip may be mid-callback after a runaway; skip destructors that would
  // touch a half-unwound state.
  std::_Exit(0);
}
