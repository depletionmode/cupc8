// Port of rp2040js src/peripherals/busctrl.ts
#pragma once

#include <array>
#include <cstdint>
#include <string>

#include "peripheral.h"

namespace rp2040js {

class RPBUSCTRL : public BasePeripheral {
 public:
  uint32_t voltageSelect = 0;
  std::array<uint32_t, 4> perfCtr = {0, 0, 0, 0};
  std::array<uint32_t, 4> perfSel = {0x1f, 0x1f, 0x1f, 0x1f};

  RPBUSCTRL(RP2040 &rp2040, const std::string &name);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
