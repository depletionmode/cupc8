// Port of rp2040js src/peripherals/peripheral.ts
#pragma once

#include <cstdint>
#include <string>

namespace rp2040js {

class RP2040;

uint32_t atomicUpdate(uint32_t currentValue, uint32_t atomicType, uint32_t newValue);

/** `interface Peripheral` */
class Peripheral {
 public:
  virtual ~Peripheral() = default;
  virtual uint32_t readUint32(uint32_t offset) = 0;
  virtual void writeUint32(uint32_t offset, uint32_t value) = 0;
  virtual void writeUint32Atomic(uint32_t offset, uint32_t value, uint32_t atomicType) = 0;
};

class BasePeripheral : public Peripheral {
 public:
  const std::string name;

  BasePeripheral(RP2040 &rp2040, std::string name);
  BasePeripheral(const BasePeripheral &) = delete;
  BasePeripheral &operator=(const BasePeripheral &) = delete;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;
  void writeUint32Atomic(uint32_t offset, uint32_t value, uint32_t atomicType) override;

  void debug(const std::string &msg);
  void info(const std::string &msg);
  void warn(const std::string &msg);
  void error(const std::string &msg);

 protected:
  RP2040 &rp2040;
  uint32_t rawWriteValue = 0;
};

class UnimplementedPeripheral : public BasePeripheral {
 public:
  using BasePeripheral::BasePeripheral;
};

}  // namespace rp2040js
