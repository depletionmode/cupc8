#include "emu.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

#include "utils/logging.h"

using namespace rp2040js;

namespace machine {

// the B1 bootrom ships with rp2040js as TypeScript source in its demo;
// CMake extracts its words the way rp2040emu.mjs's bootrom() does.
static const std::vector<uint32_t> &bootrom() {
  static const std::vector<uint32_t> words = {
#include "bootrom_b1.inc"
  };
  return words;
}

static uint32_t le32(const std::vector<uint8_t> &b, size_t at) {
  if (at + 4 > b.size()) throw std::range_error("ELF: read past the end of the file");
  return b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | (static_cast<uint32_t>(b[at + 3]) << 24);
}

static uint32_t le16(const std::vector<uint8_t> &b, size_t at) {
  if (at + 2 > b.size()) throw std::range_error("ELF: read past the end of the file");
  return b[at] | (b[at + 1] << 8);
}

// copy an ELF's loadable segments into flash (by their physical address)
static void loadElf(const std::string &file, RP2040 &mcu) {
  std::ifstream in(file, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open " + file);
  const std::vector<uint8_t> b((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  const uint32_t phoff = le32(b, 28), phentsize = le16(b, 42), phnum = le16(b, 44);
  for (uint32_t i = 0; i < phnum; i++) {
    const size_t h = phoff + static_cast<size_t>(i) * phentsize;
    if (le32(b, h) != 1) continue;  // PT_LOAD
    const uint32_t offset = le32(b, h + 4), paddr = le32(b, h + 12), filesz = le32(b, h + 16);
    if (filesz && paddr >= 0x10000000 && paddr < 0x11000000) {
      const size_t begin = std::min<size_t>(offset, b.size());
      const size_t end = std::min<size_t>(static_cast<size_t>(offset) + filesz, b.size());
      const size_t dest = paddr - 0x10000000;
      if (dest + (end - begin) > mcu.flash.size()) throw std::range_error("ELF segment past the flash");
      std::copy(b.begin() + begin, b.begin() + end, mcu.flash.begin() + dest);
    }
  }
}

Emu::Emu(const std::string &elf, double mhz) {
  mcu = std::make_unique<RP2040>(clock);
  mcu->logger = std::make_shared<ConsoleLogger>(LogLevel::Error);
  mcu->loadBootrom(bootrom());
  loadElf(elf, *mcu);
  mcu->core0.setPC(0x10000000);  // boot stage 2, as the bootrom would
  nsPerCycle = 1000 / mhz;
  // PIO normally runs itself on setTimeout; we step it with the cores
  for (RPPIO &pio : mcu->pio) pio.run = [] {};
  mcu->uart[0].onByte = [this](uint32_t b) { uart += static_cast<char>(b); };
}

}  // namespace machine
