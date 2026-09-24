// Port of rp2040js src/peripherals/i2c.ts
#pragma once

#include <cstdint>
#include <functional>
#include <string>

#include "../utils/fifo.h"
#include "peripheral.h"

namespace rp2040js {

/* Connection parameters */
enum class I2CMode {
  Write,
  Read,
};

enum class I2CSpeed {
  Invalid,
  /* standard mode (100 kbit/s) */
  Standard,
  /* fast mode (<=400 kbit/s) or fast mode plus (<=1000Kbit/s) */
  FastMode,
  /*  high speed mode (3.4 Mbit/s) */
  HighSpeedMode,
};

enum class I2CState {
  Idle,
  Start,
  Connect,
  Connected,
  Stop,
};

class RPI2C : public BasePeripheral {
 public:
  // user provided callbacks (defaults set in the constructor, as in TS):
  /** default `() => this.completeStart()` */
  std::function<void(bool repeatedStart)> onStart;
  /** default `() => this.completeConnect(false)` */
  std::function<void(uint32_t address, I2CMode mode)> onConnect;
  /** default `() => this.completeWrite(false)` */
  std::function<void(uint32_t value)> onWriteByte;
  /** default `() => this.completeRead(0xff)` */
  std::function<void(bool ack)> onReadByte;
  /** default `() => this.completeStop()` */
  std::function<void()> onStop;

  uint32_t enable = 0;
  uint32_t rxThreshold = 0;
  uint32_t txThreshold = 0;
  /** = IC_SLAVE_DISABLE | IC_RESTART_EN | (I2CSpeed.FastMode << SPEED_SHIFT) | MASTER_MODE (set in the constructor) */
  uint32_t control;
  uint32_t ssClockHighPeriod = 0x0028;
  uint32_t ssClockLowPeriod = 0x002f;
  uint32_t fsClockHighPeriod = 0x0006;
  uint32_t fsClockLowPeriod = 0x000d;
  uint32_t targetAddress = 0x55;
  uint32_t slaveAddress = 0x55;
  uint32_t abortSource = 0;
  uint32_t intRaw = 0;
  uint32_t intEnable = 0;

  const uint32_t irq;

  RPI2C(RP2040 &rp2040, const std::string &name, uint32_t irq);

  uint32_t intStatus() const;
  I2CSpeed speed() const;
  uint32_t sclLowPeriod() const;
  uint32_t sclHighPeriod() const;
  uint32_t masterBits() const;

  void checkInterrupts();

  void completeStart();
  void completeConnect(bool ack, uint32_t nackByte = 0);
  void completeWrite(bool ack);
  void completeRead(uint32_t value);
  void completeStop();
  void arbitrationLost();

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

 protected:
  uint32_t clearInterrupts(uint32_t mask);
  void setInterrupts(uint32_t mask);
  void abort(uint32_t reason);
  void nextCommand();
  void pushRX(uint32_t value);

 private:
  I2CState state = I2CState::Idle;
  bool busy = false;
  bool stop = false;
  bool pendingRestart = false;
  bool firstByte = false;
  FIFO rxFIFO{16};
  FIFO txFIFO{16};
  uint32_t spikelen = 0x07;
};

}  // namespace rp2040js
