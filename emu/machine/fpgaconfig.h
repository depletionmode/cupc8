// The two iCE40s' configuration (doc/hardware/system-slot.md, "Buses"): each
// FPGA boots itself from its own W25Q flash in SPI master mode when its
// CRESET_B is released, and reports CDONE; sysctl holds CRESET_B low while
// it reprograms that flash over its SPI1 (FL0: the chipset's flash on the
// main board, FL1: the CPU card's, through the CPU socket).
//
// This is a digital model for the netlist co-simulation (hw/cosim):
// - SpiFlash: the W25Q commands sysctl uses (fw/sysctl/core/spiflash.c):
//   JEDEC ID, read, status, write enable/disable, page program, 4 KB sector
//   erase. Program and erase complete at CS_n rising with BUSY never set
//   (tPP/tSE are not modelled: the firmware's polls return at once).
// - A configuration is the FPGA reading its flash: it succeeds when the
//   FPGA-to-flash copper is whole and the flash holds an iCE40 image (the
//   0x7EAA997E sync word in its first 4 KB); it takes CONFIG_NS after
//   CRESET_B rises (fpga.c: "an HX4K reads its ~135 KB image in ~0.2 s").
//   The bitstream itself is not decoded: the configured logic is the RTL.
//   At power-on the FPGAs are configured at once, as the emulator always
//   assumed (the real ~0.2 s start-up is not modelled).
#pragma once

#include <algorithm>
#include <cstdint>
#include <vector>

namespace machine {

class SpiFlash {
 public:
  static constexpr size_t SIZE = 4u << 20;  // W25Q32JV
  std::vector<uint8_t> mem = std::vector<uint8_t>(SIZE, 0xff);
  uint8_t id[3] = {0xef, 0x40, 0x16};

  // one byte shifted while CS_n is low; returns the byte on DO
  uint8_t exchange(uint8_t in) {
    uint8_t out = 0xff;
    if (count == 0) {
      cmd = in;
      if (cmd == 0x06) wel = true;
      if (cmd == 0x04) wel = false;
    } else {
      switch (cmd) {
        case 0x9f:
          out = count <= 3 ? id[count - 1] : 0xff;
          break;
        case 0x05:
          out = wel ? 0x02 : 0x00;  // BUSY (bit 0) is never set
          break;
        case 0x03:
          if (count <= 3) {
            addr = (addr << 8) | in;
          } else {
            out = mem[addr % SIZE];
            addr++;
          }
          break;
        case 0x02:
        case 0x20:
          if (count <= 3) {
            addr = (addr << 8) | in;
          } else if (cmd == 0x02) {
            page.push_back(in);
          }
          break;
        default:
          break;
      }
    }
    count++;
    return out;
  }

  // CS_n rising: a page program or an erase takes effect now
  void deselect() {
    if (count >= 4 && wel && cmd == 0x02) {
      const uint32_t base = addr & ~0xffu & (SIZE - 1);
      uint32_t at = addr & 0xff;
      // more than 256 bytes: the last 256 count, wrapping in the page
      const size_t skip = page.size() > 256 ? page.size() - 256 : 0;
      for (size_t i = skip; i < page.size(); i++, at = (at + 1) & 0xff) mem[base + at] &= page[i];
      wel = false;
    } else if (count == 4 && wel && cmd == 0x20) {
      const uint32_t base = addr & ~0xfffu & (SIZE - 1);
      std::fill(mem.begin() + base, mem.begin() + base + 4096, 0xff);
      wel = false;
    }
    count = 0;
    addr = 0;
    page.clear();
  }

  // an iCE40 image: the sync word within the first 4 KB
  bool holdsBitstream() const {
    for (size_t i = 0; i + 4 <= 4096; i++)
      if (mem[i] == 0x7e && mem[i + 1] == 0xaa && mem[i + 2] == 0x99 && mem[i + 3] == 0x7e) return true;
    return false;
  }

 private:
  uint8_t cmd = 0;
  uint32_t count = 0, addr = 0;
  bool wel = false;
  std::vector<uint8_t> page;
};

// an FPGA's CRESET_B/CDONE state machine
struct FpgaConfig {
  static constexpr double CONFIG_NS = 200e6;
  bool configured = true;
  bool held = false;          // CRESET_B low
  double readyAt = -1;        // configuring until then (-1: not configuring)
  bool copper = true;         // FPGA-to-flash and CRESET_B pull-up copper whole
  SpiFlash flash;

  // CRESET_B's level at time t; returns true when `configured` changed
  bool step(bool cresetLow, double t) {
    const bool was = configured;
    if (cresetLow) {
      held = true;
      configured = false;
      readyAt = -1;
    } else if (held) {
      held = false;
      readyAt = t + CONFIG_NS;
    }
    if (readyAt >= 0 && t >= readyAt) {
      readyAt = -1;
      configured = copper && flash.holdsBitstream();
    }
    return configured != was;
  }
};

}  // namespace machine
