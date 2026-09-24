// Port of rp2040js src/peripherals/clocks.ts
#pragma once

#include <cstdint>
#include <string>

#include "peripheral.h"

namespace rp2040js {

class RPClocks : public BasePeripheral {
 public:
  uint32_t gpout0Ctrl = 0;
  uint32_t gpout0Div = 0x100;
  uint32_t gpout1Ctrl = 0;
  uint32_t gpout1Div = 0x100;
  uint32_t gpout2Ctrl = 0;
  uint32_t gpout2Div = 0x100;
  uint32_t gpout3Ctrl = 0;
  uint32_t gpout3Div = 0x100;
  uint32_t refCtrl = 0;
  uint32_t refDiv = 0x100;
  uint32_t periCtrl = 0;
  uint32_t periDiv = 0x100;
  uint32_t usbCtrl = 0;
  uint32_t usbDiv = 0x100;
  uint32_t sysCtrl = 0;
  uint32_t sysDiv = 0x100;
  uint32_t adcCtrl = 0;
  uint32_t adcDiv = 0x100;
  uint32_t rtcCtrl = 0;
  uint32_t rtcDiv = 0x100;

  RPClocks(RP2040 &rp2040, const std::string &name);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
};

}  // namespace rp2040js
