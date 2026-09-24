// Port of rp2040js src/peripherals/adc.ts
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

#include "../clock/clock.h"
#include "../utils/fifo.h"
#include "dreq.h"
#include "peripheral.h"

namespace rp2040js {

class RPADC : public BasePeripheral {
 public:
  /* Number of ADC channels */
  const uint32_t numChannels = 5;

  /** ADC resolution (in bits) */
  const uint32_t resolution = 12;

  /** Time to read a single sample, in microseconds */
  const double sampleTime = 2;

  /**
   * ADC Channel values. Channels 0...3 are connected to GPIO 26...29, and channel 4 is connected to the built-in
   * temperature sensor: T=27-(ADC_voltage-0.706)/0.001721.
   *
   * Changing the values will change the ADC reading, unless you override onADCRead() with a custom implementation.
   */
  std::array<uint32_t, 5> channelValues = {0, 0, 0, 0, 0};

  /**
   * Invoked whenever the emulated code performs an ADC read.
   *
   * The default implementation reads the result from the `channelValues` array, and then calls
   * completeADCRead() after `sampleTime` microseconds.
   *
   * If you override the default implementation, make sure to call `completeADCRead()` after
   * `sampleTime` microseconds (or else the ADC read will never complete).
   *
   * (default set in the constructor)
   */
  std::function<void(uint32_t channel)> onADCRead;

  FIFO fifo{4};
  const DREQChannel dreq = DREQ_ADC;

  // Registers
  uint32_t cs = 0;
  uint32_t fcs = 0;
  uint32_t clockDiv = 0;
  uint32_t intEnable = 0;
  uint32_t intForce = 0;
  uint32_t result = 0;

  // Status
  bool busy = false;
  bool err = false;

  uint32_t currentChannel = 0;
  /** Used to simulate ADC sample time */
  std::unique_ptr<IAlarm> sampleAlarm;

  /** For scheduling multi-shot ADC capture */
  std::unique_ptr<IAlarm> multiShotAlarm;

  RPADC(RP2040 &rp2040, const std::string &name);

  /** (sic) returns `cs & CS_TS_EN`, a number */
  uint32_t temperatueEnable() const;
  /** returns `cs & CS_EN`, a number */
  uint32_t enabled() const;
  double divider() const;
  uint32_t intRaw() const;
  uint32_t intStatus() const;

  void checkInterrupts();
  void startADCRead();
  void completeADCRead(uint32_t value, bool error);

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 private:
  uint32_t activeChannel() const;
  void setActiveChannel(uint32_t channel);
  void updateDMA();
};

}  // namespace rp2040js
