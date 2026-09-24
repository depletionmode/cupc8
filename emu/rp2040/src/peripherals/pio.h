// Port of rp2040js src/peripherals/pio.ts (with the cupc8 dual-core patch:
// clock divider (clockTick/divPhase), delayLeft, FIFO join on SHIFTCTRL).
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>

#include "../utils/fifo.h"
#include "dreq.h"
#include "peripheral.h"

namespace rp2040js {

class RPPIO;

enum class WaitType {
  None,
  Pin,
  rxFIFO,
  txFIFO,
  IRQ,
  Out,  // Out instruction
};

/**
 * JS number note: x, y, inputShiftReg and outputShiftReg hold a JS number that
 * is sometimes a negative int32 (after `<<=`, `|=`, or `x = osr`) and
 * sometimes a uint32 (after `>>>`). Every use of them in pio.ts is bitwise,
 * a Uint32Array store (FIFO push), `=== 0`, `(x - 1) >>> 0` or `x >>> 0 !==
 * y >>> 0`, all of which only see the 32-bit pattern, so a uint32_t holding
 * that pattern behaves identically (compare them as `v >>> 0` against JS).
 */
class StateMachine {
 public:
  bool enabled = false;

  // State machine registers
  uint32_t x = 0;
  uint32_t y = 0;
  uint32_t pc = 0;
  uint32_t inputShiftReg = 0;
  uint32_t inputShiftCount = 0;
  uint32_t outputShiftReg = 0;
  uint32_t outputShiftCount = 0;
  double cycles = 0;

  uint32_t execOpcode = 0;
  bool execValid = false;
  bool updatePC = true;

  uint32_t clockDivInt = 1;
  uint32_t clockDivFrac = 0;
  uint32_t execCtrl = 0x1f << 12;
  uint32_t shiftCtrl = 0b11 << 18;
  uint32_t pinCtrl = 0x5 << 26;
  FIFO rxFIFO{4};
  FIFO txFIFO{4};

  uint32_t outPinValues = 0;
  uint32_t outPinDirection = 0;

  bool waiting = false;
  WaitType waitType = WaitType::None;
  uint32_t waitIndex = 0;
  bool waitPolarity = false;
  int32_t waitDelay = -1;

  RP2040 &rp2040;
  RPPIO &pio;
  const uint32_t index;

  /** `this.pio.dreqRx[this.index]` / `dreqTx` (set in the constructor) */
  const DREQChannel dreqRx;
  const DREQChannel dreqTx;

  StateMachine(RP2040 &rp2040, RPPIO &pio, uint32_t index);
  StateMachine(const StateMachine &) = delete;
  StateMachine &operator=(const StateMachine &) = delete;

  void writeFIFO(uint32_t value);
  uint32_t readFIFO();

  uint32_t status() const;

  bool jmpCondition(uint32_t condition);

  uint32_t inPins() const;
  uint32_t inSourceValue(uint32_t source);
  void writeOutValue(uint32_t destination, uint32_t value, uint32_t bitCount);

  uint32_t pushThreshold() const;
  uint32_t pullThreshold() const;
  uint32_t sidesetCount() const;
  uint32_t setCount() const;
  uint32_t outCount() const;
  uint32_t inBase() const;
  uint32_t sidesetBase() const;
  uint32_t setBase() const;
  uint32_t outBase() const;
  uint32_t jmpPin() const;
  uint32_t wrapTop() const;
  uint32_t wrapBottom() const;

  void setOutPinDirs(uint32_t value);
  void setOutPins(uint32_t value);
  void outInstruction(uint32_t arg);
  void executeInstruction(uint32_t opcode);
  void wait(WaitType type, bool polarity, uint32_t index);
  void nextPC();
  void step();
  void setSetPinDirs(uint32_t value);
  void setSetPins(uint32_t value);
  void setSideset(uint32_t value, uint32_t count);
  uint32_t transformMovValue(uint32_t value, uint32_t op);
  void setMovDestination(uint32_t destination, uint32_t value);

  uint32_t readUint32(uint32_t offset);
  void writeUint32(uint32_t offset, uint32_t value);

  uint32_t fifoStat() const;

  void restart();
  void clkDivRestart();

  /** One system clock: the machine runs if enabled, at INT.FRAC (INT 0 = 65536). */
  void clockTick();

  void checkWait();

  /** Test access to the private divider/delay state (not in TS). */
  uint32_t debugDivPhase() const { return divPhase; }
  int32_t debugDelayLeft() const { return delayLeft; }

 private:
  /** system cycles (in 1/256ths) owed to this machine by its clock divider */
  uint32_t divPhase = 0;
  /** delay cycles ([n]) still to run after the last instruction */
  int32_t delayLeft = 0;

  void updateDMATx();
  void updateDMARx();
};

class RPPIO : public BasePeripheral {
 public:
  std::array<uint32_t, 32> instructions{};  // `new Uint32Array(32)`

  const uint32_t firstIrq;
  const uint32_t index;

  /** `this.index ? dreqRx1 : dreqRx0` (set in the constructor) */
  const std::array<DREQChannel, 4> dreqRx;
  const std::array<DREQChannel, 4> dreqTx;
  /** `[new StateMachine(this.rp2040, this, 0), ... 3]` (in the constructor's initialiser list) */
  std::array<StateMachine, 4> machines;

  bool stopped = true;
  uint32_t fdebug = 0;
  uint32_t txStall = 0;
  uint32_t rxStall = 0;
  uint32_t inputSyncBypass = 0;
  uint32_t irq = 0;
  uint32_t pinValues = 0;
  uint32_t pinDirections = 0;
  uint32_t oldPinValues = 0;
  uint32_t oldPinDirections = 0;

  uint32_t irq0IntEnable = 0;
  uint32_t irq0IntForce = 0;
  uint32_t irq1IntEnable = 0;
  uint32_t irq1IntForce = 0;

  /**
   * `run()`. In TS it steps 1000 cycles and re-arms itself with setTimeout;
   * there is no event loop here, so the default (set in the constructor) runs
   * one batch of up to 1000 steps. Hosts that step PIO themselves replace it,
   * exactly as test/emu/rp2040emu.mjs does (`pio.run = () => {}`).
   */
  std::function<void()> run;

  RPPIO(RP2040 &rp2040, const std::string &name, uint32_t firstIrq, uint32_t index);

  uint32_t intRaw() const;
  uint32_t irq0IntStatus() const;
  uint32_t irq1IntStatus() const;

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

  void pinValuesChanged(uint32_t value, uint32_t firstPin, uint32_t count);
  void pinDirectionsChanged(uint32_t value, uint32_t firstPin, uint32_t count);
  void checkInterrupts();
  void irqUpdated();
  void checkChangedPins();
  void step();
  void stop();

  // `private runTimer: NodeJS.Timeout | null` has no native counterpart.
};

}  // namespace rp2040js
