// Port of rp2040js src/peripherals/dma.ts
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

#include "../clock/clock.h"
#include "dreq.h"
#include "peripheral.h"

namespace rp2040js {

class RPDMA;

enum class TREQ : uint32_t {
  Timer0 = 0x3b,
  Timer1 = 0x3c,
  Timer2 = 0x3d,
  Timer3 = 0x3e,
  Permanent = 0x3f,
};

class RPDMAChannel {
 public:
  RPDMA &dma;
  RP2040 &rp2040;
  const uint32_t index;

  RPDMAChannel(RPDMA &dma, RP2040 &rp2040, uint32_t index);
  RPDMAChannel(const RPDMAChannel &) = delete;
  RPDMAChannel &operator=(const RPDMAChannel &) = delete;

  void start();

  uint32_t treq() const;
  /** `ctrl & EN && ctrl & BUSY`: a number in TS */
  uint32_t active() const;

  // arrow-function fields in TS
  void transfer8();
  void transfer16();
  void transferSwap16();
  void transfer32();
  void transferSwap32();
  void transfer();

  void scheduleTransfer();
  void abort();

  uint32_t readUint32(uint32_t offset);
  void writeUint32(uint32_t offset, uint32_t value);
  void reset();

 private:
  uint32_t ctrl = 0;
  uint32_t readAddr = 0;
  uint32_t writeAddr = 0;
  /** a JS number: `transCount--` from 0 (BUSY with a zero reload) goes negative */
  double transCount = 0;
  uint32_t dreqCounter = 0;
  uint32_t transCountReload = 0;
  uint32_t treqValue = 0;
  uint32_t dataSize = 1;
  uint32_t chainTo = 0;
  uint32_t ringMask = 0;
  /** `private transferFn: () => void = () => 0;` (a member-function pointer to one of the transfer* methods) */
  void (RPDMAChannel::*transferFn)() = nullptr;
  std::unique_ptr<IAlarm> transferAlarm;
};

class RPDMA : public BasePeripheral {
 public:
  /** `[new RPDMAChannel(this, this.rp2040, 0), ... 11]` (in the constructor's initialiser list) */
  std::array<RPDMAChannel, 12> channels;

  uint32_t intRaw = 0;

  /**
   * `Array(DREQChannel.DREQ_MAX)` of booleans (initially undefined = false).
   * Sized 64 because TS also indexes it with TREQ_SEL values up to 0x3f,
   * which read as undefined (false).
   */
  std::array<bool, 64> dreq{};

  RPDMA(RP2040 &rp2040, const std::string &name);

  uint32_t intStatus0() const;
  uint32_t intStatus1() const;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

  void setDREQ(DREQChannel dreqChannel);
  void clearDREQ(DREQChannel dreqChannel);

  /**
   * Returns the number of microseconds for a cycle of the given DMA timer, or 0 if the timer is disabled.
   */
  double getTimer(TREQ treq) const;

  void checkInterrupts();

 private:
  uint32_t intEnable0 = 0;
  uint32_t intForce0 = 0;
  uint32_t intEnable1 = 0;
  uint32_t intForce1 = 0;
  uint32_t timer0 = 0;
  uint32_t timer1 = 0;
  uint32_t timer2 = 0;
  uint32_t timer3 = 0;
};

}  // namespace rp2040js
