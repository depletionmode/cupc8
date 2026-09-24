// Port of rp2040js src/cortex-m0-core.ts (with the cupc8 dual-core patch:
// waitingForEvent, SEV -> rp2040.sendEvent()).
#pragma once

#include <array>
#include <cstdint>
#include <functional>

#include "utils/js.h"

namespace rp2040js {

class RP2040;
class Logger;

/* eslint-disable @typescript-eslint/no-unused-vars */
constexpr uint32_t SYSM_MSP = 8;
constexpr uint32_t SYSM_PSP = 9;
constexpr uint32_t SYSM_PRIMASK = 16;
constexpr uint32_t SYSM_CONTROL = 20;

enum class ExecutionMode {
  Mode_Thread,
  Mode_Handler,
};

enum class StackPointerBank {
  SPmain,
  SPprocess,
};

class CortexM0Core {
 public:
  std::array<uint32_t, 16> registers{};  // `new Uint32Array(16)`
  uint32_t bankedSP = 0;
  /** A JS number in TS; integral, so a double is exact (and what the rule says). */
  double cycles = 0;

  bool eventRegistered = false;
  bool waiting = false;
  bool waitingForEvent = false;

  // APSR fields
  bool N = false;
  bool C = false;
  bool Z = false;
  bool V = false;

  // How many bytes to rewind the last break instruction
  uint32_t breakRewind = 0;

  // PRIMASK fields
  bool PM = false;

  // CONTROL fields
  StackPointerBank SPSEL = StackPointerBank::SPmain;
  bool nPRIV = false;

  ExecutionMode currentMode = ExecutionMode::Mode_Thread;
  uint32_t IPSR = 0;
  uint32_t interruptNMIMask = 0;
  uint32_t pendingInterrupts = 0;
  uint32_t enabledInterrupts = 0;
  std::array<uint32_t, 4> interruptPriorities = {0xffffffff, 0x0, 0x0, 0x0};
  bool pendingNMI = false;
  bool pendingPendSV = false;
  bool pendingSVCall = false;
  bool pendingSystick = false;
  bool interruptsUpdated = false;
  uint32_t VTOR = 0;
  uint32_t SHPR2 = 0;
  uint32_t SHPR3 = 0;

  /** Hook to listen for function calls - branch-link (BL/BLX) instructions */
  std::function<void(CortexM0Core &core, bool blx)> blTaken = [](CortexM0Core &, bool) {};

  /**
   * Not in TS. The JS test harness (test/emu/rp2040emu.mjs, --core1-slow)
   * replaces `core1.executeInstruction` on the instance; C++ cannot, so when
   * this is set RP2040::step() calls it instead of executeInstruction(), and it
   * calls executeInstruction() itself for the real instruction.
   */
  std::function<uint32_t()> executeInstructionOverride;

  RP2040 &rp2040;

  explicit CortexM0Core(RP2040 &rp2040);
  CortexM0Core(const CortexM0Core &) = delete;
  CortexM0Core &operator=(const CortexM0Core &) = delete;

  Logger &logger();

  void reset();

  uint32_t SP() const { return registers[13]; }
  void setSP(uint32_t value) { registers[13] = value & ~0x3u; }

  uint32_t LR() const { return registers[14]; }
  void setLR(uint32_t value) { registers[14] = value; }

  uint32_t PC() const { return registers[15]; }
  void setPC(uint32_t value) { registers[15] = value; }

  uint32_t APSR() const;
  void setAPSR(uint32_t value);

  uint32_t xPSR() const;
  void setXPSR(uint32_t value);

  bool checkCondition(uint32_t cond) const;

  uint32_t readUint32(uint32_t address);
  uint32_t readUint16(uint32_t address);
  uint32_t readUint8(uint32_t address);
  void writeUint32(uint32_t address, uint32_t value);
  void writeUint16(uint32_t address, uint32_t value);
  void writeUint8(uint32_t address, uint32_t value);

  void switchStack(StackPointerBank stack);

  uint32_t SPprocess() const;
  void setSPprocess(uint32_t value);

  uint32_t SPmain() const;
  void setSPmain(uint32_t value);

  void exceptionEntry(uint32_t exceptionNumber);
  void exceptionReturn(uint32_t excReturn);

  uint32_t pendSVPriority() const;
  uint32_t svCallPriority() const;
  uint32_t systickPriority() const;

  /** -3 (reset) .. 4 (LOWEST_PRIORITY) */
  int32_t exceptionPriority(uint32_t n) const;

  uint32_t vectPending() const;

  void setInterrupt(uint32_t irq, bool value) {
    // the TS below, with its common cases inline: an interrupt that is
    // already pending stays so, and clearing one only clears its bit
    const uint32_t irqBit = static_cast<uint32_t>(jsShl(1, irq));
    if (!value) {
      pendingInterrupts &= ~irqBit;
    } else if (!(pendingInterrupts & irqBit)) {
      raiseInterrupt(irqBit);
    }
  }
  /** setInterrupt(irq, true) for an interrupt that is not pending */
  void raiseInterrupt(uint32_t irqBit);
  bool checkForInterrupts();

  uint32_t readSpecialRegister(uint32_t sysm);
  void writeSpecialRegister(uint32_t sysm, uint32_t value);

  void BXWritePC(uint32_t address);

  uint32_t cyclesIO(uint32_t addr, bool write = false) const;

  /** One instruction; returns deltaCycles (and adds it to `cycles`). */
  uint32_t executeInstruction();

 private:
  // JS arithmetic on 32-bit values that can overflow 32 bits (e.g.
  // registers[Rdn] + carry == 2**32), hence double in and out, as in TS.
  double substractUpdateFlags(double minuend, double subtrahend);
  double addUpdateFlags(double addend1, double addend2);

  // Not in TS: this.readUint16(addr) / this.writeUint16(addr, v) where addr is the JS number
  // `reg + reg` or `reg + imm`, which can be >= 2**32; see the .cpp.
  uint32_t readUint16Number(double address);
  void writeUint16Number(double address, uint32_t value);
};

}  // namespace rp2040js
