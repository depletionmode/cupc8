// The whole CUPC/8 machine, emulated natively (doc/milestone-1.md, "Emulator
// speed"): test/emu/machine.mjs in C++. The main board's CPU and chipset from
// their RTL (Verilated, soc/emu/board.h), the SRAM and the SST39 ROM chip,
// and the cards on their real firmware: the RP2040 cards (GPU, IO, system
// card) on the native RP2040 (emu/rp2040), the Wi-Fi card in Espressif's
// QEMU over pipes, exactly as machine.mjs's EspCard.
//
// The loop is machine.mjs's runFor, iteration for iteration: one 12 MHz
// clock at a time while any slot or the bridge is selected ("busy"), up to
// IDLE_CLOCKS at a time otherwise, with the main board's inputs sampled once
// per board run and every card advanced to the board's time afterwards.
//
// Threaded mode (the default) runs each RP2040 card on its own thread and
// gives exactly the same result. In an idle window the board runs with its
// inputs fixed at the window start, and every card chases the board's clock
// count (published after each board clock) up to the window's end, which is
// where the serial loop advances it to, then takes its end-of-window drive().
// Nothing a card does in the window reaches the board or another card before
// the window ends: the cards meet only at the barrier, where the board
// samples their pins. A card behind a clock count the board has passed takes
// exactly the steps the serial loop takes (advance(t) is `while (ns < t)
// step()`, and the step sequence does not depend on t). There is no board
// thread: the last card thread to finish a window leads the next, running
// the serial part (bridgePins, busy iterations in lockstep with every card in
// machine.mjs's order, the board's run); see machine.cpp, "Threads".
#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <deque>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "emu.h"
#include "sdcard.h"
#include "tmds.h"
#include "usb/cdc.h"
#include "usb/usbkbd.h"

struct MainBoard;

namespace machine {

using rp2040js::harness::Emu;

constexpr double NS_PER_CLOCK = 1000.0 / 12.0;
constexpr uint32_t IDLE_CLOCKS = 120;  // 10 us between syncs while no slot is selected

// one slot SPI frame a card saw (machine.mjs's Rp2040Card log)
struct SpiFrame {
  double start, ns;
  std::vector<uint8_t> bytes, miso;
  uint32_t extra;
};

class Card {
 public:
  std::string kind;
  int slot = 0;
  virtual ~Card() = default;
  virtual void advance(double) {}
  virtual void drive(uint32_t sck, uint32_t mosi, bool selected) = 0;
  virtual uint32_t miso() = 0;
  virtual bool irq() = 0;
  virtual Emu *emu() { return nullptr; }
};

// The GPU's DVI output decoded (test/emu/tmds.mjs's analyse() and frame())
// from the symbols the harness's TmdsCapture records
class TmdsCapture : public rp2040js::harness::TmdsCapture {
 public:
  struct Line {
    size_t start, total, hsyncLen;
    long dataStart;
    size_t dataLen;
    bool vsync;
  };
  struct Frame {
    std::string error;
    std::vector<uint32_t> rgb;  // 640x480 RGB888
    size_t firstLine = 0;
  };
  using rp2040js::harness::TmdsCapture::TmdsCapture;
  std::vector<Line> analyse() const;
  Frame frame(const std::vector<Line> &lines) const;
};

class Rp2040Card : public Card {
 public:
  Emu e;
  bool logging = false;
  std::vector<SpiFrame> log;
  std::unique_ptr<rp2040js::harness::SdSocket> sd;  // the storage card's microSD socket (SPI1)

  Rp2040Card(const std::string &kind, const std::string &elf, double mhz);
  // advance: run until the chip's time reaches `ns`
  void advance(double ns) override {
    while (e.ns() < ns) e.step();
  }
  void drive(uint32_t sck, uint32_t mosi, bool selected) override;
  uint32_t miso() override;
  bool irq() override;
  Emu *emu() override { return &e; }

 private:
  bool sel = false, sck_ = false;
  std::vector<uint8_t> bits, rbits;
  double t0 = 0;
};

// the Wi-Fi card in QEMU: tx/rx are the pipes to its UART1 (machine.mjs EspCard)
class EspCard : public Card {
 public:
  EspCard(int tx, int rx);
  ~EspCard() override;
  // CUPC8_ESP_TRACE=FILE: every exchange with QEMU, with the board's time
  std::function<double()> now;
  void drive(uint32_t sck, uint32_t mosi, bool selected) override;
  uint32_t miso() override;
  bool irq() override { return false; }

 private:
  int tx, rx;
  FILE *trace = nullptr;
  void traceBytes(const char *dir, const uint8_t *b, size_t n);
  bool selected = false;
  std::vector<uint8_t> bits, mosi_;
  size_t bit = 0;
  uint32_t lastSck = 0;
  void read(uint8_t *b, size_t n);
  void write(const std::vector<uint8_t> &b);
};

struct BridgePins {
  uint32_t sck = 0, mosi = 0, ncs = 1;
};

// the system card (machine.mjs SysctlCard): its bridge SPI master clocked
// into the chipset's BR_* pins at 1 MHz, its USB CDC a byte queue each way
class SysctlCard {
 public:
  Emu e;
  rp2040js::USBCDC cdc;
  struct Pending {
    uint32_t out, bit, got, half;
  };
  std::optional<Pending> pending;
  std::deque<uint8_t> toCard;
  std::vector<uint8_t> fromCard;  // CDC output not yet collected by the host side

  explicit SysctlCard(const std::string &elf);
  void feed();                    // the CDC half of advance()
  void advance(double ns) {
    feed();
    while (e.ns() < ns) e.step();
  }
  BridgePins bridgePins(uint32_t brMiso);
  bool sysReset();
};

class Machine {
 public:
  struct Options {
    std::map<int, std::string> slots;  // slot -> gpu | io | storage | wifi
    std::vector<uint8_t> rom;
    bool sysctl = false;
    std::string root;                  // the repository (build/rp2040/*.elf, the font)
    int espTx = -1, espRx = -1;        // the Wi-Fi card's pipes
    bool threaded = true;
    bool spiLog = false;
  };
  struct Stats {
    uint64_t idleWindows = 0, busyIterations = 0, idleClocks = 0, busyClocks = 0;
    uint64_t trace = 0xcbf29ce484222325ull;  // FNV-1a over (board clocks, card times) after every iteration
    bool traceOn = false;
  };

  explicit Machine(const Options &o);
  ~Machine();

  void powerOn();
  void runFor(double ns);
  double ns() const;
  void setThreaded(bool on);
  bool threaded() const { return threaded_; }

  struct State {
    uint32_t pc, sp, r0, r1, halted, nrst, gpo;
  };
  State state() const;
  TmdsCapture::Frame frame();
  // the text on screen (80x30); empty with `error` set if there is no picture
  std::vector<std::string> screen(std::string *error);
  void type(const std::string &text);
  // the storage card's microSD socket (the first storage card), or null
  rp2040js::harness::SdSocket *sd();

  std::vector<std::pair<int, std::unique_ptr<Card>>> cards;  // slot order
  std::unique_ptr<SysctlCard> sysctl;
  std::unique_ptr<TmdsCapture> tmds;
  std::unique_ptr<rp2040js::UsbKeyboard> keyboard;
  std::unique_ptr<MainBoard> board;
  Stats stats;
  // CPU seconds used by each card thread: (kind, seconds)
  std::vector<std::pair<std::string, double>> threadCpu() const;

 private:
  std::string root;
  std::vector<uint8_t> romImage;
  bool threaded_;
  bool pwrHi = true;
  BridgePins br;
  std::vector<std::array<uint8_t, 16>> font;

  uint32_t inputs(bool por = true);
  void iterate();
  void iterateSerial(bool busy, uint32_t cs);
  void traceStep();

  // --- the card threads (see machine.cpp, "Threads")
  struct Worker {
    Card *card = nullptr;          // a slot card, or
    SysctlCard *sys = nullptr;     // the system card
    bool volunteer = false;
    std::atomic<double> cpu{0};    // this thread's CPU seconds so far        // a quick card: may lead the next window while the slow one finishes
    std::thread th;
  };
  // a 32-bit word threads can sleep on (futex), with a count of sleepers so
  // that waking costs nothing while nobody sleeps
  struct Word {
    alignas(64) std::atomic<uint32_t> v{0};
    std::atomic<uint32_t> sleepers{0};
    void wake();
    // wait while v == old: spin `spins` times, then sleep
    uint32_t waitWhile(uint32_t old, unsigned spins);
  };
  std::vector<std::unique_ptr<Worker>> workers;
  std::vector<Card *> mainCards;   // cards with no emulator (the Wi-Fi card): driven by the leader
  Word epoch;                      // bumped when a window or a run starts, or on quit
  Word progress;                   // board clocks run in this window; FINAL once it has ended
  Word runDone;                    // the last run() that has finished
  alignas(64) std::atomic<uint32_t> window{0};   // window number
  std::atomic<uint32_t> arrived{0};              // cards done with this window
  std::atomic<uint32_t> runSeq{0};               // run() requests
  std::atomic<uint32_t> handoff{0};              // 0 none, 1 a volunteer waits to lead, 2 accepted
  unsigned volunteerSpins = 200000;              // CUPC8_EMU_VOLUNTEER_SPINS (0: never volunteer)
  uint64_t windowStart = 0;        // the board's clock count at the window's start
  uint32_t windowOut = 0;          // the board's outputs at the window's end
  double runEnd = 0;
  bool pendingTrace = false;
  std::atomic<bool> quit{false};
  static constexpr uint32_t FINAL = 1u << 31;
  void startWorkers();
  void stopWorkers();
  void workerLoop(size_t index, uint32_t seenWindow, uint32_t seenRun);
  bool leadNext();
  void cardWindow(Worker &w);
};

}  // namespace machine
