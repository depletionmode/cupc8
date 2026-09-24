// The CUPC/8 side of a card slot at pin level, natively: test/emu/slothost.mjs
// with the same timing, step for step. An SPI master in mode 0 with the
// chipset's clock divider (SCK = 12 MHz / (2 x clk_div)), the host timing
// rules of doc/hardware/slot.md, and MISO's pull-up on the main board.
//
// The JS SlotHost runs a generator that yields nanoseconds; here the script
// is a callback that is handed the result of the last operation and returns
// the next one (a wait, or a whole byte / select / deselect / frame / READ),
// so a script only runs between operations (per frame, not per cycle). The
// operations themselves are C++20 coroutines written like slothost.mjs's
// generators: every pin change and every wait happens on the same cycle as
// there. tick() must be called once per PIO cycle (Emu::onCycle).
#pragma once

#include <coroutine>
#include <cstdint>
#include <exception>
#include <functional>
#include <memory>
#include <utility>
#include <vector>

#include "emu.h"

namespace rp2040js::harness {

/** A lazily started coroutine returning T; `co_await` one to run it to completion. */
template <class T>
class Co {
 public:
  struct promise_type {
    T value{};
    std::coroutine_handle<> continuation;
    std::exception_ptr error;
    Co get_return_object() { return Co(std::coroutine_handle<promise_type>::from_promise(*this)); }
    std::suspend_always initial_suspend() noexcept { return {}; }
    struct Final {
      bool await_ready() noexcept { return false; }
      std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
        auto c = h.promise().continuation;
        return c ? c : std::noop_coroutine();
      }
      void await_resume() noexcept {}
    };
    Final final_suspend() noexcept { return {}; }
    void return_value(T v) { value = std::move(v); }
    void unhandled_exception() { error = std::current_exception(); }
  };

  Co() = default;
  explicit Co(std::coroutine_handle<promise_type> h) : h(h) {}
  Co(Co &&o) noexcept : h(std::exchange(o.h, {})) {}
  Co &operator=(Co &&o) noexcept {
    if (this != &o) {
      if (h) h.destroy();
      h = std::exchange(o.h, {});
    }
    return *this;
  }
  ~Co() {
    if (h) h.destroy();
  }

  bool await_ready() const noexcept { return false; }
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> c) noexcept {
    h.promise().continuation = c;
    return h;
  }
  T await_resume() {
    if (h.promise().error) std::rethrow_exception(h.promise().error);
    return std::move(h.promise().value);
  }

  std::coroutine_handle<promise_type> h;
};

class SlotHost {
 public:
  static constexpr uint32_t SCK = 2, MOSI = 3, MISO = 4, CS = 5;

  /** what a script asks for next */
  struct Op {
    enum Kind { Done, Wait, Byte, Select, Deselect, Frame, Read } kind = Done;
    double ns = 0;               // Wait: nanoseconds; Read: retryNs
    double tries = 0;            // Read
    std::vector<uint32_t> bytes; // Byte: {out}; Frame: the MOSI bytes
  };
  /** what the last operation returned */
  struct Result {
    enum Kind { None, Number, Bytes, Attempts } kind = None;
    uint32_t number = 0;                          // Byte: the MISO byte
    std::vector<uint32_t> bytes;                  // Frame: the MISO bytes
    std::vector<std::vector<uint32_t>> attempts;  // Read: each try's [status, len, ...data]
  };
  using Script = std::function<Op(const Result &)>;

  Emu &emu;
  double clkDiv, csSetupNs, byteGapNs, frameGapNs;
  bool done = true;
  double wakeAt = 0;

  SlotHost(Emu &emu, double clkDiv = 2, double csSetupNs = 2000, double byteGapNs = 1000,
           double frameGapNs = 20000);
  SlotHost(const SlotHost &) = delete;
  SlotHost &operator=(const SlotHost &) = delete;

  double halfNs() const;
  // MISO has a pull-up on the main board: an undriven line reads 1
  uint32_t miso();

  /** start a script: its first call is on the next tick */
  void run(Script script);
  /** once per PIO cycle */
  void tick() {
    if (done || emu.ns() < wakeAt) return;
    resume();
  }

 private:
  std::shared_ptr<Script> script;
  uint64_t generation = 0;            // run() count: a script may start another
  bool inOp = false;                  // an operation's coroutine is running
  Co<Result> op;                      // the operation in progress
  std::coroutine_handle<> waiting;    // where it waits

  struct WaitFor {
    SlotHost &host;
    double ns;
    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<> h) noexcept {
      host.wakeAt = host.emu.ns() + ns;
      host.waiting = h;
    }
    void await_resume() const noexcept {}
  };
  WaitFor wait(double ns) { return WaitFor{*this, ns}; }

  GPIOPin &pin(uint32_t n) { return emu.mcu->gpio[n]; }
  void resume();
  void drive(Result r);

  Co<uint32_t> byte(uint32_t out);
  Co<bool> select();
  Co<bool> deselect();
  Co<std::vector<uint32_t>> frame(std::vector<uint32_t> bytes);
  Co<std::vector<std::vector<uint32_t>>> read(double tries, double retryNs);
  Co<Result> start(Op o);
};

}  // namespace rp2040js::harness
