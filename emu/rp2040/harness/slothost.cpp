// See slothost.h. Each coroutine below is the generator of the same name in
// test/emu/slothost.mjs; a `co_await wait(x)` is its `yield x`.
#include "slothost.h"

#include <algorithm>
#include <stdexcept>

namespace rp2040js::harness {

SlotHost::SlotHost(Emu &emu, double clkDiv, double csSetupNs, double byteGapNs, double frameGapNs)
    : emu(emu), clkDiv(clkDiv), csSetupNs(csSetupNs), byteGapNs(byteGapNs), frameGapNs(frameGapNs) {
  pin(CS).setInputValue(true);
  pin(SCK).setInputValue(false);
  pin(MOSI).setInputValue(false);
}

double SlotHost::halfNs() const { return (std::max(1.0, clkDiv) * 1000) / 12; }

uint32_t SlotHost::miso() {
  GPIOPin &p = pin(MISO);
  return p.outputEnable() ? (p.outputValue() ? 1 : 0) : 1;
}

void SlotHost::run(Script s) {
  if (inOp) throw std::logic_error("SlotHost::run() during a host operation");
  op = Co<Result>();
  waiting = {};
  script = std::make_shared<Script>(std::move(s));
  generation++;
  done = false;
  wakeAt = emu.ns();
}

void SlotHost::resume() {
  Result r;
  if (waiting) {
    // an operation is waiting: carry on with it
    auto h = std::exchange(waiting, {});
    inOp = true;
    try {
      h.resume();
    } catch (...) {
      inOp = false;
      throw;
    }
    inOp = false;
    if (waiting) return;
    r = op.await_resume();
    op = Co<Result>();
  }
  drive(std::move(r));
}

// the script's control flow: ask it what to do next until it waits
void SlotHost::drive(Result r) {
  const uint64_t gen = generation;
  for (;;) {
    const std::shared_ptr<Script> s = script;
    Op o = (*s)(r);
    if (generation != gen) return;  // the script started another run()
    switch (o.kind) {
      case Op::Done:
        done = true;
        return;
      case Op::Wait:
        wakeAt = emu.ns() + o.ns;
        return;
      default:
        break;
    }
    op = start(std::move(o));
    inOp = true;
    try {
      op.h.resume();  // up to its first wait
    } catch (...) {
      inOp = false;
      throw;
    }
    inOp = false;
    if (waiting) return;
    r = op.await_resume();  // finished without waiting
    op = Co<Result>();
  }
}

Co<SlotHost::Result> SlotHost::start(Op o) {
  Result r;
  switch (o.kind) {
    case Op::Byte:
      r.kind = Result::Number;
      r.number = co_await byte(o.bytes.at(0));
      break;
    case Op::Select:
      co_await select();
      break;
    case Op::Deselect:
      co_await deselect();
      break;
    case Op::Frame:
      r.kind = Result::Bytes;
      r.bytes = co_await frame(std::move(o.bytes));
      break;
    case Op::Read:
      r.kind = Result::Attempts;
      r.attempts = co_await read(o.tries, o.ns);
      break;
    default:
      throw std::logic_error("SlotHost: not an operation");
  }
  co_return r;
}

// one byte on the wire; returns the MISO byte (sampled at each rising edge)
Co<uint32_t> SlotHost::byte(uint32_t out) {
  uint32_t got = 0;
  for (int bit = 7; bit >= 0; bit--) {
    pin(MOSI).setInputValue((out >> bit) & 1);
    co_await wait(halfNs());
    pin(SCK).setInputValue(true);
    got = (got << 1) | miso();
    co_await wait(halfNs());
    pin(SCK).setInputValue(false);
  }
  co_return got;
}

Co<bool> SlotHost::select() {
  pin(CS).setInputValue(false);
  co_await wait(csSetupNs);
  co_return true;
}

Co<bool> SlotHost::deselect() {
  pin(CS).setInputValue(true);
  co_await wait(frameGapNs);
  co_return true;
}

// a whole frame; returns the MISO bytes
Co<std::vector<uint32_t>> SlotHost::frame(std::vector<uint32_t> bytes) {
  co_await select();
  std::vector<uint32_t> miso;
  miso.reserve(bytes.size());
  for (size_t i = 0; i < bytes.size(); i++) {
    if (i) co_await wait(byteGapNs);
    miso.push_back(co_await byte(bytes[i]));
  }
  co_await deselect();
  co_return miso;
}

// READ frame: $FE, RESP_LEN, then that many bytes. Retries while RESP_LEN is
// 0. Returns every try's MISO bytes [status, len, ...data]; the caller makes
// { status, data } or null from the last one, as slothost.mjs's read() does.
Co<std::vector<std::vector<uint32_t>>> SlotHost::read(double tries, double retryNs) {
  std::vector<std::vector<uint32_t>> attempts;
  for (double t = 0; t < tries; t++) {
    co_await select();
    const uint32_t status = co_await byte(0xfe);
    co_await wait(byteGapNs);
    const uint32_t len = co_await byte(0);
    std::vector<uint32_t> got{status, len};
    if (len != 0 && len != 0xff) {
      for (uint32_t i = 0; i < len; i++) {
        co_await wait(byteGapNs);
        got.push_back(co_await byte(0));
      }
    }
    co_await deselect();
    attempts.push_back(std::move(got));
    if (len == 0xff) co_return attempts;  // empty slot
    if (len) co_return attempts;
    co_await wait(retryNs);
  }
  co_return attempts;
}

}  // namespace rp2040js::harness
