// Port of rp2040js src/gpio-pin.ts
#include "gpio-pin.h"

#include <utility>

#include "rp2040.h"
#include "utils/js.h"

namespace rp2040js {

static bool applyOverride(bool value, uint32_t overrideType) {
  switch (overrideType) {
    case 0:
      return value;
    case 1:
      return !value;
    case 2:
      return false;
    case 3:
      return true;
  }
  consoleError("applyOverride received invalid override type " + std::to_string(overrideType));
  return value;
}

static constexpr uint32_t IRQ_EDGE_HIGH = 1 << 3;
static constexpr uint32_t IRQ_EDGE_LOW = 1 << 2;
static constexpr uint32_t IRQ_LEVEL_HIGH = 1 << 1;
static constexpr uint32_t IRQ_LEVEL_LOW = 1 << 0;

GPIOPin::GPIOPin(RP2040 &rp2040, uint32_t index)
    : GPIOPin(rp2040, index, std::to_string(index)) {}

GPIOPin::GPIOPin(RP2040 &rp2040, uint32_t index, std::string name)
    : rp2040(rp2040), index(index), name(std::move(name)) {}

bool GPIOPin::rawInterrupt() const { return !!((irqStatus & irqEnableMask) | irqForceMask); }

bool GPIOPin::isSlewFast() const { return !!(padValue & 1); }

bool GPIOPin::schmittEnabled() const { return !!(padValue & 2); }

bool GPIOPin::pulldownEnabled() const { return !!(padValue & 4); }

bool GPIOPin::pullupEnabled() const { return !!(padValue & 8); }

uint32_t GPIOPin::driveStrength() const { return (padValue >> 4) & 0x3; }

bool GPIOPin::inputEnable() const { return !!(padValue & 0x40); }

bool GPIOPin::outputDisable() const { return !!(padValue & 0x80); }

uint32_t GPIOPin::functionSelect() const { return ctrl & 0x1f; }

uint32_t GPIOPin::outputOverride() const { return (ctrl >> 8) & 0x3; }

uint32_t GPIOPin::outputEnableOverride() const { return (ctrl >> 12) & 0x3; }

uint32_t GPIOPin::inputOverride() const { return (ctrl >> 16) & 0x3; }

uint32_t GPIOPin::irqOverride() const { return (ctrl >> 28) & 0x3; }

bool GPIOPin::rawOutputEnable() const {
  const uint32_t bitmask = 1u << index;
  switch (functionSelect()) {
    case FUNCTION_PWM:
      return !!(rp2040.pwm.gpioDirection & bitmask);

    case FUNCTION_SIO:
      return !!(rp2040.sio.gpioOutputEnable & bitmask);

    case FUNCTION_PIO0:
      rp2040.pio[0].sync();  // PIO fast path: see its exact output
      return !!(rp2040.pio[0].pinDirections & bitmask);

    case FUNCTION_PIO1:
      rp2040.pio[1].sync();  // PIO fast path: see its exact output
      return !!(rp2040.pio[1].pinDirections & bitmask);

    default:
      return false;
  }
}

bool GPIOPin::rawOutputValue() const {
  const uint32_t bitmask = 1u << index;
  switch (functionSelect()) {
    case FUNCTION_PWM:
      return !!(rp2040.pwm.gpioValue & bitmask);

    case FUNCTION_SIO:
      return !!(rp2040.sio.gpioValue & bitmask);

    case FUNCTION_PIO0:
      rp2040.pio[0].sync();  // PIO fast path: see its exact output
      return !!(rp2040.pio[0].pinValues & bitmask);

    case FUNCTION_PIO1:
      rp2040.pio[1].sync();  // PIO fast path: see its exact output
      return !!(rp2040.pio[1].pinValues & bitmask);

    default:
      return false;
  }
}

bool GPIOPin::inputValue() const {
  return applyOverride(rawInputValue && inputEnable(), inputOverride());
}

bool GPIOPin::irqValue() const { return applyOverride(rawInterrupt(), irqOverride()); }

bool GPIOPin::outputEnable() const { return applyOverride(rawOutputEnable(), outputEnableOverride()); }

bool GPIOPin::outputValue() const { return applyOverride(rawOutputValue(), outputOverride()); }

uint32_t GPIOPin::status() const {
  const uint32_t irqToProc = irqValue() ? 1 << 26 : 0;
  const uint32_t irqFromPad = rawInterrupt() ? 1 << 24 : 0;
  const uint32_t inToPeri = inputValue() ? 1 << 19 : 0;
  const uint32_t inFromPad = rawInputValue ? 1 << 17 : 0;
  const uint32_t oeToPad = outputEnable() ? 1 << 13 : 0;
  const uint32_t oeFromPeri = rawOutputEnable() ? 1 << 12 : 0;
  const uint32_t outToPad = outputValue() ? 1 << 9 : 0;
  const uint32_t outFromPeri = rawOutputValue() ? 1 << 8 : 0;
  return irqToProc | irqFromPad | inToPeri | inFromPad | oeToPad | oeFromPeri | outToPad |
         outFromPeri;
}

GPIOPinState GPIOPin::value() const {
  if (outputEnable()) {
    return outputValue() ? GPIOPinState::High : GPIOPinState::Low;
  } else {
    // TODO: check what happens when we enable both pullup/pulldown
    // ANSWER: It is valid, see: 2.19.4.1. Bus Keeper Mode, datasheet p240
    if (pulldownEnabled() && pullupEnabled()) {
      // Pull high when high, pull low when low:
      return GPIOPinState::InputBusKeeper;
    } else if (pulldownEnabled()) {
      return GPIOPinState::InputPullDown;
    } else if (pullupEnabled()) {
      return GPIOPinState::InputPullUp;
    }
    return GPIOPinState::Input;
  }
}

void GPIOPin::setInputValue(bool value) {
  rp2040.syncPIO();  // PIO fast path: an input may wake a stalled machine
  rawInputValue = value;
  const bool prevIrqValue = irqValue();
  if (value && inputEnable()) {
    irqStatus |= IRQ_EDGE_HIGH | IRQ_LEVEL_HIGH;
    irqStatus &= ~IRQ_LEVEL_LOW;
  } else {
    irqStatus |= IRQ_EDGE_LOW | IRQ_LEVEL_LOW;
    irqStatus &= ~IRQ_LEVEL_HIGH;
  }
  if (irqValue() != prevIrqValue) {
    rp2040.updateIOInterrupt();
  }
  if (functionSelect() == FUNCTION_PWM) {
    rp2040.pwm.gpioOnInput(index);
  }
  for (RPPIO &pio : rp2040.pio) {
    for (StateMachine &machine : pio.machines) {
      if (machine.enabled && machine.waiting && machine.waitType == WaitType::Pin &&
          machine.waitIndex == index) {
        machine.checkWait();
      }
    }
  }
}

void GPIOPin::checkForUpdates() {
  const GPIOPinState lastValue = this->lastValue;
  const GPIOPinState value = this->value();
  if (value != lastValue) {
    this->lastValue = value;
    // `for (const listener of this.listeners)`: Set iteration semantics
    uint64_t lastId = 0;
    bool first = true;
    for (;;) {
      auto it = first ? listeners.begin() : listeners.upper_bound(lastId);
      if (it == listeners.end()) {
        break;
      }
      first = false;
      lastId = it->first;
      GPIOPinListener listener = it->second;  // a copy: the listener may remove itself
      listener(value, lastValue);
    }
  }
}

void GPIOPin::refreshInput() { setInputValue(rawInputValue); }

void GPIOPin::updateIRQValue(uint32_t value) {
  if (value & IRQ_EDGE_LOW && irqStatus & IRQ_EDGE_LOW) {
    irqStatus &= ~IRQ_EDGE_LOW;
    rp2040.updateIOInterrupt();
  }
  if (value & IRQ_EDGE_HIGH && irqStatus & IRQ_EDGE_HIGH) {
    irqStatus &= ~IRQ_EDGE_HIGH;
    rp2040.updateIOInterrupt();
  }
}

std::function<void()> GPIOPin::addListener(GPIOPinListener callback) {
  rp2040.syncPIO();  // PIO fast path: the listener sees every change from now on
  const uint64_t id = nextListenerId++;
  listeners.emplace(id, std::move(callback));
  return [this, id]() { listeners.erase(id); };
}

}  // namespace rp2040js
