// Port of rp2040js src/peripherals/ppb.ts
//
// `rp2040.core` (the dual-core patch's getter: the core executing the
// current instruction, core 0 outside step()) is `rp2040.core()`.
#include "ppb.h"

#include "../irq.h"
#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

// Exported by ppb.ts (for its tests only); file-local here, see ppb.h.
static constexpr uint32_t CPUID = 0xd00;
static constexpr uint32_t ICSR = 0xd04;
static constexpr uint32_t VTOR = 0xd08;
static constexpr uint32_t SHPR2 = 0xd1c;
static constexpr uint32_t SHPR3 = 0xd20;

static constexpr uint32_t SYST_CSR = 0x010;  // SysTick Control and Status Register
static constexpr uint32_t SYST_RVR = 0x014;  // SysTick Reload Value Register
static constexpr uint32_t SYST_CVR = 0x018;  // SysTick Current Value Register
static constexpr uint32_t SYST_CALIB = 0x01c;  // SysTick Calibration Value Register
static constexpr uint32_t NVIC_ISER = 0x100;  // Interrupt Set-Enable Register
static constexpr uint32_t NVIC_ICER = 0x180;  // Interrupt Clear-Enable Register
static constexpr uint32_t NVIC_ISPR = 0x200;  // Interrupt Set-Pending Register
static constexpr uint32_t NVIC_ICPR = 0x280;  // Interrupt Clear-Pending Register

// Interrupt priority registers:
static constexpr uint32_t NVIC_IPR0 = 0x400;
static constexpr uint32_t NVIC_IPR1 = 0x404;
static constexpr uint32_t NVIC_IPR2 = 0x408;
static constexpr uint32_t NVIC_IPR3 = 0x40c;
static constexpr uint32_t NVIC_IPR4 = 0x410;
static constexpr uint32_t NVIC_IPR5 = 0x414;
static constexpr uint32_t NVIC_IPR6 = 0x418;
static constexpr uint32_t NVIC_IPR7 = 0x41c;

/** ICSR Bits */
static constexpr uint32_t NMIPENDSET = 1u << 31;
static constexpr uint32_t PENDSVSET = 1 << 28;
static constexpr uint32_t PENDSVCLR = 1 << 27;
static constexpr uint32_t PENDSTSET = 1 << 26;
static constexpr uint32_t PENDSTCLR = 1 << 25;
[[maybe_unused]] static constexpr uint32_t ISRPREEMPT = 1 << 23;
static constexpr uint32_t ISRPENDING = 1 << 22;
[[maybe_unused]] static constexpr uint32_t VECTPENDING_MASK = 0x1ff;
static constexpr uint32_t VECTPENDING_SHIFT = 12;
static constexpr uint32_t VECTACTIVE_MASK = 0x1ff;
static constexpr uint32_t VECTACTIVE_SHIFT = 0;

RPPPB::RPPPB(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      systickTimer(rp2040.clock, rp2040.clkSys),
      systickAlarm(systickTimer, [this] {
        systickCountFlag = true;
        if (systickIntEnable) {
          this->rp2040.core().pendingSystick = true;
          this->rp2040.core().interruptsUpdated = true;
        }
        systickTimer.set(systickReload);
      }) {
  systickTimer.setTop(0xffffff);
  systickTimer.setMode(TimerMode::Decrement);
  systickAlarm.setTarget(0);
  systickAlarm.setEnable(true);
  reset();
}

void RPPPB::reset() {
  writeUint32(SYST_CSR, 0);
  writeUint32(SYST_RVR, 0xffffff);
  systickTimer.set(0xffffff);
}

uint32_t RPPPB::readUint32(uint32_t offset) {
  CortexM0Core &core = rp2040.core();

  switch (offset) {
    case CPUID:
      return 0x410cc601; /* Verified against actual hardware */

    case ICSR: {
      const bool pendingInterrupts =
          core.pendingInterrupts || core.pendingPendSV || core.pendingSystick || core.pendingSVCall;
      const uint32_t vectPending = core.vectPending();
      return (core.pendingNMI ? NMIPENDSET : 0) | (core.pendingPendSV ? PENDSVSET : 0) |
             (core.pendingSystick ? PENDSTSET : 0) | (pendingInterrupts ? ISRPENDING : 0) |
             (vectPending << VECTPENDING_SHIFT) | ((core.IPSR & VECTACTIVE_MASK) << VECTACTIVE_SHIFT);
    }

    case VTOR:
      return core.VTOR;

    /* NVIC */
    case NVIC_ISPR:
      return core.pendingInterrupts >> 0;
    case NVIC_ICPR:
      return core.pendingInterrupts >> 0;
    case NVIC_ISER:
      return core.enabledInterrupts >> 0;
    case NVIC_ICER:
      return core.enabledInterrupts >> 0;

    case NVIC_IPR0:
    case NVIC_IPR1:
    case NVIC_IPR2:
    case NVIC_IPR3:
    case NVIC_IPR4:
    case NVIC_IPR5:
    case NVIC_IPR6:
    case NVIC_IPR7: {
      const uint32_t regIndex = (offset - NVIC_IPR0) >> 2;
      uint32_t result = 0;
      for (uint32_t byteIndex = 0; byteIndex < 4; byteIndex++) {
        const uint32_t interruptNumber = regIndex * 4 + byteIndex;
        for (uint32_t priority = 0; priority < core.interruptPriorities.size(); priority++) {
          if (core.interruptPriorities[priority] & (1u << interruptNumber)) {
            // JS: priority 2 or 3 in byte 3 makes this a negative int32 (same bits)
            result |= priority << (8 * byteIndex + 6);
          }
        }
      }
      return result;
    }

    case SHPR2:
      return core.SHPR2;
    case SHPR3:
      return core.SHPR3;

    /* SysTick */
    case SYST_CSR: {
      const uint32_t countFlagValue = systickCountFlag ? 1 << 16 : 0;
      const uint32_t clkSourceValue = systickClkSource ? 1 << 2 : 0;
      const uint32_t tickIntValue = systickIntEnable ? 1 << 1 : 0;
      const uint32_t enableFlagValue = systickTimer.enable() ? 1 << 0 : 0;
      systickCountFlag = false;
      return countFlagValue | clkSourceValue | tickIntValue | enableFlagValue;
    }
    case SYST_CVR:
      return systickTimer.counter();
    case SYST_RVR:
      return systickReload;
    case SYST_CALIB:
      return 0x0000270f;
  }
  return BasePeripheral::readUint32(offset);
}

void RPPPB::writeUint32(uint32_t offset, uint32_t value) {
  CortexM0Core &core = rp2040.core();

  const uint32_t hardwareInterruptMask = (1u << MAX_HARDWARE_IRQ) - 1;

  switch (offset) {
    case ICSR:
      if (value & NMIPENDSET) {
        core.pendingNMI = true;
        core.interruptsUpdated = true;
      }
      if (value & PENDSVSET) {
        core.pendingPendSV = true;
        core.interruptsUpdated = true;
      }
      if (value & PENDSVCLR) {
        core.pendingPendSV = false;
      }
      if (value & PENDSTSET) {
        core.pendingSystick = true;
        core.interruptsUpdated = true;
      }
      if (value & PENDSTCLR) {
        core.pendingSystick = false;
      }
      return;

    case VTOR:
      core.VTOR = value;
      return;

    /* NVIC */
    case NVIC_ISPR:
      core.pendingInterrupts |= value;
      core.interruptsUpdated = true;
      return;
    case NVIC_ICPR:
      // (as in TS: the hardware IRQ bits 0..MAX_HARDWARE_IRQ-1 can never be cleared here)
      core.pendingInterrupts &= ~value | hardwareInterruptMask;
      return;
    case NVIC_ISER:
      core.enabledInterrupts |= value;
      core.interruptsUpdated = true;
      return;
    case NVIC_ICER:
      core.enabledInterrupts &= ~value;
      return;

    case NVIC_IPR0:
    case NVIC_IPR1:
    case NVIC_IPR2:
    case NVIC_IPR3:
    case NVIC_IPR4:
    case NVIC_IPR5:
    case NVIC_IPR6:
    case NVIC_IPR7: {
      const uint32_t regIndex = (offset - NVIC_IPR0) >> 2;
      for (uint32_t byteIndex = 0; byteIndex < 4; byteIndex++) {
        const uint32_t interruptNumber = regIndex * 4 + byteIndex;
        const uint32_t newPriority = (value >> (8 * byteIndex + 6)) & 0x3;
        for (uint32_t priority = 0; priority < core.interruptPriorities.size(); priority++) {
          core.interruptPriorities[priority] &= ~(1u << interruptNumber);
        }
        core.interruptPriorities[newPriority] |= 1u << interruptNumber;
      }
      core.interruptsUpdated = true;
      return;
    }

    case SHPR2:
      core.SHPR2 = value;
      return;
    case SHPR3:
      core.SHPR3 = value;
      return;

    // SysTick
    case SYST_CSR:
      systickClkSource = value & (1 << 2) ? true : false;
      systickIntEnable = value & (1 << 1) ? true : false;
      systickTimer.setEnable(value & (1 << 0) ? true : false);
      return;
    case SYST_CVR:
      systickTimer.set(0);
      return;
    case SYST_RVR:
      systickReload = value;
      return;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
