// Port of rp2040js src/peripherals/ppb.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "ppb.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPPPB::RPPPB(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      systickTimer(rp2040.clock, rp2040.clkSys),
      systickAlarm(systickTimer, [] {
        // TODO(port): peripherals/ppb.ts
        //   readonly systickAlarm = new Timer32PeriodicAlarm(this.systickTimer, () => {
        //     this.systickCountFlag = true;
        //     if (this.systickIntEnable) {
        //       this.rp2040.core.pendingSystick = true;
        //       this.rp2040.core.interruptsUpdated = true;
        //     }
        //     this.systickTimer.set(this.systickReload);
        //   });
      }) {
  // TODO(port): peripherals/ppb.ts
  //   constructor(rp2040: RP2040, name: string) {
  //     super(rp2040, name);
  //     this.systickTimer.top = 0xffffff;
  //     this.systickTimer.mode = TimerMode.Decrement;
  //     this.systickAlarm.target = 0;
  //     this.systickAlarm.enable = true;
  //     this.reset();
  //   }
}

void RPPPB::reset() {
  // TODO(port): peripherals/ppb.ts
  //   reset() {
  //     this.writeUint32(SYST_CSR, 0);
  //     this.writeUint32(SYST_RVR, 0xffffff);
  //     this.systickTimer.set(0xffffff);
  //   }
}

uint32_t RPPPB::readUint32(uint32_t offset) {
  // TODO(port): peripherals/ppb.ts
  //   readUint32(offset: number) {
  //     const { rp2040 } = this;
  //     const { core } = rp2040;
  //
  //     switch (offset) {
  //       case CPUID:
  //         return 0x410cc601; /* Verified against actual hardware */
  //
  //       case ICSR: {
  //         const pendingInterrupts =
  //           core.pendingInterrupts || core.pendingPendSV || core.pendingSystick || core.pendingSVCall;
  //         const vectPending = core.vectPending;
  //         return (
  //           (core.pendingNMI ? NMIPENDSET : 0) |
  //           (core.pendingPendSV ? PENDSVSET : 0) |
  //           (core.pendingSystick ? PENDSTSET : 0) |
  //           (pendingInterrupts ? ISRPENDING : 0) |
  //           (vectPending << VECTPENDING_SHIFT) |
  //           ((core.IPSR & VECTACTIVE_MASK) << VECTACTIVE_SHIFT)
  //         );
  //       }
  //
  //       case VTOR:
  //         return core.VTOR;
  //
  //       /* NVIC */
  //       case NVIC_ISPR:
  //         return core.pendingInterrupts >>> 0;
  //       case NVIC_ICPR:
  //         return core.pendingInterrupts >>> 0;
  //       case NVIC_ISER:
  //         return core.enabledInterrupts >>> 0;
  //       case NVIC_ICER:
  //         return core.enabledInterrupts >>> 0;
  //
  //       case NVIC_IPR0:
  //       case NVIC_IPR1:
  //       case NVIC_IPR2:
  //       case NVIC_IPR3:
  //       case NVIC_IPR4:
  //       case NVIC_IPR5:
  //       case NVIC_IPR6:
  //       case NVIC_IPR7: {
  //         const regIndex = (offset - NVIC_IPR0) >> 2;
  //         let result = 0;
  //         for (let byteIndex = 0; byteIndex < 4; byteIndex++) {
  //           const interruptNumber = regIndex * 4 + byteIndex;
  //           for (let priority = 0; priority < core.interruptPriorities.length; priority++) {
  //             if (core.interruptPriorities[priority] & (1 << interruptNumber)) {
  //               result |= priority << (8 * byteIndex + 6);
  //             }
  //           }
  //         }
  //         return result;
  //       }
  //
  //       case SHPR2:
  //         return core.SHPR2;
  //       case SHPR3:
  //         return core.SHPR3;
  //
  //       /* SysTick */
  //       case SYST_CSR: {
  //         const countFlagValue = this.systickCountFlag ? 1 << 16 : 0;
  //         const clkSourceValue = this.systickClkSource ? 1 << 2 : 0;
  //         const tickIntValue = this.systickIntEnable ? 1 << 1 : 0;
  //         const enableFlagValue = this.systickTimer.enable ? 1 << 0 : 0;
  //         this.systickCountFlag = false;
  //         return countFlagValue | clkSourceValue | tickIntValue | enableFlagValue;
  //       }
  //       case SYST_CVR:
  //         return this.systickTimer.counter;
  //       case SYST_RVR:
  //         return this.systickReload;
  //       case SYST_CALIB:
  //         return 0x0000270f;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/ppb.ts", "RPPPB::readUint32");
}

void RPPPB::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/ppb.ts
  //   writeUint32(offset: number, value: number) {
  //     const { rp2040 } = this;
  //     const { core } = rp2040;
  //
  //     const hardwareInterruptMask = (1 << MAX_HARDWARE_IRQ) - 1;
  //
  //     switch (offset) {
  //       case ICSR:
  //         if (value & NMIPENDSET) {
  //           core.pendingNMI = true;
  //           core.interruptsUpdated = true;
  //         }
  //         if (value & PENDSVSET) {
  //           core.pendingPendSV = true;
  //           core.interruptsUpdated = true;
  //         }
  //         if (value & PENDSVCLR) {
  //           core.pendingPendSV = false;
  //         }
  //         if (value & PENDSTSET) {
  //           core.pendingSystick = true;
  //           core.interruptsUpdated = true;
  //         }
  //         if (value & PENDSTCLR) {
  //           core.pendingSystick = false;
  //         }
  //         return;
  //
  //       case VTOR:
  //         core.VTOR = value;
  //         return;
  //
  //       /* NVIC */
  //       case NVIC_ISPR:
  //         core.pendingInterrupts |= value;
  //         core.interruptsUpdated = true;
  //         return;
  //       case NVIC_ICPR:
  //         core.pendingInterrupts &= ~value | hardwareInterruptMask;
  //         return;
  //       case NVIC_ISER:
  //         core.enabledInterrupts |= value;
  //         core.interruptsUpdated = true;
  //         return;
  //       case NVIC_ICER:
  //         core.enabledInterrupts &= ~value;
  //         return;
  //
  //       case NVIC_IPR0:
  //       case NVIC_IPR1:
  //       case NVIC_IPR2:
  //       case NVIC_IPR3:
  //       case NVIC_IPR4:
  //       case NVIC_IPR5:
  //       case NVIC_IPR6:
  //       case NVIC_IPR7: {
  //         const regIndex = (offset - NVIC_IPR0) >> 2;
  //         for (let byteIndex = 0; byteIndex < 4; byteIndex++) {
  //           const interruptNumber = regIndex * 4 + byteIndex;
  //           const newPriority = (value >> (8 * byteIndex + 6)) & 0x3;
  //           for (let priority = 0; priority < core.interruptPriorities.length; priority++) {
  //             core.interruptPriorities[priority] &= ~(1 << interruptNumber);
  //           }
  //           core.interruptPriorities[newPriority] |= 1 << interruptNumber;
  //         }
  //         core.interruptsUpdated = true;
  //         return;
  //       }
  //
  //       case SHPR2:
  //         core.SHPR2 = value;
  //         return;
  //       case SHPR3:
  //         core.SHPR3 = value;
  //         return;
  //
  //       // SysTick
  //       case SYST_CSR:
  //         this.systickClkSource = value & (1 << 2) ? true : false;
  //         this.systickIntEnable = value & (1 << 1) ? true : false;
  //         this.systickTimer.enable = value & (1 << 0) ? true : false;
  //         return;
  //       case SYST_CVR:
  //         this.systickTimer.set(0);
  //         return;
  //       case SYST_RVR:
  //         this.systickReload = value;
  //         return;
  //
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/ppb.ts", "RPPPB::writeUint32");
}

}  // namespace rp2040js
