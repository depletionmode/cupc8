// Capture of the graphics card's DVI output, natively: what
// test/emu/tmds.mjs's TmdsCapture records by wrapping the TX FIFOs' pull()
// of PIO0 SM0-2 (blue, green, red): two 10-bit symbols per word, first in
// bits 9:0, and the emulated ns of each lane-0 word. Uses FIFO::onPull.
#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "emu.h"

namespace rp2040js::harness {

class TmdsCapture {
 public:
  std::array<std::vector<uint16_t>, 3> lanes;
  std::vector<double> times;  // emulated ns of each lane-0 word
  bool on = false;

  explicit TmdsCapture(Emu &emu) : emu(emu) {
    for (uint32_t lane = 0; lane < 3; lane++) {
      emu.mcu->pio[0].machines[lane].txFIFO.onPull = [this, lane](uint32_t w) {
        if (!on) return;
        lanes[lane].push_back(w & 0x3ff);
        lanes[lane].push_back((w >> 10) & 0x3ff);
        if (lane == 0) times.push_back(this->emu.ns());
      };
    }
  }
  ~TmdsCapture() {
    for (uint32_t lane = 0; lane < 3; lane++) emu.mcu->pio[0].machines[lane].txFIFO.onPull = nullptr;
  }
  TmdsCapture(const TmdsCapture &) = delete;
  TmdsCapture &operator=(const TmdsCapture &) = delete;

  void start() {
    for (auto &l : lanes) l.clear();
    times.clear();
    on = true;
  }
  void stop() { on = false; }

 private:
  Emu &emu;
};

}  // namespace rp2040js::harness
