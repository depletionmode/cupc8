// Replay a captured real CPU display stream against the genuine RP2040 ELF.
// Reuse GPU-009's pin-level SPI and independent core raster, without running
// its main suite or changing the card firmware.
#define main einkcard_suite_main
#include "einkcard.cpp"
#undef main

int main(int argc, char **argv) {
  if (argc != 12) {
    std::fprintf(stderr, "usage: einkqueue ELF TRACE_TSV ERRORS_ADDR QHEAD_ADDR QTAIL_ADDR QCOMMANDS_ADDR STEP_ADDR CHANGE_ADDR SHOWN_ADDR RESPONSE_READY_ADDR loss|fixed\n");
    return 2;
  }
  const bool loss = std::string(argv[11]) == "loss";
  auto address = [](const char *s) { return static_cast<uint32_t>(std::stoul(s, nullptr, 0)); };
  const uint32_t errorsAt = address(argv[3]), headAt = address(argv[4]);
  const uint32_t tailAt = address(argv[5]), commandsAt = address(argv[6]);
  const uint32_t stepAt = address(argv[7]), changeAt = address(argv[8]);
  const uint32_t shownAt = address(argv[9]), readyAt = address(argv[10]);
  epd_cfg_t cfg = EinkPanel::config(800, 480);
  if (!std::getenv("CUPC8_EINK_SCALE")) cfg.time_scale = 0.1;
  Bench b(argv[1], cfg);
  auto word = [&](uint32_t a) { return b.e.mcu->readUint32(a); };
  auto queued = [&] { return word(headAt) - word(tailAt); };
  auto observeUntil = [&](auto condition) {
    const double deadline = b.ns() + 10e9;
    while (!condition() && b.ns() < deadline) b.e.steps(64);
    return condition();
  };
  uint32_t zeroCredits = 0, maxQueued = 0;
  // Preserve each captured CS interval. Bytes use the actual 3 MHz SCK;
  // the remaining interval models the real CPU's polling/instruction gaps.
  auto timedFrame = [&](const std::vector<uint8_t> &f, double duration) {
    auto &g = b.e.mcu->gpio;
    const double begin = b.ns();
    const double perByte = (duration - 2000) / f.size();
    g[NCS].setInputValue(false);
    b.wait(2000);
    for (uint8_t c : f) {
      b.wait(std::max(0.0, perByte - 16 * HALF));
      b.byte(c);
    }
    g[NCS].setInputValue(true);
    b.wait(20000);
    maxQueued = std::max(maxQueued, queued());
    CHECK(b.ns() >= begin + duration, "replayed CS interval");
  };
  std::ifstream in(argv[2]);
  double start, end;
  size_t count, frames = 0;
  std::string putc;
  while (in >> start >> end >> count) {
    std::vector<uint8_t> f(count);
    unsigned c;
    for (auto &v : f) { in >> c; v = static_cast<uint8_t>(c); }
    if (!in || f.empty()) return 2;
    if (b.ns() < start) b.wait(start - b.ns());
    if (!loss && f[0] == 0x10) {
      const double deadline = b.ns() + 10e9;
      for (;;) {
        uint8_t st = b.frame({0xff})[0] & 0x7f;
        if (st >= 1) break;
        zeroCredits++;
        if (b.ns() >= deadline) {
          CHECK(false, "FREE did not recover within existing panel busy deadline");
          return 1;
        }
      }
    }
    timedFrame(f, end - start);
    card_frame(&b.ref.gpu.card, f.data(), nullptr, static_cast<int>(f.size()));
    do { b.ref.gpu.hold = false; b.ref.explicit_req = -1; } while (gpu_run(&b.ref.gpu, 1000));
    if (f.size() == 2 && f[0] == 0x10) putc += static_cast<char>(f[1]);
    frames++;
  }
  const std::string http = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nM1 NETWORK VERIFIED eink750-wifi3\n";
  CHECK(putc.find(http) != std::string::npos, "trace contains complete authentic 98-byte response");
  // GPU-009's settle() actively polls EPD_STATUS/READ at bench speed; those
  // extra frames can themselves saturate the transport. Observe firmware's
  // completed work instead, within the same existing deadline.
  const uint32_t droppedAtTraceEnd = word(errorsAt);
  CHECK(loss ? droppedAtTraceEnd > 0 : droppedAtTraceEnd == 0,
        "captured trace transport errors: %u", droppedAtTraceEnd);
  CHECK(observeUntil([&] { return !queued() && word(stepAt) == 0 && word(changeAt) == word(shownAt) && !b.panel.m.busy_op; }),
        "captured stream settles within existing 10-second gate");
  auto pic = b.panel.picture();
  std::vector<uint8_t> want(pic.grey.size());
  eink_render(&b.ref, want.data(), false);
  size_t diff = 0;
  for (size_t i = 0; i < want.size(); i++) diff += want[i] != pic.grey[i];
  const uint32_t dropped = word(errorsAt);
  if (loss) {
    CHECK(dropped > 0 && diff > 0, "original firmware must reproduce transport loss and glass mismatch");
  } else {
    CHECK(dropped == 0, "corrected transport loses zero frames (%u)", dropped);
    CHECK(diff == 0, "corrected glass equals full command-stream raster (%zu pixels differ)", diff);
    CHECK(zeroCredits > 0, "regression exercises FREE=0 backpressure");
  }
  CHECK(b.panel.m.errors == 0, "controller accepts the surviving/repaired stream");

  // A ready INFO response must survive more polls than the descriptor queue
  // can hold. Observe the queue immediately after each real CS interrupt,
  // and subsequently READ the original response, not a replacement command.
  b.frame({0x08});
  CHECK(observeUntil([&] { return !queued() && b.e.mcu->readUint8(readyAt); }), "INFO is ready before preservation test");
  const uint32_t beforeHead = word(headAt), beforeCommands = word(commandsAt);
  const uint32_t beforeErrors = word(errorsAt);
  for (int i = 0; i < 96; i++) b.frame({0xff});
  if (!loss) {
    CHECK(word(headAt) == beforeHead, "96 FF polls consume no descriptors");
    CHECK(word(commandsAt) == beforeCommands, "FF polls do not become queued commands");
    CHECK(word(errorsAt) == beforeErrors, "FF polls cause no transport errors");
  }
  auto info = b.read(9);
  CHECK(info == std::vector<uint8_t>({1,32,3,224,1,4,3,80,30}), "unread INFO survives FF polling and READ returns original bytes");
  CHECK(observeUntil([&] { return !queued(); }), "READ frame completes through normal transport path");
  if (!loss) CHECK(word(errorsAt) == 0, "all corrected trace/poll/READ traffic has zero errors");
  std::printf("EINK-QUEUE %s: %zu captured frames, max descriptors %u, FREE=0 polls %u, dropped %u, raster diff %zu; %d checks, %d failures\n",
              loss ? "original counterexample" : "repaired", frames, maxQueued, zeroCredits, dropped, diff, checks, failures);
  return failures ? 1 : 0;
}
