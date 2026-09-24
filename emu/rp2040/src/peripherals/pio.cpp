// Port of rp2040js src/peripherals/pio.ts (with the cupc8 dual-core patch).
//
// JS numbers: see the note on StateMachine in pio.h. Every shift below has a
// count in 0..31 unless commented (then jsShl/jsSar or an explicit & 31).
#include "pio.h"

#include <algorithm>
#include <tuple>
#include <type_traits>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

// Generic registers
static constexpr uint32_t CTRL = 0x000;
static constexpr uint32_t FSTAT = 0x004;
static constexpr uint32_t FDEBUG = 0x008;
static constexpr uint32_t FLEVEL = 0x00c;
// `IRQ` in TS; renamed: it clashes with `namespace IRQ` (irq.h)
static constexpr uint32_t IRQ_ = 0x030;
static constexpr uint32_t IRQ_FORCE = 0x034;
static constexpr uint32_t INPUT_SYNC_BYPASS = 0x038;
static constexpr uint32_t DBG_PADOUT = 0x03c;
static constexpr uint32_t DBG_PADOE = 0x040;
static constexpr uint32_t DBG_CFGINFO = 0x044;
static constexpr uint32_t INSTR_MEM0 = 0x48;
static constexpr uint32_t INSTR_MEM31 = 0x0c4;

static constexpr uint32_t INTR = 0x128;       // Raw Interrupts
static constexpr uint32_t IRQ0_INTE = 0x12c;  // Interrupt Enable for irq0
static constexpr uint32_t IRQ0_INTF = 0x130;  // Interrupt Force for irq0
static constexpr uint32_t IRQ0_INTS = 0x134;  // Interrupt status after masking & forcing for irq0
static constexpr uint32_t IRQ1_INTE = 0x138;  // Interrupt Enable for irq1
static constexpr uint32_t IRQ1_INTF = 0x13c;  // Interrupt Force for irq1
static constexpr uint32_t IRQ1_INTS = 0x140;  // Interrupt status after masking & forcing for irq1

// State-machine specific registers
static constexpr uint32_t TXF0 = 0x010;
static constexpr uint32_t TXF1 = 0x014;
static constexpr uint32_t TXF2 = 0x018;
static constexpr uint32_t TXF3 = 0x01c;
static constexpr uint32_t RXF0 = 0x020;
static constexpr uint32_t RXF1 = 0x024;
static constexpr uint32_t RXF2 = 0x028;
static constexpr uint32_t RXF3 = 0x02c;
static constexpr uint32_t SM0_CLKDIV = 0x0c8;     // Clock divisor register for state machine 0
static constexpr uint32_t SM0_EXECCTRL = 0x0cc;   // Execution/behavioural settings for state machine 0
static constexpr uint32_t SM0_SHIFTCTRL = 0x0d0;  // Control behaviour of the input/output shift registers for state machine 0
static constexpr uint32_t SM0_ADDR = 0x0d4;       // Current instruction address of state machine 0
static constexpr uint32_t SM0_INSTR = 0x0d8;  // Write to execute an instruction immediately (including jumps) and then resume execution.
static constexpr uint32_t SM0_PINCTRL = 0x0dc;  // State machine pin control
static constexpr uint32_t SM1_CLKDIV = 0x0e0;
static constexpr uint32_t SM1_PINCTRL = 0x0f4;
static constexpr uint32_t SM2_CLKDIV = 0x0f8;
static constexpr uint32_t SM2_PINCTRL = 0x10c;
static constexpr uint32_t SM3_CLKDIV = 0x110;
static constexpr uint32_t SM3_PINCTRL = 0x124;

// FSTAT bits
static constexpr uint32_t FSTAT_TXEMPTY = 1u << 24;
static constexpr uint32_t FSTAT_TXFULL = 1u << 16;
static constexpr uint32_t FSTAT_RXEMPTY = 1u << 8;
static constexpr uint32_t FSTAT_RXFULL = 1u << 0;

// FDEBUG bits
static constexpr uint32_t FDEBUG_TXSTALL = 1u << 24;
static constexpr uint32_t FDEBUG_TXOVER = 1u << 16;
static constexpr uint32_t FDEBUG_RXUNDER = 1u << 8;
static constexpr uint32_t FDEBUG_RXSTALL = 1u << 0;

// SHIFTCTRL bits
static constexpr uint32_t SHIFTCTRL_AUTOPUSH = 1u << 16;
static constexpr uint32_t SHIFTCTRL_AUTOPULL = 1u << 17;
static constexpr uint32_t SHIFTCTRL_IN_SHIFTDIR = 1u << 18;  // 1 = shift input shift register to right (data enters from left). 0 = to left
static constexpr uint32_t SHIFTCTRL_OUT_SHIFTDIR = 1u << 19;  // 1 = shift out of output shift register to right. 0 = to left
static constexpr uint32_t SHIFTCTRL_FJOIN_TX = 1u << 30;
static constexpr uint32_t SHIFTCTRL_FJOIN_RX = 1u << 31;

// EXECCTRL bits
static constexpr uint32_t EXECCTRL_STATUS_SEL = 1u << 4;
static constexpr uint32_t EXECCTRL_SIDE_PINDIR = 1u << 29;
static constexpr uint32_t EXECCTRL_SIDE_EN = 1u << 30;
static constexpr uint32_t EXECCTRL_EXEC_STALLED = 1u << 31;

static inline uint32_t bitReverse(uint32_t x) {
  x = ((x & 0x55555555) << 1) | ((x & 0xaaaaaaaa) >> 1);
  x = ((x & 0x33333333) << 2) | ((x & 0xcccccccc) >> 2);
  x = ((x & 0x0f0f0f0f) << 4) | ((x & 0xf0f0f0f0) >> 4);
  x = ((x & 0x00ff00ff) << 8) | ((x & 0xff00ff00) >> 8);
  x = ((x & 0x0000ffff) << 16) | ((x & 0xffff0000) >> 16);
  return x;
}

static inline uint32_t irqIndex(uint32_t irq, uint32_t machineIndex) {
  const bool rel = !!(irq & 0x10);
  return rel ? (irq & 0x4) | (((irq & 0x3) + machineIndex) & 0x3) : irq & 0x7;
}

static const std::array<DREQChannel, 4> dreqRx0 = {DREQ_PIO0_RX0, DREQ_PIO0_RX1, DREQ_PIO0_RX2, DREQ_PIO0_RX3};
static const std::array<DREQChannel, 4> dreqTx0 = {DREQ_PIO0_TX0, DREQ_PIO0_TX1, DREQ_PIO0_TX2, DREQ_PIO0_TX3};
static const std::array<DREQChannel, 4> dreqRx1 = {DREQ_PIO1_RX0, DREQ_PIO1_RX1, DREQ_PIO1_RX2, DREQ_PIO1_RX3};
static const std::array<DREQChannel, 4> dreqTx1 = {DREQ_PIO1_TX0, DREQ_PIO1_TX1, DREQ_PIO1_TX2, DREQ_PIO1_TX3};

/** `(1 << n) - 1` for n in 0..31, as the int32 pattern JS produces (n = 31 gives 0x7fffffff). */
static inline uint32_t lowMask(uint32_t n) { return (1u << (n & 31)) - 1u; }

// ---------------------------------------------------------------------------
// StateMachine

StateMachine::StateMachine(RP2040 &rp2040, RPPIO &pio, uint32_t index)
    : rp2040(rp2040), pio(pio), index(index), dreqRx(pio.dreqRx[index]), dreqTx(pio.dreqTx[index]) {
  updateDMARx();
  updateDMATx();
}

void StateMachine::updateDMATx() {
  if (txFIFO.full()) {
    rp2040.dma.clearDREQ(dreqTx);
  } else {
    rp2040.dma.setDREQ(dreqTx);
  }
}

void StateMachine::updateDMARx() {
  if (rxFIFO.empty()) {
    rp2040.dma.clearDREQ(dreqRx);
  } else {
    rp2040.dma.setDREQ(dreqRx);
  }
}

void StateMachine::writeFIFO(uint32_t value) {
  if (txFIFO.full()) {
    pio.fdebug |= FDEBUG_TXOVER << index;
    return;
  }
  txFIFO.push(value);
  pio.txStall &= ~(FDEBUG_TXSTALL << index);
  updateDMATx();
  checkWait();
  if (txFIFO.full()) {
    pio.checkInterrupts();
  }
}

uint32_t StateMachine::readFIFO() {
  if (rxFIFO.empty()) {
    pio.fdebug |= FDEBUG_RXUNDER << index;
    return 0;
  }
  const uint32_t result = rxFIFO.pull();
  pio.rxStall &= ~(FDEBUG_RXSTALL << index);
  updateDMARx();
  checkWait();
  if (rxFIFO.empty()) {
    pio.checkInterrupts();
  }
  return result;
}

uint32_t StateMachine::status() const {
  const uint32_t statusN = execCtrl & 0xf;
  if (execCtrl & EXECCTRL_STATUS_SEL) {
    return rxFIFO.itemCount() < statusN ? 0xffffffff : 0;
  } else {
    return txFIFO.itemCount() < statusN ? 0xffffffff : 0;
  }
}

bool StateMachine::jmpCondition(uint32_t condition) {
  switch (condition) {
    // (no condition): Always
    case 0b000:
      return true;

    // !X: scratch X zero
    case 0b001:
      return x == 0;

    // X--: scratch X non-zero, post-decrement
    case 0b010: {
      const uint32_t oldX = x;
      x = x - 1;  // `(this.x - 1) >>> 0`: exact for any int32/uint32 pattern
      return oldX != 0;
    }

    // !Y: scratch Y zero
    case 0b011:
      return y == 0;

    // Y--: scratch Y non-zero, post-decrement
    case 0b100: {
      const uint32_t oldY = y;
      y = y - 1;
      return oldY != 0;
    }

    // X!=Y: scratch X not equal scratch Y
    case 0b101:
      return x != y;

    // PIN: branch on input pin
    case 0b110: {
      auto &gpio = rp2040.gpio;
      const uint32_t jmpPin = this->jmpPin();
      return jmpPin < gpio.size() ? gpio[jmpPin].inputValue() : false;
    }

    // !OSRE: output shift register not empty
    case 0b111:
      return outputShiftCount < pullThreshold();
  }

  pio.error("jmpCondition with unsupported condition: " + std::to_string(condition));
  return false;
}

uint32_t StateMachine::inPins() const {
  const uint32_t gpioValues = rp2040.gpioValues();
  const uint32_t inBase = this->inBase();
  return inBase ? (gpioValues << (32 - inBase)) | (gpioValues >> inBase) : gpioValues;
}

uint32_t StateMachine::inSourceValue(uint32_t source) {
  switch (source) {
    // PINS
    case 0b000:
      return inPins();

    // X (scratch register X)
    case 0b001:
      return x;

    // Y (scratch register Y)
    case 0b010:
      return y;

    // NULL (all zeroes)
    case 0b011:
      return 0;

    // Reserved
    case 0b100:
      return 0;

    // Reserved for IN, STATUS for MOV
    case 0b101:
      return status();

    // ISR
    case 0b110:
      return inputShiftReg;

    // OSR
    case 0b111:
      return outputShiftReg;
  }

  pio.error("inSourceValue with unsupported source: " + std::to_string(source));
  return 0;
}

void StateMachine::writeOutValue(uint32_t destination, uint32_t value, uint32_t bitCount) {
  switch (destination) {
    // PINS
    case 0b000:
      setOutPins(value);
      break;

    // X (scratch register X)
    case 0b001:
      x = value;
      break;

    // Y (scratch register Y)
    case 0b010:
      y = value;
      break;

    // NULL (discard data)
    case 0b011:
      break;

    // PINDIRS
    case 0b100:
      setOutPinDirs(value);
      break;

    // PC
    case 0b101:
      pc = value & 0x1f;
      updatePC = false;
      break;

    // ISR (also sets ISR shift counter to Bit count)
    case 0b110:
      inputShiftReg = value;
      inputShiftCount = bitCount;
      break;

    // EXEC (Execute OSR shift data as instruction)
    case 0b111:
      execOpcode = value;
      execValid = true;
      break;
  }
}

uint32_t StateMachine::pushThreshold() const {
  const uint32_t value = (shiftCtrl >> 20) & 0x1f;
  return value ? value : 32;
}

uint32_t StateMachine::pullThreshold() const {
  const uint32_t value = (shiftCtrl >> 25) & 0x1f;
  return value ? value : 32;
}

uint32_t StateMachine::sidesetCount() const { return (pinCtrl >> 29) & 0x7; }

uint32_t StateMachine::setCount() const { return (pinCtrl >> 26) & 0x7; }

uint32_t StateMachine::outCount() const { return (pinCtrl >> 20) & 0x3f; }

uint32_t StateMachine::inBase() const { return (pinCtrl >> 15) & 0x1f; }

uint32_t StateMachine::sidesetBase() const { return (pinCtrl >> 10) & 0x1f; }

uint32_t StateMachine::setBase() const { return (pinCtrl >> 5) & 0x1f; }

uint32_t StateMachine::outBase() const { return (pinCtrl >> 0) & 0x1f; }

uint32_t StateMachine::jmpPin() const { return (execCtrl >> 24) & 0x1f; }

uint32_t StateMachine::wrapTop() const { return (execCtrl >> 12) & 0x1f; }

uint32_t StateMachine::wrapBottom() const { return (execCtrl >> 7) & 0x1f; }

void StateMachine::setOutPinDirs(uint32_t value) {
  outPinDirection = value;
  pio.pinDirectionsChanged(value, outBase(), outCount());
}

void StateMachine::setOutPins(uint32_t value) {
  outPinValues = value;
  pio.pinValuesChanged(value, outBase(), outCount());
}

void StateMachine::outInstruction(uint32_t arg) {
  const uint32_t bitCount = arg & 0x1f;
  const uint32_t destination = arg >> 5;

  if (bitCount == 0) {
    writeOutValue(destination, outputShiftReg, 32);
    outputShiftCount = 32;
  } else {
    if (shiftCtrl & SHIFTCTRL_OUT_SHIFTDIR) {
      const uint32_t value = outputShiftReg & lowMask(bitCount);
      outputShiftReg >>= bitCount;
      writeOutValue(destination, value, bitCount);
    } else {
      const uint32_t value = outputShiftReg >> (32 - bitCount);
      outputShiftReg <<= bitCount;
      writeOutValue(destination, value, bitCount);
    }
    outputShiftCount += bitCount;
    if (outputShiftCount > 32) {
      outputShiftCount = 32;
    }
  }
}

void StateMachine::executeInstruction(uint32_t opcode) {
  const uint32_t arg = opcode & 0xff;
  // `opcode >>> 13`: opcode is 16 bits (instructions[], `value & 0xffff`) except
  // for EXEC, whose opcode is a 32-bit OUT/MOV value; then this is 0..0x7ffff
  // and matches no case, exactly as in TS.
  switch (opcode >> 13) {
    /* JMP */
    case 0b000:
      if (jmpCondition(arg >> 5)) {
        pc = arg & 0x1f;
        updatePC = false;
      }
      break;

    /* WAIT */
    case 0b001: {
      const bool polarity = !!(arg & 0x80);
      const uint32_t source = (arg >> 5) & 0x3;
      const uint32_t index = arg & 0x1f;
      switch (source) {
        // GPIO:
        case 0b00:
          wait(WaitType::Pin, polarity, index);
          break;

        // PIN:
        case 0b01:
          wait(WaitType::Pin, polarity, (index + inBase()) % 32);
          break;

        // IRQ:
        case 0b10:
          wait(WaitType::IRQ, polarity, irqIndex(index, this->index));
          break;
      }
      break;
    }

    /* IN */
    case 0b010: {
      const uint32_t bitCount = arg & 0x1f;
      uint32_t sourceValue = inSourceValue(arg >> 5);

      if (bitCount == 0) {
        inputShiftReg = sourceValue;
        inputShiftCount = 32;
      } else {
        sourceValue &= lowMask(bitCount);
        if (shiftCtrl & SHIFTCTRL_IN_SHIFTDIR) {
          inputShiftReg >>= bitCount;
          inputShiftReg |= sourceValue << (32 - bitCount);
        } else {
          inputShiftReg <<= bitCount;
          inputShiftReg |= sourceValue;
        }
        inputShiftCount += bitCount;
        if (inputShiftCount > 32) {
          inputShiftCount = 32;
        }
      }

      if (shiftCtrl & SHIFTCTRL_AUTOPUSH && inputShiftCount >= pushThreshold()) {
        if (!rxFIFO.full()) {
          rxFIFO.push(inputShiftReg);
          updateDMARx();
          pio.checkInterrupts();
        } else {
          pio.rxStall |= FDEBUG_RXSTALL << this->index;
          pio.fdebug |= pio.rxStall;
          wait(WaitType::rxFIFO, false, inputShiftReg);
        }
        inputShiftCount = 0;
        inputShiftReg = 0;
      }

      break;
    }

    /* OUT */
    case 0b011: {
      if (shiftCtrl & SHIFTCTRL_AUTOPULL && outputShiftCount >= pullThreshold()) {
        outputShiftCount = 0;
        if (!txFIFO.empty()) {
          outputShiftReg = txFIFO.pull();
          updateDMATx();
          pio.checkInterrupts();
        } else {
          pio.txStall |= FDEBUG_TXSTALL << this->index;
          pio.fdebug |= pio.txStall;
          wait(WaitType::Out, false, arg);
        }
      }

      if (!waiting) {
        outInstruction(arg);
      }
      break;
    }

    /* PUSH/PULL */
    case 0b100: {
      const bool block = !!(arg & (1 << 5));
      const bool ifFullOrEmpty = !!(arg & (1 << 6));
      if (arg & 0x1f) {
        // Unknown instruction
        break;
      }
      if (arg & 0x80) {
        // PULL
        if (ifFullOrEmpty && shiftCtrl & SHIFTCTRL_AUTOPULL && outputShiftCount < pullThreshold()) {
          break;
        }
        if (!txFIFO.empty()) {
          outputShiftReg = txFIFO.pull();
          updateDMATx();
          pio.checkInterrupts();
        } else {
          pio.txStall |= FDEBUG_TXSTALL << this->index;
          pio.fdebug |= pio.txStall;
          if (block) {
            wait(WaitType::txFIFO, false, 0);
          } else {
            outputShiftReg = x;
          }
        }
        outputShiftCount = 0;
      } else {
        // PUSH
        if (ifFullOrEmpty && shiftCtrl & SHIFTCTRL_AUTOPUSH && inputShiftCount < pushThreshold()) {
          break;
        }
        if (!rxFIFO.full()) {
          rxFIFO.push(inputShiftReg);
          updateDMARx();
          pio.checkInterrupts();
        } else {
          pio.rxStall |= FDEBUG_RXSTALL << this->index;
          pio.fdebug |= pio.rxStall;
          if (block) {
            wait(WaitType::rxFIFO, false, inputShiftReg);
          }
        }
        inputShiftReg = 0;
        inputShiftCount = 0;
      }
      break;
    }

    /* MOV */
    case 0b101: {
      const uint32_t source = arg & 0x7;
      const uint32_t op = (arg >> 3) & 0x3;
      const uint32_t destination = (arg >> 5) & 0x7;
      const uint32_t value = inSourceValue(source);
      const uint32_t transformedValue = transformMovValue(value, op);
      setMovDestination(destination, transformedValue);
      break;
    }

    /* IRQ */
    case 0b110: {
      if (arg & 0x80) {
        // Unknown instruction
        break;
      }
      const bool clear = !!(arg & 0x40);
      const bool wait = !!(arg & 0x20);
      const uint32_t irq = irqIndex(arg & 0x1f, this->index);
      if (clear) {
        pio.irq &= ~(1u << irq);
        pio.irqUpdated();
      } else {
        pio.irq |= 1u << irq;
        pio.irqUpdated();
        if (wait) {
          this->wait(WaitType::IRQ, false, irq);
        }
      }
      break;
    }

    /* SET */
    case 0b111: {
      const uint32_t data = arg & 0x1f;
      const uint32_t destination = arg >> 5;
      switch (destination) {
        case 0b000:
          setSetPins(data);
          break;
        case 0b001:
          x = data;
          break;
        case 0b010:
          y = data;
          break;
        case 0b100:
          setSetPinDirs(data);
          break;
      }
      break;
    }
  }

  cycles++;

  const uint32_t sidesetCount = this->sidesetCount();
  const uint32_t execCtrl = this->execCtrl;
  // `opcode >> 8`: for an EXEC'd 32-bit value with bit 31 set JS gives a
  // negative number, but `& 0x1f` only keeps bits 8..12 either way.
  const uint32_t delaySideset = (opcode >> 8) & 0x1f;
  const bool sideEn = !!(execCtrl & EXECCTRL_SIDE_EN);
  // sidesetCount is 0..7: for 6 and 7 the JS shift count `5 - sidesetCount`
  // is negative and taken & 31 (so the mask is 0x7fffffff / 0x3fffffff).
  const int32_t delay =
      static_cast<int32_t>(delaySideset & lowMask(static_cast<uint32_t>(5 - static_cast<int32_t>(sidesetCount))));

  if (sidesetCount && (!sideEn || delaySideset & 0x10)) {
    const uint32_t sideset = static_cast<uint32_t>(
        jsSar(static_cast<int32_t>(delaySideset), static_cast<uint32_t>(5 - static_cast<int32_t>(sidesetCount))));
    setSideset(sideset, sideEn ? sidesetCount - 1 : sidesetCount);
  }

  if (execValid) {
    execValid = false;
    executeInstruction(execOpcode);
  } else if (waiting) {
    if (waitDelay < 0) {
      waitDelay = delay;
    }
    checkWait();
  } else {
    cycles += delay;
    delayLeft = delay;
  }
}

void StateMachine::wait(WaitType type, bool polarity, uint32_t index) {
  waiting = true;
  waitType = type;
  waitPolarity = polarity;
  waitIndex = index;
  waitDelay = -1;
  updatePC = false;
}

void StateMachine::nextPC() {
  if (pc == wrapTop()) {
    pc = wrapBottom();
  } else {
    pc = (pc + 1) & 0x1f;
  }
}

void StateMachine::step() {
  if (delayLeft > 0) {
    delayLeft--;
    return;
  }
  if (waiting) {
    checkWait();
    if (waiting) {
      return;
    }
  }

  updatePC = true;
  executeInstruction(pio.instructions[pc]);
  if (updatePC) {
    nextPC();
  }
}

void StateMachine::setSetPinDirs(uint32_t value) { pio.pinDirectionsChanged(value, setBase(), setCount()); }

void StateMachine::setSetPins(uint32_t value) { pio.pinValuesChanged(value, setBase(), setCount()); }

void StateMachine::setSideset(uint32_t value, uint32_t count) {
  if (execCtrl & EXECCTRL_SIDE_PINDIR) {
    pio.pinDirectionsChanged(value, sidesetBase(), count);
  } else {
    pio.pinValuesChanged(value, sidesetBase(), count);
  }
}

uint32_t StateMachine::transformMovValue(uint32_t value, uint32_t op) {
  // The caller applies `>>> 0` (so `~value` is only ever seen as a pattern).
  switch (op) {
    case 0b00:
      return value;
    case 0b01:
      return ~value;
    case 0b10:
      return bitReverse(value);
    case 0b11:
    default:
      return value;  // reserved
  }
}

void StateMachine::setMovDestination(uint32_t destination, uint32_t value) {
  switch (destination) {
    // PINS
    case 0b000:
      setOutPins(value);
      break;

    // X (scratch register X)
    case 0b001:
      x = value;
      break;

    // Y (scratch register Y)
    case 0b010:
      y = value;
      break;

    // reserved (discard data)
    case 0b011:
      break;

    // EXEC
    case 0b100:
      execOpcode = value;
      execValid = true;
      break;

    // PC
    case 0b101:
      pc = value & 0x1f;
      updatePC = false;
      break;

    // ISR (Input shift counter is reset to 0 by this operation, i.e. empty)
    case 0b110:
      inputShiftReg = value;
      inputShiftCount = 0;
      break;

    // OSR (Output shift counter is reset to 0 by this operation, i.e. full)
    case 0b111:
      outputShiftReg = value;
      outputShiftCount = 0;
      break;
  }
}

uint32_t StateMachine::readUint32(uint32_t offset) {
  switch (offset + SM0_CLKDIV) {
    case SM0_CLKDIV:
      return (clockDivInt << 16) | (clockDivFrac << 8);
    case SM0_EXECCTRL:
      return execCtrl;
    case SM0_SHIFTCTRL:
      return shiftCtrl;
    case SM0_ADDR:
      return pc;
    case SM0_INSTR:
      return pio.instructions[pc];
    case SM0_PINCTRL:
      return pinCtrl;
  }
  pio.error("Read from invalid state machine register: " + std::to_string(offset));
  return 0;
}

void StateMachine::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset + SM0_CLKDIV) {
    case SM0_CLKDIV:
      clockDivFrac = (value >> 8) & 0xff;
      clockDivInt = value >> 16;
      break;
    case SM0_EXECCTRL:
      execCtrl = (value & 0x7fffffff) | (execCtrl & 0x80000000);
      break;
    case SM0_SHIFTCTRL: {
      // Changing either join bit flushes both FIFOs (pio_sm_clear_fifos
      // relies on this); joining gives one FIFO all 8 entries.
      const uint32_t join = SHIFTCTRL_FJOIN_TX | SHIFTCTRL_FJOIN_RX;
      if ((value ^ shiftCtrl) & join) {
        const uint32_t tx = value & SHIFTCTRL_FJOIN_TX ? 8 : value & SHIFTCTRL_FJOIN_RX ? 0 : 4;
        const uint32_t rx = value & SHIFTCTRL_FJOIN_RX ? 8 : value & SHIFTCTRL_FJOIN_TX ? 0 : 4;
        txFIFO.resize(tx);
        rxFIFO.resize(rx);
        updateDMATx();
        updateDMARx();
      }
      shiftCtrl = value;
      break;
    }
    case SM0_ADDR:
      /* read-only */
      break;
    case SM0_INSTR:
      executeInstruction(value & 0xffff);
      if (waiting) {
        execCtrl |= EXECCTRL_EXEC_STALLED;
      }
      break;
    case SM0_PINCTRL:
      pinCtrl = value;
      break;
    default:
      pio.error("Write to invalid state machine register: " + std::to_string(offset));
  }
}

uint32_t StateMachine::fifoStat() const {
  const uint32_t result = (txFIFO.empty() ? FSTAT_TXEMPTY : 0) | (txFIFO.full() ? FSTAT_TXFULL : 0) |
                          (rxFIFO.empty() ? FSTAT_RXEMPTY : 0) | (rxFIFO.full() ? FSTAT_RXFULL : 0);
  return result << index;
}

void StateMachine::restart() {
  cycles = 0;
  delayLeft = 0;
  inputShiftCount = 0;
  outputShiftCount = 32;
  inputShiftReg = 0;
  waiting = false;
  // TODO any pin write left asserted due to OUT_STICKY.
}

void StateMachine::clkDivRestart() { divPhase = 0; }

void StateMachine::clockTick() {
  if (!enabled) {
    return;
  }
  const uint32_t div = (clockDivInt ? clockDivInt : 65536) * 256 + clockDivFrac;
  divPhase += 256;
  if (divPhase >= div) {
    divPhase -= div;
    step();
  }
}

void StateMachine::checkWait() {
  if (!waiting) {
    return;
  }

  switch (waitType) {
    case WaitType::IRQ: {
      // waitIndex is an IRQ number 0..7 here (irqIndex)
      const bool irqValue = !!(pio.irq & (1u << (waitIndex & 31)));
      if (irqValue == waitPolarity) {
        waiting = false;
        if (irqValue) {
          pio.irq &= ~(1u << (waitIndex & 31));
        }
      }
      break;
    }

    case WaitType::Pin: {
      if (waitIndex < rp2040.gpio.size() && rp2040.gpio[waitIndex].inputValue() == waitPolarity) {
        waiting = false;
      }
      break;
    }

    case WaitType::rxFIFO: {
      if (!rxFIFO.full()) {
        rxFIFO.push(waitIndex);
        waiting = false;
        updateDMARx();
        pio.checkInterrupts();
      }
      break;
    }

    case WaitType::txFIFO: {
      if (!txFIFO.empty()) {
        outputShiftReg = txFIFO.pull();
        waiting = false;
        updateDMATx();
        pio.checkInterrupts();
      }
      break;
    }

    case WaitType::Out: {
      if (!txFIFO.empty()) {
        outputShiftReg = txFIFO.pull();
        outInstruction(waitIndex);
        waiting = false;
        updateDMATx();
        pio.checkInterrupts();
      }
      break;
    }

    case WaitType::None:
      break;
  }

  if (!waiting) {
    nextPC();
    cycles += waitDelay;
    // a stalled instruction's delay starts once it completes
    delayLeft = std::max(0, waitDelay);
    execCtrl &= ~EXECCTRL_EXEC_STALLED;
  }
}

// ---------------------------------------------------------------------------
// RPPIO

RPPIO::RPPIO(RP2040 &rp2040, const std::string &name, uint32_t firstIrq, uint32_t index)
    : BasePeripheral(rp2040, name),
      firstIrq(firstIrq),
      index(index),
      dreqRx(index ? dreqRx1 : dreqRx0),
      dreqTx(index ? dreqTx1 : dreqTx0),
      machines{{{rp2040, *this, 0}, {rp2040, *this, 1}, {rp2040, *this, 2}, {rp2040, *this, 3}}} {
  // `run()`: one batch; TS then re-arms itself with `setTimeout(() => this.run(), 0)`
  // while not stopped (see pio.h).
  run = [this] {
    for (int i = 0; i < 1000 && !stopped; i++) {
      step();
    }
  };
}

uint32_t RPPIO::intRaw() const {
  return ((irq & 0xf) << 8) | (!machines[3].txFIFO.full() ? 0x80 : 0) | (!machines[2].txFIFO.full() ? 0x40 : 0) |
         (!machines[1].txFIFO.full() ? 0x20 : 0) | (!machines[0].txFIFO.full() ? 0x10 : 0) |
         (!machines[3].rxFIFO.empty() ? 0x08 : 0) | (!machines[2].rxFIFO.empty() ? 0x04 : 0) |
         (!machines[1].rxFIFO.empty() ? 0x02 : 0) | (!machines[0].rxFIFO.empty() ? 0x01 : 0);
}

uint32_t RPPIO::irq0IntStatus() const { return (intRaw() & irq0IntEnable) | irq0IntForce; }

uint32_t RPPIO::irq1IntStatus() const { return (intRaw() & irq1IntEnable) | irq1IntForce; }

uint32_t RPPIO::readUint32(uint32_t offset) {
  sync();  // fast path: the bus sees the exact state
  if (offset >= SM0_CLKDIV && offset <= SM0_PINCTRL) {
    return machines[0].readUint32(offset - SM0_CLKDIV);
  }
  if (offset >= SM1_CLKDIV && offset <= SM1_PINCTRL) {
    return machines[1].readUint32(offset - SM1_CLKDIV);
  }
  if (offset >= SM2_CLKDIV && offset <= SM2_PINCTRL) {
    return machines[2].readUint32(offset - SM2_CLKDIV);
  }
  if (offset >= SM3_CLKDIV && offset <= SM3_PINCTRL) {
    return machines[3].readUint32(offset - SM3_CLKDIV);
  }

  switch (offset) {
    case CTRL:
      return (machines[0].enabled ? 1 << 0 : 0) | (machines[1].enabled ? 1 << 1 : 0) |
             (machines[2].enabled ? 1 << 2 : 0) | (machines[3].enabled ? 1 << 3 : 0);
    case FSTAT:
      return machines[0].fifoStat() | machines[1].fifoStat() | machines[2].fifoStat() | machines[3].fifoStat();
    case FDEBUG:
      return fdebug;
    case FLEVEL:
      return (machines[0].txFIFO.itemCount() & 0xf) | ((machines[0].rxFIFO.itemCount() & 0xf) << 4) |
             ((machines[1].txFIFO.itemCount() & 0xf) << 8) | ((machines[1].rxFIFO.itemCount() & 0xf) << 12) |
             ((machines[2].txFIFO.itemCount() & 0xf) << 16) | ((machines[2].rxFIFO.itemCount() & 0xf) << 20) |
             ((machines[3].txFIFO.itemCount() & 0xf) << 24) | ((machines[3].rxFIFO.itemCount() & 0xf) << 28);

    case RXF0:
      return machines[0].readFIFO();
    case RXF1:
      return machines[1].readFIFO();
    case RXF2:
      return machines[2].readFIFO();
    case RXF3:
      return machines[3].readFIFO();
    case IRQ_:
      return irq;
    case IRQ_FORCE:
      return 0;
    case INPUT_SYNC_BYPASS:
      return inputSyncBypass;
    case DBG_PADOUT:
      return pinValues;
    case DBG_PADOE:
      return pinDirections;
    case DBG_CFGINFO:
      return 0x200404;
    case INTR:
      return intRaw();
    case IRQ0_INTE:
      return irq0IntEnable;
    case IRQ0_INTF:
      return irq0IntForce;
    case IRQ0_INTS:
      return irq0IntStatus();
    case IRQ1_INTE:
      return irq1IntEnable;
    case IRQ1_INTF:
      return irq1IntForce;
    case IRQ1_INTS:
      return irq1IntStatus();
  }
  return BasePeripheral::readUint32(offset);
}

void RPPIO::writeUint32(uint32_t offset, uint32_t value) {
  sync();  // fast path: the write lands on the exact state
  if (offset == CTRL || (offset >= INSTR_MEM0 && offset <= INSTR_MEM31) ||
      (offset >= SM0_CLKDIV && offset <= SM3_PINCTRL)) {
    // a program or configuration change: the fast path's analysis is stale
    progEpoch = progEpoch + 1 ? progEpoch + 1 : 1;
  }
  if (offset >= INSTR_MEM0 && offset <= INSTR_MEM31) {
    const uint32_t index = (offset - INSTR_MEM0) >> 2;
    instructions[index] = value & 0xffff;
    return;
  }
  if (offset >= SM0_CLKDIV && offset <= SM0_PINCTRL) {
    machines[0].writeUint32(offset - SM0_CLKDIV, value);
    return;
  }
  if (offset >= SM1_CLKDIV && offset <= SM1_PINCTRL) {
    machines[1].writeUint32(offset - SM1_CLKDIV, value);
    return;
  }
  if (offset >= SM2_CLKDIV && offset <= SM2_PINCTRL) {
    machines[2].writeUint32(offset - SM2_CLKDIV, value);
    return;
  }
  if (offset >= SM3_CLKDIV && offset <= SM3_PINCTRL) {
    machines[3].writeUint32(offset - SM3_CLKDIV, value);
    return;
  }
  switch (offset) {
    case CTRL: {
      for (uint32_t index = 0; index < 4; index++) {
        machines[index].enabled = value & (1u << index) ? true : false;
        if (value & (1u << (4 + index))) {
          machines[index].restart();
        }
        if (value & (1u << (8 + index))) {
          machines[index].clkDivRestart();
        }
      }
      const uint32_t shouldRun = value & 0xf;
      if (stopped && shouldRun) {
        stopped = false;
        run();
      }
      if (!shouldRun) {
        stopped = true;
      }
      break;
    }
    case FDEBUG:
      fdebug &= ~rawWriteValue;
      fdebug |= txStall | rxStall;
      break;
    case TXF0:
      machines[0].writeFIFO(value);
      break;
    case TXF1:
      machines[1].writeFIFO(value);
      break;
    case TXF2:
      machines[2].writeFIFO(value);
      break;
    case TXF3:
      machines[3].writeFIFO(value);
      break;
    case IRQ_:
      irq &= ~rawWriteValue;
      irqUpdated();
      break;
    case INPUT_SYNC_BYPASS:
      inputSyncBypass = value;
      break;
    case IRQ_FORCE:
      irq |= value;
      irqUpdated();
      break;
    case IRQ0_INTE:
      irq0IntEnable = value & 0xfff;
      checkInterrupts();
      break;
    case IRQ0_INTF:
      irq0IntForce = value & 0xfff;
      checkInterrupts();
      break;
    case IRQ1_INTE:
      irq1IntEnable = value & 0xfff;
      checkInterrupts();
      break;
    case IRQ1_INTF:
      irq1IntForce = value & 0xfff;
      checkInterrupts();
      break;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

void RPPIO::pinValuesChanged(uint32_t value, uint32_t firstPin, uint32_t count) {
  // TODO: wrapping after pin 31
  const uint32_t mask = count > 31 ? 0xffffffff : lowMask(count) << firstPin;
  const uint32_t newValue = ((pinValues & ~mask) | ((value << firstPin) & mask)) & 0x3fffffff;
  pinValues = newValue;
}

void RPPIO::pinDirectionsChanged(uint32_t value, uint32_t firstPin, uint32_t count) {
  // TODO: wrapping after pin 31
  const uint32_t mask = count > 31 ? 0xffffffff : lowMask(count) << firstPin;
  const uint32_t newValue = ((pinDirections & ~mask) | ((value << firstPin) & mask)) & 0x3fffffff;
  pinDirections = newValue;
}

void RPPIO::checkInterrupts() {
  const uint32_t firstIrq = this->firstIrq;
  rp2040.setInterrupt(firstIrq, !!irq0IntStatus());
  rp2040.setInterrupt(firstIrq + 1, !!irq1IntStatus());
}

void RPPIO::irqUpdated() {
  for (StateMachine &machine : machines) {
    machine.checkWait();
  }
  checkInterrupts();
}

void RPPIO::checkChangedPins() {
  const uint32_t changedPins = (oldPinDirections ^ pinDirections) | (oldPinValues ^ pinValues);
  if (changedPins) {
    oldPinDirections = pinDirections;
    oldPinValues = pinValues;

    // Notify GPIO about the changed pins
    // (`for gpioIndex < gpio.length: if (changedPins & (1 << gpioIndex))`,
    // visiting only the set bits, in the same ascending order)
    auto &gpio = rp2040.gpio;
    static_assert(std::tuple_size<std::remove_reference_t<decltype(gpio)>>::value < 32, "gpio.length < 32");
    for (uint32_t bits = changedPins & ((1u << gpio.size()) - 1); bits; bits &= bits - 1) {
      gpio[static_cast<uint32_t>(__builtin_ctz(bits))].checkForUpdates();
    }
  }
}

void RPPIO::step() {
  if (lazy) {
    if (owed < nextEvent) {
      owed++;
      return;
    }
    materialize();
  }
  for (StateMachine &machine : machines) {
    machine.clockTick();
  }
  checkChangedPins();
  if (fastPath) {
    tryEnterLazy();
  }
}

void RPPIO::stop() {
  sync();
  for (StateMachine &machine : machines) {
    machine.enabled = false;
  }
  stopped = true;
  // (no runTimer to clear)
}

// ---------------------------------------------------------------------------
// Fast path (not in rp2040js).
//
// The block goes lazy after a step() when every enabled machine is either
//  - stalled: waiting, no delay or EXEC pending, its wait condition false now
//    and changeable only by an event that syncs first (a GPIO input, IO_BANK0
//    or PADS write, or a bus access to this block: FIFOs and IRQ flags only
//    change through the bus or through other machines of the block, which
//    here execute nothing but OUTs). Its step() is then a no-op apart from the
//    clock divider phase, which advances by 256 mod the divisor per cycle; or
//  - a runner: divider 1, autopull on, and every instruction reachable from
//    its pc an OUT to PINS/X/Y/NULL/PINDIRS/PC/ISR with one common nonzero
//    bit count and no delay (PicoDVI's `out pc, 1 side n` loop). Until the
//    instruction that autopulls, its step() touches only its own registers
//    and the block's pinValues/pinDirections under its pin mask: no FIFO,
//    DREQ, IRQ or wait, and nothing that reads anything outside the machine.
//    That instruction's cycle (nextEvent) is run for real.
// and the runners' pin masks are disjoint, free of GPIO listeners and muxed
// to this block, and oldPin* == pin* (checkChangedPins has run).
//
// While lazy, step() only counts cycles. Per cycle, the exact path's only
// effects outside the machines are then checkChangedPins' calls to
// GPIOPin::checkForUpdates for the runners' pins; with no listeners that only
// sets the pin's lastValue to value(), which depends on the pin's PIO output
// bits and its ctrl and pad registers, and those registers cannot change
// without a sync. So materialize() replays each runner's owed cycles with the
// real clockTick() (each machine alone: the masks are disjoint and nothing in
// them reads another machine's state) and then calls checkForUpdates, in
// ascending order, for every pin that changed in any of those cycles, which
// leaves every pin's lastValue as the exact path would. Everything else (pc,
// shift registers, counts, cycles, pin registers, divider phases) is then
// exactly what per-cycle stepping gives.

bool StateMachine::stalledStable() const {
  if (!waiting || delayLeft > 0 || execValid) {
    return false;
  }
  const uint32_t div = (clockDivInt ? clockDivInt : 65536) * 256 + clockDivFrac;
  if (divPhase >= div) {
    return false;  // the divider would step more than once in a cycle (a divisor shrunk)
  }
  switch (waitType) {
    case WaitType::IRQ:
      return !!(pio.irq & (1u << (waitIndex & 31))) != waitPolarity;
    case WaitType::Pin:
      return !(waitIndex < rp2040.gpio.size() && rp2040.gpio[waitIndex].inputValue() == waitPolarity);
    case WaitType::rxFIFO:
      return rxFIFO.full();
    case WaitType::txFIFO:
    case WaitType::Out:
      return txFIFO.empty();
    case WaitType::None:
      break;
  }
  return false;
}

/** the pins `pinValuesChanged(value, firstPin, count)` can change */
static inline uint32_t pinMask(uint32_t firstPin, uint32_t count) {
  return (count > 31 ? 0xffffffff : lowMask(count) << firstPin) & 0x3fffffff;
}

bool StateMachine::runnerProgram(uint32_t &mask, uint32_t &bits) {
  if (analysedEpoch != pio.progEpoch) {
    analysedEpoch = pio.progEpoch;
    analysedPcs = 0;
    runnerPcs = 0;
    runnerPcOnly = 0;
  }
  const uint32_t start = pc & 0x1f;
  if (!(analysedPcs & (1u << start))) {
    analysedPcs |= 1u << start;
    const uint32_t sidesetCount = this->sidesetCount();
    const bool sideEn = !!(execCtrl & EXECCTRL_SIDE_EN);
    const uint32_t sideMask = sidesetCount ? pinMask(sidesetBase(), sideEn ? sidesetCount - 1 : sidesetCount) : 0;
    const uint32_t outMask = pinMask(outBase(), outCount());
    uint32_t seen = 1u << start, todo = 1u << start, m = 0, b = 0;
    bool ok = true, pcOnly = true;
    while (todo && ok) {
      const uint32_t at = static_cast<uint32_t>(__builtin_ctz(todo));
      todo &= todo - 1;
      const uint32_t opcode = pio.instructions[at];
      const uint32_t arg = opcode & 0xff;
      const uint32_t bitCount = arg & 0x1f, destination = arg >> 5;
      const uint32_t delaySideset = (opcode >> 8) & 0x1f;
      const uint32_t delay = delaySideset & lowMask(static_cast<uint32_t>(5 - static_cast<int32_t>(sidesetCount)));
      if (opcode >> 13 != 0b011 || bitCount == 0 || (b && bitCount != b) || destination == 0b111 || delay) {
        ok = false;
        break;
      }
      b = bitCount;
      pcOnly = pcOnly && destination == 0b101;
      LazyOp &op = lazyOps[at];
      op.destination = static_cast<uint8_t>(destination);
      op.bitCount = static_cast<uint8_t>(bitCount);
      op.next = static_cast<uint8_t>(at == wrapTop() ? wrapBottom() : (at + 1) & 0x1f);
      op.sideset = sidesetCount && (!sideEn || delaySideset & 0x10);
      if (op.sideset) {
        // setSideset(sideset, count) -> pinValuesChanged(value, sidesetBase(), count)
        const uint32_t sideset =
            static_cast<uint32_t>(jsSar(static_cast<int32_t>(delaySideset), static_cast<uint32_t>(5 - static_cast<int32_t>(sidesetCount))));
        op.sideMask = sideMask;
        op.sideBits = (sideset << sidesetBase()) & sideMask;
      }
      if (destination == 0b000 || destination == 0b100) {
        m |= outMask;
      }
      if (sidesetCount && (!sideEn || delaySideset & 0x10)) {
        m |= sideMask;
      }
      uint32_t next;
      if (destination == 0b101) {
        next = bitCount >= 5 ? 0xffffffff : lowMask(1u << bitCount);  // pcs 0 .. 2**bitCount - 1
      } else {
        next = 1u << (at == wrapTop() ? wrapBottom() : (at + 1) & 0x1f);
      }
      todo |= next & ~seen;
      seen |= next;
    }
    if (ok) {
      runnerPcs |= 1u << start;
      if (pcOnly) {
        runnerPcOnly |= 1u << start;
      }
      runnerMask[start] = m;
      runnerBits[start] = static_cast<uint8_t>(b);
    }
  }
  if (!(runnerPcs & (1u << start))) {
    return false;
  }
  mask = runnerMask[start];
  bits = runnerBits[start];
  return true;
}

// clockTick() for a runner, `cycles` times: with divider 1 each tick is a
// step() (divPhase keeps its value), with no delay left and no wait each step
// executes pio.instructions[pc], an OUT that does not autopull (runnerProgram
// and nextEvent). This is that path of step(), executeInstruction(),
// outInstruction(), writeOutValue(), setSideset() and nextPC(), in the same
// order, specialised: bitCount != 0, destination != EXEC, delay 0.
uint32_t StateMachine::runLazy(uint64_t n) {
  if (!n) {
    return 0;
  }
  const bool shiftRight = !!(shiftCtrl & SHIFTCTRL_OUT_SHIFTDIR);
  const bool sidePinDir = !!(execCtrl & EXECCTRL_SIDE_PINDIR);
  const uint32_t outBase = this->outBase(), outMask = pinMask(outBase, outCount());
  // the machine's state in locals (the member and pio references may alias)
  uint32_t values = pio.pinValues, directions = pio.pinDirections;
  uint32_t osr = outputShiftReg, count = outputShiftCount, pc = this->pc;
  uint32_t x = this->x, y = this->y, isr = inputShiftReg, isc = inputShiftCount;
  uint32_t outValues = outPinValues, outDirections = outPinDirection;
  uint32_t touched = 0;
  bool update = true;
  const std::array<LazyOp, 32> &ops = lazyOps;
  if (runnerPcOnly & (1u << pc)) {
    // The same loop for a program of `out pc, n` only (the PicoDVI
    // serialiser): the OUT changes no pins and sets next = value & 0x1f,
    // update = false; every bit count is ops[pc].bitCount.
    const uint32_t bitCount = ops[pc].bitCount;
    const uint32_t mask = lowMask(bitCount);
    uint32_t previous = values, previousDirections = directions;
    for (uint64_t i = 0; i < n; i++) {
      const LazyOp &op = ops[pc];
      uint32_t value;
      if (shiftRight) {
        value = osr & mask;
        osr >>= bitCount;
      } else {
        value = osr >> (32 - bitCount);
        osr <<= bitCount;
      }
      if (op.sideset) {
        if (sidePinDir) {
          directions = ((directions & ~op.sideMask) | op.sideBits) & 0x3fffffff;
        } else {
          values = ((values & ~op.sideMask) | op.sideBits) & 0x3fffffff;
        }
      }
      pc = value & 0x1f;
      touched |= (previous ^ values) | (previousDirections ^ directions);
      previous = values;
      previousDirections = directions;
    }
    // count += bitCount per instruction, capped at 32
    const uint64_t total = count + n * bitCount;
    count = total > 32 ? 32 : static_cast<uint32_t>(total);
    update = false;
  } else {
  for (uint64_t i = 0; i < n; i++) {
    const uint32_t before = values, beforeDirections = directions;
    const LazyOp &op = ops[pc];
    // outInstruction(arg)
    const uint32_t bitCount = op.bitCount;
    uint32_t value;
    if (shiftRight) {
      value = osr & lowMask(bitCount);
      osr >>= bitCount;
    } else {
      value = osr >> (32 - bitCount);
      osr <<= bitCount;
    }
    uint32_t next = op.next;
    update = true;
    switch (op.destination) {
      case 0b000:  // setOutPins(value)
        outValues = value;
        values = ((values & ~outMask) | ((value << outBase) & outMask)) & 0x3fffffff;
        break;
      case 0b001:
        x = value;
        break;
      case 0b010:
        y = value;
        break;
      case 0b011:
        break;
      case 0b100:  // setOutPinDirs(value)
        outDirections = value;
        directions = ((directions & ~outMask) | ((value << outBase) & outMask)) & 0x3fffffff;
        break;
      case 0b101:
        next = value & 0x1f;
        update = false;
        break;
      case 0b110:
        isr = value;
        isc = bitCount;
        break;
    }
    count += bitCount;
    if (count > 32) {
      count = 32;
    }
    if (op.sideset) {  // setSideset(): pinDirectionsChanged / pinValuesChanged
      if (sidePinDir) {
        directions = ((directions & ~op.sideMask) | op.sideBits) & 0x3fffffff;
      } else {
        values = ((values & ~op.sideMask) | op.sideBits) & 0x3fffffff;
      }
    }
    pc = next;
    touched |= (before ^ values) | (beforeDirections ^ directions);
  }
  }
  pio.pinValues = values;
  pio.pinDirections = directions;
  outputShiftReg = osr;
  outputShiftCount = count;
  this->pc = pc;
  this->x = x;
  this->y = y;
  inputShiftReg = isr;
  inputShiftCount = isc;
  outPinValues = outValues;
  outPinDirection = outDirections;
  // `cycles++` once per instruction (delay 0): the sum of n ones is exact below 2**53
  cycles += static_cast<double>(n);
  updatePC = update;
  delayLeft = 0;  // not waiting, delay 0: `cycles += 0; delayLeft = 0`
  return touched;
}

void RPPIO::tryEnterLazy() {
  if (oldPinValues != pinValues || oldPinDirections != pinDirections) {
    return;
  }
  uint64_t next = UINT64_MAX;
  uint32_t used = 0;
  for (StateMachine &sm : machines) {
    if (!sm.enabled) {
      continue;
    }
    if (sm.waiting) {
      if (!sm.stalledStable()) {
        return;
      }
      continue;
    }
    if (sm.execValid || sm.delayLeft > 0 || sm.clockDivInt != 1 || sm.clockDivFrac != 0 ||
        !(sm.shiftCtrl & SHIFTCTRL_AUTOPULL)) {
      return;
    }
    uint32_t mask, bits;
    if (!sm.runnerProgram(mask, bits)) {
      return;
    }
    const uint32_t threshold = sm.pullThreshold(), count = sm.outputShiftCount;
    if (count >= threshold || (mask & used)) {
      return;
    }
    used |= mask;
    // the instructions before the one that autopulls (the count caps at 32 >= threshold)
    next = std::min<uint64_t>(next, (threshold - count + bits - 1) / bits);
  }
  const uint32_t function = index ? FUNCTION_PIO1 : FUNCTION_PIO0;
  for (uint32_t bits = used & ((1u << rp2040.gpio.size()) - 1); bits; bits &= bits - 1) {
    const GPIOPin &pin = rp2040.gpio[static_cast<uint32_t>(__builtin_ctz(bits))];
    if (pin.hasListeners() || pin.functionSelect() != function) {
      return;
    }
  }
  lazy = true;
  owed = 0;
  nextEvent = next;
}

void RPPIO::materialize() {
  lazy = false;
  const uint64_t cycles = owed;
  owed = 0;
  if (!cycles) {
    return;
  }
  lazyCycles += cycles;
  uint32_t touched = 0;
  for (StateMachine &sm : machines) {
    if (!sm.enabled) {
      continue;
    }
    if (sm.waiting) {
      const uint64_t div = (sm.clockDivInt ? sm.clockDivInt : 65536) * 256ull + sm.clockDivFrac;
      sm.divPhase = static_cast<uint32_t>((sm.divPhase + 256 * cycles) % div);
      continue;
    }
    touched |= sm.runLazy(cycles);
  }
  oldPinValues = pinValues;
  oldPinDirections = pinDirections;
  auto &gpio = rp2040.gpio;
  for (uint32_t bits = touched & ((1u << gpio.size()) - 1); bits; bits &= bits - 1) {
    gpio[static_cast<uint32_t>(__builtin_ctz(bits))].checkForUpdates();
  }
}

}  // namespace rp2040js
