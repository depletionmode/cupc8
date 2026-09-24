// EMU-008: the SD card SPI-mode model (harness/sdcard.h) on its own, and in
// its socket on an RP2040's SPI1 driven through the chip's registers (no
// firmware): the byte timing at the programmed SCK rate, nCS, card detect,
// and a DMA block read. Each check cites the SD Physical Layer Simplified
// Specification v9.00 section it holds the model to.
//
//   build/emu-native/test_sdcard
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "clock/simulation-clock.h"
#include "rp2040.h"
#include "sdcard.h"

using namespace rp2040js;
using namespace rp2040js::harness;

static int checks = 0, bad = 0;
static void expect(bool ok, const std::string &what) {
  checks++;
  if (!ok) {
    bad++;
    std::printf("FAIL %s\n", what.c_str());
  }
}
static std::string hex(uint32_t v) {
  char b[16];
  std::snprintf(b, sizeof b, "$%02X", v);
  return b;
}

static std::vector<uint8_t> pattern(size_t n) {
  std::vector<uint8_t> v(n);
  for (size_t i = 0; i < n; i++) v[i] = static_cast<uint8_t>(i * 7 + i / 512);
  return v;
}

// a host on the card's pins, a byte at a time, `byteNs` per byte
struct Host {
  SdCard &c;
  double t = 0, byteNs = 20000;  // 400 kHz
  bool crcGood = true;
  uint8_t x(uint8_t b) {
    const uint8_t r = c.exchange(b, t);
    t += byteNs;
    return r;
  }
  void clocks(unsigned bytes) {
    for (unsigned i = 0; i < bytes; i++) c.clocksDeselected(8);
    t += bytes * byteNs;
  }
  void wait(double ns) { t += ns; }
  static std::vector<uint8_t> frame(uint8_t idx, uint32_t arg) {
    std::vector<uint8_t> f = {static_cast<uint8_t>(0x40 | idx), static_cast<uint8_t>(arg >> 24),
                              static_cast<uint8_t>(arg >> 16), static_cast<uint8_t>(arg >> 8), static_cast<uint8_t>(arg)};
    f.push_back(static_cast<uint8_t>(sdCrc7(f.data(), 5) << 1 | 1));
    return f;
  }
  // a command and its response (R1 then n - 1 more bytes); empty if no R1 in 8 bytes (NCR, 7.5.4)
  std::vector<uint8_t> cmd(uint8_t idx, uint32_t arg, size_t n = 1) {
    auto f = frame(idx, arg);
    if (!crcGood) f[5] ^= 0x10;
    for (uint8_t b : f) x(b);
    std::vector<uint8_t> r;
    for (int i = 0; i < 8; i++) {
      const uint8_t b = x(0xff);
      if (!(b & 0x80)) {
        r.push_back(b);
        break;
      }
    }
    if (r.empty()) return r;
    while (r.size() < n) r.push_back(x(0xff));
    return r;
  }
  std::vector<uint8_t> acmd(uint8_t idx, uint32_t arg, size_t n = 1) {
    cmd(55, 0);
    return cmd(idx, arg, n);
  }
  // power-up clocks, CMD0, CMD8, ACMD41 until ready; the number of ACMD41s
  int init(uint32_t hcs = 1u << 30) {
    clocks(10);
    cmd(0, 0);
    cmd(8, 0x1aa, 5);
    for (int i = 1; i < 1000; i++) {
      auto r = acmd(41, hcs);
      if (!r.empty() && r[0] == 0) return i;
      wait(1e6);
    }
    return -1;
  }
  // a data block after a read command: {token, data..., crc16 ok}
  bool block(std::vector<uint8_t> &out, size_t n, double *waited = nullptr, uint8_t *token = nullptr) {
    const double t0 = t;
    uint8_t b = 0xff;
    for (int i = 0; i < 100000 && b == 0xff; i++) b = x(0xff);
    if (waited) *waited = t - t0;
    if (token) *token = b;
    if (b != 0xfe) return false;
    out.resize(n);
    for (size_t i = 0; i < n; i++) out[i] = x(0xff);
    const uint16_t crc = static_cast<uint16_t>(x(0xff) << 8 | x(0xff));
    return crc == sdCrc16(out.data(), n);
  }
  // a data block for a write, with its token; returns the data response token
  uint8_t send(uint8_t token, const std::vector<uint8_t> &d, bool badCrc = false) {
    x(0xff);  // NWR
    x(token);
    for (uint8_t b : d) x(b);
    uint16_t crc = sdCrc16(d.data(), d.size());
    if (badCrc) crc ^= 1;
    x(static_cast<uint8_t>(crc >> 8));
    x(static_cast<uint8_t>(crc));
    return x(0xff) & 0x1f;
  }
  // CMD12 in a multiple-block read: the stuff byte, R1, then busy (7.5.2.2); R1
  uint8_t stop() {
    for (uint8_t v : frame(12, 0)) x(v);
    x(0xff);
    uint8_t r = 0xff;
    for (int i = 0; i < 8 && r == 0xff; i++) r = x(0xff);
    busy();
    return r;
  }
  // busy bytes ($00) until DO is released
  double busy() {
    const double t0 = t;
    for (int i = 0; i < 10000000 && x(0xff) != 0xff;) i++;
    return t - t0;
  }
};

// capacity from the CSD (5.3.2, 5.3.3)
static uint64_t csdCapacity(const std::vector<uint8_t> &csd) {
  auto bits = [&](int hi, int lo) {
    uint64_t v = 0;
    for (int b = hi; b >= lo; b--) v = v << 1 | ((csd[15 - b / 8] >> (b % 8)) & 1);
    return v;
  };
  if (bits(127, 126) == 1) return (bits(69, 48) + 1) * 512 * 1024;
  return (bits(73, 62) + 1) << (bits(49, 47) + 2) << bits(83, 80);
}

static void crcs() {
  const uint8_t cmd0[] = {0x40, 0, 0, 0, 0}, cmd8[] = {0x48, 0, 0, 1, 0xaa};
  expect((sdCrc7(cmd0, 5) << 1 | 1) == 0x95, "CRC7: CMD0 ends $95 (4.5, 7.2.2)");
  expect((sdCrc7(cmd8, 5) << 1 | 1) == 0x87, "CRC7: CMD8($1AA) ends $87 (4.5)");
  std::vector<uint8_t> ff(512, 0xff);
  expect(sdCrc16(ff.data(), 512) == 0x7fa1, "CRC16 of 512 x $FF is $7FA1 (4.5)");
}

static void powerUp() {
  SdCard c(pattern(1 << 20), {});
  Host h{c};
  expect(h.cmd(0, 0).empty(), "power-up: CMD0 before 74 clocks is not answered (6.4.1)");
  expect(!c.violations.empty(), "power-up: the missing clocks are recorded");
  h.clocks(10);
  h.crcGood = false;
  expect(h.cmd(0, 0).empty(), "SD mode: CMD0 with a bad CRC is not answered (7.2.2)");
  h.crcGood = true;
  expect(h.cmd(17, 0).empty(), "SD mode: a command other than CMD0 is not answered (7.2.1)");
  auto r = h.cmd(0, 0);
  expect(r.size() == 1 && r[0] == 0x01, "CMD0 enters SPI mode: R1 idle $01 (7.2.1)");
  h.crcGood = false;
  r = h.cmd(0, 0);
  expect(r.size() == 1 && r[0] == 0x01, "SPI mode, CRC off: CMD0's CRC is no longer checked (7.2.2)");
  h.crcGood = true;
  r = h.cmd(13, 0, 2);
  expect(r.size() == 2 && r[0] == 0x01, "idle: commands are available in SPI mode (7.2.1), R1 with the idle bit");
  r = h.cmd(8, 0x1aa, 5);
  expect(r == std::vector<uint8_t>({0x01, 0, 0, 1, 0xaa}), "CMD8: R7 echoes voltage 1 and pattern $AA (7.3.2.6)");
  h.crcGood = false;
  r = h.cmd(8, 0x1aa, 1);
  expect(r.size() == 1 && r[0] == 0x09, "CMD8's CRC is checked with CRC off: R1 $09 (7.2.2)");
  r = h.cmd(58, 0, 1);
  expect(r.size() == 1 && r[0] == 0x01, "CRC off: CMD58's bad CRC is ignored (7.2.2)");
  h.crcGood = true;
  r = h.cmd(58, 0, 5);
  expect(r.size() == 5 && r[1] == 0x00 && r[2] == 0xff && r[3] == 0x80, "CMD58 while idle: OCR busy bit 31 clear, 2.7-3.6 V (5.1)");

  SdCard fast(pattern(1 << 20), {});
  Host g{fast};
  const int n = g.init();
  expect(n > 1 && g.t >= fast.opt.initNs, "ACMD41 idle until initNs has passed, then $00 (4.2.3), " + std::to_string(n) + " tries");
  expect(fast.violations.empty(), "a clean initialisation records no violation");
  r = g.cmd(58, 0, 5);
  expect(r == std::vector<uint8_t>({0x00, 0xc0, 0xff, 0x80, 0x00}), "SDHC: OCR $C0FF8000 (busy set, CCS set, 5.1)");
  SdCard mid(pattern(1 << 20), {});
  Host q{mid};
  q.clocks(10);
  q.cmd(0, 0);
  q.cmd(8, 0x1aa, 5);
  q.acmd(41, 1u << 30);
  q.cmd(58, 0, 5);
  expect(!mid.violations.empty() && mid.violations[0].find("CMD58 between ACMD41s") != std::string::npos,
         "CMD58 while repeating ACMD41 is recorded (7.2.1)");
  q.wait(10e6);
  expect(q.acmd(41, 0) == std::vector<uint8_t>{0}, "HCS is taken from the first ACMD41 only (7.2.1)");

  SdCard noHcs(pattern(1 << 20), {});
  Host k{noHcs};
  expect(k.init(0) < 0, "SDHC: ACMD41 without HCS stays idle for ever (4.2.3.1)");
  SdCard no8(pattern(1 << 20), {});
  Host m{no8};
  m.clocks(10);
  m.cmd(0, 0);
  bool ready = false;
  for (int i = 0; i < 200 && !ready; i++, m.wait(1e6)) ready = m.acmd(41, 1u << 30) == std::vector<uint8_t>{0};
  expect(!ready, "SDHC: no CMD8 before ACMD41 means the card never leaves idle (4.2.3.1)");

  SdCard::Options so;
  so.highCapacity = false;
  SdCard sdsc(pattern(1 << 20), so);
  Host s{sdsc};
  expect(s.init(0) > 0, "SDSC: ACMD41 without HCS initialises");
  r = s.cmd(58, 0, 5);
  expect(r == std::vector<uint8_t>({0x00, 0x80, 0xff, 0x80, 0x00}), "SDSC: OCR $80FF8000 (CCS clear)");
  r = s.cmd(1, 0);
  expect(r.size() == 1 && r[0] == 0x04, "CMD1 is illegal here (the firmware must use ACMD41)");
  r = s.cmd(0, 0);
  expect(r.size() == 1 && r[0] == 0x01, "CMD0 in SPI mode: back to idle");
}

static void registers() {
  for (bool hc : {true, false})
    for (size_t size : {size_t(1) << 20, size_t(8) << 20, size_t(64) << 20}) {
      SdCard::Options o;
      o.highCapacity = hc;
      SdCard c(std::vector<uint8_t>(size), o);
      Host h{c};
      h.init(hc ? 1u << 30 : 0);
      h.cmd(9, 0);
      std::vector<uint8_t> csd;
      const bool crc = h.block(csd, 16);
      const std::string what = std::string(hc ? "SDHC" : "SDSC") + " " + std::to_string(size >> 20) + " MB";
      expect(crc && csd == c.csd(), what + ": CMD9 sends the CSD as a 16-byte data block with CRC16 (7.2.6)");
      expect((sdCrc7(csd.data(), 15) << 1 | 1) == csd[15], what + ": the CSD's CRC7 is right (5.3)");
      expect(csdCapacity(csd) == size, what + ": the CSD's capacity is the image's (" + std::to_string(csdCapacity(csd)) + ")");
      expect((csd[0] >> 6) == (hc ? 1 : 0), what + ": CSD_STRUCTURE " + std::string(hc ? "2.0" : "1.0"));
    }
  SdCard::Options wp;
  wp.writeProtect = true;
  SdCard c(pattern(1 << 20), wp);
  expect(c.csd()[14] & 0x10, "write-protect: CSD TMP_WRITE_PROTECT (bit 12) set (5.3)");
  Host h{c};
  h.init();
  h.cmd(10, 0);
  std::vector<uint8_t> cid;
  expect(h.block(cid, 16) && cid == c.cid() && (sdCrc7(cid.data(), 15) << 1 | 1) == cid[15], "CMD10: the CID with a right CRC7 (5.2)");
  h.acmd(51, 0);
  std::vector<uint8_t> scr;
  expect(h.block(scr, 8) && scr[0] == 0x02 && (scr[1] >> 4) == 3, "ACMD51: SCR, SD_SPEC 2, SDHC security (5.6)");
  auto r = h.acmd(13, 0, 2);
  std::vector<uint8_t> sds;
  expect(r.size() == 2 && h.block(sds, 64), "ACMD13: R2 then the 64-byte SD status (4.10.2)");
}

static void readWrite() {
  auto img = pattern(1 << 20);
  SdCard c(img, {});
  std::vector<std::pair<uint64_t, size_t>> writes;
  c.onWrite = [&](uint64_t o, size_t n) { writes.emplace_back(o, n); };
  Host h{c};
  h.init();
  h.byteNs = 320;  // 25 MHz
  auto r = h.cmd(17, 3);
  std::vector<uint8_t> b;
  double waited = 0;
  expect(r == std::vector<uint8_t>{0} && h.block(b, 512, &waited), "CMD17: R1 $00, token $FE, 512 bytes, CRC16 (7.2.3, 7.3.3.2)");
  expect(std::equal(b.begin(), b.end(), img.begin() + 3 * 512), "CMD17 on SDHC: the argument is a block number (7.2.3)");
  expect(waited >= c.opt.readNs - 2 * h.byteNs, "CMD17: $FF until the access time has passed (4.6.2.1)");
  r = h.cmd(17, 2048);
  expect(r == std::vector<uint8_t>{0x40}, "CMD17 beyond the end: R1 parameter error $40 (7.3.2.1)");

  std::vector<uint8_t> d(512);
  for (size_t i = 0; i < 512; i++) d[i] = static_cast<uint8_t>(0xa5 ^ i);
  r = h.cmd(24, 5);
  expect(r == std::vector<uint8_t>{0}, "CMD24: R1 $00");
  const uint8_t resp = h.send(0xfe, d);
  expect(resp == 0x05, "CMD24: data response 'accepted' $05 (7.3.3.1), got " + hex(resp));
  expect(std::equal(d.begin(), d.end(), c.data.begin() + 5 * 512) == false, "a written block is not in the image while it is programming");
  const double busy = h.busy();
  expect(busy >= c.opt.writeNs - 2 * h.byteNs && busy < c.opt.writeNs + 2 * h.byteNs, "CMD24: DO held low for the programming time (" + std::to_string(busy / 1e3) + " us, 7.2.4)");
  c.settle(h.t);
  expect(std::equal(d.begin(), d.end(), c.data.begin() + 5 * 512), "CMD24: the block is in the image once programmed");
  expect(writes.size() == 1 && writes[0] == std::make_pair(uint64_t(5 * 512), size_t(512)), "onWrite reports the block");

  // busy survives deselection; a command while busy is ignored
  h.cmd(24, 6);
  h.send(0xfe, d);
  c.deselect();
  h.wait(100e3);
  expect(h.x(0xff) == 0x00, "busy again on DO after CS goes low again (7.2.4)");
  auto early = Host::frame(13, 0);
  for (uint8_t v : early) h.x(v);
  expect(!c.violations.empty() && c.violations.back().find("busy") != std::string::npos, "a command while busy is recorded");
  h.busy();

  // CMD59: CRC on
  r = h.cmd(59, 1);
  expect(r == std::vector<uint8_t>{0}, "CMD59: CRC on");
  h.cmd(24, 7);
  expect(h.send(0xfe, d, true) == 0x0b, "CRC on: a data block with a bad CRC16 gets $0B (7.3.3.1)");
  h.busy();
  h.crcGood = false;
  r = h.cmd(13, 0, 2);
  expect(r.size() >= 1 && r[0] == 0x08, "CRC on: a command with a bad CRC7 gets R1 $08");
  h.crcGood = true;
  h.cmd(59, 0);

  // multiple-block read, CMD12
  r = h.cmd(18, 10);
  bool ok = true;
  for (int k = 0; k < 3; k++) {
    ok &= h.block(b, 512);
    ok &= std::equal(b.begin(), b.end(), c.data.begin() + (10 + k) * 512);
  }
  const uint8_t r1 = h.stop();
  expect(ok && r1 == 0, "CMD18: consecutive blocks with CRC16, CMD12 stops: stuff byte, R1 $00, busy (7.5.2.2)");
  r = h.cmd(18, 2047);
  uint8_t token = 0;
  h.block(b, 512);
  expect(!h.block(b, 512, nullptr, &token) && token == 0x08, "CMD18 off the end: data error token 'out of range' $08 (7.3.3.3), got " + hex(token));
  h.stop();
  r = h.cmd(13, 0, 2);
  expect(r.size() == 2 && (r[1] & 0x80), "CMD13 after it: R2 out of range (7.3.2.3)");

  // multiple-block write
  h.acmd(23, 2);
  r = h.cmd(25, 20);
  std::vector<uint8_t> d2(512, 0x3c);
  ok = r == std::vector<uint8_t>{0};
  ok &= h.send(0xfc, d) == 0x05;
  ok &= h.busy() >= c.opt.writeNs - 2 * h.byteNs;
  ok &= h.send(0xfc, d2) == 0x05;
  h.busy();
  h.x(0xfd);  // stop tran token
  h.x(0xff);
  h.busy();
  c.settle(h.t);
  ok &= std::equal(d.begin(), d.end(), c.data.begin() + 20 * 512) && std::equal(d2.begin(), d2.end(), c.data.begin() + 21 * 512);
  expect(ok, "CMD25: $FC blocks, each accepted and programmed, $FD stops (7.3.3.2)");

  // deselect in the middle of a data block drops it
  const auto before = std::vector<uint8_t>(c.data.begin() + 30 * 512, c.data.begin() + 31 * 512);
  h.cmd(24, 30);
  h.x(0xff);
  h.x(0xfe);
  for (int i = 0; i < 100; i++) h.x(0);
  c.deselect();
  h.wait(10e6);
  c.settle(h.t);
  expect(std::equal(before.begin(), before.end(), c.data.begin() + 30 * 512), "CS high in the middle of a data block: nothing written");
  r = h.cmd(13, 0, 2);
  expect(r == std::vector<uint8_t>({0, 0}), "and the card takes commands again");

  // erase
  r = h.cmd(38, 0);
  expect(r == std::vector<uint8_t>{0x10}, "CMD38 without CMD32/33: erase sequence error $10");
  h.cmd(32, 40);
  h.cmd(33, 41);
  r = h.cmd(38, 0);
  h.busy();
  expect(r == std::vector<uint8_t>{0} && std::all_of(c.data.begin() + 40 * 512, c.data.begin() + 42 * 512, [](uint8_t v) { return v == 0; }),
         "CMD32/33/38 erase blocks 40-41 to $00, R1b");
}

static void sdsc() {
  SdCard::Options o;
  o.highCapacity = false;
  auto img = pattern(1 << 20);
  SdCard c(img, o);
  Host h{c};
  h.init(0);
  auto r = h.cmd(17, 3 * 512);
  std::vector<uint8_t> b;
  expect(r == std::vector<uint8_t>{0} && h.block(b, 512) && std::equal(b.begin(), b.end(), img.begin() + 3 * 512),
         "SDSC: CMD17's argument is a byte address (7.2.3)");
  r = h.cmd(16, 16);
  r = h.cmd(17, 1000);
  expect(r == std::vector<uint8_t>{0} && h.block(b, 16) && std::equal(b.begin(), b.end(), img.begin() + 1000),
         "SDSC: CMD16 16, a partial 16-byte read at 1000 (READ_BL_PARTIAL, 7.2.3)");
  r = h.cmd(17, 510);
  expect(r == std::vector<uint8_t>{0x20}, "SDSC: a partial read across a block boundary is an address error $20");
  r = h.cmd(24, 0);
  expect(r == std::vector<uint8_t>{0x40}, "SDSC: a write with block length 16 is refused (WRITE_BL_PARTIAL = 0)");
  h.cmd(16, 512);
  r = h.cmd(24, 100);
  expect(r == std::vector<uint8_t>{0x20}, "SDSC: a misaligned write is an address error $20");
  r = h.cmd(16, 1024);
  expect(r == std::vector<uint8_t>{0x40}, "SDSC: CMD16 over 512 is a parameter error");
}

static void writeProtect() {
  SdCard::Options o;
  o.writeProtect = true;
  auto img = pattern(1 << 20);
  SdCard c(img, o);
  Host h{c};
  h.init();
  h.cmd(24, 1);
  expect(h.send(0xfe, std::vector<uint8_t>(512, 0)) == 0x0d, "write-protected: data response 'write error' $0D (7.3.3.1)");
  auto r = h.cmd(13, 0, 2);
  expect(r.size() == 2 && (r[1] & 0x20), "write-protected: R2 WP violation (7.3.2.3)");
  r = h.cmd(13, 0, 2);
  expect(r == std::vector<uint8_t>({0, 0}), "R2's error bits clear once read");
  c.settle(h.t + 1e9);
  expect(c.data == img, "write-protected: the image is unchanged");
}

// ---------------------------------------------------------------- the socket on an RP2040

struct Chip {
  SimulationClock clock;
  RP2040 mcu{clock};
  SdSocket sock{mcu};
  static constexpr uint32_t SPI1 = 0x40040000, IO = 0x40014000, SIO = 0xd0000000, DMA = 0x50000000;
  Chip() {
    for (unsigned pin : {12u, 14u, 15u}) mcu.writeUint32(IO + 8 * pin + 4, 1);  // SPI1
    mcu.writeUint32(IO + 8 * 13 + 4, 5);                                          // nCS: SIO
    mcu.writeUint32(SIO + 0x14, 1u << 13);                                        // high
    mcu.writeUint32(SIO + 0x24, 1u << 13);                                        // output
    speed(400e3);
    mcu.writeUint32(SPI1 + 0x04, 2);                                              // SSE
  }
  // CPSDVSR and SCR as the SDK's spi_set_baudrate picks them
  void speed(double hz) {
    uint32_t pre = 2;
    while (pre <= 254 && 125e6 >= (pre + 2) * 256 * hz) pre += 2;
    uint32_t post = 256;
    while (post > 1 && 125e6 / (pre * (post - 1)) <= hz) post--;
    mcu.writeUint32(SPI1 + 0x10, pre);
    mcu.writeUint32(SPI1 + 0x00, ((post - 1) << 8) | 7);  // 8 bits, mode 0
  }
  void cs(bool low) { mcu.writeUint32(SIO + (low ? 0x18 : 0x14), 1u << 13); }
  void run(double ns) { clock.tick(ns); }
  // one byte through SSPDR, waiting in steps of 10 ns like a polling loop
  uint8_t x(uint8_t b, double *took = nullptr) {
    const double t0 = clock.nanos();
    mcu.writeUint32(SPI1 + 0x08, b);
    while (!(mcu.readUint32(SPI1 + 0x0c) & 4)) clock.tick(10);
    if (took) *took = clock.nanos() - t0;
    return static_cast<uint8_t>(mcu.readUint32(SPI1 + 0x08));
  }
  std::vector<uint8_t> cmd(uint8_t idx, uint32_t arg, size_t n = 1) {
    for (uint8_t b : Host::frame(idx, arg)) x(b);
    std::vector<uint8_t> r;
    for (int i = 0; i < 8 && r.empty(); i++) {
      const uint8_t b = x(0xff);
      if (!(b & 0x80)) r.push_back(b);
    }
    while (!r.empty() && r.size() < n) r.push_back(x(0xff));
    return r;
  }
  bool detect() { return mcu.gpio[17].status() & (1u << 17); }  // the pad's input
  bool init() {
    cs(false);
    for (int i = 0; i < 10; i++) x(0xff);
    cs(true);
    cmd(0, 0);
    cmd(8, 0x1aa, 5);
    for (int i = 0; i < 100; i++) {
      cmd(55, 0);
      if (cmd(41, 1u << 30) == std::vector<uint8_t>{0}) return true;
      run(1e6);
    }
    return false;
  }
};

static void socket() {
  {
    Chip c;
    expect(c.detect(), "socket empty: card detect high (the pull-up)");
    c.sock.insert(pattern(1 << 20), {});
    expect(!c.detect(), "card in: card detect low (hw/pins.yaml SD_nDETECT)");
    double took = 0;
    c.x(0xff, &took);
    const double want = 8e9 / c.sock.sckHz();
    expect(std::fabs(took - want) < 20, "a byte takes 8 SCK periods at the programmed rate (" + std::to_string(took) + " ns, SCK " +
                                            std::to_string(c.sock.sckHz()) + " Hz)");
    expect(c.sock.sckHz() <= 400e3, "the SDK's divider gives <= 400 kHz");
    expect(c.init(), "init through SPI1's registers");
    expect(c.sock.card()->violations.empty(), "no violations at 400 kHz with SIO nCS: " +
                                                  (c.sock.card()->violations.empty() ? "" : c.sock.card()->violations[0]));
    c.speed(25e6);
    took = 0;
    c.x(0xff, &took);
    expect(took < 400, "after init, 25 MHz: a byte in " + std::to_string(took) + " ns");
    auto r = c.cmd(17, 2);
    std::vector<uint8_t> b;
    uint8_t t = 0xff;
    for (int i = 0; i < 10000 && t == 0xff; i++) t = c.x(0xff);
    for (int i = 0; i < 514; i++) b.push_back(c.x(0xff));
    expect(r == std::vector<uint8_t>{0} && t == 0xfe && std::equal(b.begin(), b.begin() + 512, c.sock.card()->data.begin() + 1024),
           "CMD17 through SPI1: the block arrives");

    // DMA: 512 bytes out of SPI1 into SRAM on DREQ_SPI1_RX, $FF in on DREQ_SPI1_TX
    r = c.cmd(17, 4);
    t = 0xff;
    for (int i = 0; i < 10000 && t != 0xfe; i++) t = c.x(0xff);
    const uint32_t src = 0x20000000, dst = 0x20001000;
    for (uint32_t i = 0; i < 512; i += 4) c.mcu.writeUint32(src + i, 0xffffffff);
    auto chan = [&](int ch, uint32_t rd, uint32_t wr, uint32_t ctrl) {
      c.mcu.writeUint32(Chip::DMA + ch * 0x40 + 0x0, rd);
      c.mcu.writeUint32(Chip::DMA + ch * 0x40 + 0x4, wr);
      c.mcu.writeUint32(Chip::DMA + ch * 0x40 + 0x8, 512);
      c.mcu.writeUint32(Chip::DMA + ch * 0x40 + 0xc, ctrl | (uint32_t(ch) << 11) | 1);  // chain to itself, EN
    };
    c.mcu.writeUint32(Chip::SPI1 + 0x24, 3);                                  // SSPDMACR
    chan(1, Chip::SPI1 + 8, dst, (DREQ_SPI1_RX << 15) | (1 << 5));           // bytes, INCR_WRITE
    chan(0, src, Chip::SPI1 + 8, (DREQ_SPI1_TX << 15) | (1 << 4));           // bytes, INCR_READ
    for (int i = 0; i < 100000 && (c.mcu.readUint32(Chip::DMA + 0x40 + 0xc) & (1u << 24)); i++) c.run(10);
    bool same = true;
    for (uint32_t i = 0; i < 512; i++) same &= (c.mcu.readUint32(dst + (i & ~3u)) >> (8 * (i & 3)) & 0xff) == c.sock.card()->data[4 * 512 + i];
    expect(same, "a block read by DMA on SPI1's DREQs, both channels byte-wide");
    c.x(0xff);
    c.x(0xff);

    // pulling the card out: power off
    c.sock.remove();
    expect(c.detect() && c.x(0xff) == 0xff, "card out: card detect high, DO released ($FF)");
    c.sock.insert(pattern(1 << 20), {});
    c.speed(400e3);
    auto again = c.cmd(17, 0);
    expect(again.empty(), "a card put back in needs initialising again (it was powered off)");
    expect(c.init(), "and initialises");
  }
  {
    Chip c;
    c.sock.insert(pattern(1 << 20), {});
    c.speed(12.5e6);
    c.init();
    bool fast = false;
    for (auto &v : c.sock.card()->violations) fast |= v.find("400 kHz") != std::string::npos;
    expect(fast, "initialising at 12.5 MHz is recorded as a violation (4.2.1)");
  }
  {
    Chip c;
    c.sock.insert(pattern(1 << 20), {});
    c.mcu.writeUint32(Chip::IO + 8 * 13 + 4, 1);  // nCS on SPI1's CSn
    const bool ok = c.init();
    bool hw = false;
    for (auto &v : c.sock.card()->violations) hw |= v.find("CSn") != std::string::npos;
    expect(!ok && hw, "nCS on SPI1's own CSn: the card does not answer, and it is recorded");
  }
}

int main() {
  crcs();
  powerUp();
  registers();
  readWrite();
  sdsc();
  writeProtect();
  socket();
  std::printf("EMU-008: SD card SPI-mode model, %d checks, %d failures\n", checks, bad);
  return bad ? 1 : 0;
}
