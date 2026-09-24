// Port of rp2040js src/peripherals/pwm.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "pwm.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

PWMChannel::PWMChannel(RPPWM &pwm, IClock &clock, uint32_t index)
    : timer(clock, pwm.clockFreq()),
      alarmA(timer, [this] { setA(false); }),
      alarmB(timer, [this] { setB(false); }),
      alarmBottom(timer, [this] { wrap(); }),
      clock(clock),
      index(index),
      pinA1(static_cast<int32_t>(index * 2)),
      pinB1(static_cast<int32_t>(index * 2 + 1)),
      pinA2(index < 7 ? static_cast<int32_t>(16 + index * 2) : -1),
      pinB2(index < 7 ? static_cast<int32_t>(16 + index * 2 + 1) : -1),
      pwm(pwm) {
  // TODO(port): peripherals/pwm.ts
  //   constructor(
  //     private pwm: RPPWM,
  //     readonly clock: IClock,
  //     readonly index: number,
  //   ) {
  //     this.alarmA.enable = true;
  //     this.alarmB.enable = true;
  //     this.alarmBottom.enable = true;
  //   }
}

uint32_t PWMChannel::readRegister(uint32_t offset) {
  // TODO(port): peripherals/pwm.ts
  //   readRegister(offset: number) {
  //     switch (offset) {
  //       case CHn_CSR:
  //         return this.csr;
  //       case CHn_DIV:
  //         return this.div;
  //       case CHn_CTR:
  //         return this.timer.counter;
  //       case CHn_CC:
  //         return this.cc;
  //       case CHn_TOP:
  //         return this.top;
  //     }
  //     /* Shouldn't get here */
  //     return 0;
  //   }
  (void)offset;
  return 0;
}

void PWMChannel::writeRegister(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/pwm.ts
  //   writeRegister(offset: number, value: number) {
  //     switch (offset) {
  //       case CHn_CSR:
  //         if (value & CSR_EN && !(this.csr & CSR_EN)) {
  //           this.updateDoubleBuffered();
  //         }
  //         this.csr = value & ~(CSR_PH_ADV | CSR_PH_RET);
  //         if (this.csr & CSR_PH_ADV) {
  //           this.timer.advance(1);
  //         }
  //         if (this.csr & CSR_PH_RET) {
  //           this.timer.advance(-1);
  //         }
  //         this.divMode = (this.csr >> CSR_DIVMODE_SHIFT) & CSR_DIVMODE_MASK;
  //         this.setBDirection(this.divMode === PWMDivMode.FreeRunning);
  //         this.updateEnable();
  //         this.lastBValue = this.gpioBValue;
  //         this.timer.mode = value & CSR_PH_CORRECT ? TimerMode.ZigZag : TimerMode.Increment;
  //         break;
  //       case CHn_DIV: {
  //         this.div = value & 0x000f_ffff;
  //         const intValue = (value >> 4) & 0xff;
  //         const fracValue = value & 0xf;
  //         this.timer.prescaler = (intValue ? intValue : 256) + fracValue / 16;
  //         break;
  //       }
  //       case CHn_CTR:
  //         this.timer.set(value & 0xffff);
  //         break;
  //       case CHn_CC:
  //         this.cc = value;
  //         this.ccUpdated = true;
  //         break;
  //       case CHn_TOP:
  //         this.top = value & 0xffff;
  //         this.topUpdated = true;
  //         break;
  //     }
  //   }
  (void)offset;
  (void)value;
}

void PWMChannel::reset() {
  // TODO(port): peripherals/pwm.ts
  //   reset() {
  //     this.writeRegister(CHn_CSR, 0);
  //     this.writeRegister(CHn_DIV, 0x01 << 4);
  //     this.writeRegister(CHn_CTR, 0);
  //     this.writeRegister(CHn_CC, 0);
  //     this.writeRegister(CHn_TOP, 0xffff);
  //     this.countingUp = true;
  //     this.timer.enable = false;
  //     this.timer.reset();
  //   }
}

void PWMChannel::updateDoubleBuffered() {
  // TODO(port): peripherals/pwm.ts
  //   private updateDoubleBuffered() {
  //     if (this.ccUpdated) {
  //       this.alarmB.target = this.cc >>> 16;
  //       this.alarmA.target = this.cc & 0xffff;
  //       this.ccUpdated = false;
  //     }
  //     if (this.topUpdated) {
  //       this.timer.top = this.top;
  //       this.topUpdated = false;
  //     }
  //   }
}

void PWMChannel::wrap() {
  // TODO(port): peripherals/pwm.ts
  //   private wrap() {
  //     this.pwm.channelInterrupt(this.index);
  //     this.updateDoubleBuffered();
  //     if (!(this.csr & CSR_PH_CORRECT)) {
  //       this.setA(this.alarmA.target > 0);
  //       this.setB(this.alarmB.target > 0);
  //     }
  //   }
}

void PWMChannel::setA(bool value) {
  // TODO(port): peripherals/pwm.ts
  //   setA(value: boolean) {
  //     if (this.csr & CSR_A_INV) {
  //       value = !value;
  //     }
  //     this.pwm.gpioSet(this.pinA1, value);
  //     if (this.pinA2 >= 0) {
  //       this.pwm.gpioSet(this.pinA2, value);
  //     }
  //   }
  (void)value;
}

void PWMChannel::setB(bool value) {
  // TODO(port): peripherals/pwm.ts
  //   setB(value: boolean) {
  //     if (this.csr & CSR_B_INV) {
  //       value = !value;
  //     }
  //     this.pwm.gpioSet(this.pinB1, value);
  //     if (this.pinB2 >= 0) {
  //       this.pwm.gpioSet(this.pinB2, value);
  //     }
  //   }
  (void)value;
}

bool PWMChannel::gpioBValue() const {
  // TODO(port): peripherals/pwm.ts
  //   get gpioBValue() {
  //     return (
  //       this.pwm.gpioRead(this.pinB1) || (this.pinB2 > 0 ? this.pwm.gpioRead(this.pinB2) : false)
  //     );
  //   }
  return false;
}

void PWMChannel::setBDirection(bool value) {
  // TODO(port): peripherals/pwm.ts
  //   setBDirection(value: boolean) {
  //     this.pwm.gpioSetDir(this.pinB1, value);
  //     if (this.pinB2 >= 0) {
  //       this.pwm.gpioSetDir(this.pinB2, value);
  //     }
  //   }
  (void)value;
}

void PWMChannel::gpioBChanged() {
  // TODO(port): peripherals/pwm.ts
  //   gpioBChanged() {
  //     const value = this.gpioBValue;
  //     if (value === this.lastBValue) {
  //       return;
  //     }
  //     this.lastBValue = value;
  //     switch (this.divMode) {
  //       case PWMDivMode.BGated:
  //         this.updateEnable();
  //         break;
  //
  //       case PWMDivMode.BRisingEdge:
  //         if (value) {
  //           this.tickCounter++;
  //         }
  //         break;
  //
  //       case PWMDivMode.BFallingEdge:
  //         if (!value) {
  //           this.tickCounter++;
  //         }
  //         break;
  //     }
  //
  //     if (this.tickCounter >= this.timer.prescaler) {
  //       this.timer.advance(1);
  //       this.tickCounter -= this.timer.prescaler;
  //     }
  //   }
}

void PWMChannel::updateEnable() {
  // TODO(port): peripherals/pwm.ts
  //   updateEnable() {
  //     const { csr, divMode } = this;
  //     const enable = !!(csr & CSR_EN);
  //     this.timer.enable =
  //       enable &&
  //       (divMode === PWMDivMode.FreeRunning || (divMode === PWMDivMode.BGated && this.gpioBValue));
  //   }
}

void PWMChannel::setEn(uint32_t value) {
  // TODO(port): peripherals/pwm.ts
  //   set en(value: number) {
  //     if (value && !(this.csr & CSR_EN)) {
  //       this.updateDoubleBuffered();
  //     }
  //     if (value) {
  //       this.csr |= CSR_EN;
  //     } else {
  //       this.csr &= ~CSR_EN;
  //     }
  //     this.updateEnable();
  //   }
  (void)value;
}

RPPWM::RPPWM(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      channels{{
          {*this, rp2040.clock, 0},
          {*this, rp2040.clock, 1},
          {*this, rp2040.clock, 2},
          {*this, rp2040.clock, 3},
          {*this, rp2040.clock, 4},
          {*this, rp2040.clock, 5},
          {*this, rp2040.clock, 6},
          {*this, rp2040.clock, 7},
      }} {
  // TODO(port): peripherals/pwm.ts
  //   readonly channels = [
  //     new PWMChannel(this, this.rp2040.clock, 0),
}

uint32_t RPPWM::intStatus() const {
  // TODO(port): peripherals/pwm.ts
  //   get intStatus() {
  //     return (this.intRaw & this.intEnable) | this.intForce;
  //   }
  return 0;
}

uint32_t RPPWM::readUint32(uint32_t offset) {
  // TODO(port): peripherals/pwm.ts
  //   readUint32(offset: number) {
  //     if (offset < EN) {
  //       const channel = Math.floor(offset / 0x14);
  //       return this.channels[channel].readRegister(offset % 0x14);
  //     }
  //     switch (offset) {
  //       case EN:
  //         return (
  //           (this.channels[7].en << 7) |
  //           (this.channels[6].en << 6) |
  //           (this.channels[5].en << 5) |
  //           (this.channels[4].en << 4) |
  //           (this.channels[3].en << 3) |
  //           (this.channels[2].en << 2) |
  //           (this.channels[1].en << 1) |
  //           (this.channels[0].en << 0)
  //         );
  //       case INTR:
  //         return this.intRaw;
  //       case INTE:
  //         return this.intEnable;
  //       case INTF:
  //         return this.intForce;
  //       case INTS:
  //         return this.intStatus;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/pwm.ts", "RPPWM::readUint32");
}

void RPPWM::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/pwm.ts
  //   writeUint32(offset: number, value: number) {
  //     if (offset < EN) {
  //       const channel = Math.floor(offset / 0x14);
  //       return this.channels[channel].writeRegister(offset % 0x14, value);
  //     }
  //
  //     switch (offset) {
  //       case EN:
  //         this.channels[7].en = value & (1 << 7);
  //         this.channels[6].en = value & (1 << 6);
  //         this.channels[5].en = value & (1 << 5);
  //         this.channels[4].en = value & (1 << 4);
  //         this.channels[3].en = value & (1 << 3);
  //         this.channels[2].en = value & (1 << 2);
  //         this.channels[1].en = value & (1 << 1);
  //         this.channels[0].en = value & (1 << 0);
  //         break;
  //       case INTR:
  //         this.intRaw &= ~(value & INT_MASK);
  //         this.checkInterrupts();
  //         break;
  //       case INTE:
  //         this.intEnable = value & INT_MASK;
  //         this.checkInterrupts();
  //         break;
  //       case INTF:
  //         this.intForce = value & INT_MASK;
  //         this.checkInterrupts();
  //         break;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/pwm.ts", "RPPWM::writeUint32");
}

double RPPWM::clockFreq() const {
  // TODO(port): peripherals/pwm.ts
  //   get clockFreq() {
  //     return this.rp2040.clkSys;
  //   }
  return 0;
}

void RPPWM::channelInterrupt(uint32_t index) {
  // TODO(port): peripherals/pwm.ts
  //   channelInterrupt(index: number) {
  //     this.intRaw |= 1 << index;
  //     this.checkInterrupts();
  //
  //     // We also set the DMA Request (DREQ) for the channel
  //     this.rp2040.dma.setDREQ(DREQChannel.DREQ_PWM_WRAP0 + index);
  //   }
  (void)index;
}

void RPPWM::checkInterrupts() {
  // TODO(port): peripherals/pwm.ts
  //   checkInterrupts() {
  //     this.rp2040.setInterrupt(IRQ.PWM_WRAP, !!this.intStatus);
  //   }
}

void RPPWM::gpioSet(uint32_t index, bool value) {
  // TODO(port): peripherals/pwm.ts
  //   gpioSet(index: number, value: boolean) {
  //     const bit = 1 << index;
  //     const newGpioValue = value ? this.gpioValue | bit : this.gpioValue & ~bit;
  //     if (this.gpioValue != newGpioValue) {
  //       this.gpioValue = newGpioValue;
  //       this.rp2040.gpio[index].checkForUpdates();
  //     }
  //   }
  (void)index;
  (void)value;
}

void RPPWM::gpioSetDir(uint32_t index, bool output) {
  // TODO(port): peripherals/pwm.ts
  //   gpioSetDir(index: number, output: boolean) {
  //     const bit = 1 << index;
  //     const newGpioDirection = output ? this.gpioDirection | bit : this.gpioDirection & ~bit;
  //     if (this.gpioDirection != newGpioDirection) {
  //       this.gpioDirection = newGpioDirection;
  //       this.rp2040.gpio[index].checkForUpdates();
  //     }
  //   }
  (void)index;
  (void)output;
}

bool RPPWM::gpioRead(uint32_t index) {
  // TODO(port): peripherals/pwm.ts
  //   gpioRead(index: number) {
  //     return this.rp2040.gpio[index].inputValue;
  //   }
  (void)index;
  return false;
}

void RPPWM::gpioOnInput(uint32_t index) {
  // TODO(port): peripherals/pwm.ts
  //   gpioOnInput(index: number) {
  //     if (this.gpioDirection && 1 << index) {
  //       return;
  //     }
  //     for (const channel of this.channels) {
  //       if (channel.pinB1 === index || channel.pinB2 === index) {
  //         channel.gpioBChanged();
  //       }
  //     }
  //   }
  (void)index;
}

void RPPWM::reset() {
  // TODO(port): peripherals/pwm.ts
  //   reset() {
  //     this.gpioDirection = 0xffffffff;
  //     for (const channel of this.channels) {
  //       channel.reset();
  //     }
  //   }
}

}  // namespace rp2040js
