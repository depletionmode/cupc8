// Port of rp2040js src/gpio-pin.ts
#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <string>

namespace rp2040js {

class RP2040;

enum class GPIOPinState {
  Low,
  High,
  Input,
  InputPullUp,
  InputPullDown,
  InputBusKeeper,
};

constexpr uint32_t FUNCTION_PWM = 4;
constexpr uint32_t FUNCTION_SIO = 5;
constexpr uint32_t FUNCTION_PIO0 = 6;
constexpr uint32_t FUNCTION_PIO1 = 7;

using GPIOPinListener = std::function<void(GPIOPinState state, GPIOPinState oldState)>;

class GPIOPin {
 public:
  uint32_t ctrl = 0x1f;
  uint32_t padValue = 0b0110110;
  uint32_t irqEnableMask = 0;
  uint32_t irqForceMask = 0;
  uint32_t irqStatus = 0;

  RP2040 &rp2040;
  const uint32_t index;
  const std::string name;

  GPIOPin(RP2040 &rp2040, uint32_t index);
  GPIOPin(RP2040 &rp2040, uint32_t index, std::string name);
  GPIOPin(const GPIOPin &) = delete;
  GPIOPin &operator=(const GPIOPin &) = delete;

  bool rawInterrupt() const;
  bool isSlewFast() const;
  bool schmittEnabled() const;
  bool pulldownEnabled() const;
  bool pullupEnabled() const;
  uint32_t driveStrength() const;
  bool inputEnable() const;
  bool outputDisable() const;
  uint32_t functionSelect() const;
  uint32_t outputOverride() const;
  uint32_t outputEnableOverride() const;
  uint32_t inputOverride() const;
  uint32_t irqOverride() const;
  bool rawOutputEnable() const;
  bool rawOutputValue() const;
  bool inputValue() const;
  bool irqValue() const;
  bool outputEnable() const;
  bool outputValue() const;

  /**
   * Returns the STATUS register value for the pin, as outlined in section 2.19.6 of the datasheet
   */
  uint32_t status() const;

  GPIOPinState value() const;

  void setInputValue(bool value);
  void checkForUpdates();
  void refreshInput();
  void updateIRQValue(uint32_t value);

  /** Returns the function that removes the listener (as the TS does). */
  std::function<void()> addListener(GPIOPinListener callback);

 private:
  bool rawInputValue = false;
  /**
   * `private lastValue = this.value;` runs before `ctrl` and `padValue` are
   * initialised (both undefined, so no function, no override, no pulls):
   * the value getter then yields GPIOPinState.Input.
   */
  GPIOPinState lastValue = GPIOPinState::Input;

  /**
   * `new Set<GPIOPinListener>()`: keyed by insertion order, so iteration
   * visits listeners in insertion order, skips ones deleted during the
   * iteration and visits ones added during it, as a JS Set does.
   */
  std::map<uint64_t, GPIOPinListener> listeners;
  uint64_t nextListenerId = 0;
};

}  // namespace rp2040js
