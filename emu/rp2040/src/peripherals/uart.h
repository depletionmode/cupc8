// Port of rp2040js src/peripherals/uart.ts
#pragma once

#include <cstdint>
#include <functional>
#include <string>

#include "../utils/fifo.h"
#include "dreq.h"
#include "peripheral.h"

namespace rp2040js {

struct IUARTDMAChannels {
  DREQChannel rx;
  DREQChannel tx;
};

class RPUART : public BasePeripheral {
 public:
  /** `onByte?: (value: number) => void` (empty = undefined) */
  std::function<void(uint32_t value)> onByte;
  std::function<void(double baudRate)> onBaudRateChange;

  const uint32_t irq;
  const IUARTDMAChannels dreq;

  RPUART(RP2040 &rp2040, const std::string &name, uint32_t irq, IUARTDMAChannels dreq);

  bool enabled() const;
  bool txEnabled() const;
  bool rxEnabled() const;
  bool fifosEnabled() const;

  /**
   * Number of bits per UART character
   */
  uint32_t wordLength() const;

  double baudDivider() const;
  double baudRate() const;
  uint32_t flags() const;

  void checkInterrupts();
  void feedByte(uint32_t value);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  uint32_t ctrlRegister;  // = RXE | TXE (set in the constructor)
  uint32_t lineCtrlRegister = 0;
  FIFO rxFIFO{32};
  uint32_t interruptMask = 0;
  uint32_t interruptStatus = 0;
  uint32_t intDivisor = 0;
  uint32_t fracDivisor = 0;
};

}  // namespace rp2040js
