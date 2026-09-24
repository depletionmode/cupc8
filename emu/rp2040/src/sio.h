// Port of rp2040js src/sio.ts (with the cupc8 dual-core patch: per-core
// divider and interpolators, inter-core FIFOs, CPUID).
#pragma once

#include <array>
#include <cstdint>
#include <deque>
#include <memory>

#include "interpolator.h"

namespace rp2040js {

class RP2040;

class RPSIO {
 public:
  uint32_t gpioValue = 0;
  uint32_t gpioOutputEnable = 0;
  uint32_t qspiGpioValue = 0;
  uint32_t qspiGpioOutputEnable = 0;
  /**
   * The divider keeps JS numbers: the quotient is a float division
   * (e.g. -3.5), truncated only when read onto the bus (toUint32).
   */
  double divDividend = 0;
  double divDivisor = 1;
  double divQuotient = 0;
  double divRemainder = 0;
  uint32_t divCSR = 0;
  uint32_t spinLock = 0;
  /** `interp0 = new Interpolator(0)`: points into banks[bank]; selectCore() swaps it. */
  Interpolator *interp0;
  Interpolator *interp1;

  /** fifo[n] is read by core n (written by the other core) */
  std::array<std::deque<uint32_t>, 2> fifo;

  explicit RPSIO(RP2040 &rp2040);
  RPSIO(const RPSIO &) = delete;
  RPSIO &operator=(const RPSIO &) = delete;

  /**
   * Make core `index`'s divider and interpolators the current ones. The swap
   * itself waits until the next SIO access (readUint32, writeUint32,
   * updateHardwareDivider: the only users of the banked fields), so that
   * RP2040::step() selecting core 1 and back for every core 1 instruction
   * costs nothing. Code outside sio.cpp that reads the banked public fields
   * directly must call selectCore and then flushSelect() first.
   */
  void selectCore(uint32_t index) { selected = index; }
  void flushSelect() { swapBank(selected); }

  void updateHardwareDivider(bool signed_);

  uint32_t readUint32(uint32_t offset);
  void writeUint32(uint32_t offset, uint32_t value);

 private:
  // each core has its own divider and interpolators; selectCore() swaps them in
  struct Bank {
    std::array<double, 5> div;
    std::unique_ptr<Interpolator> interp0;
    std::unique_ptr<Interpolator> interp1;
  };
  std::array<Bank, 2> banks;
  uint32_t bank = 0;      // the bank in the fields above
  uint32_t selected = 0;  // the bank selectCore() asked for
  void swapBank(uint32_t index);

  std::array<uint32_t, 2> fifoErr = {0, 0};  // bit 2 WOF, bit 3 ROE

  RP2040 &rp2040;

  uint32_t fifoStatus(uint32_t core) const;
  void updateFifoIrq();
};

}  // namespace rp2040js
