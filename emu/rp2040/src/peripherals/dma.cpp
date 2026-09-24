// Port of rp2040js src/peripherals/dma.ts
#include "dma.h"

#include <stdexcept>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

// Per-channel registers
static constexpr uint32_t CHn_READ_ADDR = 0x000;             // DMA Channel n Read Address pointer
static constexpr uint32_t CHn_WRITE_ADDR = 0x004;            // DMA Channel n Write Address pointer
static constexpr uint32_t CHn_TRANS_COUNT = 0x008;           // DMA Channel n Transfer Count
static constexpr uint32_t CHn_CTRL_TRIG = 0x00c;             // DMA Channel n Control and Status
static constexpr uint32_t CHn_AL1_CTRL = 0x010;              // Alias for channel n CTRL register
static constexpr uint32_t CHn_AL1_READ_ADDR = 0x014;         // Alias for channel n READ_ADDR register
static constexpr uint32_t CHn_AL1_WRITE_ADDR = 0x018;        // Alias for channel n WRITE_ADDR register
static constexpr uint32_t CHn_AL1_TRANS_COUNT_TRIG = 0x01c;  // Alias for channel n TRANS_COUNT register
static constexpr uint32_t CHn_AL2_CTRL = 0x020;              // Alias for channel n CTRL register
static constexpr uint32_t CHn_AL2_TRANS_COUNT = 0x024;       // Alias for channel n TRANS_COUNT register
static constexpr uint32_t CHn_AL2_READ_ADDR = 0x028;         // Alias for channel n READ_ADDR register
static constexpr uint32_t CHn_AL2_WRITE_ADDR_TRIG = 0x02c;   // Alias for channel n WRITE_ADDR register
static constexpr uint32_t CHn_AL3_CTRL = 0x030;              // Alias for channel n CTRL register
static constexpr uint32_t CHn_AL3_WRITE_ADDR = 0x034;        // Alias for channel n WRITE_ADDR register
static constexpr uint32_t CHn_AL3_TRANS_COUNT = 0x038;       // Alias for channel n TRANS_COUNT register
static constexpr uint32_t CHn_AL3_READ_ADDR_TRIG = 0x03c;    // Alias for channel n READ_ADDR register
static constexpr uint32_t CHn_DBG_CTDREQ = 0x800;
static constexpr uint32_t CHn_DBG_TCR = 0x804;
static constexpr uint32_t CHANNEL_REGISTERS_SIZE = 12 * 0x40;
static constexpr uint32_t CHANNEL_REGISTERS_MASK = 0x83f;

// General DMA registers
static constexpr uint32_t INTR = 0x400;                // Interrupt Status (raw)
static constexpr uint32_t INTE0 = 0x404;               // Interrupt Enables for IRQ 0
static constexpr uint32_t INTF0 = 0x408;               // Force Interrupts
static constexpr uint32_t INTS0 = 0x40c;               // Interrupt Status for IRQ 0
static constexpr uint32_t INTE1 = 0x414;               // Interrupt Enables for IRQ 1
static constexpr uint32_t INTF1 = 0x418;               // Force Interrupts for IRQ 1
static constexpr uint32_t INTS1 = 0x41c;               // Interrupt Status (masked) for IRQ 1
static constexpr uint32_t TIMER0 = 0x420;              // Pacing (X/Y) Fractional Timer
static constexpr uint32_t TIMER1 = 0x424;              // Pacing (X/Y) Fractional Timer
static constexpr uint32_t TIMER2 = 0x428;              // Pacing (X/Y) Fractional Timer
static constexpr uint32_t TIMER3 = 0x42c;              // Pacing (X/Y) Fractional Timer
static constexpr uint32_t MULTI_CHAN_TRIGGER = 0x430;  // Trigger one or more channels simultaneously
static constexpr uint32_t SNIFF_CTRL = 0x434;          // Sniffer Control
static constexpr uint32_t SNIFF_DATA = 0x438;          // Data accumulator for sniff hardware
static constexpr uint32_t FIFO_LEVELS = 0x440;         // Debug RAF, WAF, TDF levels
static constexpr uint32_t CHAN_ABORT = 0x444;  // Abort an in-progress transfer sequence on one or more channels
static constexpr uint32_t N_CHANNELS = 0x448;

// CHn_CTRL_TRIG bits
static constexpr uint32_t AHB_ERROR = 1u << 31;
static constexpr uint32_t READ_ERROR = 1 << 30;
static constexpr uint32_t WRITE_ERROR = 1 << 29;
static constexpr uint32_t BUSY = 1 << 24;
static constexpr uint32_t SNIFF_EN = 1 << 23;
static constexpr uint32_t BSWAP = 1 << 22;
static constexpr uint32_t IRQ_QUIET = 1 << 21;
static constexpr uint32_t TREQ_SEL_MASK = 0x3f;
static constexpr uint32_t TREQ_SEL_SHIFT = 15;
static constexpr uint32_t CHAIN_TO_MASK = 0xf;
static constexpr uint32_t CHAIN_TO_SHIFT = 11;
static constexpr uint32_t RING_SEL = 1 << 10;
static constexpr uint32_t RING_SIZE_MASK = 0xf;
static constexpr uint32_t RING_SIZE_SHIFT = 6;
static constexpr uint32_t INCR_WRITE = 1 << 5;
static constexpr uint32_t INCR_READ = 1 << 4;
static constexpr uint32_t DATA_SIZE_MASK = 0x3;
static constexpr uint32_t DATA_SIZE_SHIFT = 2;
static constexpr uint32_t HIGH_PRIORITY = 1 << 1;
static constexpr uint32_t EN = 1 << 0;
static constexpr uint32_t CHn_CTRL_TRIG_WRITE_MASK = 0xffffff;
static constexpr uint32_t CHn_CTRL_TRIG_WC_MASK = READ_ERROR | WRITE_ERROR;

// Unused in the TS too; referenced so -Wunused stays quiet.
[[maybe_unused]] static constexpr uint32_t UNUSED_DMA_CONSTS[] = {
    SNIFF_CTRL, SNIFF_DATA, FIFO_LEVELS, AHB_ERROR, SNIFF_EN, HIGH_PRIORITY};

RPDMAChannel::RPDMAChannel(RPDMA &dma, RP2040 &rp2040, uint32_t index)
    : dma(dma), rp2040(rp2040), index(index) {
  transferAlarm = rp2040.clock.createAlarm([this] { transfer(); });
  reset();
}

void RPDMAChannel::start() {
  if (!(ctrl & EN) || ctrl & BUSY) {
    return;
  }
  ctrl |= BUSY;
  transCount = transCountReload;
  if (transCount) {
    scheduleTransfer();
  }
}

uint32_t RPDMAChannel::treq() const { return treqValue; }

// `this.ctrl & EN && this.ctrl & BUSY`: the value of `&&` (BUSY or 0)
uint32_t RPDMAChannel::active() const { return ctrl & EN ? ctrl & BUSY : 0; }

// In each transfer the TS evaluates `this.writeAddr` before calling the read
// (left-to-right argument evaluation); C++ does not fix the order, so the
// operands are sequenced explicitly.

void RPDMAChannel::transfer8() {
  const uint32_t writeAddr = this->writeAddr;
  const uint32_t value = rp2040.readUint8(readAddr);
  rp2040.writeUint8(writeAddr, value);
}

void RPDMAChannel::transfer16() {
  const uint32_t writeAddr = this->writeAddr;
  const uint32_t value = rp2040.readUint16(readAddr);
  rp2040.writeUint16(writeAddr, value);
}

void RPDMAChannel::transferSwap16() {
  const uint32_t input = rp2040.readUint16(readAddr);
  rp2040.writeUint16(writeAddr, ((input & 0xff) << 8) | (input >> 8));
}

void RPDMAChannel::transfer32() {
  const uint32_t writeAddr = this->writeAddr;
  const uint32_t value = rp2040.readUint32(readAddr);
  rp2040.writeUint32(writeAddr, value);
}

void RPDMAChannel::transferSwap32() {
  const uint32_t input = rp2040.readUint32(readAddr);
  // JS-SIGN: in TS `(input & 0xff) << 24` makes this a negative int32 when
  // bit 7 of the input is set; the bus consumer gets the same 32-bit pattern.
  rp2040.writeUint32(writeAddr, ((input & 0x000000ff) << 24) | ((input & 0x0000ff00) << 8) |
                                    ((input & 0x00ff0000) >> 8) | ((input >> 24) & 0xff));
}

void RPDMAChannel::transfer() {
  const uint32_t ctrl = this->ctrl, dataSize = this->dataSize, ringMask = this->ringMask;
  (this->*transferFn)();
  // JS-RANGE: in TS readAddr / writeAddr are plain numbers and `+= dataSize`
  // can carry past 2**32 (the ring expression below is an int32). Every
  // consumer masks or `>>> 0`s the address except the SRAM/flash range tests
  // of readUint8/16 and writeUint8/16, which only differ after the address
  // has run ~2**28 transfers past 0xffffffff; here the address wraps.
  if (ctrl & INCR_READ) {
    if (ringMask && !(ctrl & RING_SEL)) {
      readAddr = (readAddr & ~ringMask) | ((readAddr + dataSize) & ringMask);
    } else {
      readAddr += dataSize;
    }
  }
  if (ctrl & INCR_WRITE) {
    if (ringMask && ctrl & RING_SEL) {
      writeAddr = (writeAddr & ~ringMask) | ((writeAddr + dataSize) & ringMask);
    } else {
      writeAddr += dataSize;
    }
  }
  transCount--;
  if (transCount > 0) {
    scheduleTransfer();
  } else {
    this->ctrl &= ~BUSY;
    if (!(this->ctrl & IRQ_QUIET)) {
      dma.intRaw |= 1 << index;
      dma.checkInterrupts();
    }
    if (chainTo != index) {
      // `this.dma.channels[this.chainTo]?.start()`: CHAIN_TO 12..15 is undefined
      if (chainTo < dma.channels.size()) {
        dma.channels[chainTo].start();
      }
    }
  }
}

void RPDMAChannel::scheduleTransfer() {
  if (dma.dreq[treqValue] || treqValue == static_cast<uint32_t>(TREQ::Permanent)) {
    transferAlarm->schedule(0);
  } else {
    const double delay = dma.getTimer(static_cast<TREQ>(treqValue));
    if (delay) {
      transferAlarm->schedule(delay * 1000);
    }
  }
}

void RPDMAChannel::abort() {
  ctrl &= ~BUSY;
  transferAlarm->cancel();
}

uint32_t RPDMAChannel::readUint32(uint32_t offset) {
  switch (offset) {
    case CHn_READ_ADDR:
    case CHn_AL1_READ_ADDR:
    case CHn_AL2_READ_ADDR:
    case CHn_AL3_READ_ADDR_TRIG:
      return readAddr;

    case CHn_WRITE_ADDR:
    case CHn_AL1_WRITE_ADDR:
    case CHn_AL2_WRITE_ADDR_TRIG:
    case CHn_AL3_WRITE_ADDR:
      return writeAddr;

    case CHn_TRANS_COUNT:
    case CHn_AL1_TRANS_COUNT_TRIG:
    case CHn_AL2_TRANS_COUNT:
    case CHn_AL3_TRANS_COUNT:
      return toUint32(transCount);  // may be negative in TS (see transCount)

    case CHn_CTRL_TRIG:
    case CHn_AL1_CTRL:
    case CHn_AL2_CTRL:
    case CHn_AL3_CTRL:
      return ctrl;

    case CHn_DBG_CTDREQ:
      return dreqCounter;

    case CHn_DBG_TCR:
      return transCountReload;
  }

  return 0;
}

void RPDMAChannel::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case CHn_READ_ADDR:
    case CHn_AL1_READ_ADDR:
    case CHn_AL2_READ_ADDR:
    case CHn_AL3_READ_ADDR_TRIG:
      readAddr = value;
      break;

    case CHn_WRITE_ADDR:
    case CHn_AL1_WRITE_ADDR:
    case CHn_AL2_WRITE_ADDR_TRIG:
    case CHn_AL3_WRITE_ADDR:
      writeAddr = value;
      break;

    case CHn_TRANS_COUNT:
    case CHn_AL1_TRANS_COUNT_TRIG:
    case CHn_AL2_TRANS_COUNT:
    case CHn_AL3_TRANS_COUNT:
      // JS-SIGN: a negative int32 here (writeUint8/16 byte replication, an
      // atomic alias write) makes the TS transCount negative, so start()
      // would run one transfer; here it is a large positive count.
      transCountReload = value;
      break;

    case CHn_CTRL_TRIG:
    case CHn_AL1_CTRL:
    case CHn_AL2_CTRL:
    case CHn_AL3_CTRL: {
      ctrl = (ctrl & ~CHn_CTRL_TRIG_WRITE_MASK) | (value & CHn_CTRL_TRIG_WRITE_MASK);
      ctrl &= ~(value & CHn_CTRL_TRIG_WC_MASK);  // Handle write-clear (WC) bits
      treqValue = (ctrl >> TREQ_SEL_SHIFT) & TREQ_SEL_MASK;
      chainTo = (ctrl >> CHAIN_TO_SHIFT) & CHAIN_TO_MASK;
      const uint32_t ringSize = (ctrl >> RING_SIZE_SHIFT) & RING_SIZE_MASK;
      ringMask = ringSize ? (1u << ringSize) - 1 : 0;
      switch ((ctrl >> DATA_SIZE_SHIFT) & DATA_SIZE_MASK) {
        case 1:
          dataSize = 2;
          transferFn = ctrl & BSWAP ? &RPDMAChannel::transferSwap16 : &RPDMAChannel::transfer16;
          break;
        case 2:
          dataSize = 4;
          transferFn = ctrl & BSWAP ? &RPDMAChannel::transferSwap32 : &RPDMAChannel::transfer32;
          break;
        case 0:
        default:
          transferFn = &RPDMAChannel::transfer8;
          dataSize = 1;
      }
      if (ctrl & EN && ctrl & BUSY) {
        scheduleTransfer();
      }
      if (!(ctrl & EN)) {
        transferAlarm->cancel();
      }
      break;
    }

    case CHn_DBG_CTDREQ:
      dreqCounter = 0;
      break;
  }

  if (offset == CHn_AL3_READ_ADDR_TRIG || offset == CHn_AL2_WRITE_ADDR_TRIG ||
      offset == CHn_AL1_TRANS_COUNT_TRIG || offset == CHn_CTRL_TRIG) {
    if (value) {
      start();
    } else if (ctrl & IRQ_QUIET) {
      // Null trigger interrupts
      dma.intRaw |= 1 << index;
      dma.checkInterrupts();
    }
  }
}

void RPDMAChannel::reset() { writeUint32(CHn_CTRL_TRIG, index << CHAIN_TO_SHIFT); }

RPDMA::RPDMA(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      channels{{
          {*this, rp2040, 0},
          {*this, rp2040, 1},
          {*this, rp2040, 2},
          {*this, rp2040, 3},
          {*this, rp2040, 4},
          {*this, rp2040, 5},
          {*this, rp2040, 6},
          {*this, rp2040, 7},
          {*this, rp2040, 8},
          {*this, rp2040, 9},
          {*this, rp2040, 10},
          {*this, rp2040, 11},
      }} {}

uint32_t RPDMA::intStatus0() const { return (intRaw & intEnable0) | intForce0; }

uint32_t RPDMA::intStatus1() const { return (intRaw & intEnable1) | intForce1; }

// `(offset & 0x7ff) <= CHANNEL_REGISTERS_SIZE` lets offset 0x300 through to
// `this.channels[12]`, which is undefined: the TS throws a TypeError there.
static void checkChannelIndex(uint32_t channelIndex, size_t count, const char *method) {
  if (channelIndex >= count) {
    throw std::runtime_error(std::string("TypeError: Cannot read properties of undefined (reading '") +
                             method + "')");
  }
}

uint32_t RPDMA::readUint32(uint32_t offset) {
  if ((offset & 0x7ff) <= CHANNEL_REGISTERS_SIZE) {
    const uint32_t channelIndex = (offset & 0x7ff) >> 6;
    checkChannelIndex(channelIndex, channels.size(), "readUint32");
    return channels[channelIndex].readUint32(offset & CHANNEL_REGISTERS_MASK);
  }
  switch (offset) {
    case TIMER0:
      return timer0;
    case TIMER1:
      return timer1;
    case TIMER2:
      return timer2;
    case TIMER3:
      return timer3;
    case INTR:
      return intRaw;
    case INTE0:
      return intEnable0;
    case INTF0:
      return intForce0;
    case INTS0:
      return intStatus0();
    case INTE1:
      return intEnable1;
    case INTF1:
      return intForce1;
    case INTS1:
      return intStatus1();
    case N_CHANNELS:
      return static_cast<uint32_t>(channels.size());
  }
  return BasePeripheral::readUint32(offset);
}

void RPDMA::writeUint32(uint32_t offset, uint32_t value) {
  if ((offset & 0x7ff) <= CHANNEL_REGISTERS_SIZE) {
    const uint32_t channelIndex = (offset & 0x7ff) >> 6;
    checkChannelIndex(channelIndex, channels.size(), "writeUint32");
    channels[channelIndex].writeUint32(offset & CHANNEL_REGISTERS_MASK, value);
    return;
  }
  switch (offset) {
    case TIMER0:
      timer0 = value;
      return;
    case TIMER1:
      timer1 = value;
      return;
    case TIMER2:
      timer2 = value;
      return;
    case TIMER3:
      timer3 = value;
      return;
    case INTR:
    case INTS0:
    case INTS1:
      intRaw &= ~rawWriteValue;
      checkInterrupts();
      return;
    case INTE0:
      intEnable0 = value & 0xffff;
      checkInterrupts();
      return;
    case INTF0:
      intForce0 = value & 0xffff;
      checkInterrupts();
      return;
    case INTE1:
      intEnable1 = value & 0xffff;
      checkInterrupts();
      return;
    case INTF1:
      intForce1 = value & 0xffff;
      checkInterrupts();
      return;
    case MULTI_CHAN_TRIGGER:
      for (RPDMAChannel &chan : channels) {
        if (value & (1u << chan.index)) {
          chan.start();
        }
      }
      return;
    case CHAN_ABORT:
      for (RPDMAChannel &chan : channels) {
        if (value & (1u << chan.index)) {
          chan.abort();
        }
      }
      return;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

void RPDMA::setDREQ(DREQChannel dreqChannel) {
  if (!dreq[dreqChannel]) {
    dreq[dreqChannel] = true;
    for (RPDMAChannel &channel : channels) {
      if (channel.treq() == dreqChannel && channel.active()) {
        channel.scheduleTransfer();
      }
    }
  }
}

void RPDMA::clearDREQ(DREQChannel dreqChannel) { dreq[dreqChannel] = false; }

double RPDMA::getTimer(TREQ treq) const {
  double dividend = 0, divisor = 1;
  switch (treq) {
    case TREQ::Permanent:
      dividend = 1;
      divisor = 1;
      break;
    case TREQ::Timer0:
      dividend = timer0 >> 16;
      divisor = timer0 & 0xffff;
      break;
    case TREQ::Timer1:
      dividend = timer1 >> 16;
      divisor = timer1 & 0xffff;
      break;
    case TREQ::Timer2:
      dividend = timer2 >> 16;
      divisor = timer2 & 0xffff;
      break;
    case TREQ::Timer3:
      // TS bug (kept): `this.timer3 >>> 36`, and JS shift counts are & 31, so >>> 4.
      dividend = jsShr(timer3, 36);
      divisor = timer3 & 0xffff;
      break;
  }
  if (divisor == 0) {
    return 0;
  }
  return ((dividend / divisor) * 1e6) / rp2040.clkSys;
}

void RPDMA::checkInterrupts() {
  rp2040.setInterrupt(IRQ::DMA_IRQ0, !!intStatus0());
  rp2040.setInterrupt(IRQ::DMA_IRQ1, !!intStatus1());
}

}  // namespace rp2040js
