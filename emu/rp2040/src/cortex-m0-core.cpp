// Port of rp2040js src/cortex-m0-core.ts (with the cupc8 dual-core patch:
// waitingForEvent, SEV -> rp2040.sendEvent()).
//
// JS number notes. Registers live in a Uint32Array, so every
// `this.registers[x] = <number>` is a ToUint32; here that is plain uint32_t
// wrap-around wherever the TS value is an integer that the store reduces mod
// 2**32 (sums of two registers, `SP - 4 * n`, `PC + imm`, int32 results of
// bitwise operators). Addresses the TS computes as `reg + reg` (up to 2**33)
// or `(pc & 0xfffffffc) + imm` (negative for pc >= 2**31) reach the bus as
// that JS number; rp2040.readUint32/writeUint32 and cyclesIO() do `>>> 0` on
// them, and readUint16/readUint8/writeUint16/writeUint8 end up at the same
// wrapped address (such a number is never inside flash/SRAM, so they take
// the aligned readUint32/writeUint32 path, whose `& 0xfffffffc` / `>>> 14`
// wrap it), so the uint32_t address here gives the same accesses. The two
// flag helpers take and return double: their operands can be 2**32
// (`reg + carry`) and substractUpdateFlags returns a negative number.
#include "cortex-m0-core.h"

#include <algorithm>
#include <string>

#include "rp2040.h"
#include "utils/js.h"
#include "utils/logging.h"

namespace rp2040js {

/* eslint-disable @typescript-eslint/no-unused-vars */
static constexpr uint32_t EXC_RESET = 1;
static constexpr uint32_t EXC_NMI = 2;
static constexpr uint32_t EXC_HARDFAULT = 3;
static constexpr uint32_t EXC_SVCALL = 11;
static constexpr uint32_t EXC_PENDSV = 14;
static constexpr uint32_t EXC_SYSTICK = 15;

static constexpr uint32_t SYSM_APSR = 0;
[[maybe_unused]] static constexpr uint32_t SYSM_IAPSR = 1;
[[maybe_unused]] static constexpr uint32_t SYSM_EAPSR = 2;
static constexpr uint32_t SYSM_XPSR = 3;
static constexpr uint32_t SYSM_IPSR = 5;
[[maybe_unused]] static constexpr uint32_t SYSM_EPSR = 6;
[[maybe_unused]] static constexpr uint32_t SYSM_IEPSR = 7;
// SYSM_MSP, SYSM_PSP, SYSM_PRIMASK, SYSM_CONTROL are exported: see the header.

/* eslint-enable @typescript-eslint/no-unused-vars */

// Lowest possible exception priority
static constexpr int32_t LOWEST_PRIORITY = 4;

static int32_t signExtend8(uint32_t value) {
  return jsSar(jsShl(static_cast<int32_t>(value), 24), 24);
}

static int32_t signExtend16(uint32_t value) {
  return jsSar(jsShl(static_cast<int32_t>(value), 16), 16);
}

static constexpr uint32_t spRegister = 13;
static constexpr uint32_t pcRegister = 15;

static const char *const LOG_NAME = "CortexM0Core";

CortexM0Core::CortexM0Core(RP2040 &rp2040) : rp2040(rp2040) {
  setSP(0xfffffffc);
  bankedSP = 0xfffffffc;
}

Logger &CortexM0Core::logger() { return *rp2040.logger; }

void CortexM0Core::reset() {
  setSP(rp2040.readUint32(VTOR));
  setPC(rp2040.readUint32(VTOR + 4) & 0xfffffffe);
  cycles = 0;
}

uint32_t CortexM0Core::APSR() const {
  return (N ? 0x80000000 : 0) | (Z ? 0x40000000 : 0) | (C ? 0x20000000 : 0) |
         (V ? 0x10000000 : 0);
}

void CortexM0Core::setAPSR(uint32_t value) {
  N = !!(value & 0x80000000);
  Z = !!(value & 0x40000000);
  C = !!(value & 0x20000000);
  V = !!(value & 0x10000000);
}

uint32_t CortexM0Core::xPSR() const { return APSR() | IPSR | (1 << 24); }

void CortexM0Core::setXPSR(uint32_t value) {
  setAPSR(value);
  IPSR = value & 0x3f;
}

bool CortexM0Core::checkCondition(uint32_t cond) const {
  // Evaluate base condition.
  bool result = false;
  switch (cond >> 1) {
    case 0b000:
      result = Z;
      break;
    case 0b001:
      result = C;
      break;
    case 0b010:
      result = N;
      break;
    case 0b011:
      result = V;
      break;
    case 0b100:
      result = C && !Z;
      break;
    case 0b101:
      result = N == V;
      break;
    case 0b110:
      result = N == V && !Z;
      break;
    case 0b111:
      result = true;
      break;
  }
  return (cond & 0b1) && cond != 0b1111 ? !result : result;
}

uint32_t CortexM0Core::readUint32(uint32_t address) { return rp2040.readUint32(address); }

uint32_t CortexM0Core::readUint16(uint32_t address) { return rp2040.readUint16(address); }

uint32_t CortexM0Core::readUint8(uint32_t address) { return rp2040.readUint8(address); }

void CortexM0Core::writeUint32(uint32_t address, uint32_t value) {
  rp2040.writeUint32(address, value);
}

void CortexM0Core::writeUint16(uint32_t address, uint32_t value) {
  rp2040.writeUint16(address, value);
}

void CortexM0Core::writeUint8(uint32_t address, uint32_t value) {
  rp2040.writeUint8(address, value);
}

void CortexM0Core::switchStack(StackPointerBank stack) {
  if (SPSEL != stack) {
    const uint32_t temp = SP();
    setSP(bankedSP);
    bankedSP = temp;
    SPSEL = stack;
  }
}

uint32_t CortexM0Core::SPprocess() const {
  return SPSEL == StackPointerBank::SPprocess ? SP() : bankedSP;
}

void CortexM0Core::setSPprocess(uint32_t value) {
  if (SPSEL == StackPointerBank::SPprocess) {
    setSP(value);
  } else {
    bankedSP = value >> 0;
  }
}

uint32_t CortexM0Core::SPmain() const {
  return SPSEL == StackPointerBank::SPmain ? SP() : bankedSP;
}

void CortexM0Core::setSPmain(uint32_t value) {
  if (SPSEL == StackPointerBank::SPmain) {
    setSP(value);
  } else {
    bankedSP = value >> 0;
  }
}

void CortexM0Core::exceptionEntry(uint32_t exceptionNumber) {
  // PushStack:
  uint32_t framePtr = 0;
  uint32_t framePtrAlign = 0;
  if (SPSEL != StackPointerBank::SPmain && currentMode == ExecutionMode::Mode_Thread) {
    framePtrAlign = SPprocess() & 0b100 ? 1 : 0;
    // JS: `(SPprocess - 0x20) & ~0b100` is ToInt32 of a possibly negative number: the same bits
    setSPprocess((SPprocess() - 0x20) & ~0b100u);
    framePtr = SPprocess();
  } else {
    framePtrAlign = SPmain() & 0b100 ? 1 : 0;
    setSPmain((SPmain() - 0x20) & ~0b100u);
    framePtr = SPmain();
  }
  /* only the stack locations, not the store order, are architected */
  writeUint32(framePtr, registers[0]);
  writeUint32(framePtr + 0x4, registers[1]);
  writeUint32(framePtr + 0x8, registers[2]);
  writeUint32(framePtr + 0xc, registers[3]);
  writeUint32(framePtr + 0x10, registers[12]);
  writeUint32(framePtr + 0x14, LR());
  writeUint32(framePtr + 0x18, PC() & ~1u);  // ReturnAddress(ExceptionType);
  writeUint32(framePtr + 0x1c, (xPSR() & ~(1u << 9)) | (framePtrAlign << 9));
  if (currentMode == ExecutionMode::Mode_Handler) {
    setLR(0xfffffff1);
  } else {
    if (SPSEL == StackPointerBank::SPmain) {
      setLR(0xfffffff9);
    } else {
      setLR(0xfffffffd);
    }
  }
  // ExceptionTaken:
  currentMode = ExecutionMode::Mode_Handler;  // Enter Handler Mode, now Privileged
  IPSR = exceptionNumber;
  switchStack(StackPointerBank::SPmain);
  eventRegistered = true;
  const uint32_t vectorTable = VTOR;
  setPC(readUint32(vectorTable + 4 * exceptionNumber));
}

void CortexM0Core::exceptionReturn(uint32_t excReturn) {
  uint32_t framePtr = SPmain();
  switch (excReturn & 0xf) {
    case 0b0001:  // Return to Handler
      currentMode = ExecutionMode::Mode_Handler;
      switchStack(StackPointerBank::SPmain);
      break;
    case 0b1001:  // Return to Thread using Main stack
      currentMode = ExecutionMode::Mode_Thread;
      switchStack(StackPointerBank::SPmain);
      break;
    case 0b1101:  // Return to Thread using Process stack
      framePtr = SPprocess();
      currentMode = ExecutionMode::Mode_Thread;
      switchStack(StackPointerBank::SPprocess);
      break;
      // Assigning CurrentMode to Mode_Thread causes a drop in privilege
      // if CONTROL.nPRIV is set to 1
  }

  // PopStack:
  registers[0] = readUint32(framePtr);  // Stack accesses are performed as Unprivileged accesses if
  registers[1] = readUint32(framePtr + 0x4);  // CONTROL<0>=='1' && EXC_RETURN<3>=='1' Privileged otherwise
  registers[2] = readUint32(framePtr + 0x8);
  registers[3] = readUint32(framePtr + 0xc);
  registers[12] = readUint32(framePtr + 0x10);
  setLR(readUint32(framePtr + 0x14));
  setPC(readUint32(framePtr + 0x18));
  const uint32_t psr = readUint32(framePtr + 0x1c);

  const uint32_t framePtrAlign = psr & (1 << 9) ? 0b100 : 0;

  switch (excReturn & 0xf) {
    case 0b0001:  // Returning to Handler mode
      setSPmain((SPmain() + 0x20) | framePtrAlign);
      break;

    case 0b1001:  // Returning to Thread mode using Main stack
      setSPmain((SPmain() + 0x20) | framePtrAlign);
      break;

    case 0b1101:  // Returning to Thread mode using Process stack
      setSPprocess((SPprocess() + 0x20) | framePtrAlign);
      break;
  }

  setAPSR(psr & 0xf0000000);
  const bool forceThread = currentMode == ExecutionMode::Mode_Thread && nPRIV;
  IPSR = forceThread ? 0 : psr & 0x3f;
  interruptsUpdated = true;
  // Thumb bit should always be one! EPSR<24> = psr<24>; // Load valid EPSR bits from memory
  eventRegistered = true;
  // if CurrentMode == Mode_Thread && SCR.SLEEPONEXIT == '1' then
  // SleepOnExit(); // IMPLEMENTATION DEFINED
}

uint32_t CortexM0Core::pendSVPriority() const { return (SHPR3 >> 22) & 0x3; }

uint32_t CortexM0Core::svCallPriority() const { return SHPR2 >> 30; }

uint32_t CortexM0Core::systickPriority() const { return SHPR3 >> 30; }

int32_t CortexM0Core::exceptionPriority(uint32_t n) const {
  switch (n) {
    case EXC_RESET:
      return -3;
    case EXC_NMI:
      return -2;
    case EXC_HARDFAULT:
      return -1;
    case EXC_SVCALL:
      return static_cast<int32_t>(svCallPriority());
    case EXC_PENDSV:
      return static_cast<int32_t>(pendSVPriority());
    case EXC_SYSTICK:
      return static_cast<int32_t>(systickPriority());
    default: {
      if (n < 16) {
        return LOWEST_PRIORITY;
      }
      // n can be any IPSR value (MSR IPSR stores all 32 bits): `1 << intNum` takes intNum & 31
      const uint32_t intNum = n - 16;
      for (uint32_t priority = 0; priority < 4; priority++) {
        if (interruptPriorities[priority] & static_cast<uint32_t>(jsShl(1, intNum))) {
          return static_cast<int32_t>(priority);
        }
      }
      return LOWEST_PRIORITY;
    }
  }
}

uint32_t CortexM0Core::vectPending() const {
  if (pendingNMI) {
    return EXC_NMI;
  }
  const uint32_t svCallPriority = this->svCallPriority();
  const uint32_t systickPriority = this->systickPriority();
  const uint32_t pendSVPriority = this->pendSVPriority();
  const uint32_t pendingInterrupts = this->pendingInterrupts;
  for (uint32_t priority = 0; priority < static_cast<uint32_t>(LOWEST_PRIORITY); priority++) {
    const uint32_t levelInterrupts = pendingInterrupts & interruptPriorities[priority];
    if (pendingSVCall && priority == svCallPriority) {
      return EXC_SVCALL;
    }
    if (pendingPendSV && priority == pendSVPriority) {
      return EXC_PENDSV;
    }
    if (pendingSystick && priority == systickPriority) {
      return EXC_SYSTICK;
    }
    if (levelInterrupts) {
      for (uint32_t interruptNumber = 0; interruptNumber < 32; interruptNumber++) {
        if (levelInterrupts & (1u << interruptNumber)) {
          return 16 + interruptNumber;
        }
      }
    }
  }
  return 0;
}

void CortexM0Core::setInterrupt(uint32_t irq, bool value) {
  const uint32_t irqBit = static_cast<uint32_t>(jsShl(1, irq));
  if (value && !(pendingInterrupts & irqBit)) {
    pendingInterrupts |= irqBit;
    interruptsUpdated = true;
    if (waiting && checkForInterrupts()) {
      waiting = false;
      waitingForEvent = false;
    }
  } else if (!value) {
    pendingInterrupts &= ~irqBit;
  }
}

bool CortexM0Core::checkForInterrupts() {
  /* If we're waiting for an interrupt (i.e. WFI/WFE), the ARM says:
     > If PRIMASK.PM is set to 1, an asynchronous exception that has a higher group priority than any
     > active exception results in a WFI instruction exit. If the group priority of the exception is less than or
     > equal to the execution group priority, the exception is ignored.
  */
  const int32_t currentPriority =
      waiting ? PM ? exceptionPriority(IPSR) : LOWEST_PRIORITY
              : std::min(exceptionPriority(IPSR), PM ? 0 : LOWEST_PRIORITY);
  const uint32_t interruptSet = pendingInterrupts & enabledInterrupts;
  const int32_t svCallPriority = static_cast<int32_t>(this->svCallPriority());
  const int32_t systickPriority = static_cast<int32_t>(this->systickPriority());
  const int32_t pendSVPriority = static_cast<int32_t>(this->pendSVPriority());
  if (pendingNMI) {
    pendingNMI = false;
    exceptionEntry(EXC_NMI);
    return true;
  }
  for (int32_t priority = 0; priority < currentPriority; priority++) {
    const uint32_t levelInterrupts = interruptSet & interruptPriorities[priority];
    if (pendingSVCall && priority == svCallPriority) {
      pendingSVCall = false;
      exceptionEntry(EXC_SVCALL);
      return true;
    }
    if (pendingPendSV && priority == pendSVPriority) {
      pendingPendSV = false;
      exceptionEntry(EXC_PENDSV);
      return true;
    }
    if (pendingSystick && priority == systickPriority) {
      pendingSystick = false;
      exceptionEntry(EXC_SYSTICK);
      return true;
    }
    if (levelInterrupts) {
      for (uint32_t interruptNumber = 0; interruptNumber < 32; interruptNumber++) {
        if (levelInterrupts & (1u << interruptNumber)) {
          if (interruptNumber > MAX_HARDWARE_IRQ) {
            pendingInterrupts &= ~(1u << interruptNumber);
          }
          exceptionEntry(16 + interruptNumber);
          return true;
        }
      }
    }
  }
  interruptsUpdated = false;
  return false;
}

uint32_t CortexM0Core::readSpecialRegister(uint32_t sysm) {
  switch (sysm) {
    case SYSM_APSR:
      return APSR();

    case SYSM_XPSR:
      return xPSR();

    case SYSM_IPSR:
      return IPSR;

    case SYSM_PRIMASK:
      return PM ? 1 : 0;

    case SYSM_MSP:
      return SPmain();

    case SYSM_PSP:
      return SPprocess();

    case SYSM_CONTROL:
      return (SPSEL == StackPointerBank::SPprocess ? 2 : 0) | (nPRIV ? 1 : 0);

    default:
      logger().warn(LOG_NAME, "MRS with unimplemented SYSm value: " + std::to_string(sysm));
      return 0;
  }
}

void CortexM0Core::writeSpecialRegister(uint32_t sysm, uint32_t value) {
  switch (sysm) {
    case SYSM_APSR:
      setAPSR(value);
      break;

    case SYSM_XPSR:
      setXPSR(value);
      break;

    case SYSM_IPSR:
      IPSR = value;
      break;

    case SYSM_PRIMASK:
      PM = !!(value & 1);
      interruptsUpdated = true;
      break;

    case SYSM_MSP:
      setSPmain(value);
      break;

    case SYSM_PSP:
      setSPprocess(value);
      break;

    case SYSM_CONTROL:
      nPRIV = !!(value & 1);
      if (currentMode == ExecutionMode::Mode_Thread) {
        switchStack(value & 2 ? StackPointerBank::SPprocess : StackPointerBank::SPmain);
      }
      break;

    default:
      // (sic: "MRS" in the TS too)
      logger().warn(LOG_NAME, "MRS with unimplemented SYSm value: " + std::to_string(sysm));
      return;
  }
}

void CortexM0Core::BXWritePC(uint32_t address) {
  if (currentMode == ExecutionMode::Mode_Handler && address >> 28 == 0b1111) {
    exceptionReturn(address & 0x0fffffff);
  } else {
    setPC(address & ~1u);
  }
}

double CortexM0Core::substractUpdateFlags(double minuend, double subtrahend) {
  // JS: result may be negative (or subtrahend 2**32, from `reg + (1 - C)`); the bitwise tests
  // see ToInt32 of each operand, the `>=` compares the unconverted numbers.
  const double result = minuend - subtrahend;
  N = !!(toUint32(result) & 0x80000000);
  Z = toUint32(result) == 0;
  C = minuend >= subtrahend;
  V = (!!(toUint32(result) & 0x80000000) && !(toUint32(minuend) & 0x80000000) &&
       !!(toUint32(subtrahend) & 0x80000000)) ||
      (!(toUint32(result) & 0x80000000) && !!(toUint32(minuend) & 0x80000000) &&
       !(toUint32(subtrahend) & 0x80000000));
  // unmasked (possibly negative): the caller's Uint32Array store makes it 32-bit
  return result;
}

double CortexM0Core::addUpdateFlags(double addend1, double addend2) {
  // JS: addend2 may be 2**32 (`reg + C`), the sum up to 2**33
  const double unsignedSum = toUint32(addend1 + addend2);
  const double signedSum =
      static_cast<double>(toInt32(addend1)) + static_cast<double>(toInt32(addend2));
  const double result = addend1 + addend2;
  N = !!(toUint32(result) & 0x80000000);
  Z = toUint32(result) == 0;
  C = result == unsignedSum ? false : true;
  V = static_cast<double>(toInt32(result)) == signedSum ? false : true;
  // `result & 0xffffffff` is an int32
  return toInt32(result);
}

uint32_t CortexM0Core::cyclesIO(uint32_t addr, bool write) const {
  addr = addr >> 0;
  if (addr >= SIO_START_ADDRESS && addr < SIO_START_ADDRESS + 0x10000000) {
    return 0;
  }
  if (addr >= APB_START_ADDRESS && addr < APB_START_ADDRESS + 0x10000000) {
    return write ? 4 : 3;
  }
  return 1;
}

uint32_t CortexM0Core::executeInstruction() {
  if (interruptsUpdated) {
    if (checkForInterrupts()) {
      waiting = false;
      waitingForEvent = false;
    }
  }
  // ARM Thumb instruction encoding - 16 bits / 2 bytes
  // JS: `this.PC & ~1` is an int32 (negative for PC >= 2**31); only its hex in the warning shows it
  const uint32_t opcodePC = PC() & ~1u;  // ensure no LSB set PC are executed
  const uint32_t opcode = readUint16(opcodePC);
  const bool wideInstruction = opcode >> 12 == 0b1111 || opcode >> 11 == 0b11101;
  const uint32_t opcode2 = wideInstruction ? readUint16(opcodePC + 2) : 0;
  registers[15] += 2;
  uint32_t deltaCycles = 1;
  // ADCS
  if (opcode >> 6 == 0b0100000101) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    // JS: registers[Rdn] + 1 can be 2**32
    registers[Rdn] = toUint32(addUpdateFlags(registers[Rm], static_cast<double>(registers[Rdn]) +
                                                                (C ? 1 : 0)));
  }
  // ADD (register = SP plus immediate)
  else if (opcode >> 11 == 0b10101) {
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t Rd = (opcode >> 8) & 0x7;
    registers[Rd] = SP() + (imm8 << 2);
  }
  // ADD (SP plus immediate)
  else if (opcode >> 7 == 0b101100000) {
    const uint32_t imm32 = (opcode & 0x7f) << 2;
    setSP(SP() + imm32);
  }
  // ADDS (Encoding T1)
  else if (opcode >> 9 == 0b0001110) {
    const uint32_t imm3 = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = toUint32(addUpdateFlags(registers[Rn], imm3));
  }
  // ADDS (Encoding T2)
  else if (opcode >> 11 == 0b00110) {
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t Rdn = (opcode >> 8) & 0x7;
    registers[Rdn] = toUint32(addUpdateFlags(registers[Rdn], imm8));
  }
  // ADDS (register)
  else if (opcode >> 9 == 0b0001100) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = toUint32(addUpdateFlags(registers[Rn], registers[Rm]));
  }
  // ADD (register)
  else if (opcode >> 8 == 0b01000100) {
    const uint32_t Rm = (opcode >> 3) & 0xf;
    const uint32_t Rdn = ((opcode & 0x80) >> 4) | (opcode & 0x7);
    const uint32_t leftValue = Rdn == pcRegister ? PC() + 2 : registers[Rdn];
    const uint32_t rightValue = registers[Rm];
    // JS: up to 2**33; every use below is ToInt32 / ToUint32 of it
    const uint32_t result = leftValue + rightValue;
    if (Rdn != spRegister && Rdn != pcRegister) {
      registers[Rdn] = result;
    } else if (Rdn == pcRegister) {
      registers[Rdn] = result & ~0x1u;
      deltaCycles++;
    } else if (Rdn == spRegister) {
      registers[Rdn] = result & ~0x3u;
    }
  }
  // ADR
  else if (opcode >> 11 == 0b10100) {
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t Rd = (opcode >> 8) & 0x7;
    registers[Rd] = (opcodePC & 0xfffffffc) + 4 + (imm8 << 2);
  }
  // ANDS (Encoding T2)
  else if (opcode >> 6 == 0b0100000000) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t result = registers[Rdn] & registers[Rm];
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = (result & 0xffffffff) == 0;
  }
  // ASRS (immediate)
  else if (opcode >> 11 == 0b00010) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    const uint32_t shiftN = imm5 ? imm5 : 32;
    // JS: `input >> shiftN` sign-extends ToInt32(input)
    const uint32_t result =
        static_cast<uint32_t>(shiftN < 32 ? jsSar(static_cast<int32_t>(input), shiftN)
                                          : jsSar(static_cast<int32_t>(input & 0x80000000), 31));
    registers[Rd] = result;
    N = !!(result & 0x80000000);
    Z = (result & 0xffffffff) == 0;
    C = input & static_cast<uint32_t>(jsShl(1, shiftN - 1)) ? true : false;
  }
  // ASRS (register)
  else if (opcode >> 6 == 0b0100000100) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t input = registers[Rdn];
    const uint32_t shiftN = (registers[Rm] & 0xff) < 32 ? registers[Rm] & 0xff : 32;
    const uint32_t result =
        static_cast<uint32_t>(shiftN < 32 ? jsSar(static_cast<int32_t>(input), shiftN)
                                          : jsSar(static_cast<int32_t>(input & 0x80000000), 31));
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = (result & 0xffffffff) == 0;
    // TS bug, kept: for shiftN == 0 this is `1 << -1` == 1 << 31, so C = input bit 31
    // (the architecture leaves C unchanged)
    C = input & static_cast<uint32_t>(jsShl(1, shiftN - 1)) ? true : false;
  }
  // B (with cond)
  else if (opcode >> 12 == 0b1101 && ((opcode >> 9) & 0x7) != 0b111) {
    int32_t imm8 = static_cast<int32_t>((opcode & 0xff) << 1);
    const uint32_t cond = (opcode >> 8) & 0xf;
    if (imm8 & (1 << 8)) {
      imm8 = (imm8 & 0x1ff) - 0x200;
    }
    if (checkCondition(cond)) {
      registers[15] += static_cast<uint32_t>(imm8 + 2);
      deltaCycles++;
    }
  }
  // B
  else if (opcode >> 11 == 0b11100) {
    int32_t imm11 = static_cast<int32_t>((opcode & 0x7ff) << 1);
    if (imm11 & (1 << 11)) {
      imm11 = (imm11 & 0x7ff) - 0x800;
    }
    registers[15] += static_cast<uint32_t>(imm11 + 2);
    deltaCycles++;
  }
  // BICS
  else if (opcode >> 6 == 0b0100001110) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t result = (registers[Rdn] &= ~registers[Rm]);
    N = !!(result & 0x80000000);
    Z = result == 0;
  }
  // BKPT
  else if (opcode >> 8 == 0b10111110) {
    const uint32_t imm8 = opcode & 0xff;
    breakRewind = 2;
    rp2040.onBreak(imm8);
  }
  // BL
  else if (opcode >> 11 == 0b11110 && opcode2 >> 14 == 0b11 && ((opcode2 >> 12) & 0x1) == 1) {
    const uint32_t imm11 = opcode2 & 0x7ff;
    const uint32_t J2 = (opcode2 >> 11) & 0x1;
    const uint32_t J1 = (opcode2 >> 13) & 0x1;
    const uint32_t imm10 = opcode & 0x3ff;
    const uint32_t S = (opcode >> 10) & 0x1;
    const uint32_t I1 = 1 - (S ^ J1);
    const uint32_t I2 = 1 - (S ^ J2);
    const uint32_t imm32 =
        ((S ? 0b11111111u : 0) << 24) | ((I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1));
    setLR((PC() + 2) | 0x1);
    registers[15] += 2 + imm32;
    deltaCycles += 2;
    blTaken(*this, false);
  }
  // BLX
  else if (opcode >> 7 == 0b010001111 && (opcode & 0x7) == 0) {
    const uint32_t Rm = (opcode >> 3) & 0xf;
    setLR(PC() | 0x1);
    setPC(registers[Rm] & ~1u);
    deltaCycles++;
    blTaken(*this, true);
  }
  // BX
  else if (opcode >> 7 == 0b010001110 && (opcode & 0x7) == 0) {
    const uint32_t Rm = (opcode >> 3) & 0xf;
    BXWritePC(registers[Rm]);
    deltaCycles++;
  }
  // CMN (register)
  else if (opcode >> 6 == 0b0100001011) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rn = opcode & 0x7;
    addUpdateFlags(registers[Rn], registers[Rm]);
  }
  // CMP immediate
  else if (opcode >> 11 == 0b00101) {
    const uint32_t Rn = (opcode >> 8) & 0x7;
    const uint32_t imm8 = opcode & 0xff;
    substractUpdateFlags(registers[Rn], imm8);
  }
  // CMP (register)
  else if (opcode >> 6 == 0b0100001010) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rn = opcode & 0x7;
    substractUpdateFlags(registers[Rn], registers[Rm]);
  }
  // CMP (register) encoding T2
  else if (opcode >> 8 == 0b01000101) {
    const uint32_t Rm = (opcode >> 3) & 0xf;
    const uint32_t Rn = ((opcode >> 4) & 0x8) | (opcode & 0x7);
    substractUpdateFlags(registers[Rn], registers[Rm]);
  }
  // CPSID i
  else if (opcode == 0xb672) {
    PM = true;
  }
  // CPSIE i
  else if (opcode == 0xb662) {
    PM = false;
    interruptsUpdated = true;
  }
  // DMB SY
  else if (opcode == 0xf3bf && (opcode2 & 0xfff0) == 0x8f50) {
    registers[15] += 2;
    deltaCycles += 2;
  }
  // DSB SY
  else if (opcode == 0xf3bf && (opcode2 & 0xfff0) == 0x8f40) {
    registers[15] += 2;
    deltaCycles += 2;
  }
  // EORS
  else if (opcode >> 6 == 0b0100000001) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t result = registers[Rm] ^ registers[Rdn];
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
  }
  // ISB SY
  else if (opcode == 0xf3bf && (opcode2 & 0xfff0) == 0x8f60) {
    registers[15] += 2;
    deltaCycles += 2;
  }
  // LDMIA
  else if (opcode >> 11 == 0b11001) {
    const uint32_t Rn = (opcode >> 8) & 0x7;
    const uint32_t registers_ = opcode & 0xff;
    uint32_t address = registers[Rn];
    for (uint32_t i = 0; i < 8; i++) {
      if (registers_ & (1u << i)) {
        registers[i] = readUint32(address);
        address += 4;
        deltaCycles++;
      }
    }
    // Write back
    if (!(registers_ & (1u << Rn))) {
      registers[Rn] = address;
    }
  }
  // LDR (immediate)
  else if (opcode >> 11 == 0b01101) {
    const uint32_t imm5 = ((opcode >> 6) & 0x1f) << 2;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rn] + imm5;
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint32(addr);
  }
  // LDR (sp + immediate)
  else if (opcode >> 11 == 0b10011) {
    const uint32_t Rt = (opcode >> 8) & 0x7;
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t addr = SP() + (imm8 << 2);
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint32(addr);
  }
  // LDR (literal)
  else if (opcode >> 11 == 0b01001) {
    const uint32_t imm8 = (opcode & 0xff) << 2;
    const uint32_t Rt = (opcode >> 8) & 7;
    const uint32_t nextPC = PC() + 2;
    const uint32_t addr = (nextPC & 0xfffffffc) + imm8;
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint32(addr);
  }
  // LDR (register)
  else if (opcode >> 9 == 0b0101100) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint32(addr);
  }
  // LDRB (immediate)
  else if (opcode >> 11 == 0b01111) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rn] + imm5;
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint8(addr);
  }
  // LDRB (register)
  else if (opcode >> 9 == 0b0101110) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint8(addr);
  }
  // LDRH (immediate)
  else if (opcode >> 11 == 0b10001) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rn] + (imm5 << 1);
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint16(addr);
  }
  // LDRH (register)
  else if (opcode >> 9 == 0b0101101) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(addr);
    registers[Rt] = readUint16(addr);
  }
  // LDRSB
  else if (opcode >> 9 == 0b0101011) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(addr);
    registers[Rt] = static_cast<uint32_t>(signExtend8(readUint8(addr)));
  }
  // LDRSH
  else if (opcode >> 9 == 0b0101111) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t addr = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(addr);
    registers[Rt] = static_cast<uint32_t>(signExtend16(readUint16(addr)));
  }
  // LSLS (immediate)
  else if (opcode >> 11 == 0b00000) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    const uint32_t result = static_cast<uint32_t>(jsShl(static_cast<int32_t>(input), imm5));
    registers[Rd] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
    C = imm5 ? !!(input & static_cast<uint32_t>(jsShl(1, 32 - imm5))) : C;
  }
  // LSLS (register)
  else if (opcode >> 6 == 0b0100000010) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t input = registers[Rdn];
    const uint32_t shiftCount = registers[Rm] & 0xff;
    const uint32_t result =
        shiftCount >= 32 ? 0 : static_cast<uint32_t>(jsShl(static_cast<int32_t>(input), shiftCount));
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
    // TS bug, kept: for shiftCount > 32, `1 << (32 - shiftCount)` takes the count mod 32,
    // so C is some bit of input instead of 0
    C = shiftCount ? !!(input & static_cast<uint32_t>(jsShl(1, 32 - shiftCount))) : C;
  }
  // LSRS (immediate)
  else if (opcode >> 11 == 0b00001) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    const uint32_t result = imm5 ? input >> imm5 : 0;
    registers[Rd] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
    C = !!((input >> (imm5 ? imm5 - 1 : 31)) & 0x1);
  }
  // LSRS (register)
  else if (opcode >> 6 == 0b0100000011) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t shiftAmount = registers[Rm] & 0xff;
    const uint32_t input = registers[Rdn];
    const uint32_t result = shiftAmount < 32 ? input >> shiftAmount : 0;
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
    // TS bug, kept: for shiftAmount == 0 this is `input >>> -1` == input >>> 31, so C = input
    // bit 31 (the architecture leaves C unchanged)
    C = shiftAmount <= 32 ? !!(jsShr(input, shiftAmount - 1) & 0x1) : false;
  }
  // MOV
  else if (opcode >> 8 == 0b01000110) {
    const uint32_t Rm = (opcode >> 3) & 0xf;
    const uint32_t Rd = ((opcode >> 4) & 0x8) | (opcode & 0x7);
    uint32_t value = Rm == pcRegister ? PC() + 2 : registers[Rm];
    if (Rd == pcRegister) {
      deltaCycles++;
      value &= ~1u;
    } else if (Rd == spRegister) {
      value &= ~3u;
    }
    registers[Rd] = value;
  }
  // MOVS
  else if (opcode >> 11 == 0b00100) {
    const uint32_t value = opcode & 0xff;
    const uint32_t Rd = (opcode >> 8) & 7;
    registers[Rd] = value;
    N = !!(value & 0x80000000);
    Z = value == 0;
  }
  // MRS
  else if (opcode == 0b1111001111101111 && opcode2 >> 12 == 0b1000) {
    const uint32_t SYSm = opcode2 & 0xff;
    const uint32_t Rd = (opcode2 >> 8) & 0xf;
    registers[Rd] = readSpecialRegister(SYSm);
    registers[15] += 2;
    deltaCycles += 2;
  }
  // MSR
  else if (opcode >> 4 == 0b111100111000 && opcode2 >> 8 == 0b10001000) {
    const uint32_t SYSm = opcode2 & 0xff;
    const uint32_t Rn = opcode & 0xf;
    writeSpecialRegister(SYSm, registers[Rn]);
    registers[15] += 2;
    deltaCycles += 2;
  }
  // MULS
  else if (opcode >> 6 == 0b0100001101) {
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rdm = opcode & 0x7;
    // Math.imul: the low 32 bits of the product
    const uint32_t result = registers[Rn] * registers[Rdm];
    registers[Rdm] = result;
    N = !!(result & 0x80000000);
    Z = (result & 0xffffffff) == 0;
  }
  // MVNS
  else if (opcode >> 6 == 0b0100001111) {
    const uint32_t Rm = (opcode >> 3) & 7;
    const uint32_t Rd = opcode & 7;
    const uint32_t result = ~registers[Rm];
    registers[Rd] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
  }
  // ORRS (Encoding T2)
  else if (opcode >> 6 == 0b0100001100) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t result = registers[Rdn] | registers[Rm];
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = (result & 0xffffffff) == 0;
  }
  // POP
  else if (opcode >> 9 == 0b1011110) {
    const uint32_t P = (opcode >> 8) & 1;
    uint32_t address = SP();
    for (uint32_t i = 0; i <= 7; i++) {
      if (opcode & (1u << i)) {
        registers[i] = readUint32(address);
        address += 4;
        deltaCycles++;
      }
    }
    if (P) {
      setSP(address + 4);
      BXWritePC(readUint32(address));
      deltaCycles += 2;
    } else {
      setSP(address);
    }
  }
  // PUSH
  else if (opcode >> 9 == 0b1011010) {
    uint32_t bitCount = 0;
    for (uint32_t i = 0; i <= 8; i++) {
      if (opcode & (1u << i)) {
        bitCount++;
      }
    }
    uint32_t address = SP() - 4 * bitCount;
    for (uint32_t i = 0; i <= 7; i++) {
      if (opcode & (1u << i)) {
        writeUint32(address, registers[i]);
        deltaCycles++;
        address += 4;
      }
    }
    if (opcode & (1u << 8)) {
      writeUint32(address, registers[14]);
    }
    setSP(SP() - 4 * bitCount);
  }
  // REV
  else if (opcode >> 6 == 0b1011101000) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    registers[Rd] = ((input & 0xff) << 24) | (((input >> 8) & 0xff) << 16) |
                    (((input >> 16) & 0xff) << 8) | ((input >> 24) & 0xff);
  }
  // REV16
  else if (opcode >> 6 == 0b1011101001) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    registers[Rd] = (((input >> 16) & 0xff) << 24) | (((input >> 24) & 0xff) << 16) |
                    ((input & 0xff) << 8) | ((input >> 8) & 0xff);
  }
  // REVSH
  else if (opcode >> 6 == 0b1011101011) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    const uint32_t input = registers[Rm];
    registers[Rd] = static_cast<uint32_t>(signExtend16(((input & 0xff) << 8) | ((input >> 8) & 0xff)));
  }
  // ROR
  else if (opcode >> 6 == 0b0100000111) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    const uint32_t input = registers[Rdn];
    const uint32_t shift = (registers[Rm] & 0xff) % 32;
    // shift == 0: `input << 32` is `input << 0`
    const uint32_t result =
        jsShr(input, shift) | static_cast<uint32_t>(jsShl(static_cast<int32_t>(input), 32 - shift));
    registers[Rdn] = result;
    N = !!(result & 0x80000000);
    Z = result == 0;
    // TS bug, kept: C is set from the result even when (Rm & 0xff) == 0 (should be unchanged)
    C = !!(result & 0x80000000);
  }
  // NEGS / RSBS
  else if (opcode >> 6 == 0b0100001001) {
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = toUint32(substractUpdateFlags(0, registers[Rn]));
  }
  // NOP
  else if (opcode == 0b1011111100000000) {
    // Do nothing!
  }
  // SBCS (Encoding T1)
  else if (opcode >> 6 == 0b0100000110) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rdn = opcode & 0x7;
    // JS: registers[Rm] + 1 can be 2**32
    registers[Rdn] = toUint32(substractUpdateFlags(
        registers[Rdn], static_cast<double>(registers[Rm]) + (1 - (C ? 1 : 0))));
  }
  // SEV
  else if (opcode == 0b1011111101000000) {
    rp2040.sendEvent();
  }
  // STMIA
  else if (opcode >> 11 == 0b11000) {
    const uint32_t Rn = (opcode >> 8) & 0x7;
    const uint32_t registers_ = opcode & 0xff;
    uint32_t address = registers[Rn];
    for (uint32_t i = 0; i < 8; i++) {
      if (registers_ & (1u << i)) {
        writeUint32(address, registers[i]);
        address += 4;
        deltaCycles++;
      }
    }
    // Write back
    if (!(registers_ & (1u << Rn))) {
      registers[Rn] = address;
    }
  }
  // STR (immediate)
  else if (opcode >> 11 == 0b01100) {
    const uint32_t imm5 = ((opcode >> 6) & 0x1f) << 2;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rn] + imm5;
    deltaCycles += cyclesIO(address, true);
    writeUint32(address, registers[Rt]);
  }
  // STR (sp + immediate)
  else if (opcode >> 11 == 0b10010) {
    const uint32_t Rt = (opcode >> 8) & 0x7;
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t address = SP() + (imm8 << 2);
    deltaCycles += cyclesIO(address, true);
    writeUint32(address, registers[Rt]);
  }
  // STR (register)
  else if (opcode >> 9 == 0b0101000) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(address, true);
    writeUint32(address, registers[Rt]);
  }
  // STRB (immediate)
  else if (opcode >> 11 == 0b01110) {
    const uint32_t imm5 = (opcode >> 6) & 0x1f;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rn] + imm5;
    deltaCycles += cyclesIO(address, true);
    writeUint8(address, registers[Rt]);
  }
  // STRB (register)
  else if (opcode >> 9 == 0b0101010) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(address, true);
    writeUint8(address, registers[Rt]);
  }
  // STRH (immediate)
  else if (opcode >> 11 == 0b10000) {
    const uint32_t imm5 = ((opcode >> 6) & 0x1f) << 1;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rn] + imm5;
    deltaCycles += cyclesIO(address, true);
    writeUint16(address, registers[Rt]);
  }
  // STRH (register)
  else if (opcode >> 9 == 0b0101001) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rt = opcode & 0x7;
    const uint32_t address = registers[Rm] + registers[Rn];
    deltaCycles += cyclesIO(address, true);
    writeUint16(address, registers[Rt]);
  }
  // SUB (SP minus immediate)
  else if (opcode >> 7 == 0b101100001) {
    const uint32_t imm32 = (opcode & 0x7f) << 2;
    setSP(SP() - imm32);
  }
  // SUBS (Encoding T1)
  else if (opcode >> 9 == 0b0001111) {
    const uint32_t imm3 = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = toUint32(substractUpdateFlags(registers[Rn], imm3));
  }
  // SUBS (Encoding T2)
  else if (opcode >> 11 == 0b00111) {
    const uint32_t imm8 = opcode & 0xff;
    const uint32_t Rdn = (opcode >> 8) & 0x7;
    registers[Rdn] = toUint32(substractUpdateFlags(registers[Rdn], imm8));
  }
  // SUBS (register)
  else if (opcode >> 9 == 0b0001101) {
    const uint32_t Rm = (opcode >> 6) & 0x7;
    const uint32_t Rn = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = toUint32(substractUpdateFlags(registers[Rn], registers[Rm]));
  }
  // SVC
  else if (opcode >> 8 == 0b11011111) {
    pendingSVCall = true;
    interruptsUpdated = true;
  }
  // SXTB
  else if (opcode >> 6 == 0b1011001001) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = static_cast<uint32_t>(signExtend8(registers[Rm]));
  }
  // SXTH
  else if (opcode >> 6 == 0b1011001000) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = static_cast<uint32_t>(signExtend16(registers[Rm]));
  }
  // TST
  else if (opcode >> 6 == 0b0100001000) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rn = opcode & 0x7;
    const uint32_t result = registers[Rn] & registers[Rm];
    N = !!(result & 0x80000000);
    Z = result == 0;
  }
  // UDF
  else if (opcode >> 8 == 0b11011110) {
    const uint32_t imm8 = opcode & 0xff;
    breakRewind = 2;
    rp2040.onBreak(imm8);
  }
  // UDF (Encoding T2)
  else if (opcode >> 4 == 0b111101111111 && opcode2 >> 12 == 0b1010) {
    const uint32_t imm4 = opcode & 0xf;
    const uint32_t imm12 = opcode2 & 0xfff;
    breakRewind = 4;
    rp2040.onBreak((imm4 << 12) | imm12);
    registers[15] += 2;
  }
  // UXTB
  else if (opcode >> 6 == 0b1011001011) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = registers[Rm] & 0xff;
  }
  // UXTH
  else if (opcode >> 6 == 0b1011001010) {
    const uint32_t Rm = (opcode >> 3) & 0x7;
    const uint32_t Rd = opcode & 0x7;
    registers[Rd] = registers[Rm] & 0xffff;
  }
  // WFE
  else if (opcode == 0b1011111100100000) {
    deltaCycles++;
    if (eventRegistered) {
      eventRegistered = false;
    } else {
      waiting = true;
      waitingForEvent = true;
    }
  }
  // WFI
  else if (opcode == 0b1011111100110000) {
    deltaCycles++;
    waiting = true;
  }
  // YIELD
  else if (opcode == 0b1011111100010000) {
    // do nothing for now. Wait for event!
    logger().info(LOG_NAME, "Yield");
  } else {
    // JS: opcodePC is an int32, so `.toString(16)` shows a '-' for PC >= 2**31
    logger().warn(LOG_NAME, "Warning: Instruction at " +
                                toHex(static_cast<double>(static_cast<int32_t>(opcodePC))) +
                                " is not implemented yet!");
    logger().warn(LOG_NAME, "Opcode: 0x" + toHex(opcode) + " (0x" + toHex(opcode2) + ")");
  }

  cycles += deltaCycles;
  return deltaCycles;
}

}  // namespace rp2040js
