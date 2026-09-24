// Port of rp2040js src/peripherals/peripheral.ts
#include "peripheral.h"

#include <utility>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t ATOMIC_NORMAL = 0;
static constexpr uint32_t ATOMIC_XOR = 1;
static constexpr uint32_t ATOMIC_SET = 2;
static constexpr uint32_t ATOMIC_CLEAR = 3;

uint32_t atomicUpdate(uint32_t currentValue, uint32_t atomicType, uint32_t newValue) {
  switch (atomicType) {
    case ATOMIC_XOR:
      return currentValue ^ newValue;
    case ATOMIC_SET:
      return currentValue | newValue;
    case ATOMIC_CLEAR:
      return currentValue & ~newValue;
    default:
      // console.warn('Atomic update called with invalid writeType', atomicType);
      consoleWarn("Atomic update called with invalid writeType " + std::to_string(atomicType));
      return newValue;
  }
}

BasePeripheral::BasePeripheral(RP2040 &rp2040, std::string name)
    : name(std::move(name)), rp2040(rp2040) {}

uint32_t BasePeripheral::readUint32(uint32_t offset) {
  warn("Unimplemented peripheral read from 0x" + toHex(offset));
  if (offset > 0x1000) {
    warn("Unimplemented read from peripheral in the atomic operation region");
  }
  return 0xffffffff;
}

void BasePeripheral::writeUint32(uint32_t offset, uint32_t value) {
  warn("Unimplemented peripheral write to 0x" + toHex(offset) + ": 0x" + toHex(value));
}

void BasePeripheral::writeUint32Atomic(uint32_t offset, uint32_t value, uint32_t atomicType) {
  rawWriteValue = value;
  const uint32_t newValue =
      atomicType != ATOMIC_NORMAL ? atomicUpdate(readUint32(offset), atomicType, value) : value;
  writeUint32(offset, newValue);
}

void BasePeripheral::debug(const std::string &msg) { rp2040.logger->debug(name, msg); }

void BasePeripheral::info(const std::string &msg) { rp2040.logger->info(name, msg); }

void BasePeripheral::warn(const std::string &msg) { rp2040.logger->warn(name, msg); }

void BasePeripheral::error(const std::string &msg) { rp2040.logger->error(name, msg); }

}  // namespace rp2040js
