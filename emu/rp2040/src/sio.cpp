// Port of rp2040js src/sio.ts (with the cupc8 dual-core patch).
#include "sio.h"

#include <cmath>

#include "rp2040.h"
#include "utils/js.h"

namespace rp2040js {


static constexpr uint32_t CPUID = 0x000;
static constexpr uint32_t FIFO_ST = 0x050;
static constexpr uint32_t FIFO_WR = 0x054;
static constexpr uint32_t FIFO_RD = 0x058;
static constexpr uint32_t FIFO_DEPTH = 8;

// GPIO
static constexpr uint32_t GPIO_IN = 0x004; // Input value for GPIO pins
static constexpr uint32_t GPIO_HI_IN = 0x008; // Input value for QSPI pins
static constexpr uint32_t GPIO_OUT = 0x010; // GPIO output value
static constexpr uint32_t GPIO_OUT_SET = 0x014; // GPIO output value set
static constexpr uint32_t GPIO_OUT_CLR = 0x018; // GPIO output value clear
static constexpr uint32_t GPIO_OUT_XOR = 0x01c; // GPIO output value XOR
static constexpr uint32_t GPIO_OE = 0x020; // GPIO output enable
static constexpr uint32_t GPIO_OE_SET = 0x024; // GPIO output enable set
static constexpr uint32_t GPIO_OE_CLR = 0x028; // GPIO output enable clear
static constexpr uint32_t GPIO_OE_XOR = 0x02c; // GPIO output enable XOR
static constexpr uint32_t GPIO_HI_OUT = 0x030; // QSPI output value
static constexpr uint32_t GPIO_HI_OUT_SET = 0x034; // QSPI output value set
static constexpr uint32_t GPIO_HI_OUT_CLR = 0x038; // QSPI output value clear
static constexpr uint32_t GPIO_HI_OUT_XOR = 0x03c; // QSPI output value XOR
static constexpr uint32_t GPIO_HI_OE = 0x040; // QSPI output enable
static constexpr uint32_t GPIO_HI_OE_SET = 0x044; // QSPI output enable set
static constexpr uint32_t GPIO_HI_OE_CLR = 0x048; // QSPI output enable clear
static constexpr uint32_t GPIO_HI_OE_XOR = 0x04c; // QSPI output enable XOR

static constexpr uint32_t GPIO_MASK = 0x3fffffff;

//HARDWARE DIVIDER
static constexpr uint32_t DIV_UDIVIDEND = 0x060; //  Divider unsigned dividend
static constexpr uint32_t DIV_UDIVISOR = 0x064; //  Divider unsigned divisor
static constexpr uint32_t DIV_SDIVIDEND = 0x068; //  Divider signed dividend
static constexpr uint32_t DIV_SDIVISOR = 0x06c; //  Divider signed divisor
static constexpr uint32_t DIV_QUOTIENT = 0x070; //  Divider result quotient
static constexpr uint32_t DIV_REMAINDER = 0x074; //Divider result remainder
static constexpr uint32_t DIV_CSR = 0x078;

//INTERPOLATOR
static constexpr uint32_t INTERP0_ACCUM0 = 0x080; // Read/write access to accumulator 0
static constexpr uint32_t INTERP0_ACCUM1 = 0x084; // Read/write access to accumulator 1
static constexpr uint32_t INTERP0_BASE0 = 0x088; // Read/write access to BASE0 register
static constexpr uint32_t INTERP0_BASE1 = 0x08c; // Read/write access to BASE1 register
static constexpr uint32_t INTERP0_BASE2 = 0x090; // Read/write access to BASE2 register
static constexpr uint32_t INTERP0_POP_LANE0 = 0x094; // Read LANE0 result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP0_POP_LANE1 = 0x098; // Read LANE1 result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP0_POP_FULL = 0x09c; // Read FULL result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP0_PEEK_LANE0 = 0x0a0; // Read LANE0 result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP0_PEEK_LANE1 = 0x0a4; // Read LANE1 result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP0_PEEK_FULL = 0x0a8; // Read FULL result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP0_CTRL_LANE0 = 0x0ac; // Control register for lane 0
static constexpr uint32_t INTERP0_CTRL_LANE1 = 0x0b0; // Control register for lane 1
static constexpr uint32_t INTERP0_ACCUM0_ADD = 0x0b4; // Values written here are atomically added to ACCUM0
static constexpr uint32_t INTERP0_ACCUM1_ADD = 0x0b8; // Values written here are atomically added to ACCUM1
static constexpr uint32_t INTERP0_BASE_1AND0 = 0x0bc; // On write, the lower 16 bits go to BASE0, upper bits to BASE1 simultaneously
static constexpr uint32_t INTERP1_ACCUM0 = 0x0c0; // Read/write access to accumulator 0
static constexpr uint32_t INTERP1_ACCUM1 = 0x0c4; // Read/write access to accumulator 1
static constexpr uint32_t INTERP1_BASE0 = 0x0c8; // Read/write access to BASE0 register
static constexpr uint32_t INTERP1_BASE1 = 0x0cc; // Read/write access to BASE1 register
static constexpr uint32_t INTERP1_BASE2 = 0x0d0; // Read/write access to BASE2 register
static constexpr uint32_t INTERP1_POP_LANE0 = 0x0d4; // Read LANE0 result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP1_POP_LANE1 = 0x0d8; // Read LANE1 result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP1_POP_FULL = 0x0dc; // Read FULL result, and simultaneously write lane results to both accumulators (POP)
static constexpr uint32_t INTERP1_PEEK_LANE0 = 0x0e0; // Read LANE0 result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP1_PEEK_LANE1 = 0x0e4; // Read LANE1 result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP1_PEEK_FULL = 0x0e8; // Read FULL result, without altering any internal state (PEEK)
static constexpr uint32_t INTERP1_CTRL_LANE0 = 0x0ec; // Control register for lane 0
static constexpr uint32_t INTERP1_CTRL_LANE1 = 0x0f0; // Control register for lane 1
static constexpr uint32_t INTERP1_ACCUM0_ADD = 0x0f4; // Values written here are atomically added to ACCUM0
static constexpr uint32_t INTERP1_ACCUM1_ADD = 0x0f8; // Values written here are atomically added to ACCUM1
static constexpr uint32_t INTERP1_BASE_1AND0 = 0x0fc; // On write, the lower 16 bits go to BASE0, upper bits to BASE1 simultaneously

//SPINLOCK
static constexpr uint32_t SPINLOCK_ST = 0x5c;
static constexpr uint32_t SPINLOCK0 = 0x100;
static constexpr uint32_t SPINLOCK31 = 0x17c;

RPSIO::RPSIO(RP2040 &rp2040) : rp2040(rp2040) {
  // interp0 = new Interpolator(0); interp1 = new Interpolator(1);
  // banks[0] holds those, banks[1] core 1's own pair.
  banks[0] = {{0, 1, 0, 0, 0}, std::make_unique<Interpolator>(0), std::make_unique<Interpolator>(1)};
  banks[1] = {{0, 1, 0, 0, 0}, std::make_unique<Interpolator>(0), std::make_unique<Interpolator>(1)};
  interp0 = banks[0].interp0.get();
  interp1 = banks[0].interp1.get();
}

void RPSIO::selectCore(uint32_t index) {
  if (index == bank) {
    return;
  }
  Bank &out = banks[bank];
  out.div = {divDividend, divDivisor, divQuotient, divRemainder, static_cast<double>(divCSR)};
  Bank &bank = banks[index];
  divDividend = bank.div[0];
  divDivisor = bank.div[1];
  divQuotient = bank.div[2];
  divRemainder = bank.div[3];
  divCSR = static_cast<uint32_t>(bank.div[4]);
  interp0 = bank.interp0.get();
  interp1 = bank.interp1.get();
  this->bank = index;
}

uint32_t RPSIO::fifoStatus(uint32_t core) const {
  const auto &other = fifo[1 - core];
  return (fifo[core].size() ? 1 : 0) | (other.size() < FIFO_DEPTH ? 2 : 0) | fifoErr[core];
}

void RPSIO::updateFifoIrq() {
  // SIO_IRQ_PROC0 goes only to core 0's NVIC, SIO_IRQ_PROC1 only to core 1's
  for (uint32_t core = 0; core < 2; core++) {
    const bool level = !!(fifo[core].size() || fifoErr[core]);
    rp2040.cores[core]->setInterrupt(15 + core, level);
  }
}

void RPSIO::updateHardwareDivider(bool signed_) {
  if (divDivisor == 0) {
    divQuotient = divDividend > 0 ? -1 : 1;
    divRemainder = divDividend;
  } else {
    if (signed_) {
      // JS `/` and `%` on numbers: a float quotient, fmod-style remainder
      divQuotient = static_cast<double>(toInt32(divDividend)) / toInt32(divDivisor);
      divRemainder =
          std::fmod(static_cast<double>(toInt32(divDividend)), static_cast<double>(toInt32(divDivisor)));
    } else {
      divQuotient = static_cast<double>(toUint32(divDividend)) / toUint32(divDivisor);
      divRemainder = std::fmod(static_cast<double>(toUint32(divDividend)),
                               static_cast<double>(toUint32(divDivisor)));
    }
  }
  divCSR = 0b11;
  rp2040.core().cycles += 8;
}

uint32_t RPSIO::readUint32(uint32_t offset) {
  if (offset >= SPINLOCK0 && offset <= SPINLOCK31) {
    const uint32_t bitIndexMask = 1u << ((offset - SPINLOCK0) / 4);
    if (spinLock & bitIndexMask) {
      return 0;
    } else {
      spinLock |= bitIndexMask;
      return bitIndexMask;
    }
  }
  switch (offset) {
    case GPIO_IN:
      return rp2040.gpioValues();
    case GPIO_HI_IN: {
      const auto &qspi = rp2040.qspi;
      uint32_t result = 0;
      for (uint32_t qspiIndex = 0; qspiIndex < qspi.size(); qspiIndex++) {
        if (qspi[qspiIndex].inputValue()) {
          result |= 1u << qspiIndex;
        }
      }
      return result;
    }
    case GPIO_OUT:
      return gpioValue;
    case GPIO_OE:
      return gpioOutputEnable;
    case GPIO_HI_OUT:
      return qspiGpioValue;
    case GPIO_HI_OE:
      return qspiGpioOutputEnable;
    case GPIO_OUT_SET:
    case GPIO_OUT_CLR:
    case GPIO_OUT_XOR:
    case GPIO_OE_SET:
    case GPIO_OE_CLR:
    case GPIO_OE_XOR:
    case GPIO_HI_OUT_SET:
    case GPIO_HI_OUT_CLR:
    case GPIO_HI_OUT_XOR:
    case GPIO_HI_OE_SET:
    case GPIO_HI_OE_CLR:
    case GPIO_HI_OE_XOR:
      return 0;  // TODO verify with silicone
    case CPUID:
      return rp2040.coreIndex;
    case FIFO_ST:
      return fifoStatus(rp2040.coreIndex);
    case FIFO_RD: {
      const uint32_t core = rp2040.coreIndex;
      // `this.fifo[core].shift()`: undefined when empty
      const bool empty = fifo[core].empty();
      uint32_t value = 0;
      if (!empty) {
        value = fifo[core].front();
        fifo[core].pop_front();
      }
      if (empty) {
        fifoErr[core] |= 8;
      }
      updateFifoIrq();
      return value;  // `value ?? 0`
    }
    case SPINLOCK_ST:
      return spinLock;
    case DIV_UDIVIDEND:
      return toUint32(divDividend);
    case DIV_SDIVIDEND:
      return toUint32(divDividend);
    case DIV_UDIVISOR:
      return toUint32(divDivisor);
    case DIV_SDIVISOR:
      return toUint32(divDivisor);
    case DIV_QUOTIENT:
      divCSR &= ~0b10u;
      return toUint32(divQuotient);
    case DIV_REMAINDER:
      return toUint32(divRemainder);
    case DIV_CSR:
      return divCSR;
    case INTERP0_ACCUM0:
      return interp0->accum0;
    case INTERP0_ACCUM1:
      return interp0->accum1;
    case INTERP0_BASE0:
      return interp0->base0;
    case INTERP0_BASE1:
      return interp0->base1;
    case INTERP0_BASE2:
      return interp0->base2;
    case INTERP0_CTRL_LANE0:
      return interp0->ctrl0;
    case INTERP0_CTRL_LANE1:
      return interp0->ctrl1;
    case INTERP0_PEEK_LANE0:
      return interp0->result0;
    case INTERP0_PEEK_LANE1:
      return interp0->result1;
    case INTERP0_PEEK_FULL:
      return interp0->result2;
    case INTERP0_POP_LANE0: {
      const uint32_t value = interp0->result0;
      interp0->writeback();
      return value;
    }
    case INTERP0_POP_LANE1: {
      const uint32_t value = interp0->result1;
      interp0->writeback();
      return value;
    }
    case INTERP0_POP_FULL: {
      const uint32_t value = interp0->result2;
      interp0->writeback();
      return value;
    }
    case INTERP0_ACCUM0_ADD:
      return interp0->smresult0;
    case INTERP0_ACCUM1_ADD:
      return interp0->smresult1;
    case INTERP1_ACCUM0:
      return interp1->accum0;
    case INTERP1_ACCUM1:
      return interp1->accum1;
    case INTERP1_BASE0:
      return interp1->base0;
    case INTERP1_BASE1:
      return interp1->base1;
    case INTERP1_BASE2:
      return interp1->base2;
    case INTERP1_CTRL_LANE0:
      return interp1->ctrl0;
    case INTERP1_CTRL_LANE1:
      return interp1->ctrl1;
    case INTERP1_PEEK_LANE0:
      return interp1->result0;
    case INTERP1_PEEK_LANE1:
      return interp1->result1;
    case INTERP1_PEEK_FULL:
      return interp1->result2;
    case INTERP1_POP_LANE0: {
      const uint32_t value = interp1->result0;
      interp1->writeback();
      return value;
    }
    case INTERP1_POP_LANE1: {
      const uint32_t value = interp1->result1;
      interp1->writeback();
      return value;
    }
    case INTERP1_POP_FULL: {
      const uint32_t value = interp1->result2;
      interp1->writeback();
      return value;
    }
    case INTERP1_ACCUM0_ADD:
      return interp1->smresult0;
    case INTERP1_ACCUM1_ADD:
      return interp1->smresult1;
  }
  consoleWarn("Read from invalid SIO address: " + toHex(offset));
  return 0xffffffff;
}

void RPSIO::writeUint32(uint32_t offset, uint32_t value) {
  if (offset >= SPINLOCK0 && offset <= SPINLOCK31) {
    const uint32_t bitIndexMask = ~(1u << ((offset - SPINLOCK0) / 4));
    spinLock &= bitIndexMask;
    return;
  }
  const uint32_t prevGpioValue = gpioValue;
  const uint32_t prevGpioOutputEnable = gpioOutputEnable;
  switch (offset) {
    case GPIO_OUT:
      gpioValue = value & GPIO_MASK;
      break;
    case GPIO_OUT_SET:
      gpioValue |= value & GPIO_MASK;
      break;
    case GPIO_OUT_CLR:
      gpioValue &= ~value;
      break;
    case GPIO_OUT_XOR:
      gpioValue ^= value & GPIO_MASK;
      break;
    case GPIO_OE:
      gpioOutputEnable = value & GPIO_MASK;
      break;
    case GPIO_OE_SET:
      gpioOutputEnable |= value & GPIO_MASK;
      break;
    case GPIO_OE_CLR:
      gpioOutputEnable &= ~value;
      break;
    case GPIO_OE_XOR:
      gpioOutputEnable ^= value & GPIO_MASK;
      break;
    case GPIO_HI_OUT:
      qspiGpioValue = value & GPIO_MASK;
      break;
    case GPIO_HI_OUT_SET:
      qspiGpioValue |= value & GPIO_MASK;
      break;
    case GPIO_HI_OUT_CLR:
      qspiGpioValue &= ~value;
      break;
    case GPIO_HI_OUT_XOR:
      qspiGpioValue ^= value & GPIO_MASK;
      break;
    case GPIO_HI_OE:
      qspiGpioOutputEnable = value & GPIO_MASK;
      break;
    case GPIO_HI_OE_SET:
      qspiGpioOutputEnable |= value & GPIO_MASK;
      break;
    case GPIO_HI_OE_CLR:
      qspiGpioOutputEnable &= ~value;
      break;
    case GPIO_HI_OE_XOR:
      qspiGpioOutputEnable ^= value & GPIO_MASK;
      break;
    case FIFO_ST:
      // writing clears the sticky WOF/ROE flags
      fifoErr[rp2040.coreIndex] = 0;
      updateFifoIrq();
      break;
    case FIFO_WR: {
      auto &other = fifo[1 - rp2040.coreIndex];
      if (other.size() < FIFO_DEPTH) {
        other.push_back(value >> 0);
      } else {
        fifoErr[rp2040.coreIndex] |= 4;
      }
      updateFifoIrq();
      break;
    }
    case DIV_UDIVIDEND:
      divDividend = value;
      updateHardwareDivider(false);
      break;
    case DIV_SDIVIDEND:
      divDividend = value;
      updateHardwareDivider(true);
      break;
    case DIV_UDIVISOR:
      divDivisor = value;
      updateHardwareDivider(false);
      break;
    case DIV_SDIVISOR:
      divDivisor = value;
      updateHardwareDivider(true);
      break;
    case DIV_QUOTIENT:
      divQuotient = value;
      divCSR = 0b11;
      break;
    case DIV_REMAINDER:
      divRemainder = value;
      divCSR = 0b11;
      break;
    case INTERP0_ACCUM0:
      interp0->accum0 = value;
      interp0->update();
      break;
    case INTERP0_ACCUM1:
      interp0->accum1 = value;
      interp0->update();
      break;
    case INTERP0_BASE0:
      interp0->base0 = value;
      interp0->update();
      break;
    case INTERP0_BASE1:
      interp0->base1 = value;
      interp0->update();
      break;
    case INTERP0_BASE2:
      interp0->base2 = value;
      interp0->update();
      break;
    case INTERP0_CTRL_LANE0:
      interp0->ctrl0 = value;
      interp0->update();
      break;
    case INTERP0_CTRL_LANE1:
      interp0->ctrl1 = value;
      interp0->update();
      break;
    case INTERP0_ACCUM0_ADD:
      interp0->accum0 += value;
      interp0->update();
      break;
    case INTERP0_ACCUM1_ADD:
      interp0->accum1 += value;
      interp0->update();
      break;
    case INTERP0_BASE_1AND0:
      interp0->setBase01(value);
      break;
    case INTERP1_ACCUM0:
      interp1->accum0 = value;
      interp1->update();
      break;
    case INTERP1_ACCUM1:
      interp1->accum1 = value;
      interp1->update();
      break;
    case INTERP1_BASE0:
      interp1->base0 = value;
      interp1->update();
      break;
    case INTERP1_BASE1:
      interp1->base1 = value;
      interp1->update();
      break;
    case INTERP1_BASE2:
      interp1->base2 = value;
      interp1->update();
      break;
    case INTERP1_CTRL_LANE0:
      interp1->ctrl0 = value;
      interp1->update();
      break;
    case INTERP1_CTRL_LANE1:
      interp1->ctrl1 = value;
      interp1->update();
      break;
    case INTERP1_ACCUM0_ADD:
      interp1->accum0 += value;
      interp1->update();
      break;
    case INTERP1_ACCUM1_ADD:
      interp1->accum1 += value;
      interp1->update();
      break;
    case INTERP1_BASE_1AND0:
      interp1->setBase01(value);
      break;
    default:
      consoleWarn("Write to invalid SIO address: " + toHex(offset) + ", value=" + toHex(value));
  }
  const uint32_t pinsToUpdate =
      (gpioValue ^ prevGpioValue) | (gpioOutputEnable ^ prevGpioOutputEnable);
  if (pinsToUpdate) {
    auto &gpio = rp2040.gpio;
    for (uint32_t gpioIndex = 0; gpioIndex < gpio.size(); gpioIndex++) {
      if (pinsToUpdate & (1u << gpioIndex)) {
        gpio[gpioIndex].checkForUpdates();
      }
    }
  }
}

}  // namespace rp2040js
