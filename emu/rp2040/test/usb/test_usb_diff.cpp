// C++ side of the USB differential test (see usb_diff.mjs, which writes the op
// file, runs this, and compares traces).
//
// usage: test_usb_diff <ops.txt> <trace-out.txt>
//
// Replays every op against a fresh RP2040 + RPUSBController (+ USBCDC or
// UsbKeyboard) per scenario, with no CPU core, and writes the same trace
// lines the JS side produces.
#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "peripherals/usb.h"
#include "rp2040.h"
#include "usb/cdc.h"
#include "usb/usbkbd.h"
#include "utils/js.h"
#include "utils/logging.h"

using namespace rp2040js;

static std::FILE *out = nullptr;

static void emitLine(const std::string &s) {
  std::fwrite(s.data(), 1, s.size(), out);
  std::fputc('\n', out);
}

static std::string hex(uint32_t v) {
  char b[16];
  std::snprintf(b, sizeof b, "%" PRIx32, v);
  return b;
}

/** the JS `num()`: an integer as decimal, anything else as its float64 bit pattern */
static std::string num(double v) {
  char b[40];
  if (std::trunc(v) == v && std::fabs(v) < 9007199254740992.0) {
    std::snprintf(b, sizeof b, "%.0f", v);
    if (std::strcmp(b, "-0") == 0) return "0";
    return b;
  }
  uint64_t bits;
  std::memcpy(&bits, &v, 8);
  std::snprintf(b, sizeof b, "f%" PRIx64, bits);
  return b;
}

static std::string bytesHex(const uint8_t *p, size_t n) {
  if (!n) return "-";
  static const char *digits = "0123456789abcdef";
  std::string s(2 * n, '0');
  for (size_t i = 0; i < n; i++) {
    s[2 * i] = digits[p[i] >> 4];
    s[2 * i + 1] = digits[p[i] & 15];
  }
  return s;
}
static std::string bytesHex(const std::vector<uint8_t> &b) { return bytesHex(b.data(), b.size()); }

static std::vector<uint8_t> parseBytes(const std::string &s) {
  std::vector<uint8_t> r;
  if (s == "-") return r;
  for (size_t i = 0; i + 1 < s.size(); i += 2) r.push_back(static_cast<uint8_t>(std::stoul(s.substr(i, 2), nullptr, 16)));
  return r;
}

static uint32_t fnv(const std::vector<uint8_t> &bytes) {
  uint32_t h = 0x811c9dc5;
  for (uint8_t b : bytes) h = (h ^ b) * 0x01000193u;
  return h;
}

class CaptureLogger : public Logger {
 public:
  void debug(const std::string &c, const std::string &m) override { log('D', c, m); }
  void warn(const std::string &c, const std::string &m) override { log('W', c, m); }
  void error(const std::string &c, const std::string &m) override { log('E', c, m); }
  void info(const std::string &c, const std::string &m) override { log('I', c, m); }

 private:
  static void log(char level, const std::string &c, const std::string &m) {
    if (c == "USBT") emitLine(std::string("log ") + level + " " + m);
  }
};

/** The JS LogClock: numbers and logs the alarms created while `wrap` is set. */
class LogClock : public SimulationClock {
 public:
  bool wrap = false;
  int nextId = 0;
  std::function<void()> after = [] {};

  std::unique_ptr<IAlarm> createAlarm(ClockEventCallback callback) override {
    if (!wrap) return SimulationClock::createAlarm(std::move(callback));
    const int id = nextId++;
    auto inner = SimulationClock::createAlarm([this, id, callback = std::move(callback)] {
      emitLine("F " + std::to_string(id) + " " + num(nanos()));
      callback();
      after();
    });
    return std::make_unique<Wrapped>(*this, id, std::move(inner));
  }

 private:
  class Wrapped : public IAlarm {
   public:
    Wrapped(LogClock &clock, int id, std::unique_ptr<IAlarm> inner)
        : clock(clock), id(id), inner(std::move(inner)) {}
    void schedule(double delta) override {
      emitLine("S " + std::to_string(id) + " " + num(delta) + " " + num(clock.nanos()));
      inner->schedule(delta);
    }
    void cancel() override {
      emitLine("C " + std::to_string(id));
      inner->cancel();
    }

   private:
    LogClock &clock;
    int id;
    std::unique_ptr<IAlarm> inner;
  };
};

struct Side {
  std::string mode;
  LogClock clock;
  std::unique_ptr<RP2040> mcu;
  std::unique_ptr<RPUSBController> ctl;
  std::unique_ptr<USBCDC> cdc;
  std::unique_ptr<UsbKeyboard> kbd;
  uint32_t lastInts = 0;
  uint32_t lastHash = 0;
  std::string lastIrq = "00";

  Side(const std::string &mode, uint32_t kspeed, uint32_t kinterval) : mode(mode) {
    mcu = std::make_unique<RP2040>(clock);
    mcu->logger = std::make_shared<CaptureLogger>();
    clock.wrap = true;
    clock.nextId = 0;
    ctl = std::make_unique<RPUSBController>(*mcu, "USBT");
    clock.after = [this] { after(); };
    RPUSBController &c = *ctl;
    if (mode == "cdc") {
      cdc = std::make_unique<USBCDC>(c);
      cdc->onSerialData = [](const std::vector<uint8_t> &b) { emitLine("cb ser " + bytesHex(b)); };
      cdc->onDeviceConnected = [] { emitLine("cb conn"); };
    }
    auto en = c.onUSBEnabled;
    auto rs = c.onResetReceived;
    auto ew = c.onEndpointWrite;
    auto er = c.onEndpointRead;
    c.onUSBEnabled = [en] {
      emitLine("cb en");
      if (en) en();
    };
    c.onResetReceived = [rs] {
      emitLine("cb rst");
      if (rs) rs();
    };
    c.onEndpointWrite = [ew](uint32_t e, const std::vector<uint8_t> &b) {
      emitLine("cb w " + std::to_string(e) + " " + bytesHex(b));
      if (ew) ew(e, b);
    };
    c.onEndpointRead = [er](uint32_t e, uint32_t n) {
      emitLine("cb r " + std::to_string(e) + " " + std::to_string(n));
      if (er) er(e, n);
    };
    if (mode == "host") kbd = std::make_unique<UsbKeyboard>(UsbKeyboard::Options{kspeed, kinterval});
    lastHash = fnv(mcu->usbDPRAM);
  }
  ~Side() {
    // the peripheral's alarms unlink themselves from the clock
    cdc.reset();
    ctl.reset();
    mcu.reset();
  }

  void after() {
    const uint32_t v = ctl->intStatus();
    if (v != lastInts) {
      emitLine("ints " + hex(v));
      lastInts = v;
    }
    // IRQ.USBCTRL (5) as the cores see it, through RP2040::setInterrupt
    const std::string irq = std::to_string((mcu->core0.pendingInterrupts >> 5) & 1) +
                            std::to_string((mcu->core1.pendingInterrupts >> 5) & 1);
    if (irq != lastIrq) {
      emitLine("irq " + irq);
      lastIrq = irq;
    }
    const uint32_t h = fnv(mcu->usbDPRAM);
    if (h != lastHash) {
      emitLine("dh " + hex(h));
      lastHash = h;
    }
  }

  void exec(const std::vector<std::string> &a) {
    RPUSBController &c = *ctl;
    std::vector<uint8_t> &dpram = mcu->usbDPRAM;
    auto hx = [](const std::string &s) { return static_cast<uint32_t>(std::stoul(s, nullptr, 16)); };
    const std::string &op = a[0];
    if (op == "w") {
      c.writeUint32Atomic(hx(a[1]), hx(a[2]), static_cast<uint32_t>(std::stoul(a[3])));
    } else if (op == "r") {
      emitLine("= " + hex(c.readUint32(hx(a[1]))));
    } else if (op == "d") {
      const uint32_t off = hx(a[1]), v = hx(a[2]);
      storeLE32(&dpram[off], v);
      c.DPRAMUpdated(off, v);
    } else if (op == "dr") {
      emitLine("= " + hex(loadLE32(&dpram[hx(a[1])])));
    } else if (op == "t") {
      clock.tick(std::stod(a[1]));
    } else if (op == "rd") {
      const uint32_t ep = static_cast<uint32_t>(std::stoul(a[1]));
      if (a[2] == "-")
        c.endpointReadDone(ep, parseBytes(a[3]));
      else
        c.endpointReadDone(ep, parseBytes(a[3]), std::stod(a[2]));
    } else if (op == "sp") {
      c.sendSetupPacket(parseBytes(a[1]));
    } else if (op == "rst") {
      c.resetDevice();
    } else if (op == "rdly") {
      c.readDelayMicroseconds = std::stod(a[1]);
    } else if (op == "wdly") {
      c.writeDelayMicroseconds = std::stod(a[1]);
    } else if (op == "att") {
      c.attachDevice(kbd.get());
    } else if (op == "det") {
      c.detachDevice();
    } else if (op == "key") {
      std::vector<uint32_t> keys;
      for (size_t i = 2; i < a.size(); i++) keys.push_back(static_cast<uint32_t>(std::stoul(a[i])));
      kbd->press(static_cast<uint32_t>(std::stoul(a[1])), keys);
    } else if (op == "ser") {
      cdc->sendSerialByte(static_cast<uint32_t>(std::stoul(a[1])));
    } else if (op == "fifo") {
      emitLine("fifo " + std::to_string(cdc->txFIFO.itemCount()));
    } else if (op == "kbd") {
      const UsbKeyboard &k = *kbd;
      std::string cs = "-";
      if (k.ctrl) {
        if (k.ctrl->in)
          cs = "in:" + bytesHex(*k.ctrl->in) + ":" + std::to_string(k.ctrl->pos);
        else if (k.ctrl->out)
          cs = "out:" + bytesHex(*k.ctrl->out) + ":" + std::to_string(k.ctrl->length);
        else
          cs = "st";
      }
      std::string leds, log;
      for (size_t i = 0; i < k.leds.size(); i++) {
        if (i) leds += ",";
        leds += k.leds[i] < 0 ? "u" : std::to_string(k.leds[i]);
      }
      for (size_t i = 0; i < k.log.size(); i++) {
        if (i) log += ",";
        const auto &e = k.log[i];
        log += std::to_string(e.type) + "." + std::to_string(e.req) + "." + std::to_string(e.value) + "." +
               std::to_string(e.length);
      }
      emitLine("kbd a=" + std::to_string(k.addr) + " c=" + std::to_string(k.configured) +
               " p=" + std::to_string(k.protocol) + " leds=" + leds + " n=" + std::to_string(k.reports.size()) +
               " log=" + log + " ctrl=" + cs);
    } else if (op == "dump") {
      emitLine("dpram " + bytesHex(dpram));
    } else if (op == "now") {
      emitLine("now " + num(clock.nanos()) + " next " + num(clock.nanosToNextAlarm()));
    } else {
      std::fprintf(stderr, "test_usb_diff: bad op %s\n", op.c_str());
      std::exit(2);
    }
  }
};

int main(int argc, char **argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: test_usb_diff <ops.txt> <trace-out.txt>\n");
    return 2;
  }
  std::ifstream in(argv[1]);
  if (!in) {
    std::fprintf(stderr, "test_usb_diff: cannot read %s\n", argv[1]);
    return 2;
  }
  out = std::fopen(argv[2], "w");
  if (!out) {
    std::fprintf(stderr, "test_usb_diff: cannot write %s\n", argv[2]);
    return 2;
  }
  static char buf[1 << 20];
  std::setvbuf(out, buf, _IOFBF, sizeof buf);
  std::unique_ptr<Side> side;
  std::string line;
  std::vector<std::string> a;
  while (std::getline(in, line)) {
    if (line.empty()) continue;
    a.clear();
    std::istringstream ss(line);
    for (std::string w; ss >> w;) a.push_back(w);
    emitLine("> " + line);
    if (a[0] == "scn") {
      side.reset();
      side = std::make_unique<Side>(a[1], static_cast<uint32_t>(std::stoul(a[2])),
                                    static_cast<uint32_t>(std::stoul(a[3])));
      continue;
    }
    try {
      side->exec(a);
    } catch (const std::range_error &) {
      // the JS RangeError ends the op
      emitLine("throw");
    }
    side->after();
  }
  side.reset();
  std::fclose(out);
  return 0;
}
