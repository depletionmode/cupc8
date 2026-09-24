// Port of rp2040js src/peripherals/i2c.ts
#include "i2c.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t IC_CON = 0x00;                 // I2C Control Register
static constexpr uint32_t IC_TAR = 0x04;                 // I2C Target Address Register
static constexpr uint32_t IC_SAR = 0x08;                 // I2C Slave Address Register
static constexpr uint32_t IC_DATA_CMD = 0x10;            // I2C Rx/Tx Data Buffer and Command Register
static constexpr uint32_t IC_SS_SCL_HCNT = 0x14;         // Standard Speed I2C Clock SCL High Count Register
static constexpr uint32_t IC_SS_SCL_LCNT = 0x18;         // Standard Speed I2C Clock SCL Low Count Register
static constexpr uint32_t IC_FS_SCL_HCNT = 0x1c;  // Fast Mode or Fast Mode Plus I2C Clock SCL High Count Register
static constexpr uint32_t IC_FS_SCL_LCNT = 0x20;  // Fast Mode or Fast Mode Plus I2C Clock SCL Low Count Register
static constexpr uint32_t IC_INTR_STAT = 0x2c;           // I2C Interrupt Status Register
static constexpr uint32_t IC_INTR_MASK = 0x30;           // I2C Interrupt Mask Register
static constexpr uint32_t IC_RAW_INTR_STAT = 0x34;       // I2C Raw Interrupt Status Register
static constexpr uint32_t IC_RX_TL = 0x38;               // I2C Receive FIFO Threshold Register
static constexpr uint32_t IC_TX_TL = 0x3c;               // I2C Transmit FIFO Threshold Register
static constexpr uint32_t IC_CLR_INTR = 0x40;            // Clear Combined and Individual Interrupt Register
static constexpr uint32_t IC_CLR_RX_UNDER = 0x44;        // Clear RX_UNDER Interrupt Register
static constexpr uint32_t IC_CLR_RX_OVER = 0x48;         // Clear RX_OVER Interrupt Register
static constexpr uint32_t IC_CLR_TX_OVER = 0x4c;         // Clear TX_OVER Interrupt Register
static constexpr uint32_t IC_CLR_RD_REQ = 0x50;          // Clear RD_REQ Interrupt Register
static constexpr uint32_t IC_CLR_TX_ABRT = 0x54;         // Clear TX_ABRT Interrupt Register
static constexpr uint32_t IC_CLR_RX_DONE = 0x58;         // Clear RX_DONE Interrupt Register
static constexpr uint32_t IC_CLR_ACTIVITY = 0x5c;        // Clear ACTIVITY Interrupt Register
static constexpr uint32_t IC_CLR_STOP_DET = 0x60;        // Clear STOP_DET Interrupt Register
static constexpr uint32_t IC_CLR_START_DET = 0x64;       // Clear START_DET Interrupt Register
static constexpr uint32_t IC_CLR_GEN_CALL = 0x68;        // Clear GEN_CALL Interrupt Register
static constexpr uint32_t IC_ENABLE = 0x6c;              // I2C ENABLE Register
static constexpr uint32_t IC_STATUS = 0x70;              // I2C STATUS Register
static constexpr uint32_t IC_TXFLR = 0x74;               // I2C Transmit FIFO Level Register
static constexpr uint32_t IC_RXFLR = 0x78;               // I2C Receive FIFO Level Register
static constexpr uint32_t IC_SDA_HOLD = 0x7c;            // I2C SDA Hold Time Length Register
static constexpr uint32_t IC_TX_ABRT_SOURCE = 0x80;      // I2C Transmit Abort Source Register
static constexpr uint32_t IC_SLV_DATA_NACK_ONLY = 0x84;  // Generate Slave Data NACK Register
static constexpr uint32_t IC_DMA_CR = 0x88;              // DMA Control Register
static constexpr uint32_t IC_DMA_TDLR = 0x8c;            // DMA Transmit Data Level Register
static constexpr uint32_t IC_DMA_RDLR = 0x90;            // DMA Transmit Data Level Register
static constexpr uint32_t IC_SDA_SETUP = 0x94;           // I2C SDA Setup Register
static constexpr uint32_t IC_ACK_GENERAL_CALL = 0x98;    // I2C ACK General Call Register
static constexpr uint32_t IC_ENABLE_STATUS = 0x9c;       // I2C Enable Status Register
static constexpr uint32_t IC_FS_SPKLEN = 0xa0;           // I2C SS, FS or FM+ spike suppression limit
static constexpr uint32_t IC_CLR_RESTART_DET = 0xa8;     // Clear RESTART_DET Interrupt Register
static constexpr uint32_t IC_COMP_PARAM_1 = 0xf4;        // Component Parameter Register 1
static constexpr uint32_t IC_COMP_VERSION = 0xf8;        // I2C Component Version Register
static constexpr uint32_t IC_COMP_TYPE = 0xfc;           // I2C Component Type Register

// IC_CON bits:
static constexpr uint32_t STOP_DET_IF_MASTER_ACTIVE = 1 << 10;
static constexpr uint32_t RX_FIFO_FULL_HLD_CTRL = 1 << 9;
static constexpr uint32_t TX_EMPTY_CTRL = 1 << 8;
static constexpr uint32_t STOP_DET_IFADDRESSED = 1 << 7;
static constexpr uint32_t IC_SLAVE_DISABLE = 1 << 6;
static constexpr uint32_t IC_RESTART_EN = 1 << 5;
static constexpr uint32_t IC_10BITADDR_MASTER = 1 << 4;
static constexpr uint32_t IC_10BITADDR_SLAVE = 1 << 3;
static constexpr uint32_t SPEED_SHIFT = 1;
static constexpr uint32_t SPEED_MASK = 0x3;
static constexpr uint32_t MASTER_MODE = 1 << 0;

// IC_TAR bits:
static constexpr uint32_t SPECIAL = 1 << 11;
static constexpr uint32_t GC_OR_START = 1 << 10;

// IC_STATUS bits:
static constexpr uint32_t SLV_ACTIVITY = 1 << 6;
static constexpr uint32_t MST_ACTIVITY = 1 << 5;
static constexpr uint32_t RFF = 1 << 4;
static constexpr uint32_t RFNE = 1 << 3;
static constexpr uint32_t TFE = 1 << 2;
static constexpr uint32_t TFNF = 1 << 1;
static constexpr uint32_t ACTIVITY = 1 << 0;

// IC_ENABLE bits:
static constexpr uint32_t TX_CMD_BLOCK = 1 << 2;
static constexpr uint32_t ABORT = 1 << 1;
static constexpr uint32_t ENABLE = 1 << 0;

// IC_TX_ABRT_SOURCE bits:
static constexpr uint32_t TX_FLUSH_CNT_MASK = 0x1ff;
static constexpr uint32_t TX_FLUSH_CNT_SHIFT = 23;
static constexpr uint32_t ABRT_USER_ABRT = 1 << 16;
static constexpr uint32_t ABRT_SLVRD_INT = 1 << 15;
static constexpr uint32_t ABRT_SLV_ARBLOST = 1 << 14;
static constexpr uint32_t ABRT_SLVFLUSH_TXFIFO = 1 << 13;
static constexpr uint32_t ARB_LOST = 1 << 12;
static constexpr uint32_t ABRT_MASTER_DIS = 1 << 11;
static constexpr uint32_t ABRT_10B_RD_NORSTRT = 1 << 10;
static constexpr uint32_t ABRT_SBYTE_NORSTRT = 1 << 9;
static constexpr uint32_t ABRT_HS_NORSTRT = 1 << 8;
static constexpr uint32_t ABRT_SBYTE_ACKDET = 1 << 7;
static constexpr uint32_t ABRT_HS_ACKDET = 1 << 6;
static constexpr uint32_t ABRT_GCALL_READ = 1 << 5;
static constexpr uint32_t ABRT_GCALL_NOACK = 1 << 4;
static constexpr uint32_t ABRT_TXDATA_NOACK = 1 << 3;
static constexpr uint32_t ABRT_10ADDR2_NOACK = 1 << 2;
static constexpr uint32_t ABRT_10ADDR1_NOACK = 1 << 1;
static constexpr uint32_t ABRT_7B_ADDR_NOACK = 1 << 0;

// Interrupts
static constexpr uint32_t R_RESTART_DET = 1 << 12;  // Slave mode only
static constexpr uint32_t R_GEN_CALL = 1 << 11;
static constexpr uint32_t R_START_DET = 1 << 10;
static constexpr uint32_t R_STOP_DET = 1 << 9;
static constexpr uint32_t R_ACTIVITY = 1 << 8;
static constexpr uint32_t R_RX_DONE = 1 << 7;
static constexpr uint32_t R_TX_ABRT = 1 << 6;
static constexpr uint32_t R_RD_REQ = 1 << 5;
static constexpr uint32_t R_TX_EMPTY = 1 << 4;
static constexpr uint32_t R_TX_OVER = 1 << 3;
static constexpr uint32_t R_RX_FULL = 1 << 2;
static constexpr uint32_t R_RX_OVER = 1 << 1;
static constexpr uint32_t R_RX_UNDER = 1 << 0;

// FIFO entry bits
static constexpr uint32_t FIRST_DATA_BYTE = 1 << 10;
static constexpr uint32_t RESTART = 1 << 10;
static constexpr uint32_t STOP = 1 << 9;
static constexpr uint32_t CMD = 1 << 8;  // 0 for write, 1 for read

// Unused in the TS too; referenced so -Wunused stays quiet.
[[maybe_unused]] static constexpr uint32_t UNUSED_I2C_CONSTS[] = {
    IC_SLV_DATA_NACK_ONLY, IC_DMA_CR, IC_DMA_TDLR, IC_DMA_RDLR, IC_SDA_SETUP,
    IC_ACK_GENERAL_CALL, IC_CLR_RESTART_DET, STOP_DET_IF_MASTER_ACTIVE, RX_FIFO_FULL_HLD_CTRL,
    TX_EMPTY_CTRL, STOP_DET_IFADDRESSED, IC_10BITADDR_SLAVE, SPECIAL, GC_OR_START, SLV_ACTIVITY,
    ABRT_SLVRD_INT, ABRT_SLV_ARBLOST, ABRT_SLVFLUSH_TXFIFO, ABRT_MASTER_DIS, ABRT_10B_RD_NORSTRT,
    ABRT_HS_NORSTRT, ABRT_SBYTE_ACKDET, ABRT_HS_ACKDET, ABRT_GCALL_READ, R_RESTART_DET};

RPI2C::RPI2C(RP2040 &rp2040, const std::string &name, uint32_t irq)
    : BasePeripheral(rp2040, name),
      onStart([this](bool) { completeStart(); }),
      onConnect([this](uint32_t, I2CMode) { completeConnect(false); }),
      onWriteByte([this](uint32_t) { completeWrite(false); }),
      onReadByte([this](bool) { completeRead(0xff); }),
      onStop([this] { completeStop(); }),
      control(IC_SLAVE_DISABLE | IC_RESTART_EN |
              (static_cast<uint32_t>(I2CSpeed::FastMode) << SPEED_SHIFT) | MASTER_MODE),
      irq(irq) {}

uint32_t RPI2C::intStatus() const { return intRaw & intEnable; }

I2CSpeed RPI2C::speed() const { return static_cast<I2CSpeed>((control >> SPEED_SHIFT) & SPEED_MASK); }

uint32_t RPI2C::sclLowPeriod() const {
  return speed() == I2CSpeed::Standard ? ssClockLowPeriod : fsClockLowPeriod;
}

uint32_t RPI2C::sclHighPeriod() const {
  return speed() == I2CSpeed::Standard ? ssClockHighPeriod : fsClockHighPeriod;
}

uint32_t RPI2C::masterBits() const { return control & IC_10BITADDR_MASTER ? 10 : 7; }

void RPI2C::checkInterrupts() { rp2040.setInterrupt(irq, !!intStatus()); }

uint32_t RPI2C::clearInterrupts(uint32_t mask) {
  if (intRaw & mask) {
    intRaw &= ~mask;
    checkInterrupts();
    return 1;
  } else {
    return 0;
  }
}

void RPI2C::setInterrupts(uint32_t mask) {
  if (!(intRaw & mask)) {
    intRaw |= mask;
    checkInterrupts();
  }
}

void RPI2C::abort(uint32_t reason) {
  abortSource &= ~TX_FLUSH_CNT_MASK;
  abortSource |= reason | (txFIFO.itemCount() << TX_FLUSH_CNT_SHIFT);
  txFIFO.reset();
  setInterrupts(R_TX_ABRT);
}

void RPI2C::nextCommand() {
  const uint32_t enabled = enable & ENABLE;
  const uint32_t blocked = enable & TX_CMD_BLOCK;
  if (txFIFO.empty() || busy || blocked || !enabled) {
    return;
  }
  busy = true;
  const bool restart = !!(txFIFO.peek() & RESTART) && !pendingRestart && !stop;
  if (state == I2CState::Idle || restart) {
    pendingRestart = restart;
    stop = false;
    state = I2CState::Start;
    onStart(restart);
    return;
  }
  pendingRestart = false;
  const uint32_t cmd = txFIFO.pull();
  const bool readMode = !!(cmd & CMD);
  stop = !!(cmd & STOP);
  if (readMode) {
    onReadByte(!stop);
  } else {
    onWriteByte(cmd & 0xff);
  }
  if (txFIFO.itemCount() <= txThreshold) {
    setInterrupts(R_TX_EMPTY);
  }
}

void RPI2C::pushRX(uint32_t value) {
  if (rxFIFO.full()) {
    setInterrupts(R_RX_OVER);
    return;
  }
  rxFIFO.push(value);
  if (rxFIFO.itemCount() > rxThreshold) {
    setInterrupts(R_RX_FULL);
  }
}

void RPI2C::completeStart() {
  if (txFIFO.empty() || state != I2CState::Start || stop) {
    onStop();
    return;
  }
  const I2CMode mode = txFIFO.peek() & CMD ? I2CMode::Read : I2CMode::Write;
  state = I2CState::Connect;
  setInterrupts(R_START_DET);
  const uint32_t addressMask = masterBits() == 10 ? 0x3ff : 0xff;
  onConnect(targetAddress & addressMask, mode);
}

void RPI2C::completeConnect(bool ack, uint32_t nackByte) {
  if (!ack || stop) {
    if (!ack) {
      if (!targetAddress) {
        abort(ABRT_GCALL_NOACK);
      } else if (control & IC_10BITADDR_MASTER) {
        abort(nackByte == 0 ? ABRT_10ADDR1_NOACK : ABRT_10ADDR2_NOACK);
      } else {
        abort(ABRT_7B_ADDR_NOACK);
      }
    }
    state = I2CState::Stop;
    onStop();
    return;
  }

  state = I2CState::Connected;
  busy = false;
  firstByte = true;
  nextCommand();
}

void RPI2C::completeWrite(bool ack) {
  if (!ack || stop) {
    if (!ack) {
      abort(ABRT_TXDATA_NOACK);
    }
    state = I2CState::Stop;
    onStop();
    return;
  }

  busy = false;
  nextCommand();
}

void RPI2C::completeRead(uint32_t value) {
  pushRX(value | (firstByte ? FIRST_DATA_BYTE : 0));
  if (stop) {
    state = I2CState::Stop;
    onStop();
    return;
  }
  firstByte = false;
  busy = false;
  nextCommand();
}

void RPI2C::completeStop() {
  state = I2CState::Idle;
  setInterrupts(R_STOP_DET);
  busy = false;
  pendingRestart = false;
  if (enable & ABORT) {
    enable &= ~ABORT;
  } else {
    nextCommand();
  }
}

void RPI2C::arbitrationLost() {
  state = I2CState::Idle;
  busy = false;
  abort(ARB_LOST);
}

uint32_t RPI2C::readUint32(uint32_t offset) {
  switch (offset) {
    case IC_CON:
      return control;
    case IC_TAR:
      return targetAddress;
    case IC_SAR:
      return slaveAddress;
    case IC_DATA_CMD:
      if (rxFIFO.empty()) {
        setInterrupts(R_RX_UNDER);
        return 0;
      }
      clearInterrupts(R_RX_FULL);
      return rxFIFO.pull();
    case IC_SS_SCL_HCNT:
      return ssClockHighPeriod;
    case IC_SS_SCL_LCNT:
      return ssClockLowPeriod;
    case IC_FS_SCL_HCNT:
      return fsClockHighPeriod;
    case IC_FS_SCL_LCNT:
      return fsClockLowPeriod;
    case IC_INTR_STAT:
      return intStatus();
    case IC_INTR_MASK:
      return intEnable;
    case IC_RAW_INTR_STAT:
      return intRaw;
    case IC_RX_TL:
      return rxThreshold;
    case IC_TX_TL:
      return txThreshold;
    case IC_CLR_INTR:
      abortSource &= ABRT_SBYTE_NORSTRT;  // Clear IC_TX_ABRT_SOURCE, expect for bit 9
      return clearInterrupts(R_RX_UNDER | R_RX_OVER | R_TX_OVER | R_RD_REQ | R_TX_ABRT | R_RX_DONE |
                             R_ACTIVITY | R_STOP_DET | R_START_DET | R_GEN_CALL);
    case IC_CLR_RX_UNDER:
      return clearInterrupts(R_RX_UNDER);
    case IC_CLR_RX_OVER:
      return clearInterrupts(R_RX_OVER);
    case IC_CLR_TX_OVER:
      return clearInterrupts(R_TX_OVER);
    case IC_CLR_RD_REQ:
      return clearInterrupts(R_RD_REQ);
    case IC_CLR_TX_ABRT:
      abortSource &= ABRT_SBYTE_NORSTRT;  // Clear IC_TX_ABRT_SOURCE, expect for bit 9
      return clearInterrupts(R_TX_ABRT);
    case IC_CLR_RX_DONE:
      return clearInterrupts(R_RX_DONE);
    case IC_CLR_ACTIVITY:
      return clearInterrupts(R_ACTIVITY);
    case IC_CLR_STOP_DET:
      return clearInterrupts(R_STOP_DET);
    case IC_CLR_START_DET:
      return clearInterrupts(R_START_DET);
    case IC_CLR_GEN_CALL:
      return clearInterrupts(R_GEN_CALL);
    case IC_ENABLE:
      return enable;
    case IC_STATUS:
      return (state != I2CState::Idle ? MST_ACTIVITY | ACTIVITY : 0) | (rxFIFO.full() ? RFF : 0) |
             (!rxFIFO.empty() ? RFNE : 0) | (txFIFO.empty() ? TFE : 0) |
             (!txFIFO.full() ? TFNF : 0);
    case IC_TXFLR:
      return txFIFO.itemCount();
    case IC_RXFLR:
      return rxFIFO.itemCount();
    case IC_SDA_HOLD:
      return 0x01;
    case IC_TX_ABRT_SOURCE: {
      const uint32_t value = abortSource;
      abortSource &= ABRT_SBYTE_NORSTRT;  // Clear IC_TX_ABRT_SOURCE, expect for bit 9
      return value;
    }
    case IC_ENABLE_STATUS:
      // I2C status - read only. bit 0 reflects IC_ENABLE, bit 1,2 relate to i2c slave mode.
      return enable & 0x1;
    case IC_FS_SPKLEN:
      return spikelen & 0xff;
    case IC_COMP_PARAM_1:
      // From the datasheet:
      // Note This register is not implemented and therefore reads as 0. If it was implemented it would be a constant read-only
      // register that contains encoded information about the component's parameter settings.
      return 0;
    case IC_COMP_VERSION:
      return 0x3230312a;
    case IC_COMP_TYPE:
      return 0x44570140;
  }
  return BasePeripheral::readUint32(offset);
}

void RPI2C::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case IC_CON:
      if (((value >> SPEED_SHIFT) & SPEED_MASK) == static_cast<uint32_t>(I2CSpeed::Invalid)) {
        value = (value & ~(SPEED_MASK << SPEED_SHIFT)) |
                (static_cast<uint32_t>(I2CSpeed::HighSpeedMode) << SPEED_SHIFT);
      }
      control = value;
      return;

    case IC_TAR:
      targetAddress = value & 0x3ff;
      return;

    case IC_SAR:
      slaveAddress = value & 0x3ff;
      return;

    case IC_DATA_CMD:
      if (txFIFO.full()) {
        setInterrupts(R_TX_OVER);
      } else {
        txFIFO.push(value);
        clearInterrupts(R_TX_EMPTY);
        nextCommand();
      }
      return;

    case IC_SS_SCL_HCNT:
      ssClockHighPeriod = value & 0xffff;
      return;

    case IC_SS_SCL_LCNT:
      ssClockLowPeriod = value & 0xffff;
      return;

    case IC_FS_SCL_HCNT:
      fsClockHighPeriod = value & 0xffff;
      return;

    case IC_FS_SCL_LCNT:
      fsClockLowPeriod = value & 0xffff;
      return;

    case IC_SDA_HOLD:
      if (!(value & ENABLE)) {
        if (value != 0x1) {
          warn("Unimplemented write to IC_SDA_HOLD");
        }
      }
      return;

    case IC_RX_TL:
      rxThreshold = value & 0xff;
      if (rxThreshold > rxFIFO.size()) {
        rxThreshold = rxFIFO.size();
      }
      return;

    case IC_TX_TL:
      txThreshold = value & 0xff;
      if (txThreshold > txFIFO.size()) {
        txThreshold = txFIFO.size();
      }
      return;

    case IC_ENABLE:
      // ABORT bit can only be set by software, not cleared.
      value |= enable & ABORT;
      if (value & ABORT) {
        if (state == I2CState::Idle) {
          value &= ~ABORT;
        } else {
          abort(ABRT_USER_ABRT);
          stop = true;
        }
      }
      if (!(value & ENABLE)) {
        txFIFO.reset();
        rxFIFO.reset();
      }
      enable = value;
      nextCommand();  // TX_CMD_BLOCK may have changed
      return;

    case IC_FS_SPKLEN:
      // JS-SIGN: `value > 0` is false in TS for a negative int32 (writeUint8/16
      // byte replication with bit 7 set, an atomic alias write with bit 31).
      if (!(value & ENABLE) && value > 0) {
        spikelen = value;
      }
      return;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
