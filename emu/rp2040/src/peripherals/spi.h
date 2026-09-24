// Port of rp2040js src/peripherals/spi.ts
#pragma once

#include <cstdint>
#include <functional>
#include <string>

#include "../utils/fifo.h"
#include "dreq.h"
#include "peripheral.h"

namespace rp2040js {

struct ISPIDMAChannels {
  DREQChannel rx;
  DREQChannel tx;
};

class RPSPI : public BasePeripheral {
 public:
  FIFO rxFIFO{8};
  FIFO txFIFO{8};

  // User provided callbacks
  /** default: `() => this.completeTransmit(0)` (set in the constructor) */
  std::function<void(uint32_t value)> onTransmit;

  const uint32_t irq;
  const ISPIDMAChannels dreq;

  RPSPI(RP2040 &rp2040, const std::string &name, uint32_t irq, ISPIDMAChannels dreq);

  uint32_t intStatus() const;
  bool enabled() const;
  /** Data size in bits: 4 to 16 bits */
  uint32_t dataBits() const;
  bool masterMode() const;
  uint32_t spiMode() const;
  double clockFrequency() const;

  void completeTransmit(uint32_t rxValue);
  void checkInterrupts();

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  bool busy = false;
  uint32_t control0 = 0;
  uint32_t control1 = 0;
  uint32_t dmaControl = 0;
  uint32_t clockDivisor = 0;
  uint32_t intRaw = 0;
  uint32_t intEnable = 0;

  void updateDMATx();
  void updateDMARx();
  void doTX();
  void fifosUpdated();
};

}  // namespace rp2040js
