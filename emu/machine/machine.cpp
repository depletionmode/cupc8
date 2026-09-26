// The whole machine, natively: see machine.h. Every function here is the
// machine.mjs / tmds.mjs function of the same name, in the same order.
#include "machine.h"

#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <climits>
#include <ctime>
#include <cstdlib>

#include <algorithm>
#include <set>
#include <stdexcept>
#include <cctype>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <iterator>
#include <sstream>
#include <stdexcept>

#include "../../soc/emu/board.h"

#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
static inline void cpuRelax() { _mm_pause(); }
#else
static inline void cpuRelax() {}
#endif

using namespace rp2040js;

namespace machine {

// the RP2040 cards' slot pins (hw/pins.yaml)
namespace P {
constexpr int SCK = 2, MOSI = 3, MISO = 4, NCS = 5, NIRQ = 6;
}

static std::vector<uint8_t> packBits(const std::vector<uint8_t> &bits) {
  std::vector<uint8_t> out;
  for (size_t i = 0; i + 8 <= bits.size(); i += 8) {
    uint8_t v = 0;
    for (size_t j = 0; j < 8; j++) v = static_cast<uint8_t>((v << 1) | bits[i + j]);
    out.push_back(v);
  }
  return out;
}

// ------------------------------------------------------------ Rp2040Card

Rp2040Card::Rp2040Card(const std::string &kind_, const std::string &elf, double mhz) : e(elf, mhz) {
  kind = kind_;
  auto &g = e.mcu->gpio;
  g[P::NCS].setInputValue(true);
  g[P::SCK].setInputValue(false);
  g[P::MOSI].setInputValue(false);
}

void Rp2040Card::drive(uint32_t sck, uint32_t mosi, bool selected) {
  if (logging) {
    // record every frame: its MOSI bytes, and the time it ended
    if (selected && !sel) {
      bits.clear();
      rbits.clear();
      t0 = e.ns();
    }
    if (selected && sck && !sck_) {
      bits.push_back(static_cast<uint8_t>(mosi));
      rbits.push_back(static_cast<uint8_t>(miso()));
    }
    if (!selected && sel && !bits.empty()) {
      log.push_back({t0, e.ns(), packBits(bits), packBits(rbits), static_cast<uint32_t>(bits.size() % 8)});
    }
    sel = selected;
    sck_ = sck;
  }
  // Only the pins that change. setInputValue (rp2040js's, ported) latches
  // an edge on every call, so setting CS_n high again while it was high
  // made a rising edge the card never had: slotspi's CS_n interrupt then
  // restarted its PIO machine, and when that landed at the start of the
  // host's next frame the frame lost its first byte (exec's quick chunk
  // reads went unanswered, E2E-011).
  auto &g = e.mcu->gpio;
  constexpr uint32_t EDGE_HIGH = 1u << 3;  // the GPIO's latched rising edge (INTR)
  const bool edgeWas = g[P::NCS].irqStatus & EDGE_HIGH;
  if (!!mosi != pinMosi) g[P::MOSI].setInputValue(pinMosi = !!mosi);
  if (!!sck != pinSck) g[P::SCK].setInputValue(pinSck = !!sck);
  if (!selected != pinNcs) g[P::NCS].setInputValue(pinNcs = !selected);
  if (!edgeWas && (g[P::NCS].irqStatus & EDGE_HIGH)) csEdges++;
  if (!selected && selNow) csRises++;
  selNow = selected;
}

uint32_t Rp2040Card::miso() {
  GPIOPin &p = e.mcu->gpio[P::MISO];
  return p.outputEnable() ? (p.outputValue() ? 1 : 0) : 1;  // released: the main board's pull-up
}

bool Rp2040Card::irq() {
  GPIOPin &p = e.mcu->gpio[P::NIRQ];
  return p.outputEnable() && !p.outputValue();  // open drain, active low
}

// ------------------------------------------------------------ EspCard

// The firmware's QEMU build takes the slot's SPI frames over UART1
// (fw/wifi/port/esp32c3/main/transport_uart.c): $A6 asks for the MISO
// preload before a frame, $A5 len16 bytes delivers the MOSI bytes after it.
// QEMU runs in icount mode, its clock a function of the instructions run,
// and only as far as this card lets it (tools/patches/qemu-esp-lockstep.patch,
// system/cupc8-lockstep.c): advance(t) grants it the board's time t in
// GRANT_NS steps, so it trails the board, and each UART exchange is sent at
// the board's time of the select or deselect, reaches the guest at that
// guest time, and waits for the guest's answer (which takes guest time: QEMU
// may then be ahead of the board, and later grants below its clock are no-ops).
// The same board run gives the same guest run, cycle for cycle.

EspCard::EspCard(int tx_, int rx_) : tx(tx_), rx(rx_) {
  kind = "wifi";
  if (const char *f = std::getenv("CUPC8_ESP_TRACE")) trace = std::fopen(f, "w");
}

EspCard::~EspCard() {
  if (trace) std::fclose(trace);
}

void EspCard::readAll(uint8_t *b, size_t n) {
  for (size_t got = 0; got < n;) {
    const ssize_t r = ::read(rx, b + got, n - got);
    if (r < 0 && errno == EINTR) continue;
    if (r <= 0) throw std::runtime_error("the Wi-Fi card's QEMU has gone");
    got += static_cast<size_t>(r);
  }
}

void EspCard::writeAll(const std::vector<uint8_t> &b) {
  for (size_t put = 0; put < b.size();) {
    const ssize_t r = ::write(tx, b.data() + put, b.size() - put);
    if (r < 0 && errno == EINTR) continue;
    if (r <= 0) throw std::runtime_error("cannot write to the Wi-Fi card's QEMU");
    put += static_cast<size_t>(r);
  }
}

template <typename T>
static void putLE(std::vector<uint8_t> &v, T x) {
  for (size_t i = 0; i < sizeof x; i++) v.push_back(static_cast<uint8_t>(static_cast<uint64_t>(x) >> (8 * i)));
}

void EspCard::advance(double ns) {
  if (ns < granted + GRANT_NS) return;
  granted = ns;
  std::vector<uint8_t> m = {'G'};
  putLE(m, static_cast<int64_t>(ns));
  writeAll(m);
}

// the UART receives `send` at the board's time, then QEMU runs until the
// UART has sent k bytes, which are returned
std::vector<uint8_t> EspCard::exchange(uint32_t k, const std::vector<uint8_t> &send) {
  const double t = now();
  std::vector<uint8_t> m = {'X'};
  putLE(m, static_cast<int64_t>(t));
  putLE(m, k);
  putLE(m, static_cast<uint16_t>(send.size()));
  m.insert(m.end(), send.begin(), send.end());
  writeAll(m);
  uint8_t h[9];
  readAll(h, 9);
  int64_t g = 0;
  for (int i = 7; i >= 0; i--) g = (g << 8) | h[1 + i];
  guestNs = g;
  if (h[0] != 'R')
    throw std::runtime_error("the Wi-Fi card's firmware did not answer in 10 s of its time (QEMU at " +
                             std::to_string(g) + " ns, board at " + std::to_string(t) + " ns)");
  std::vector<uint8_t> got(k);
  readAll(got.data(), k);
  if (trace) {
    std::fprintf(trace, "%.0f W", t);
    for (uint8_t b : send) std::fprintf(trace, " %02x", b);
    std::fprintf(trace, "\n%.0f R", t);
    for (uint8_t b : got) std::fprintf(trace, " %02x", b);
    std::fprintf(trace, " @%lld\n", static_cast<long long>(g));
    std::fflush(trace);
  }
  return got;
}

void EspCard::drive(uint32_t sck, uint32_t mosi, bool sel) {
  if (sel && !selected) {
    const std::vector<uint8_t> h = exchange(3, {0xa6});
    const std::vector<uint8_t> pre = exchange(h[1] | (h[2] << 8), {});
    bits.clear();
    for (uint8_t b : pre)
      for (int i = 7; i >= 0; i--) bits.push_back((b >> i) & 1);
    mosi_.clear();
    bit = 0;
    start = now();
  } else if (!sel && selected) {
    const std::vector<uint8_t> bytes = packBits(mosi_);
    if (!bytes.empty()) {
      std::vector<uint8_t> msg = {0xa5, static_cast<uint8_t>(bytes.size() & 0xff),
                                  static_cast<uint8_t>(bytes.size() >> 8)};
      msg.insert(msg.end(), bytes.begin(), bytes.end());
      exchange(static_cast<uint32_t>(3 + bytes.size()), msg);
    }
    if (logging) {
      std::vector<uint8_t> shifted(bits.begin(), bits.begin() + static_cast<long>(std::min(bit, bits.size())));
      shifted.resize(mosi_.size(), 0);
      log.push_back({start, static_cast<double>(guestNs), bytes, packBits(shifted), static_cast<uint32_t>(mosi_.size() % 8)});
    }
  }
  if (sel && sck && !lastSck) {  // mode 0: sampled on the rising edge
    mosi_.push_back(static_cast<uint8_t>(mosi));
    bit++;
  }
  selected = sel;
  lastSck = sck;
}

uint32_t EspCard::miso() { return selected ? (bit < bits.size() ? bits[bit] : 0) : 1; }

// ------------------------------------------------------------ SysctlCard

static constexpr int BR_NCS = 5, SYS_NRST = 23, CHIPSET_CDONE = 7, CPUCARD_CDONE = 17;

SysctlCard::SysctlCard(const std::string &elf) : e(elf, 125), cdc(e.mcu->usbCtrl, 2) {
  auto &g = e.mcu->gpio;
  g[CHIPSET_CDONE].setInputValue(true);  // both FPGAs configured
  g[CPUCARD_CDONE].setInputValue(true);
  g[8].setInputValue(true);
  e.mcu->spi[0].onTransmit = [this](uint32_t b) { pending = Pending{b, 0, 0, 0}; };
  for (size_t p = 0; p < 2; p++) {
    cdc.ports[p].onSerialData = [this, p](const std::vector<uint8_t> &buf) {
      fromCard[p].insert(fromCard[p].end(), buf.begin(), buf.end());
    };
  }
}

void SysctlCard::feed() {
  for (size_t p = 0; p < 2; p++) {
    while (!toCard[p].empty() && cdc.ports[p].txFIFO.itemCount() < 256) {
      cdc.sendSerialByte(toCard[p].front(), p);
      toCard[p].pop_front();
    }
  }
}

void SysctlCard::openConsole(bool on) {
  if (on == consoleOpen) return;
  consoleOpen = on;
  cdc.open(CONSOLE, on);
}

// the bridge pins, as they are this clock (called once per core clock while busy)
BridgePins SysctlCard::bridgePins(uint32_t brMiso) {
  GPIOPin &n = e.mcu->gpio[BR_NCS];
  const uint32_t ncs = n.outputEnable() ? (n.outputValue() ? 1 : 0) : 1;
  if (!pending) return {0, 0, ncs};
  Pending &p = *pending;
  // 1 MHz: 6 core clocks a half period; sample MISO as SCK rises (mode 0)
  const uint32_t phase = p.half / 6;
  const uint32_t bit = phase >> 1, high = phase & 1;
  if (high && p.half % 6 == 0) p.got = (p.got << 1) | brMiso;
  p.half++;
  if (bit >= 8) {
    const uint32_t got = p.got;
    pending.reset();
    e.mcu->spi[0].completeTransmit(got & 0xff);
    return {0, 0, ncs};
  }
  return {high, (p.out >> (7 - bit)) & 1, ncs};
}

bool SysctlCard::sysReset() {
  GPIOPin &p = e.mcu->gpio[SYS_NRST];
  return p.outputEnable() && !p.outputValue();  // driven low: the supervisor resets the board
}

// ------------------------------------------------------------ TmdsCapture

// control tokens: (C1 = vsync, C0 = hsync)
static int ctrlToken(uint32_t sym) {
  switch (sym) {
    case 0b1101010100: return 0;
    case 0b0010101011: return 1;
    case 0b0101010100: return 2;
    case 0b1010101011: return 3;
    default: return -1;
  }
}

static uint32_t decodeData(uint32_t sym) {
  uint32_t q = sym & 0xff;
  if (sym & 0x200) q = ~q & 0xff;
  uint32_t d = q & 1;
  for (int i = 1; i < 8; i++) {
    const uint32_t bit = ((q >> i) ^ (q >> (i - 1))) & 1;
    d |= (sym & 0x100 ? bit : bit ^ 1) << i;
  }
  return d;
}

std::vector<TmdsCapture::Line> TmdsCapture::analyse() const {
  const auto &blue = lanes[0];
  const size_t n = std::min({lanes[0].size(), lanes[1].size(), lanes[2].size()});
  auto ctrl = [&](size_t i) { return i < blue.size() ? ctrlToken(blue[i]) : -1; };  // -1 for data symbols
  // hsync is active low: C0 = 0 during the pulse
  auto hs = [&](size_t i) { int c = ctrl(i); return c >= 0 && (c & 1) == 0; };
  auto vs = [&](size_t i) { int c = ctrl(i); return c >= 0 && (c & 2) == 0; };
  std::vector<size_t> starts;
  for (size_t i = 1; i < n; i++)
    if (hs(i) && !hs(i - 1)) starts.push_back(i);
  std::vector<Line> out;
  for (size_t l = 0; l + 1 < starts.size(); l++) {
    const size_t a = starts[l], b = starts[l + 1];
    size_t hsLen = 0;
    while (hs(a + hsLen)) hsLen++;
    long ds = -1;
    size_t dl = 0;
    for (size_t i = a; i < b; i++) {
      if (ctrl(i) < 0) {
        if (ds < 0) ds = static_cast<long>(i);
        dl++;
      }
    }
    out.push_back({a, b - a, hsLen, ds, dl, vs(a)});
  }
  return out;
}

TmdsCapture::Frame TmdsCapture::frame(const std::vector<Line> &lines) const {
  Frame f;
  // a frame starts at the first line after a vsync run
  size_t k = 1;
  while (k < lines.size() && !(lines[k - 1].vsync && !lines[k].vsync)) k++;
  std::vector<const Line *> active;
  for (size_t l = k; l < lines.size() && active.size() < 480; l++) {
    if (lines[l].vsync) {
      f.error = "vsync after " + std::to_string(active.size()) + " active lines";
      return f;
    }
    if (lines[l].dataLen) active.push_back(&lines[l]);
  }
  if (active.size() < 480) {
    f.error = "only " + std::to_string(active.size()) + " active lines captured";
    return f;
  }
  f.rgb.assign(640 * 480, 0);
  for (size_t y = 0; y < 480; y++) {
    const Line &L = *active[y];
    if (L.dataLen != 640) {
      f.error = "line " + std::to_string(y) + " has " + std::to_string(L.dataLen) + " data symbols";
      f.rgb.clear();
      return f;
    }
    for (size_t x = 0; x < 640; x++) {
      const size_t i = static_cast<size_t>(L.dataStart) + x;
      f.rgb[y * 640 + x] = (decodeData(lanes[2][i]) << 16) | (decodeData(lanes[1][i]) << 8) | decodeData(lanes[0][i]);
    }
  }
  f.firstLine = k;
  return f;
}

// ------------------------------------------------------------ Machine

Machine::Machine(const Options &o) : board(std::make_unique<MainBoard>()), root(o.root), threaded_(o.threaded) {
  if (o.sysctl) sysctl = std::make_unique<SysctlCard>(root + "/build/rp2040/sysctl.elf");
  for (const auto &[slot, kind] : o.slots) {
    if (kind == "wifi") {
      auto c = std::make_unique<EspCard>(o.espTx, o.espRx);
      c->now = [this] { return board->ns(); };
      c->slot = slot;
      c->logging = o.spiLog;
      cards.emplace_back(slot, std::move(c));
      continue;
    }
    // the HDMI card's firmware is the graphics card's, gpu.elf
    static const std::set<std::string> known{"hdmi", "eink", "eink750", "io", "storage"};
    if (!known.count(kind)) throw std::runtime_error("unknown slot kind '" + kind + "' (hdmi, eink, eink750, io, storage, wifi)");
    const std::string elf = kind == "hdmi" ? "gpu" : kind;
    auto c = std::make_unique<Rp2040Card>(kind, root + "/build/rp2040/" + elf + ".elf", kind == "hdmi" ? 252 : 125);
    c->slot = slot;
    c->logging = o.spiLog;
    if (kind == "hdmi") tmds = std::make_unique<TmdsCapture>(c->e);
    if (kind == "eink" || kind == "eink750")  // the panel on its header: 5.83" 648x480 or 7.5" 800x480
      panels[slot] = std::make_unique<EinkPanel>(c->e, EinkPanel::config(kind == "eink" ? 648 : 800, 480));
    if (kind == "storage") c->sd = std::make_unique<rp2040js::harness::SdSocket>(*c->e.mcu);  // empty until a card goes in
    if (kind == "io") {
      c->e.mcu->gpio[8].setInputValue(true);  // VBUS switch: no fault
      keyboard = std::make_unique<UsbKeyboard>(UsbKeyboard::Options{1, 10});
    }
    cards.emplace_back(slot, std::move(c));
  }
  romImage = o.rom;
  if (threaded_) startWorkers();
}

Machine::~Machine() { stopWorkers(); }

void Machine::powerOn() {
  board->init(romImage.data(), romImage.size());
  board->run(12, inputs(false));  // the supervisor holds nPOR a moment
  if (keyboard)
    for (auto &[slot, c] : cards)
      if (c->kind == "io") {
        c->emu()->mcu->usbCtrl.attachDevice(keyboard.get());
        break;
      }
}

uint32_t Machine::inputs(bool por) {
  const uint32_t out = board->outputs();
  const uint32_t cs = (out >> 2) & 0x7f;
  uint32_t miso = 1, nirq = 0x3f;
  for (auto &[slot, card] : cards) {
    const int dev = slot - 1;
    if (!((cs >> dev) & 1)) miso &= card->miso();
    if (card->irq()) nirq &= ~(1u << dev);
  }
  const bool reset = sysctl && sysctl->sysReset();
  return miso | (nirq << 1) | (br.sck << 7) | (br.mosi << 8) | (br.ncs << 9) | ((pwrHi ? 1u : 0u) << 10) |
         (1u << 11) | ((por && !reset ? 1u : 0u) << 12);
}

double Machine::ns() const { return board->ns(); }

// run the machine for `ns` of emulated time
void Machine::runFor(double ns) {
  const double end = board->ns() + ns;
  if (workers.empty()) {
    while (board->ns() < end) iterate();
    return;
  }
  // the card threads run it (the first iteration led by worker 0) and say
  // when they have reached `end`
  runEnd = end;
  const uint32_t r = runSeq.fetch_add(1, std::memory_order_seq_cst) + 1;
  epoch.v.fetch_add(1, std::memory_order_seq_cst);
  epoch.wake();
  for (uint32_t d = runDone.v.load(std::memory_order_acquire); d != r; d = runDone.v.load(std::memory_order_acquire))
    runDone.waitWhile(d, 2000);
}

void Machine::iterate() {
  const uint32_t out = board->outputs();
  const uint32_t cs = (out >> 2) & 0x7f;
  if (sysctl) br = sysctl->bridgePins((out >> 9) & 1);
  const bool busy = cs != 0x7f || (sysctl && (!br.ncs || sysctl->pending));
  iterateSerial(busy, cs);
  stats.busyIterations += busy;
  stats.idleWindows += !busy;
  if (stats.traceOn) traceStep();
}

void Machine::iterateSerial(bool busy, uint32_t cs) {
  // A card reacts to the pins it was given at the last clock during the
  // clock that follows, so it runs up to the next edge before the core
  // samples MISO there (machine.mjs).
  if (cs != 0x7f)
    for (auto &[slot, card] : cards) card->advance(board->ns() + NS_PER_CLOCK);
  const uint32_t n = board->run(busy ? 1 : IDLE_CLOCKS, inputs());
  (busy ? stats.busyClocks : stats.idleClocks) += n;
  const double t = board->ns();
  if (sysctl) sysctl->advance(t);
  const uint32_t now = board->outputs();
  const uint32_t sck = now & 1, mosi = (now >> 1) & 1, ncs = (now >> 2) & 0x7f;
  for (auto &[slot, card] : cards) {
    card->advance(t);
    card->drive(sck, mosi, !((ncs >> (slot - 1)) & 1));
  }
}

// ------------------------------------------------------------ Threads
//
// Each RP2040 card has a thread. There is no board thread: the last card
// thread to finish a window is the leader for what follows. It runs the
// serial part of the loop exactly as iterate() does (bridgePins, busy
// iterations in lockstep with every card, the board's run for an idle
// window), then does its own card's share of the window like the others.
// While the leader runs the board for an idle window, the other cards chase
// its clock count; each advances to the window's end and takes its drive()
// once the leader marks the window FINAL. The slowest card (the GPU) is
// usually the last to finish, so it goes straight on with no hand-off.

void Machine::Word::wake() {
  if (sleepers.load(std::memory_order_seq_cst))
    syscall(SYS_futex, &v, FUTEX_WAKE_PRIVATE, INT32_MAX, nullptr, nullptr, 0);
}

uint32_t Machine::Word::waitWhile(uint32_t old, unsigned spins) {
  for (unsigned i = 0; i < spins; i++) {
    const uint32_t now = v.load(std::memory_order_acquire);
    if (now != old) return now;
    cpuRelax();
  }
  sleepers.fetch_add(1, std::memory_order_seq_cst);
  while (v.load(std::memory_order_seq_cst) == old)
    syscall(SYS_futex, &v, FUTEX_WAIT_PRIVATE, old, nullptr, nullptr, 0);
  sleepers.fetch_sub(1, std::memory_order_seq_cst);
  return v.load(std::memory_order_acquire);
}

// The serial part, up to the start of the next idle window (true), or to the
// end of the run (false: the run is over and every card thread parks).
bool Machine::leadNext() {
  if (pendingTrace) {
    traceStep();
    pendingTrace = false;
  }
  for (;;) {
    if (!(board->ns() < runEnd) || quit.load(std::memory_order_relaxed)) {
      runDone.v.store(runSeq.load(std::memory_order_relaxed), std::memory_order_seq_cst);
      runDone.wake();
      return false;
    }
    const uint32_t out = board->outputs();
    const uint32_t cs = (out >> 2) & 0x7f;
    if (sysctl) br = sysctl->bridgePins((out >> 9) & 1);
    const bool busy = cs != 0x7f || (sysctl && (!br.ncs || sysctl->pending));
    if (busy) {
      iterateSerial(busy, cs);
      stats.busyIterations++;
      if (stats.traceOn) traceStep();
      continue;
    }
    // an idle window: nothing is advanced before the board runs
    const uint32_t in = inputs();
    windowStart = board->clocks;
    progress.v.store(0, std::memory_order_relaxed);
    arrived.store(0, std::memory_order_relaxed);
    window.fetch_add(1, std::memory_order_release);
    epoch.v.fetch_add(1, std::memory_order_seq_cst);
    epoch.wake();
    // (the chasers spin on this; one that has gone to sleep is woken at FINAL)
    const uint32_t n = board->run(IDLE_CLOCKS, in, [this] {
      progress.v.store(static_cast<uint32_t>(board->clocks - windowStart), std::memory_order_release);
    });
    stats.idleClocks += n;
    windowOut = board->outputs();
    progress.v.store(static_cast<uint32_t>(board->clocks - windowStart) | FINAL, std::memory_order_seq_cst);
    progress.wake();
    const uint32_t sck = windowOut & 1, mosi = (windowOut >> 1) & 1, ncs = (windowOut >> 2) & 0x7f;
    for (Card *c : mainCards) {  // as iterateSerial: advance to the window's end, then drive
      c->advance(board->ns());
      c->drive(sck, mosi, !((ncs >> (c->slot - 1)) & 1));
    }
    stats.idleWindows++;
    pendingTrace = stats.traceOn;
    return true;
  }
}

// one card's share of an idle window: SysctlCard.advance / Rp2040Card.advance
// to the window's end, chasing the board, then drive()
void Machine::cardWindow(Worker &w) {
  Emu &e = w.sys ? w.sys->e : *w.card->emu();
  if (w.sys) w.sys->feed();  // the first half of SysctlCard.advance
  for (uint32_t p = progress.v.load(std::memory_order_acquire);;) {
    // the board has run this far, so the window ends no earlier: advance(t)
    // would take every one of these steps
    const double target = static_cast<double>(windowStart + (p & ~FINAL)) * NS_PER_CLOCK;
    while (e.ns() < target) e.step();
    if (p & FINAL) break;
    p = progress.waitWhile(p, 300);
  }
  if (w.card) {
    const uint32_t out = windowOut;
    w.card->drive(out & 1, (out >> 1) & 1, !((((out >> 2) & 0x7f) >> (w.card->slot - 1)) & 1));
  }
}

void Machine::workerLoop(size_t index, uint32_t seenWindow, uint32_t seenRun) {
  Worker &w = *workers[index];
  const uint32_t n = static_cast<uint32_t>(workers.size());
  for (;;) {
    bool lead = false;
    for (uint32_t ep = epoch.v.load(std::memory_order_acquire);; ep = epoch.waitWhile(ep, 200)) {
      if (quit.load(std::memory_order_acquire)) return;
      if (window.load(std::memory_order_acquire) != seenWindow) break;
      if (index == 0 && runSeq.load(std::memory_order_acquire) != seenRun) {
        seenRun = runSeq.load(std::memory_order_acquire);
        lead = true;
        break;
      }
    }
    if (lead && !leadNext()) continue;
    for (;;) {
      seenWindow = window.load(std::memory_order_acquire);
      cardWindow(w);
      timespec ts;
      clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
      w.cpu.store(ts.tv_sec + ts.tv_nsec * 1e-9, std::memory_order_relaxed);
      if (arrived.fetch_add(1, std::memory_order_acq_rel) + 1 != n) {
        // Not the last. A quick card volunteers to lead the next window, so
        // that the slow card (the last to arrive) need not run the board
        // before its own share: it chases the board instead. The volunteer
        // spins for a while and withdraws if the others take too long.
        uint32_t idle = 0;
        if (!w.volunteer || !handoff.compare_exchange_strong(idle, 1, std::memory_order_acq_rel)) break;
        bool accepted = false;
        for (unsigned i = 0; i < volunteerSpins; i++) {
          if (handoff.load(std::memory_order_acquire) == 2) {
            accepted = true;
            break;
          }
          cpuRelax();
        }
        uint32_t offered = 1;
        if (!accepted && handoff.compare_exchange_strong(offered, 0, std::memory_order_acq_rel)) break;  // withdrawn
        handoff.store(0, std::memory_order_relaxed);  // accepted by the last card: lead
      } else {
        uint32_t offered = 1;
        if (handoff.compare_exchange_strong(offered, 2, std::memory_order_acq_rel)) break;  // a volunteer leads
      }
      if (!leadNext()) break;  // the run is over
    }
  }
}

std::vector<std::pair<std::string, double>> Machine::threadCpu() const {
  std::vector<std::pair<std::string, double>> out;
  for (auto &w : workers) out.emplace_back(w->sys ? "sysctl" : w->card->kind, w->cpu.load());
  return out;
}

void Machine::startWorkers() {
  if (!workers.empty()) return;
  quit = false;
  mainCards.clear();
  if (sysctl) {
    auto w = std::make_unique<Worker>();
    w->sys = sysctl.get();
    w->volunteer = true;
    workers.push_back(std::move(w));
  }
  for (auto &[slot, card] : cards) {
    if (card->emu()) {
      auto w = std::make_unique<Worker>();
      w->card = card.get();
      w->volunteer = card->kind != "hdmi";
      workers.push_back(std::move(w));
    } else {
      mainCards.push_back(card.get());
    }
  }
  handoff.store(0);
  if (const char *v = std::getenv("CUPC8_EMU_VOLUNTEER_SPINS")) volunteerSpins = static_cast<unsigned>(std::atoi(v));
  // what the threads have seen so far, taken now: a thread may start after the first run()
  const uint32_t w0 = window.load(), r0 = runSeq.load();
  for (size_t i = 0; i < workers.size(); i++) workers[i]->th = std::thread([this, i, w0, r0] { workerLoop(i, w0, r0); });
}

void Machine::stopWorkers() {
  if (workers.empty()) return;
  quit.store(true, std::memory_order_seq_cst);
  epoch.v.fetch_add(1, std::memory_order_seq_cst);
  epoch.wake();
  for (auto &w : workers) w->th.join();
  workers.clear();
  mainCards.clear();
}

void Machine::setThreaded(bool on) {
  threaded_ = on;
  if (on)
    startWorkers();
  else
    stopWorkers();
}

void Machine::traceStep() {
  auto mix = [this](uint64_t v) {
    for (int i = 0; i < 8; i++) {
      stats.trace ^= (v >> (8 * i)) & 0xff;
      stats.trace *= 0x100000001b3ull;
    }
  };
  mix(board->clocks);
  mix(board->outputs());
  auto mixNs = [&](double d) {
    uint64_t b;
    std::memcpy(&b, &d, 8);
    mix(b);
  };
  if (sysctl) mixNs(sysctl->e.ns());
  for (auto &[slot, card] : cards)
    if (card->emu()) mixNs(card->emu()->ns());
}

Machine::State Machine::state() const {
  Vmachine_core *top = board->top;
  return {top->dbg_pc, top->dbg_sp, top->dbg_r0, top->dbg_r1, top->cpu_halted, top->cpu_n_rst, top->gpo};
}

// capture a whole frame from the GPU's TMDS output (about two frame times)
TmdsCapture::Frame Machine::frame() {
  if (!tmds) {
    TmdsCapture::Frame f;
    f.error = "no graphics card";
    return f;
  }
  tmds->start();
  runFor(40e6);
  tmds->stop();
  return tmds->frame(tmds->analyse());
}

// the 8x16 text font: font8x8_cp437 with each row doubled (gpu.c)
static std::vector<std::array<uint8_t, 16>> loadFont(const std::string &root) {
  std::ifstream in(root + "/fw/common/font8x8_cp437.c");
  if (!in) throw std::runtime_error("cannot read fw/common/font8x8_cp437.c");
  const std::string src((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  std::vector<uint8_t> bytes;
  auto hex = [](char c) { return std::isxdigit(static_cast<unsigned char>(c)) != 0; };
  for (size_t i = src.find('{'); i != std::string::npos && i + 3 < src.size();) {  // /0x[0-9a-fA-F]{2}/g
    if (src[i] == '0' && src[i + 1] == 'x' && hex(src[i + 2]) && hex(src[i + 3])) {
      bytes.push_back(static_cast<uint8_t>(std::stoi(src.substr(i + 2, 2), nullptr, 16)));
      i += 4;
    } else {
      i++;
    }
  }
  std::vector<std::array<uint8_t, 16>> font(256);
  for (int c = 0; c < 256; c++)
    for (int r = 0; r < 16; r++) {
      const size_t at = static_cast<size_t>(c * 8 + (r >> 1));
      font[c][r] = at < bytes.size() ? bytes[at] : 0;
    }
  return font;
}

// the text in a picture: each 8x16 cell matched against the font (either polarity,
// so the cursor's inverted cell reads as its character); px(x, y) is a colour
std::vector<std::string> Machine::cells(const std::function<uint32_t(int, int)> &px) {
  if (font.empty()) font = loadFont(root);
  std::vector<std::string> rows;
  for (int row = 0; row < 30; row++) {
    std::string line;
    for (int col = 0; col < 80; col++) {
      const int x0 = col * 8, y0 = row * 16;
      const uint32_t bg = px(x0, y0);
      std::array<uint8_t, 16> bits{}, inv{};
      bool any = false;
      for (int y = 0; y < 16; y++) {
        uint8_t b = 0;
        for (int x = 0; x < 8; x++)
          if (px(x0 + x, y0 + y) != bg) b |= 0x80 >> x;
        bits[y] = b;
        inv[y] = static_cast<uint8_t>(~b & 0xff);
        any |= b != 0;
      }
      char ch = ' ';
      if (any) {
        int c = -1;
        for (int i = 0; i < 256 && c < 0; i++)
          if (font[i] == bits || font[i] == inv) c = i;
        ch = c >= 32 && c < 127 ? static_cast<char>(c) : c < 0 ? '?' : '.';
      }
      line += ch;
    }
    while (!line.empty() && line.back() == ' ') line.pop_back();
    rows.push_back(line);
  }
  return rows;
}

EinkPanel *Machine::panel() { return panels.empty() ? nullptr : panels.begin()->second.get(); }

std::vector<std::string> Machine::panelScreen(std::string *error) {
  EinkPanel *p = panel();
  if (!p) {
    if (error) *error = "no e-ink card";
    return {};
  }
  const EinkPanel::Picture pic = p->picture();
  const int ox = (pic.w - 640) / 2;  // 80x30 centred
  return cells([&](int x, int y) { return static_cast<uint32_t>(pic.grey[y * pic.w + ox + x]); });
}

// the text on screen: each 8x16 cell matched against the font (either polarity,
// so the cursor's inverted cell reads as its character)
std::vector<std::string> Machine::screen(std::string *error) {
  const TmdsCapture::Frame f = frame();
  if (!f.error.empty()) {
    if (error) *error = f.error;
    return {};
  }
  if (font.empty()) font = loadFont(root);
  std::vector<std::string> rows;
  for (int row = 0; row < 30; row++) {
    std::string line;
    for (int col = 0; col < 80; col++) {
      auto px = [&](int x, int y) { return f.rgb[(row * 16 + y) * 640 + col * 8 + x] & 0xc0c0c0; };  // RGB222 levels
      const uint32_t bg = px(0, 0);
      std::array<uint8_t, 16> bits{}, inv{};
      bool any = false;
      for (int y = 0; y < 16; y++) {
        uint8_t b = 0;
        for (int x = 0; x < 8; x++)
          if (px(x, y) != bg) b |= 0x80 >> x;
        bits[y] = b;
        inv[y] = static_cast<uint8_t>(~b & 0xff);
        any |= b != 0;
      }
      char ch = ' ';
      if (any) {
        int c = -1;
        for (int i = 0; i < 256 && c < 0; i++)
          if (font[i] == bits || font[i] == inv) c = i;
        ch = c >= 32 && c < 127 ? static_cast<char>(c) : c < 0 ? '?' : '.';
      }
      line += ch;
    }
    while (!line.empty() && line.back() == ' ') line.pop_back();
    rows.push_back(line);
  }
  return rows;
}

rp2040js::harness::SdSocket *Machine::sd() {
  for (auto &[slot, c] : cards)
    if (c->kind == "storage") return static_cast<Rp2040Card *>(c.get())->sd.get();
  return nullptr;
}

// type on the USB keyboard: one report per key, then a release
void Machine::type(const std::string &text) {
  if (!keyboard) throw std::runtime_error("no IO card (no keyboard)");
  static const std::string shifted = "~!@#$%^&*()_+{}|:\"<>?";
  static const std::string plain = "`1234567890-=[]\\;',./";
  static const int codes[] = {53, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 46, 47, 48, 49, 51, 52, 54, 55, 56};
  for (char c : text) {
    uint32_t mods = 0, u = 0;  // an unknown key is `undefined`, which Uint8Array.from stores as 0
    if (c >= 'a' && c <= 'z')
      u = 4 + (c - 'a');
    else if (c >= 'A' && c <= 'Z') {
      u = 4 + (c - 'A');
      mods = 2;
    } else if (c >= '1' && c <= '9')
      u = 30 + (c - '1');
    else if (c == '0')
      u = 39;
    else if (c == '\n')
      u = 40;
    else if (c == ' ')
      u = 44;
    else {
      const size_t pk = plain.find(c), sk = shifted.find(c);
      const long k = pk != std::string::npos ? static_cast<long>(pk) : sk != std::string::npos ? static_cast<long>(sk) : -1;
      if (sk != std::string::npos) mods = 2;
      u = k >= 0 ? codes[k] : 0;
    }
    keyboard->press(mods, {u});
    keyboard->press(0);
  }
}

}  // namespace machine
