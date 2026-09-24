// Port of rp2040js src/peripherals/pio.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "pio.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

// Module-level tables of pio.ts, needed to construct an RPPIO.
static const std::array<DREQChannel, 4> dreqRx0 = {DREQ_PIO0_RX0, DREQ_PIO0_RX1, DREQ_PIO0_RX2, DREQ_PIO0_RX3};
static const std::array<DREQChannel, 4> dreqTx0 = {DREQ_PIO0_TX0, DREQ_PIO0_TX1, DREQ_PIO0_TX2, DREQ_PIO0_TX3};
static const std::array<DREQChannel, 4> dreqRx1 = {DREQ_PIO1_RX0, DREQ_PIO1_RX1, DREQ_PIO1_RX2, DREQ_PIO1_RX3};
static const std::array<DREQChannel, 4> dreqTx1 = {DREQ_PIO1_TX0, DREQ_PIO1_TX1, DREQ_PIO1_TX2, DREQ_PIO1_TX3};

StateMachine::StateMachine(RP2040 &rp2040, RPPIO &pio, uint32_t index)
    : rp2040(rp2040), pio(pio), index(index), dreqRx(pio.dreqRx[index]), dreqTx(pio.dreqTx[index]) {
  // TODO(port): peripherals/pio.ts
  //   constructor(
  //     readonly rp2040: RP2040,
  //     readonly pio: RPPIO,
  //     readonly index: number,
  //   ) {
  //     this.updateDMARx();
  //     this.updateDMATx();
  //   }
}

void StateMachine::updateDMATx() {
  // TODO(port): peripherals/pio.ts
  //   private updateDMATx() {
  //     if (this.txFIFO.full) {
  //       this.rp2040.dma.clearDREQ(this.dreqTx);
  //     } else {
  //       this.rp2040.dma.setDREQ(this.dreqTx);
  //     }
  //   }
}

void StateMachine::updateDMARx() {
  // TODO(port): peripherals/pio.ts
  //   private updateDMARx() {
  //     if (this.rxFIFO.empty) {
  //       this.rp2040.dma.clearDREQ(this.dreqRx);
  //     } else {
  //       this.rp2040.dma.setDREQ(this.dreqRx);
  //     }
  //   }
}

void StateMachine::writeFIFO(uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   writeFIFO(value: number) {
  //     if (this.txFIFO.full) {
  //       this.pio.fdebug |= FDEBUG_TXOVER << this.index;
  //       return;
  //     }
  //     this.txFIFO.push(value);
  //     this.pio.txStall &= ~(FDEBUG_TXSTALL << this.index);
  //     this.updateDMATx();
  //     this.checkWait();
  //     if (this.txFIFO.full) {
  //       this.pio.checkInterrupts();
  //     }
  //   }
  (void)value;
}

uint32_t StateMachine::readFIFO() {
  // TODO(port): peripherals/pio.ts
  //   readFIFO() {
  //     if (this.rxFIFO.empty) {
  //       this.pio.fdebug |= FDEBUG_RXUNDER << this.index;
  //       return 0;
  //     }
  //     const result = this.rxFIFO.pull();
  //     this.pio.rxStall &= ~(FDEBUG_RXSTALL << this.index);
  //     this.updateDMARx();
  //     this.checkWait();
  //     if (this.rxFIFO.empty) {
  //       this.pio.checkInterrupts();
  //     }
  //     return result;
  //   }
  return 0;
}

uint32_t StateMachine::status() const {
  // TODO(port): peripherals/pio.ts
  //   get status() {
  //     const statusN = this.execCtrl & 0xf;
  //     if (this.execCtrl & EXECCTRL_STATUS_SEL) {
  //       return this.rxFIFO.itemCount < statusN ? 0xffffffff : 0;
  //     } else {
  //       return this.txFIFO.itemCount < statusN ? 0xffffffff : 0;
  //     }
  //   }
  return 0;
}

bool StateMachine::jmpCondition(uint32_t condition) {
  // TODO(port): peripherals/pio.ts
  //   jmpCondition(condition: number) {
  //     switch (condition) {
  //       // (no condition): Always
  //       case 0b000:
  //         return true;
  //
  //       // !X: scratch X zero
  //       case 0b001:
  //         return this.x === 0;
  //
  //       // X--: scratch X non-zero, post-decrement
  //       case 0b010: {
  //         const oldX = this.x;
  //         this.x = (this.x - 1) >>> 0;
  //         return oldX !== 0;
  //       }
  //
  //       // !Y: scratch Y zero
  //       case 0b011:
  //         return this.y === 0;
  //
  //       // Y--: scratch Y non-zero, post-decrement
  //       case 0b100: {
  //         const oldY = this.y;
  //         this.y = (this.y - 1) >>> 0;
  //         return oldY !== 0;
  //       }
  //
  //       // X!=Y: scratch X not equal scratch Y
  //       case 0b101:
  //         return this.x >>> 0 !== this.y >>> 0;
  //
  //       // PIN: branch on input pin
  //       case 0b110: {
  //         const { gpio } = this.rp2040;
  //         const { jmpPin } = this;
  //         return jmpPin < gpio.length ? gpio[jmpPin].inputValue : false;
  //       }
  //
  //       // !OSRE: output shift register not empty
  //       case 0b111:
  //         return this.outputShiftCount < this.pullThreshold;
  //     }
  //
  //     this.pio.error(`jmpCondition with unsupported condition: ${condition}`);
  //     return false;
  //   }
  (void)condition;
  return false;
}

uint32_t StateMachine::inPins() const {
  // TODO(port): peripherals/pio.ts
  //   get inPins() {
  //     const { gpioValues } = this.rp2040;
  //     const { inBase } = this;
  //     return inBase ? (gpioValues << (32 - inBase)) | (gpioValues >>> inBase) : gpioValues;
  //   }
  return 0;
}

uint32_t StateMachine::inSourceValue(uint32_t source) {
  // TODO(port): peripherals/pio.ts
  //   inSourceValue(source: number) {
  //     switch (source) {
  //       // PINS
  //       case 0b000:
  //         return this.inPins;
  //
  //       // X (scratch register X)
  //       case 0b001:
  //         return this.x;
  //
  //       // Y (scratch register Y)
  //       case 0b010:
  //         return this.y;
  //
  //       // NULL (all zeroes)
  //       case 0b011:
  //         return 0;
  //
  //       // Reserved
  //       case 0b100:
  //         return 0;
  //
  //       // Reserved for IN, STATUS for MOV
  //       case 0b101:
  //         return this.status;
  //
  //       // ISR
  //       case 0b110:
  //         return this.inputShiftReg;
  //
  //       // OSR
  //       case 0b111:
  //         return this.outputShiftReg;
  //     }
  //
  //     this.pio.error(`inSourceValue with unsupported source: ${source}`);
  //     return 0;
  //   }
  (void)source;
  return 0;
}

void StateMachine::writeOutValue(uint32_t destination, uint32_t value, uint32_t bitCount) {
  // TODO(port): peripherals/pio.ts
  //   writeOutValue(destination: number, value: number, bitCount: number) {
  //     switch (destination) {
  //       // PINS
  //       case 0b000:
  //         this.setOutPins(value);
  //         break;
  //
  //       // X (scratch register X)
  //       case 0b001:
  //         this.x = value;
  //         break;
  //
  //       // Y (scratch register Y)
  //       case 0b010:
  //         this.y = value;
  //         break;
  //
  //       // NULL (discard data)
  //       case 0b011:
  //         break;
  //
  //       // PINDIRS
  //       case 0b100:
  //         this.setOutPinDirs(value);
  //         break;
  //
  //       // PC
  //       case 0b101:
  //         this.pc = value & 0x1f;
  //         this.updatePC = false;
  //         break;
  //
  //       // ISR (also sets ISR shift counter to Bit count)
  //       case 0b110:
  //         this.inputShiftReg = value;
  //         this.inputShiftCount = bitCount;
  //         break;
  //
  //       // EXEC (Execute OSR shift data as instruction)
  //       case 0b111:
  //         this.execOpcode = value;
  //         this.execValid = true;
  //         break;
  //     }
  //   }
  (void)destination;
  (void)value;
  (void)bitCount;
}

uint32_t StateMachine::pushThreshold() const {
  // TODO(port): peripherals/pio.ts
  //   get pushThreshold() {
  //     const value = (this.shiftCtrl >> 20) & 0x1f;
  //     return value ? value : 32;
  //   }
  return 0;
}

uint32_t StateMachine::pullThreshold() const {
  // TODO(port): peripherals/pio.ts
  //   get pullThreshold() {
  //     const value = (this.shiftCtrl >> 25) & 0x1f;
  //     return value ? value : 32;
  //   }
  return 0;
}

uint32_t StateMachine::sidesetCount() const {
  // TODO(port): peripherals/pio.ts
  //   get sidesetCount() {
  //     return (this.pinCtrl >> 29) & 0x7;
  //   }
  return 0;
}

uint32_t StateMachine::setCount() const {
  // TODO(port): peripherals/pio.ts
  //   get setCount() {
  //     return (this.pinCtrl >> 26) & 0x7;
  //   }
  return 0;
}

uint32_t StateMachine::outCount() const {
  // TODO(port): peripherals/pio.ts
  //   get outCount() {
  //     return (this.pinCtrl >> 20) & 0x3f;
  //   }
  return 0;
}

uint32_t StateMachine::inBase() const {
  // TODO(port): peripherals/pio.ts
  //   get inBase() {
  //     return (this.pinCtrl >> 15) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::sidesetBase() const {
  // TODO(port): peripherals/pio.ts
  //   get sidesetBase() {
  //     return (this.pinCtrl >> 10) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::setBase() const {
  // TODO(port): peripherals/pio.ts
  //   get setBase() {
  //     return (this.pinCtrl >> 5) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::outBase() const {
  // TODO(port): peripherals/pio.ts
  //   get outBase() {
  //     return (this.pinCtrl >> 0) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::jmpPin() const {
  // TODO(port): peripherals/pio.ts
  //   get jmpPin() {
  //     return (this.execCtrl >> 24) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::wrapTop() const {
  // TODO(port): peripherals/pio.ts
  //   get wrapTop() {
  //     return (this.execCtrl >> 12) & 0x1f;
  //   }
  return 0;
}

uint32_t StateMachine::wrapBottom() const {
  // TODO(port): peripherals/pio.ts
  //   get wrapBottom() {
  //     return (this.execCtrl >> 7) & 0x1f;
  //   }
  return 0;
}

void StateMachine::setOutPinDirs(uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   setOutPinDirs(value: number) {
  //     this.outPinDirection = value;
  //     this.pio.pinDirectionsChanged(value, this.outBase, this.outCount);
  //   }
  (void)value;
}

void StateMachine::setOutPins(uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   setOutPins(value: number) {
  //     this.outPinValues = value;
  //     this.pio.pinValuesChanged(value, this.outBase, this.outCount);
  //   }
  (void)value;
}

void StateMachine::outInstruction(uint32_t arg) {
  // TODO(port): peripherals/pio.ts
  //   outInstruction(arg: number) {
  //     const bitCount = arg & 0x1f;
  //     const destination = arg >> 5;
  //
  //     if (bitCount === 0) {
  //       this.writeOutValue(destination, this.outputShiftReg, 32);
  //       this.outputShiftCount = 32;
  //     } else {
  //       if (this.shiftCtrl & SHIFTCTRL_OUT_SHIFTDIR) {
  //         const value = this.outputShiftReg & ((1 << bitCount) - 1);
  //         this.outputShiftReg >>>= bitCount;
  //         this.writeOutValue(destination, value, bitCount);
  //       } else {
  //         const value = this.outputShiftReg >>> (32 - bitCount);
  //         this.outputShiftReg <<= bitCount;
  //         this.writeOutValue(destination, value, bitCount);
  //       }
  //       this.outputShiftCount += bitCount;
  //       if (this.outputShiftCount > 32) {
  //         this.outputShiftCount = 32;
  //       }
  //     }
  //   }
  (void)arg;
}

void StateMachine::executeInstruction(uint32_t opcode) {
  // TODO(port): peripherals/pio.ts
  //   executeInstruction(opcode: number) {
  //     const arg = opcode & 0xff;
  //     switch (opcode >>> 13) {
  //       /* JMP */
  //       case 0b000:
  //         if (this.jmpCondition(arg >> 5)) {
  //           this.pc = arg & 0x1f;
  //           this.updatePC = false;
  //         }
  //         break;
  //
  //       /* WAIT */
  //       case 0b001: {
  //         const polarity = !!(arg & 0x80);
  //         const source = (arg >> 5) & 0x3;
  //         const index = arg & 0x1f;
  //         switch (source) {
  //           // GPIO:
  //           case 0b00:
  //             this.wait(WaitType.Pin, polarity, index);
  //             break;
  //
  //           // PIN:
  //           case 0b01:
  //             this.wait(WaitType.Pin, polarity, (index + this.inBase) % 32);
  //             break;
  //
  //           // IRQ:
  //           case 0b10:
  //             this.wait(WaitType.IRQ, polarity, irqIndex(index, this.index));
  //             break;
  //         }
  //         break;
  //       }
  //
  //       /* IN */
  //       case 0b010: {
  //         const bitCount = arg & 0x1f;
  //         let sourceValue = this.inSourceValue(arg >> 5);
  //
  //         if (bitCount == 0) {
  //           this.inputShiftReg = sourceValue;
  //           this.inputShiftCount = 32;
  //         } else {
  //           sourceValue &= (1 << bitCount) - 1;
  //           if (this.shiftCtrl & SHIFTCTRL_IN_SHIFTDIR) {
  //             this.inputShiftReg >>>= bitCount;
  //             this.inputShiftReg |= sourceValue << (32 - bitCount);
  //           } else {
  //             this.inputShiftReg <<= bitCount;
  //             this.inputShiftReg |= sourceValue;
  //           }
  //           this.inputShiftCount += bitCount;
  //           if (this.inputShiftCount > 32) {
  //             this.inputShiftCount = 32;
  //           }
  //         }
  //
  //         if (this.shiftCtrl & SHIFTCTRL_AUTOPUSH && this.inputShiftCount >= this.pushThreshold) {
  //           if (!this.rxFIFO.full) {
  //             this.rxFIFO.push(this.inputShiftReg);
  //             this.updateDMARx();
  //             this.pio.checkInterrupts();
  //           } else {
  //             this.pio.rxStall |= FDEBUG_RXSTALL << this.index;
  //             this.pio.fdebug |= this.pio.rxStall;
  //             this.wait(WaitType.rxFIFO, false, this.inputShiftReg);
  //           }
  //           this.inputShiftCount = 0;
  //           this.inputShiftReg = 0;
  //         }
  //
  //         break;
  //       }
  //
  //       /* OUT */
  //       case 0b011: {
  //         if (this.shiftCtrl & SHIFTCTRL_AUTOPULL && this.outputShiftCount >= this.pullThreshold) {
  //           this.outputShiftCount = 0;
  //           if (!this.txFIFO.empty) {
  //             this.outputShiftReg = this.txFIFO.pull();
  //             this.updateDMATx();
  //             this.pio.checkInterrupts();
  //           } else {
  //             this.pio.txStall |= FDEBUG_TXSTALL << this.index;
  //             this.pio.fdebug |= this.pio.txStall;
  //             this.wait(WaitType.Out, false, arg);
  //           }
  //         }
  //
  //         if (!this.waiting) {
  //           this.outInstruction(arg);
  //         }
  //         break;
  //       }
  //
  //       /* PUSH/PULL */
  //       case 0b100: {
  //         const block = !!(arg & (1 << 5));
  //         const ifFullOrEmpty = !!(arg & (1 << 6));
  //         if (arg & 0x1f) {
  //           // Unknown instruction
  //           break;
  //         }
  //         if (arg & 0x80) {
  //           // PULL
  //           if (
  //             ifFullOrEmpty &&
  //             this.shiftCtrl & SHIFTCTRL_AUTOPULL &&
  //             this.outputShiftCount < this.pullThreshold
  //           ) {
  //             break;
  //           }
  //           if (!this.txFIFO.empty) {
  //             this.outputShiftReg = this.txFIFO.pull();
  //             this.updateDMATx();
  //             this.pio.checkInterrupts();
  //           } else {
  //             this.pio.txStall |= FDEBUG_TXSTALL << this.index;
  //             this.pio.fdebug |= this.pio.txStall;
  //             if (block) {
  //               this.wait(WaitType.txFIFO, false, 0);
  //             } else {
  //               this.outputShiftReg = this.x;
  //             }
  //           }
  //           this.outputShiftCount = 0;
  //         } else {
  //           // PUSH
  //           if (
  //             ifFullOrEmpty &&
  //             this.shiftCtrl & SHIFTCTRL_AUTOPUSH &&
  //             this.inputShiftCount < this.pushThreshold
  //           ) {
  //             break;
  //           }
  //           if (!this.rxFIFO.full) {
  //             this.rxFIFO.push(this.inputShiftReg);
  //             this.updateDMARx();
  //             this.pio.checkInterrupts();
  //           } else {
  //             this.pio.rxStall |= FDEBUG_RXSTALL << this.index;
  //             this.pio.fdebug |= this.pio.rxStall;
  //             if (block) {
  //               this.wait(WaitType.rxFIFO, false, this.inputShiftReg);
  //             }
  //           }
  //           this.inputShiftReg = 0;
  //           this.inputShiftCount = 0;
  //         }
  //         break;
  //       }
  //
  //       /* MOV */
  //       case 0b101: {
  //         const source = arg & 0x7;
  //         const op = (arg >> 3) & 0x3;
  //         const destination = (arg >> 5) & 0x7;
  //         const value = this.inSourceValue(source);
  //         const transformedValue = this.transformMovValue(value, op) >>> 0;
  //         this.setMovDestination(destination, transformedValue);
  //         break;
  //       }
  //
  //       /* IRQ */
  //       case 0b110: {
  //         if (arg & 0x80) {
  //           // Unknown instruction
  //           break;
  //         }
  //         const clear = !!(arg & 0x40);
  //         const wait = !!(arg & 0x20);
  //         const irq = irqIndex(arg & 0x1f, this.index);
  //         if (clear) {
  //           this.pio.irq &= ~(1 << irq);
  //           this.pio.irqUpdated();
  //         } else {
  //           this.pio.irq |= 1 << irq;
  //           this.pio.irqUpdated();
  //           if (wait) {
  //             this.wait(WaitType.IRQ, false, irq);
  //           }
  //         }
  //         break;
  //       }
  //
  //       /* SET */
  //       case 0b111: {
  //         const data = arg & 0x1f;
  //         const destination = arg >> 5;
  //         switch (destination) {
  //           case 0b000:
  //             this.setSetPins(data);
  //             break;
  //           case 0b001:
  //             this.x = data;
  //             break;
  //           case 0b010:
  //             this.y = data;
  //             break;
  //           case 0b100:
  //             this.setSetPinDirs(data);
  //             break;
  //         }
  //         break;
  //       }
  //     }
  //
  //     this.cycles++;
  //
  //     const { sidesetCount, execCtrl } = this;
  //     const delaySideset = (opcode >> 8) & 0x1f;
  //     const sideEn = !!(execCtrl & EXECCTRL_SIDE_EN);
  //     const delay = delaySideset & ((1 << (5 - sidesetCount)) - 1);
  //
  //     if (sidesetCount && (!sideEn || delaySideset & 0x10)) {
  //       const sideset = delaySideset >> (5 - sidesetCount);
  //       this.setSideset(sideset, sideEn ? sidesetCount - 1 : sidesetCount);
  //     }
  //
  //     if (this.execValid) {
  //       this.execValid = false;
  //       this.executeInstruction(this.execOpcode);
  //     } else if (this.waiting) {
  //       if (this.waitDelay < 0) {
  //         this.waitDelay = delay;
  //       }
  //       this.checkWait();
  //     } else {
  //       this.cycles += delay;
  //       this.delayLeft = delay;
  //     }
  //   }
  (void)opcode;
  TODO_PORT_ABORT("peripherals/pio.ts", "StateMachine::executeInstruction");
}

void StateMachine::wait(WaitType type, bool polarity, uint32_t index) {
  // TODO(port): peripherals/pio.ts
  //   wait(type: WaitType, polarity: boolean, index: number) {
  //     this.waiting = true;
  //     this.waitType = type;
  //     this.waitPolarity = polarity;
  //     this.waitIndex = index;
  //     this.waitDelay = -1;
  //     this.updatePC = false;
  //   }
  (void)type;
  (void)polarity;
  (void)index;
}

void StateMachine::nextPC() {
  // TODO(port): peripherals/pio.ts
  //   nextPC() {
  //     if (this.pc === this.wrapTop) {
  //       this.pc = this.wrapBottom;
  //     } else {
  //       this.pc = (this.pc + 1) & 0x1f;
  //     }
  //   }
}

void StateMachine::step() {
  // TODO(port): peripherals/pio.ts
  //   step() {
  //     if (this.delayLeft > 0) {
  //       this.delayLeft--;
  //       return;
  //     }
  //     if (this.waiting) {
  //       this.checkWait();
  //       if (this.waiting) {
  //         return;
  //       }
  //     }
  //
  //     this.updatePC = true;
  //     this.executeInstruction(this.pio.instructions[this.pc]);
  //     if (this.updatePC) {
  //       this.nextPC();
  //     }
  //   }
  TODO_PORT_ABORT("peripherals/pio.ts", "StateMachine::step");
}

void StateMachine::setSetPinDirs(uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   setSetPinDirs(value: number) {
  //     this.pio.pinDirectionsChanged(value, this.setBase, this.setCount);
  //   }
  (void)value;
}

void StateMachine::setSetPins(uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   setSetPins(value: number) {
  //     this.pio.pinValuesChanged(value, this.setBase, this.setCount);
  //   }
  (void)value;
}

void StateMachine::setSideset(uint32_t value, uint32_t count) {
  // TODO(port): peripherals/pio.ts
  //   setSideset(value: number, count: number) {
  //     if (this.execCtrl & EXECCTRL_SIDE_PINDIR) {
  //       this.pio.pinDirectionsChanged(value, this.sidesetBase, count);
  //     } else {
  //       this.pio.pinValuesChanged(value, this.sidesetBase, count);
  //     }
  //   }
  (void)value;
  (void)count;
}

uint32_t StateMachine::transformMovValue(uint32_t value, uint32_t op) {
  // TODO(port): peripherals/pio.ts
  //   transformMovValue(value: number, op: number) {
  //     switch (op) {
  //       case 0b00:
  //         return value;
  //       case 0b01:
  //         return ~value;
  //       case 0b10:
  //         return bitReverse(value);
  //       case 0b11:
  //       default:
  //         return value; // reserved
  //     }
  //   }
  (void)value;
  (void)op;
  return 0;
}

void StateMachine::setMovDestination(uint32_t destination, uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   setMovDestination(destination: number, value: number) {
  //     switch (destination) {
  //       // PINS
  //       case 0b000:
  //         this.setOutPins(value);
  //         break;
  //
  //       // X (scratch register X)
  //       case 0b001:
  //         this.x = value;
  //         break;
  //
  //       // Y (scratch register Y)
  //       case 0b010:
  //         this.y = value;
  //         break;
  //
  //       // reserved (discard data)
  //       case 0b011:
  //         break;
  //
  //       // EXEC
  //       case 0b100:
  //         this.execOpcode = value;
  //         this.execValid = true;
  //         break;
  //
  //       // PC
  //       case 0b101:
  //         this.pc = value & 0x1f;
  //         this.updatePC = false;
  //         break;
  //
  //       // ISR (Input shift counter is reset to 0 by this operation, i.e. empty)
  //       case 0b110:
  //         this.inputShiftReg = value;
  //         this.inputShiftCount = 0;
  //         break;
  //
  //       // OSR (Output shift counter is reset to 0 by this operation, i.e. full)
  //       case 0b111:
  //         this.outputShiftReg = value;
  //         this.outputShiftCount = 0;
  //         break;
  //     }
  //   }
  (void)destination;
  (void)value;
}

uint32_t StateMachine::readUint32(uint32_t offset) {
  // TODO(port): peripherals/pio.ts
  //   readUint32(offset: number) {
  //     switch (offset + SM0_CLKDIV) {
  //       case SM0_CLKDIV:
  //         return (this.clockDivInt << 16) | (this.clockDivFrac << 8);
  //       case SM0_EXECCTRL:
  //         return this.execCtrl;
  //       case SM0_SHIFTCTRL:
  //         return this.shiftCtrl;
  //       case SM0_ADDR:
  //         return this.pc;
  //       case SM0_INSTR:
  //         return this.pio.instructions[this.pc];
  //       case SM0_PINCTRL:
  //         return this.pinCtrl;
  //     }
  //     this.pio.error(`Read from invalid state machine register: ${offset}`);
  //     return 0;
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/pio.ts", "StateMachine::readUint32");
}

void StateMachine::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset + SM0_CLKDIV) {
  //       case SM0_CLKDIV:
  //         this.clockDivFrac = (value >>> 8) & 0xff;
  //         this.clockDivInt = value >>> 16;
  //         break;
  //       case SM0_EXECCTRL:
  //         this.execCtrl = ((value & 0x7fffffff) | (this.execCtrl & 0x80000000)) >>> 0;
  //         break;
  //       case SM0_SHIFTCTRL: {
  //         // Changing either join bit flushes both FIFOs (pio_sm_clear_fifos
  //         // relies on this); joining gives one FIFO all 8 entries.
  //         const join = SHIFTCTRL_FJOIN_TX | SHIFTCTRL_FJOIN_RX;
  //         if ((value ^ this.shiftCtrl) & join) {
  //           const tx = value & SHIFTCTRL_FJOIN_TX ? 8 : value & SHIFTCTRL_FJOIN_RX ? 0 : 4;
  //           const rx = value & SHIFTCTRL_FJOIN_RX ? 8 : value & SHIFTCTRL_FJOIN_TX ? 0 : 4;
  //           this.txFIFO.resize(tx);
  //           this.rxFIFO.resize(rx);
  //           this.updateDMATx();
  //           this.updateDMARx();
  //         }
  //         this.shiftCtrl = value >>> 0;
  //         break;
  //       }
  //       case SM0_ADDR:
  //         /* read-only */
  //         break;
  //       case SM0_INSTR:
  //         this.executeInstruction(value & 0xffff);
  //         if (this.waiting) {
  //           this.execCtrl |= EXECCTRL_EXEC_STALLED;
  //         }
  //         break;
  //       case SM0_PINCTRL:
  //         this.pinCtrl = value;
  //         break;
  //       default:
  //         this.pio.error(`Write to invalid state machine register: ${offset}`);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/pio.ts", "StateMachine::writeUint32");
}

uint32_t StateMachine::fifoStat() const {
  // TODO(port): peripherals/pio.ts
  //   get fifoStat() {
  //     const result =
  //       (this.txFIFO.empty ? FSTAT_TXEMPTY : 0) |
  //       (this.txFIFO.full ? FSTAT_TXFULL : 0) |
  //       (this.rxFIFO.empty ? FSTAT_RXEMPTY : 0) |
  //       (this.rxFIFO.full ? FSTAT_RXFULL : 0);
  //     return result << this.index;
  //   }
  return 0;
}

void StateMachine::restart() {
  // TODO(port): peripherals/pio.ts
  //   restart() {
  //     this.cycles = 0;
  //     this.delayLeft = 0;
  //     this.inputShiftCount = 0;
  //     this.outputShiftCount = 32;
  //     this.inputShiftReg = 0;
  //     this.waiting = false;
  //     // TODO any pin write left asserted due to OUT_STICKY.
  //   }
}

void StateMachine::clkDivRestart() {
  // TODO(port): peripherals/pio.ts
  //   clkDivRestart() {
  //     this.divPhase = 0;
  //   }
}

void StateMachine::clockTick() {
  // TODO(port): peripherals/pio.ts
  //   clockTick() {
  //     if (!this.enabled) {
  //       return;
  //     }
  //     const div = (this.clockDivInt || 65536) * 256 + this.clockDivFrac;
  //     this.divPhase += 256;
  //     if (this.divPhase >= div) {
  //       this.divPhase -= div;
  //       this.step();
  //     }
  //   }
  TODO_PORT_ABORT("peripherals/pio.ts", "StateMachine::clockTick");
}

void StateMachine::checkWait() {
  // TODO(port): peripherals/pio.ts
  //   checkWait() {
  //     if (!this.waiting) {
  //       return;
  //     }
  //
  //     switch (this.waitType) {
  //       case WaitType.IRQ: {
  //         const irqValue = !!(this.pio.irq & (1 << this.waitIndex));
  //         if (irqValue === this.waitPolarity) {
  //           this.waiting = false;
  //           if (irqValue) {
  //             this.pio.irq &= ~(1 << this.waitIndex);
  //           }
  //         }
  //         break;
  //       }
  //
  //       case WaitType.Pin: {
  //         if (
  //           this.waitIndex < this.rp2040.gpio.length &&
  //           this.rp2040.gpio[this.waitIndex].inputValue === this.waitPolarity
  //         ) {
  //           this.waiting = false;
  //         }
  //         break;
  //       }
  //
  //       case WaitType.rxFIFO: {
  //         if (!this.rxFIFO.full) {
  //           this.rxFIFO.push(this.waitIndex);
  //           this.waiting = false;
  //           this.updateDMARx();
  //           this.pio.checkInterrupts();
  //         }
  //         break;
  //       }
  //
  //       case WaitType.txFIFO: {
  //         if (!this.txFIFO.empty) {
  //           this.outputShiftReg = this.txFIFO.pull();
  //           this.waiting = false;
  //           this.updateDMATx();
  //           this.pio.checkInterrupts();
  //         }
  //         break;
  //       }
  //
  //       case WaitType.Out: {
  //         if (!this.txFIFO.empty) {
  //           this.outputShiftReg = this.txFIFO.pull();
  //           this.outInstruction(this.waitIndex);
  //           this.waiting = false;
  //           this.updateDMATx();
  //           this.pio.checkInterrupts();
  //         }
  //         break;
  //       }
  //     }
  //
  //     if (!this.waiting) {
  //       this.nextPC();
  //       this.cycles += this.waitDelay;
  //       // a stalled instruction's delay starts once it completes
  //       this.delayLeft = Math.max(0, this.waitDelay);
  //       this.execCtrl &= ~EXECCTRL_EXEC_STALLED;
  //     }
  //   }
}

RPPIO::RPPIO(RP2040 &rp2040, const std::string &name, uint32_t firstIrq, uint32_t index)
    : BasePeripheral(rp2040, name),
      firstIrq(firstIrq),
      index(index),
      dreqRx(index ? dreqRx1 : dreqRx0),
      dreqTx(index ? dreqTx1 : dreqTx0),
      machines{{{rp2040, *this, 0}, {rp2040, *this, 1}, {rp2040, *this, 2}, {rp2040, *this, 3}}} {
  // TODO(port): peripherals/pio.ts
  //   constructor(
  //     rp2040: RP2040,
  //     name: string,
  //     readonly firstIrq: number,
  //     readonly index: number,
  //   ) {
  //     super(rp2040, name);
  //   }
  (void)rp2040;
  (void)name;
  (void)firstIrq;
  (void)index;
  run = [] {
    // TODO(port): peripherals/pio.ts (no setTimeout: one batch, see pio.h)
    //   run() {
    //     for (let i = 0; i < 1000 && !this.stopped; i++) {
    //       this.step();
    //     }
    //     if (!this.stopped) {
    //       this.runTimer = setTimeout(() => this.run(), 0);
    //     }
    //   }
    TODO_PORT_ABORT("peripherals/pio.ts", "RPPIO::run");
  };
}

uint32_t RPPIO::intRaw() const {
  // TODO(port): peripherals/pio.ts
  //   get intRaw() {
  //     return (
  //       ((this.irq & 0xf) << 8) |
  //       (!this.machines[3].txFIFO.full ? 0x80 : 0) |
  //       (!this.machines[2].txFIFO.full ? 0x40 : 0) |
  //       (!this.machines[1].txFIFO.full ? 0x20 : 0) |
  //       (!this.machines[0].txFIFO.full ? 0x10 : 0) |
  //       (!this.machines[3].rxFIFO.empty ? 0x08 : 0) |
  //       (!this.machines[2].rxFIFO.empty ? 0x04 : 0) |
  //       (!this.machines[1].rxFIFO.empty ? 0x02 : 0) |
  //       (!this.machines[0].rxFIFO.empty ? 0x01 : 0)
  //     );
  //   }
  return 0;
}

uint32_t RPPIO::irq0IntStatus() const {
  // TODO(port): peripherals/pio.ts
  //   get irq0IntStatus() {
  //     return (this.intRaw & this.irq0IntEnable) | this.irq0IntForce;
  //   }
  return 0;
}

uint32_t RPPIO::irq1IntStatus() const {
  // TODO(port): peripherals/pio.ts
  //   get irq1IntStatus() {
  //     return (this.intRaw & this.irq1IntEnable) | this.irq1IntForce;
  //   }
  return 0;
}

uint32_t RPPIO::readUint32(uint32_t offset) {
  // TODO(port): peripherals/pio.ts
  //   readUint32(offset: number) {
  //     if (offset >= SM0_CLKDIV && offset <= SM0_PINCTRL) {
  //       return this.machines[0].readUint32(offset - SM0_CLKDIV);
  //     }
  //     if (offset >= SM1_CLKDIV && offset <= SM1_PINCTRL) {
  //       return this.machines[1].readUint32(offset - SM1_CLKDIV);
  //     }
  //     if (offset >= SM2_CLKDIV && offset <= SM2_PINCTRL) {
  //       return this.machines[2].readUint32(offset - SM2_CLKDIV);
  //     }
  //     if (offset >= SM3_CLKDIV && offset <= SM3_PINCTRL) {
  //       return this.machines[3].readUint32(offset - SM3_CLKDIV);
  //     }
  //
  //     switch (offset) {
  //       case CTRL:
  //         return (
  //           (this.machines[0].enabled ? 1 << 0 : 0) |
  //           (this.machines[1].enabled ? 1 << 1 : 0) |
  //           (this.machines[2].enabled ? 1 << 2 : 0) |
  //           (this.machines[3].enabled ? 1 << 3 : 0)
  //         );
  //       case FSTAT:
  //         return (
  //           this.machines[0].fifoStat |
  //           this.machines[1].fifoStat |
  //           this.machines[2].fifoStat |
  //           this.machines[3].fifoStat
  //         );
  //       case FDEBUG:
  //         return this.fdebug;
  //       case FLEVEL:
  //         return (
  //           (this.machines[0].txFIFO.itemCount & 0xf) |
  //           ((this.machines[0].rxFIFO.itemCount & 0xf) << 4) |
  //           ((this.machines[1].txFIFO.itemCount & 0xf) << 8) |
  //           ((this.machines[1].rxFIFO.itemCount & 0xf) << 12) |
  //           ((this.machines[2].txFIFO.itemCount & 0xf) << 16) |
  //           ((this.machines[2].rxFIFO.itemCount & 0xf) << 20) |
  //           ((this.machines[3].txFIFO.itemCount & 0xf) << 24) |
  //           ((this.machines[3].rxFIFO.itemCount & 0xf) << 28)
  //         );
  //
  //       case RXF0:
  //         return this.machines[0].readFIFO();
  //       case RXF1:
  //         return this.machines[1].readFIFO();
  //       case RXF2:
  //         return this.machines[2].readFIFO();
  //       case RXF3:
  //         return this.machines[3].readFIFO();
  //       case IRQ:
  //         return this.irq;
  //       case IRQ_FORCE:
  //         return 0;
  //       case INPUT_SYNC_BYPASS:
  //         return this.inputSyncBypass;
  //       case DBG_PADOUT:
  //         return this.pinValues;
  //       case DBG_PADOE:
  //         return this.pinDirections;
  //       case DBG_CFGINFO:
  //         return 0x200404;
  //       case INTR:
  //         return this.intRaw;
  //       case IRQ0_INTE:
  //         return this.irq0IntEnable;
  //       case IRQ0_INTF:
  //         return this.irq0IntForce;
  //       case IRQ0_INTS:
  //         return this.irq0IntStatus;
  //       case IRQ1_INTE:
  //         return this.irq1IntEnable;
  //       case IRQ1_INTF:
  //         return this.irq1IntForce;
  //       case IRQ1_INTS:
  //         return this.irq1IntStatus;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/pio.ts", "RPPIO::readUint32");
}

void RPPIO::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/pio.ts
  //   writeUint32(offset: number, value: number) {
  //     if (offset >= INSTR_MEM0 && offset <= INSTR_MEM31) {
  //       const index = (offset - INSTR_MEM0) >> 2;
  //       this.instructions[index] = value & 0xffff;
  //       return;
  //     }
  //     if (offset >= SM0_CLKDIV && offset <= SM0_PINCTRL) {
  //       this.machines[0].writeUint32(offset - SM0_CLKDIV, value);
  //       return;
  //     }
  //     if (offset >= SM1_CLKDIV && offset <= SM1_PINCTRL) {
  //       this.machines[1].writeUint32(offset - SM1_CLKDIV, value);
  //       return;
  //     }
  //     if (offset >= SM2_CLKDIV && offset <= SM2_PINCTRL) {
  //       this.machines[2].writeUint32(offset - SM2_CLKDIV, value);
  //       return;
  //     }
  //     if (offset >= SM3_CLKDIV && offset <= SM3_PINCTRL) {
  //       this.machines[3].writeUint32(offset - SM3_CLKDIV, value);
  //       return;
  //     }
  //     switch (offset) {
  //       case CTRL: {
  //         for (let index = 0; index < 4; index++) {
  //           this.machines[index].enabled = value & (1 << index) ? true : false;
  //           if (value & (1 << (4 + index))) {
  //             this.machines[index].restart();
  //           }
  //           if (value & (1 << (8 + index))) {
  //             this.machines[index].clkDivRestart();
  //           }
  //         }
  //         const shouldRun = value & 0xf;
  //         if (this.stopped && shouldRun) {
  //           this.stopped = false;
  //           this.run();
  //         }
  //         if (!shouldRun) {
  //           this.stopped = true;
  //         }
  //         break;
  //       }
  //       case FDEBUG:
  //         this.fdebug &= ~this.rawWriteValue;
  //         this.fdebug |= this.txStall | this.rxStall;
  //         break;
  //       case TXF0:
  //         this.machines[0].writeFIFO(value);
  //         break;
  //       case TXF1:
  //         this.machines[1].writeFIFO(value);
  //         break;
  //       case TXF2:
  //         this.machines[2].writeFIFO(value);
  //         break;
  //       case TXF3:
  //         this.machines[3].writeFIFO(value);
  //         break;
  //       case IRQ:
  //         this.irq &= ~this.rawWriteValue;
  //         this.irqUpdated();
  //         break;
  //       case INPUT_SYNC_BYPASS:
  //         this.inputSyncBypass = value;
  //         break;
  //       case IRQ_FORCE:
  //         this.irq |= value;
  //         this.irqUpdated();
  //         break;
  //       case IRQ0_INTE:
  //         this.irq0IntEnable = value & 0xfff;
  //         this.checkInterrupts();
  //         break;
  //       case IRQ0_INTF:
  //         this.irq0IntForce = value & 0xfff;
  //         this.checkInterrupts();
  //         break;
  //       case IRQ1_INTE:
  //         this.irq1IntEnable = value & 0xfff;
  //         this.checkInterrupts();
  //         break;
  //       case IRQ1_INTF:
  //         this.irq1IntForce = value & 0xfff;
  //         this.checkInterrupts();
  //         break;
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/pio.ts", "RPPIO::writeUint32");
}

void RPPIO::pinValuesChanged(uint32_t value, uint32_t firstPin, uint32_t count) {
  // TODO(port): peripherals/pio.ts
  //   pinValuesChanged(value: number, firstPin: number, count: number) {
  //     // TODO: wrapping after pin 31
  //     const mask = count > 31 ? 0xffffffff : ((1 << count) - 1) << firstPin;
  //     const newValue = ((this.pinValues & ~mask) | ((value << firstPin) & mask)) & 0x3fffffff;
  //     this.pinValues = newValue;
  //   }
  (void)value;
  (void)firstPin;
  (void)count;
}

void RPPIO::pinDirectionsChanged(uint32_t value, uint32_t firstPin, uint32_t count) {
  // TODO(port): peripherals/pio.ts
  //   pinDirectionsChanged(value: number, firstPin: number, count: number) {
  //     // TODO: wrapping after pin 31
  //     const mask = count > 31 ? 0xffffffff : ((1 << count) - 1) << firstPin;
  //     const newValue = ((this.pinDirections & ~mask) | ((value << firstPin) & mask)) & 0x3fffffff;
  //     this.pinDirections = newValue;
  //   }
  (void)value;
  (void)firstPin;
  (void)count;
}

void RPPIO::checkInterrupts() {
  // TODO(port): peripherals/pio.ts
  //   checkInterrupts() {
  //     const { firstIrq } = this;
  //     this.rp2040.setInterrupt(firstIrq, !!this.irq0IntStatus);
  //     this.rp2040.setInterrupt(firstIrq + 1, !!this.irq1IntStatus);
  //   }
}

void RPPIO::irqUpdated() {
  // TODO(port): peripherals/pio.ts
  //   irqUpdated() {
  //     for (const machine of this.machines) {
  //       machine.checkWait();
  //     }
  //     this.checkInterrupts();
  //   }
}

void RPPIO::checkChangedPins() {
  // TODO(port): peripherals/pio.ts
  //   checkChangedPins() {
  //     const changedPins =
  //       (this.oldPinDirections ^ this.pinDirections) | (this.oldPinValues ^ this.pinValues);
  //     if (changedPins) {
  //       this.oldPinDirections = this.pinDirections;
  //       this.oldPinValues = this.pinValues;
  //
  //       // Notify GPIO about the changed pins
  //       const { gpio } = this.rp2040;
  //       for (let gpioIndex = 0; gpioIndex < gpio.length; gpioIndex++) {
  //         if (changedPins & (1 << gpioIndex)) {
  //           gpio[gpioIndex].checkForUpdates();
  //         }
  //       }
  //     }
  //   }
}

void RPPIO::step() {
  // TODO(port): peripherals/pio.ts
  //   step() {
  //     for (const machine of this.machines) {
  //       machine.clockTick();
  //     }
  //     this.checkChangedPins();
  //   }
  TODO_PORT_ABORT("peripherals/pio.ts", "RPPIO::step");
}

void RPPIO::stop() {
  // TODO(port): peripherals/pio.ts
  //   stop() {
  //     for (const machine of this.machines) {
  //       machine.enabled = false;
  //     }
  //     this.stopped = true;
  //     if (this.runTimer) {
  //       clearTimeout(this.runTimer);
  //       this.runTimer = null;
  //     }
  //   }
}

}  // namespace rp2040js
