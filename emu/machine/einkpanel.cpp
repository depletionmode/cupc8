// See einkpanel.h.
#include "einkpanel.h"

#include <cstdlib>
#include <limits>

namespace machine {

epd_cfg_t EinkPanel::config(int w, int h) {
  epd_cfg_t c;
  epd_cfg_default(&c, w, h);
  if (const char *s = std::getenv("CUPC8_EINK_SCALE")) c.time_scale = std::atof(s);
  return c;
}

EinkPanel::EinkPanel(rp2040js::harness::Emu &e, const epd_cfg_t &cfg) : emu(e) {
  epd_init(&m, &cfg);
  if (const char *f = std::getenv("CUPC8_EINK_LOG")) {
    logFile = std::fopen(f, "w");
    m.log_ctx = logFile;
    m.log = [](void *ctx, const char *line) { std::fprintf(static_cast<FILE *>(ctx), "%s\n", line); };
  }
  pic.w = cfg.w;
  pic.h = cfg.h;
  pic.grey.assign(m.glass, m.glass + static_cast<size_t>(cfg.w) * cfg.h);

  auto &mcu = *emu.mcu;
  byteDone = emu.clock.createAlarm([this] { onByteDone(); });
  event = emu.clock.createAlarm([this] {
    epd_advance(&m, now());
    update();
  });
  // the PL022 starts a byte: it is on the wire for 8 SPI clocks
  mcu.spi[1].onTransmit = [this](uint32_t v) {
    txByte = v;
    const double hz = emu.mcu->spi[1].clockFrequency();
    byteDone->schedule(hz > 0 ? 8e9 / hz : 0);
  };
  unlistenRst = mcu.gpio[RST].addListener([this](rp2040js::GPIOPinState, rp2040js::GPIOPinState) {
    epd_rst(&m, now(), driven(RST, true));
    update();
  });
  unlistenPwr = mcu.gpio[PWR].addListener([this](rp2040js::GPIOPinState, rp2040js::GPIOPinState) {
    epd_pwr(&m, now(), driven(PWR, false));
    update();
  });
  update();
}

EinkPanel::~EinkPanel() {
  unlistenRst();
  unlistenPwr();
  emu.mcu->spi[1].onTransmit = [this](uint32_t) { emu.mcu->spi[1].completeTransmit(0); };
  epd_free(&m);
  if (logFile) std::fclose(logFile);
}

// the level on a line the card drives, or what the module sees when it does
// not (RST_N has a pull-up on the module; PWR switches the module off)
bool EinkPanel::driven(int pin, bool undriven) const {
  const rp2040js::GPIOPin &p = emu.mcu->gpio[pin];
  return p.outputEnable() ? p.outputValue() : undriven;
}

void EinkPanel::onByteDone() {
  if (driven(CS, true))
    bytesWithoutCs++;
  else
    epd_byte(&m, now(), driven(DC, true), static_cast<uint8_t>(txByte));
  emu.mcu->spi[1].completeTransmit(0);  // no MISO on the header
  update();
}

void EinkPanel::update() {
  emu.mcu->gpio[BUSY].setInputValue(epd_busy_n(&m, now()));
  const uint64_t next = epd_next_event(&m);
  if (next != std::numeric_limits<uint64_t>::max()) event->schedule(static_cast<double>(next - now()));
  if (m.seq != pic.seq) {
    std::lock_guard<std::mutex> lock(mu);
    pic.seq = m.seq;
    pic.grey.assign(m.glass, m.glass + static_cast<size_t>(pic.w) * pic.h);
  }
}

EinkPanel::Picture EinkPanel::picture() {
  std::lock_guard<std::mutex> lock(mu);
  return pic;
}

}  // namespace machine
