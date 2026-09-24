// Port of rp2040js src/peripherals/i2c.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "i2c.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

RPI2C::RPI2C(RP2040 &rp2040, const std::string &name, uint32_t irq)
    : BasePeripheral(rp2040, name),
      // IC_SLAVE_DISABLE | IC_RESTART_EN | (I2CSpeed.FastMode << SPEED_SHIFT) | MASTER_MODE
      control((1 << 6) | (1 << 5) | (2 << 1) | (1 << 0)),
      irq(irq) {
  // TODO(port): peripherals/i2c.ts
  //   constructor(
  //     rp2040: RP2040,
  //     name: string,
  //     readonly irq: number,
  //   ) {
  //     super(rp2040, name);
  //   }
  (void)rp2040;
  (void)name;
  (void)irq;
  // TODO(port): the callback defaults
  //   onStart: (repeatedStart: boolean) => void = () => this.completeStart();
  //   onConnect: (address: number, mode: I2CMode) => void = () => this.completeConnect(false);
  //   onWriteByte: (value: number) => void = () => this.completeWrite(false);
  //   onReadByte: (ack: boolean) => void = () => this.completeRead(0xff);
  //   onStop: () => void = () => this.completeStop();
}

uint32_t RPI2C::intStatus() const {
  // TODO(port): peripherals/i2c.ts
  //   get intStatus() {
  //     return this.intRaw & this.intEnable;
  //   }
  return 0;
}

I2CSpeed RPI2C::speed() const {
  // TODO(port): peripherals/i2c.ts
  //   get speed() {
  //     return ((this.control >> SPEED_SHIFT) & SPEED_MASK) as I2CSpeed;
  //   }
  return I2CSpeed::Invalid;
}

uint32_t RPI2C::sclLowPeriod() const {
  // TODO(port): peripherals/i2c.ts
  //   get sclLowPeriod() {
  //     return this.speed === I2CSpeed.Standard ? this.ssClockLowPeriod : this.fsClockLowPeriod;
  //   }
  return 0;
}

uint32_t RPI2C::sclHighPeriod() const {
  // TODO(port): peripherals/i2c.ts
  //   get sclHighPeriod() {
  //     return this.speed === I2CSpeed.Standard ? this.ssClockHighPeriod : this.fsClockHighPeriod;
  //   }
  return 0;
}

uint32_t RPI2C::masterBits() const {
  // TODO(port): peripherals/i2c.ts
  //   get masterBits() {
  //     return this.control & IC_10BITADDR_MASTER ? 10 : 7;
  //   }
  return 0;
}

void RPI2C::checkInterrupts() {
  // TODO(port): peripherals/i2c.ts
  //   checkInterrupts() {
  //     this.rp2040.setInterrupt(this.irq, !!this.intStatus);
  //   }
}

void RPI2C::clearInterrupts(uint32_t mask) {
  // TODO(port): peripherals/i2c.ts
  //   protected clearInterrupts(mask: number) {
  //     if (this.intRaw & mask) {
  //       this.intRaw &= ~mask;
  //       this.checkInterrupts();
  //       return 1;
  //     } else {
  //       return 0;
  //     }
  //   }
  (void)mask;
}

void RPI2C::setInterrupts(uint32_t mask) {
  // TODO(port): peripherals/i2c.ts
  //   protected setInterrupts(mask: number) {
  //     if (!(this.intRaw & mask)) {
  //       this.intRaw |= mask;
  //       this.checkInterrupts();
  //     }
  //   }
  (void)mask;
}

void RPI2C::abort(uint32_t reason) {
  // TODO(port): peripherals/i2c.ts
  //   protected abort(reason: number) {
  //     this.abortSource &= ~TX_FLUSH_CNT_MASK;
  //     this.abortSource |= reason | (this.txFIFO.itemCount << TX_FLUSH_CNT_SHIFT);
  //     this.txFIFO.reset();
  //     this.setInterrupts(R_TX_ABRT);
  //   }
  (void)reason;
}

void RPI2C::nextCommand() {
  // TODO(port): peripherals/i2c.ts
  //   protected nextCommand() {
  //     const enabled = this.enable & ENABLE;
  //     const blocked = this.enable & TX_CMD_BLOCK;
  //     if (this.txFIFO.empty || this.busy || blocked || !enabled) {
  //       return;
  //     }
  //     this.busy = true;
  //     const restart = !!(this.txFIFO.peek() & RESTART) && !this.pendingRestart && !this.stop;
  //     if (this.state === I2CState.Idle || restart) {
  //       this.pendingRestart = restart;
  //       this.stop = false;
  //       this.state = I2CState.Start;
  //       this.onStart(restart);
  //       return;
  //     }
  //     this.pendingRestart = false;
  //     const cmd = this.txFIFO.pull();
  //     const readMode = !!(cmd & CMD);
  //     this.stop = !!(cmd & STOP);
  //     if (readMode) {
  //       this.onReadByte(!this.stop);
  //     } else {
  //       this.onWriteByte(cmd & 0xff);
  //     }
  //     if (this.txFIFO.itemCount <= this.txThreshold) {
  //       this.setInterrupts(R_TX_EMPTY);
  //     }
  //   }
}

void RPI2C::pushRX(uint32_t value) {
  // TODO(port): peripherals/i2c.ts
  //   protected pushRX(value: number) {
  //     if (this.rxFIFO.full) {
  //       this.setInterrupts(R_RX_OVER);
  //       return;
  //     }
  //     this.rxFIFO.push(value);
  //     if (this.rxFIFO.itemCount > this.rxThreshold) {
  //       this.setInterrupts(R_RX_FULL);
  //     }
  //   }
  (void)value;
}

void RPI2C::completeStart() {
  // TODO(port): peripherals/i2c.ts
  //   completeStart() {
  //     if (this.txFIFO.empty || this.state !== I2CState.Start || this.stop) {
  //       this.onStop();
  //       return;
  //     }
  //     const mode = this.txFIFO.peek() & CMD ? I2CMode.Read : I2CMode.Write;
  //     this.state = I2CState.Connect;
  //     this.setInterrupts(R_START_DET);
  //     const addressMask = this.masterBits === 10 ? 0x3ff : 0xff;
  //     this.onConnect(this.targetAddress & addressMask, mode);
  //   }
}

void RPI2C::completeConnect(bool ack, uint32_t nackByte) {
  // TODO(port): peripherals/i2c.ts
  //   completeConnect(ack: boolean, nackByte = 0) {
  //     if (!ack || this.stop) {
  //       if (!ack) {
  //         if (!this.targetAddress) {
  //           this.abort(ABRT_GCALL_NOACK);
  //         } else if (this.control & IC_10BITADDR_MASTER) {
  //           this.abort(nackByte === 0 ? ABRT_10ADDR1_NOACK : ABRT_10ADDR2_NOACK);
  //         } else {
  //           this.abort(ABRT_7B_ADDR_NOACK);
  //         }
  //       }
  //       this.state = I2CState.Stop;
  //       this.onStop();
  //       return;
  //     }
  //
  //     this.state = I2CState.Connected;
  //     this.busy = false;
  //     this.firstByte = true;
  //     this.nextCommand();
  //   }
  (void)ack;
  (void)nackByte;
}

void RPI2C::completeWrite(bool ack) {
  // TODO(port): peripherals/i2c.ts
  //   completeWrite(ack: boolean) {
  //     if (!ack || this.stop) {
  //       if (!ack) {
  //         this.abort(ABRT_TXDATA_NOACK);
  //       }
  //       this.state = I2CState.Stop;
  //       this.onStop();
  //       return;
  //     }
  //
  //     this.busy = false;
  //     this.nextCommand();
  //   }
  (void)ack;
}

void RPI2C::completeRead(uint32_t value) {
  // TODO(port): peripherals/i2c.ts
  //   completeRead(value: number) {
  //     this.pushRX(value | (this.firstByte ? FIRST_DATA_BYTE : 0));
  //     if (this.stop) {
  //       this.state = I2CState.Stop;
  //       this.onStop();
  //       return;
  //     }
  //     this.firstByte = false;
  //     this.busy = false;
  //     this.nextCommand();
  //   }
  (void)value;
}

void RPI2C::completeStop() {
  // TODO(port): peripherals/i2c.ts
  //   completeStop() {
  //     this.state = I2CState.Idle;
  //     this.setInterrupts(R_STOP_DET);
  //     this.busy = false;
  //     this.pendingRestart = false;
  //     if (this.enable & ABORT) {
  //       this.enable &= ~ABORT;
  //     } else {
  //       this.nextCommand();
  //     }
  //   }
}

void RPI2C::arbitrationLost() {
  // TODO(port): peripherals/i2c.ts
  //   arbitrationLost() {
  //     this.state = I2CState.Idle;
  //     this.busy = false;
  //     this.abort(ARB_LOST);
  //   }
}

uint32_t RPI2C::readUint32(uint32_t offset) {
  // TODO(port): peripherals/i2c.ts
  //   readUint32(offset: number) {
  //     switch (offset) {
  //       case IC_CON:
  //         return this.control;
  //       case IC_TAR:
  //         return this.targetAddress;
  //       case IC_SAR:
  //         return this.slaveAddress;
  //       case IC_DATA_CMD:
  //         if (this.rxFIFO.empty) {
  //           this.setInterrupts(R_RX_UNDER);
  //           return 0;
  //         }
  //         this.clearInterrupts(R_RX_FULL);
  //         return this.rxFIFO.pull();
  //       case IC_SS_SCL_HCNT:
  //         return this.ssClockHighPeriod;
  //       case IC_SS_SCL_LCNT:
  //         return this.ssClockLowPeriod;
  //       case IC_FS_SCL_HCNT:
  //         return this.fsClockHighPeriod;
  //       case IC_FS_SCL_LCNT:
  //         return this.fsClockLowPeriod;
  //       case IC_INTR_STAT:
  //         return this.intStatus;
  //       case IC_INTR_MASK:
  //         return this.intEnable;
  //       case IC_RAW_INTR_STAT:
  //         return this.intRaw;
  //       case IC_RX_TL:
  //         return this.rxThreshold;
  //       case IC_TX_TL:
  //         return this.txThreshold;
  //       case IC_CLR_INTR:
  //         this.abortSource &= ABRT_SBYTE_NORSTRT; // Clear IC_TX_ABRT_SOURCE, expect for bit 9
  //         return this.clearInterrupts(
  //           R_RX_UNDER |
  //             R_RX_OVER |
  //             R_TX_OVER |
  //             R_RD_REQ |
  //             R_TX_ABRT |
  //             R_RX_DONE |
  //             R_ACTIVITY |
  //             R_STOP_DET |
  //             R_START_DET |
  //             R_GEN_CALL,
  //         );
  //       case IC_CLR_RX_UNDER:
  //         return this.clearInterrupts(R_RX_UNDER);
  //       case IC_CLR_RX_OVER:
  //         return this.clearInterrupts(R_RX_OVER);
  //       case IC_CLR_TX_OVER:
  //         return this.clearInterrupts(R_TX_OVER);
  //       case IC_CLR_RD_REQ:
  //         return this.clearInterrupts(R_RD_REQ);
  //       case IC_CLR_TX_ABRT:
  //         this.abortSource &= ABRT_SBYTE_NORSTRT; // Clear IC_TX_ABRT_SOURCE, expect for bit 9
  //         return this.clearInterrupts(R_TX_ABRT);
  //       case IC_CLR_RX_DONE:
  //         return this.clearInterrupts(R_RX_DONE);
  //       case IC_CLR_ACTIVITY:
  //         return this.clearInterrupts(R_ACTIVITY);
  //       case IC_CLR_STOP_DET:
  //         return this.clearInterrupts(R_STOP_DET);
  //       case IC_CLR_START_DET:
  //         return this.clearInterrupts(R_START_DET);
  //       case IC_CLR_GEN_CALL:
  //         return this.clearInterrupts(R_GEN_CALL);
  //       case IC_ENABLE:
  //         return this.enable;
  //       case IC_STATUS:
  //         return (
  //           (this.state !== I2CState.Idle ? MST_ACTIVITY | ACTIVITY : 0) |
  //           (this.rxFIFO.full ? RFF : 0) |
  //           (!this.rxFIFO.empty ? RFNE : 0) |
  //           (this.txFIFO.empty ? TFE : 0) |
  //           (!this.txFIFO.full ? TFNF : 0)
  //         );
  //       case IC_TXFLR:
  //         return this.txFIFO.itemCount;
  //       case IC_RXFLR:
  //         return this.rxFIFO.itemCount;
  //       case IC_SDA_HOLD:
  //         return 0x01;
  //       case IC_TX_ABRT_SOURCE: {
  //         const value = this.abortSource;
  //         this.abortSource &= ABRT_SBYTE_NORSTRT; // Clear IC_TX_ABRT_SOURCE, expect for bit 9
  //         return value;
  //       }
  //       case IC_ENABLE_STATUS:
  //         // I2C status - read only. bit 0 reflects IC_ENABLE, bit 1,2 relate to i2c slave mode.
  //         return this.enable & 0x1;
  //       case IC_FS_SPKLEN:
  //         return this.spikelen & 0xff;
  //       case IC_COMP_PARAM_1:
  //         // From the datasheet:
  //         // Note This register is not implemented and therefore reads as 0. If it was implemented it would be a constant read-only
  //         // register that contains encoded information about the component's parameter settings.
  //         return 0;
  //       case IC_COMP_VERSION:
  //         return 0x3230312a;
  //       case IC_COMP_TYPE:
  //         return 0x44570140;
  //     }
  //     return super.readUint32(offset);
  //   }
  (void)offset;
  TODO_PORT_ABORT("peripherals/i2c.ts", "RPI2C::readUint32");
}

void RPI2C::writeUint32(uint32_t offset, uint32_t value) {
  // TODO(port): peripherals/i2c.ts
  //   writeUint32(offset: number, value: number) {
  //     switch (offset) {
  //       case IC_CON:
  //         if (((value >> SPEED_SHIFT) & SPEED_MASK) === I2CSpeed.Invalid) {
  //           value = (value & ~(SPEED_MASK << SPEED_SHIFT)) | (I2CSpeed.HighSpeedMode << SPEED_SHIFT);
  //         }
  //         this.control = value;
  //         return;
  //
  //       case IC_TAR:
  //         this.targetAddress = value & 0x3ff;
  //         return;
  //
  //       case IC_SAR:
  //         this.slaveAddress = value & 0x3ff;
  //         return;
  //
  //       case IC_DATA_CMD:
  //         if (this.txFIFO.full) {
  //           this.setInterrupts(R_TX_OVER);
  //         } else {
  //           this.txFIFO.push(value);
  //           this.clearInterrupts(R_TX_EMPTY);
  //           this.nextCommand();
  //         }
  //         return;
  //
  //       case IC_SS_SCL_HCNT:
  //         this.ssClockHighPeriod = value & 0xffff;
  //         return;
  //
  //       case IC_SS_SCL_LCNT:
  //         this.ssClockLowPeriod = value & 0xffff;
  //         return;
  //
  //       case IC_FS_SCL_HCNT:
  //         this.fsClockHighPeriod = value & 0xffff;
  //         return;
  //
  //       case IC_FS_SCL_LCNT:
  //         this.fsClockLowPeriod = value & 0xffff;
  //         return;
  //
  //       case IC_SDA_HOLD:
  //         if (!(value & ENABLE)) {
  //           if (value != 0x1) {
  //             this.warn('Unimplemented write to IC_SDA_HOLD');
  //           }
  //         }
  //         return;
  //
  //       case IC_RX_TL:
  //         this.rxThreshold = value & 0xff;
  //         if (this.rxThreshold > this.rxFIFO.size) {
  //           this.rxThreshold = this.rxFIFO.size;
  //         }
  //         return;
  //
  //       case IC_TX_TL:
  //         this.txThreshold = value & 0xff;
  //         if (this.txThreshold > this.txFIFO.size) {
  //           this.txThreshold = this.txFIFO.size;
  //         }
  //         return;
  //
  //       case IC_ENABLE:
  //         // ABORT bit can only be set by software, not cleared.
  //         value |= this.enable & ABORT;
  //         if (value & ABORT) {
  //           if (this.state === I2CState.Idle) {
  //             value &= ~ABORT;
  //           } else {
  //             this.abort(ABRT_USER_ABRT);
  //             this.stop = true;
  //           }
  //         }
  //         if (!(value & ENABLE)) {
  //           this.txFIFO.reset();
  //           this.rxFIFO.reset();
  //         }
  //         this.enable = value;
  //         this.nextCommand(); // TX_CMD_BLOCK may have changed
  //         return;
  //
  //       case IC_FS_SPKLEN:
  //         if (!(value & ENABLE) && value > 0) {
  //           this.spikelen = value;
  //         }
  //         return;
  //
  //       default:
  //         super.writeUint32(offset, value);
  //     }
  //   }
  (void)offset;
  (void)value;
  TODO_PORT_ABORT("peripherals/i2c.ts", "RPI2C::writeUint32");
}

}  // namespace rp2040js
