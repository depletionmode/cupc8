// The e-ink card's panel on the native RP2040 (doc/hardware/eink-card.md):
// the UC8179 model of fw/test/epdmodel.c (the one the host tests use) wired
// to the card's panel header, hw/pins.yaml eink_mcu: SPI1 TX/SCK (GPIO 11,
// 10) as bytes from the PL022, CS_n 9, DC 12, RST_n 13, BUSY 14 (driven:
// low while busy), PWR 15.
//
// Each SPI byte reaches the model when its last bit is out (8 SPI clocks
// after the PL022 starts it, at the rate the firmware set), with DC and CS_n
// as they are then; a byte with CS_n high is counted, not delivered. BUSY
// follows the model through alarms on the chip's clock, so nothing here
// needs a per-cycle hook and the PIO fast path stays on. The picture a
// viewer sees is the glass: it changes only when a refresh completes.
#pragma once

#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "emu.h"

extern "C" {
#include "epdmodel.h"
}

namespace machine {

class EinkPanel {
 public:
  static constexpr int CS = 9, DC = 12, RST = 13, BUSY = 14, PWR = 15;

  // CUPC8_EINK_SCALE (default 1) scales every busy time, CUPC8_EINK_LOG=FILE logs the model
  static epd_cfg_t config(int w, int h);

  EinkPanel(rp2040js::harness::Emu &emu, const epd_cfg_t &cfg);
  ~EinkPanel();
  EinkPanel(const EinkPanel &) = delete;
  EinkPanel &operator=(const EinkPanel &) = delete;

  epd_model_t m{};
  uint32_t bytesWithoutCs = 0;

  struct Picture {
    int w = 0, h = 0;
    uint32_t seq = 0;               // completed refreshes
    std::vector<uint8_t> grey;      // w x h, 0 black ... 255 white
  };
  // the glass as of the last completed refresh (safe from any thread)
  Picture picture();

 private:
  rp2040js::harness::Emu &emu;
  std::unique_ptr<rp2040js::IAlarm> byteDone, event;
  uint32_t txByte = 0;
  std::function<void()> unlistenRst, unlistenPwr;
  std::mutex mu;
  Picture pic;
  FILE *logFile = nullptr;

  uint64_t now() const { return static_cast<uint64_t>(emu.ns()); }
  bool driven(int pin, bool undriven) const;
  void onByteDone();
  void update();                    // BUSY, the next alarm, the picture
};

}  // namespace machine
