// GPU-009: the real e-ink card firmware (build/rp2040/eink.elf, or
// eink750.elf) on the native RP2040 with the UC8179 panel model on its
// header (einkpanel.h), driven at its slot pins with the chipset's SPI
// timing (doc/hardware/slot.md: SCK 3 MHz, 2 us CS setup, 1 us between
// bytes, 20 us between frames). After each refresh the glass must equal the
// e-ink core's own raster of the same command stream (fw/eink/core, linked
// in here and fed the same frames) and a golden image (test/eink/golden).
//
//   einkcard --root DIR [--panel 583|750] [--record]
//
// Checks: IDENT within 5 ms at power-on and in the middle of a refresh;
// FREE = 127 idle; INFO; the console text on the glass after the power-on
// refresh and a partial one; 300 PUTCs at full speed respecting FREE; mode 2
// drawing, then REFRESH 3 with a FENCE that raises IRQ_n only once the grey
// picture is on the glass; commands sent at seeded random moments during a
// refresh all reach the glass; the panel model saw nothing the chip would
// ignore. Busy times are the vendors' x 0.1 (CUPC8_EINK_SCALE overrides).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <random>
#include <string>
#include <vector>

#include "einkpanel.h"
#include "emu.h"

extern "C" {
#include "eink.h"
}

using rp2040js::harness::Emu;
using machine::EinkPanel;

static int checks, failures;
#define CHECK(cond, ...)                                              \
  do {                                                                \
    checks++;                                                         \
    if (!(cond)) {                                                    \
      failures++;                                                     \
      std::fprintf(stderr, "%s:%d: FAIL %s: ", __FILE__, __LINE__, #cond); \
      std::fprintf(stderr, __VA_ARGS__);                              \
      std::fprintf(stderr, "\n");                                     \
    }                                                                 \
  } while (0)

namespace {

constexpr int SCK = 2, MOSI = 3, MISO = 4, NCS = 5, NIRQ = 6;
constexpr double HALF = 1000.0 / 12 * 2;  // clk_div 2: SCK = 3 MHz

struct Bench {
  Emu e;
  EinkPanel panel;
  // the reference: the same core on the host, fed the same frames
  eink_t ref{};
  std::vector<std::vector<uint8_t>> sent;

  Bench(const std::string &elf, const epd_cfg_t &cfg) : e(elf, 125), panel(e, cfg) {
    auto &g = e.mcu->gpio;
    g[NCS].setInputValue(true);
    g[SCK].setInputValue(false);
    g[MOSI].setInputValue(false);
    static const epd_bus_t none = {nullptr, [](void *, uint8_t) {}, [](void *, const uint8_t *, int) {},
                                   [](void *, int, bool) {}, [](void *) { return false; }};
    eink_init(&ref, cfg.w == 800 ? &eink_panel_750 : &eink_panel_583, &none);
  }
  double ns() const { return e.ns(); }
  void wait(double ns) { e.runTo(e.ns() + ns); }
  uint8_t byte(uint8_t out) {
    uint8_t got = 0;
    auto &g = e.mcu->gpio;
    for (int bit = 7; bit >= 0; bit--) {
      g[MOSI].setInputValue((out >> bit) & 1);
      wait(HALF);
      g[SCK].setInputValue(true);
      rp2040js::GPIOPin &p = g[MISO];
      got = static_cast<uint8_t>(got << 1 | (p.outputEnable() ? p.outputValue() : 1));
      wait(HALF);
      g[SCK].setInputValue(false);
    }
    return got;
  }
  std::vector<uint8_t> frame(const std::vector<uint8_t> &mosi) {
    std::vector<uint8_t> miso;
    e.mcu->gpio[NCS].setInputValue(false);
    wait(2000);
    for (size_t i = 0; i < mosi.size(); i++) {
      if (i) wait(1000);
      miso.push_back(byte(mosi[i]));
    }
    e.mcu->gpio[NCS].setInputValue(true);
    wait(20000);
    return miso;
  }
  // a command, if FREE allows it (retrying while it does not); also to the reference
  void send(const std::vector<uint8_t> &f) {
    for (int tries = 0;; tries++) {
      // the status byte comes back during the opcode: a NOP frame asks
      const uint8_t st = frame({0x00})[0];
      if (static_cast<size_t>(st) * 64 >= f.size()) break;
      if (tries > 100000) {
        CHECK(false, "FREE never allowed a %zu-byte frame", f.size());
        return;
      }
    }
    frame(f);
    card_frame(&ref.gpu.card, f.data(), nullptr, static_cast<int>(f.size()));
    do {
      ref.gpu.hold = false;  // the reference has no panel: a REFRESH is done at once
      ref.explicit_req = -1;
    } while (gpu_run(&ref.gpu, 1000));
  }
  // READ until RESP_LEN != 0; returns the response and the ns it took
  std::vector<uint8_t> read(int n, double *took = nullptr, double limit = 50e6) {
    const double t0 = ns();
    std::vector<uint8_t> f(2 + n, 0);
    f[0] = 0xFE;
    while (ns() - t0 < limit) {
      auto r = frame(f);
      if (r[1]) {
        if (took) *took = ns() - t0;
        return std::vector<uint8_t>(r.begin() + 2, r.begin() + 2 + std::min<int>(r[1], n));
      }
    }
    if (took) *took = ns() - t0;
    return {};
  }
  bool irq() {
    rp2040js::GPIOPin &p = e.mcu->gpio[NIRQ];
    return p.outputEnable() && !p.outputValue();
  }
  // run until the card says nothing is pending and the panel is idle
  bool settle(double limit = 10e9) {
    const double end = ns() + limit;
    while (ns() < end) {
      wait(5e6);
      frame({0x0B});
      auto st = read(3);
      if (st.size() == 3 && !st[0] && !st[1] && !panel.m.busy_op) return true;
    }
    return false;
  }
};

bool readPnm(const std::string &path, std::vector<uint8_t> &g, int w, int h) {
  std::ifstream in(path, std::ios::binary);
  std::string kind;
  int fw, fh, max = 1;
  if (!(in >> kind >> fw >> fh) || fw != w || fh != h) return false;
  if (kind == "P5") in >> max;
  in.get();
  g.assign(static_cast<size_t>(w) * h, 0);
  if (kind == "P5") return static_cast<bool>(in.read(reinterpret_cast<char *>(g.data()), g.size()));
  if (kind != "P4") return false;
  for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x += 8) {
      const int b = in.get();
      if (b == EOF) return false;
      for (int i = 0; i < 8; i++) g[y * w + x + i] = (b & (0x80 >> i)) ? 0 : 255;
    }
  return true;
}

void writePnm(const std::string &path, const std::vector<uint8_t> &g, int w, int h, bool grey) {
  std::ofstream out(path, std::ios::binary);
  if (grey) {
    out << "P5\n" << w << " " << h << "\n255\n";
    out.write(reinterpret_cast<const char *>(g.data()), static_cast<std::streamsize>(g.size()));
    return;
  }
  out << "P4\n" << w << " " << h << "\n";
  for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x += 8) {
      uint8_t b = 0;
      for (int i = 0; i < 8; i++)
        if (g[y * w + x + i] < 128) b |= static_cast<uint8_t>(0x80 >> i);
      out.put(static_cast<char>(b));
    }
}

std::string root = ".";
bool record = false;

void checkGlass(Bench &b, const std::string &name, bool grey) {
  const auto pic = b.panel.picture();
  std::vector<uint8_t> want(pic.grey.size());
  eink_render(&b.ref, want.data(), grey);
  long diff = 0;
  for (size_t i = 0; i < want.size(); i++) diff += want[i] != pic.grey[i];
  CHECK(diff == 0, "%s: the glass differs from the core's raster in %ld pixels", name.c_str(), diff);
  if (diff && std::getenv("EINK_DUMP")) {
    writePnm(std::string(std::getenv("EINK_DUMP")) + "/" + name + "_glass.pgm", pic.grey, pic.w, pic.h, true);
    writePnm(std::string(std::getenv("EINK_DUMP")) + "/" + name + "_core.pgm", want, pic.w, pic.h, true);
  }
  const std::string path = root + "/test/eink/golden/" + name + (grey ? ".pgm" : ".pbm");
  if (record) writePnm(path, pic.grey, pic.w, pic.h, grey);
  std::vector<uint8_t> gold;
  if (!readPnm(path, gold, pic.w, pic.h)) {
    CHECK(false, "%s: no golden image %s (--record once checked)", name.c_str(), path.c_str());
    return;
  }
  diff = 0;
  for (size_t i = 0; i < gold.size(); i++) diff += gold[i] != pic.grey[i];
  CHECK(diff == 0, "%s: the glass differs from %s in %ld pixels", name.c_str(), path.c_str(), diff);
}

std::vector<uint8_t> putsFrame(const std::string &s) {
  std::vector<uint8_t> f = {0x11, static_cast<uint8_t>(s.size())};
  f.insert(f.end(), s.begin(), s.end());
  return f;
}

}  // namespace

int main(int argc, char **argv) {
  std::string panelArg = "583";
  for (int i = 1; i < argc; i++) {
    if (!std::strcmp(argv[i], "--root") && i + 1 < argc) root = argv[++i];
    else if (!std::strcmp(argv[i], "--panel") && i + 1 < argc) panelArg = argv[++i];
    else if (!std::strcmp(argv[i], "--record")) record = true;
  }
  const bool p750 = panelArg == "750";
  epd_cfg_t cfg = EinkPanel::config(p750 ? 800 : 648, 480);
  if (!std::getenv("CUPC8_EINK_SCALE")) cfg.time_scale = 0.1;
  Bench b(root + "/build/rp2040/" + (p750 ? "eink750.elf" : "eink.elf"), cfg);
  const std::string sfx = p750 ? "_750" : "";

  // the card answers (a status byte, not the pull-up's $FF) within 200 ms
  // of power-on, then IDENT within the boot ROM's 5 ms
  bool up = false;
  for (int i = 0; i < 200 && !up; i++) {
    up = b.frame({0x00})[0] != 0xFF;
    if (!up) b.wait(1e6);
  }
  CHECK(up, "the card answers within 200 ms of power-on");
  b.frame({0xF0});
  double took = 0;
  auto id = b.read(4, &took);
  CHECK(id.size() == 4 && id[0] == 1 && id[3] == 0xC8, "IDENT: type $01");
  CHECK(took < 5e6, "IDENT answered in %.2f ms", took / 1e6);
  CHECK(b.frame({0x00})[0] == 127, "FREE = 127 idle");
  b.frame({0x08});
  auto info = b.read(9);
  CHECK(info.size() == 9 && info[0] == 1 && (info[1] | info[2] << 8) == (p750 ? 800 : 648) &&
            (info[3] | info[4] << 8) == 480 && info[5] == 4 && info[6] == 3 && info[7] == 80 && info[8] == 30,
        "INFO");

  // the console: what the boot ROM and the kernel send
  b.send({0x01, 0x00});
  b.send({0x14, 0x00});  // no cursor in the pictures: static, but it moves
  b.send(putsFrame("CUPC/8 e-ink card on the native emulator\r\n"));
  b.send({0x13, 0x70});
  b.send(putsFrame(" inverse "));
  b.send({0x13, 0x07});
  b.send(putsFrame("\r\n>> "));
  // IDENT during the power-on (clean) refresh
  const double t0 = b.ns();
  while (b.panel.m.busy_op != 0x12 && b.ns() - t0 < 5e9) b.wait(1e6);
  CHECK(b.panel.m.busy_op == 0x12, "the power-on refresh runs");
  b.frame({0xF0});
  id = b.read(4, &took);
  CHECK(id.size() == 4 && took < 5e6, "IDENT during a refresh in %.2f ms", took / 1e6);
  CHECK(b.settle(), "settles");
  CHECK(b.panel.m.refreshes[EPD_WF_CLEAN] == 1, "one clean refresh at power-on");
  checkGlass(b, "card_boot" + sfx, false);

  // 300 PUTCs at full speed, respecting FREE, then a partial refresh
  for (int i = 0; i < 300; i++) b.send({0x10, static_cast<uint8_t>(i % 60 == 59 ? '\n' : 'a' + i % 26)});
  CHECK(b.settle(), "settles");
  CHECK(b.panel.m.refreshes[EPD_WF_PARTIAL] >= 1, "partial refreshes");
  checkGlass(b, "card_text" + sfx, false);

  // mode 2, then REFRESH 3 and a FENCE that fires once the panel has it
  b.send({0x0A, 0, 15, 30});  // AUTO 0: nothing refreshes half-way through a drawing
  b.send({0x01, 2});
  for (int g = 0; g < 4; g++)
    b.send({0x41, static_cast<uint8_t>(g * 150), static_cast<uint8_t>((g * 150) >> 8), 0, 0, 150, 0, 100, 0,
            static_cast<uint8_t>(g)});
  b.send({0x43, 0, 0, 100, 0, 0x7F, 0x02, 0xDF, 0x01, 0});
  b.send({0x46, 20, 0, 0x2C, 0x01, 0, 0xFF, 6, 'm', 'o', 'd', 'e', ' ', '2'});
  b.send({0xF2, 1});  // IRQ_EN
  const uint32_t greyBefore = b.panel.m.refreshes[EPD_WF_GREY];
  b.send({0x09, 3});
  b.send({0x05, 0x77});
  bool early = false;
  const double t1 = b.ns();
  while (!b.irq() && b.ns() - t1 < 10e9) {
    b.wait(1e6);
    if (b.irq() && b.panel.m.refreshes[EPD_WF_GREY] == greyBefore) early = true;
  }
  CHECK(b.irq() && !early, "FENCE after REFRESH 3 fires once the grey picture is on the glass");
  CHECK(b.panel.m.refreshes[EPD_WF_GREY] == greyBefore + 1, "one greyscale refresh");
  b.frame({0x06});
  auto tag = b.read(1);
  CHECK(tag.size() == 1 && tag[0] == 0x77 && !b.irq(), "FENCE_READ");
  checkGlass(b, "card_grey" + sfx, true);

  // commands at seeded random moments during refreshes all reach the glass
  b.send({0x0A, 1, 15, 30});
  b.send({0x01, 0});
  std::mt19937 rng(8);
  for (int i = 0; i < 120; i++) {
    b.wait(std::uniform_real_distribution<double>(0, 20e6)(rng));
    b.send({0x17, static_cast<uint8_t>(rng() % 80), static_cast<uint8_t>(rng() % 30),
            static_cast<uint8_t>('A' + rng() % 26), static_cast<uint8_t>(rng() % 2 ? 0x07 : 0x70)});
  }
  CHECK(b.settle(), "settles");
  checkGlass(b, "card_random" + sfx, false);

  CHECK(b.panel.m.errors == 0, "the UC8179 model saw nothing the chip would ignore (%u: %s)", b.panel.m.errors,
        b.panel.m.error);
  CHECK(b.panel.bytesWithoutCs == 0, "no SPI byte without CS");
  std::printf("GPU-009 e-ink card (%s) on the native emulator: refreshes clean %u fast %u grey %u partial %u, "
              "%.2f s emulated: %d checks, %d failures\n",
              p750 ? "7.5in" : "5.83in", b.panel.m.refreshes[0], b.panel.m.refreshes[1], b.panel.m.refreshes[2],
              b.panel.m.refreshes[3], b.ns() / 1e9, checks, failures);
  return failures ? 1 : 0;
}
