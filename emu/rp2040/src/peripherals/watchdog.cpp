// Port of rp2040js src/peripherals/watchdog.ts
#include "watchdog.h"

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t CTRL = 0x00;      // Control register
static constexpr uint32_t LOAD = 0x04;      // Load the watchdog timer.
static constexpr uint32_t REASON = 0x08;    // Logs the reason for the last reset.
static constexpr uint32_t SCRATCH0 = 0x0c;  // Scratch register
static constexpr uint32_t SCRATCH1 = 0x10;  // Scratch register
static constexpr uint32_t SCRATCH2 = 0x14;  // Scratch register
static constexpr uint32_t SCRATCH3 = 0x18;  // Scratch register
static constexpr uint32_t SCRATCH4 = 0x1c;  // Scratch register
static constexpr uint32_t SCRATCH5 = 0x20;  // Scratch register
static constexpr uint32_t SCRATCH6 = 0x24;  // Scratch register
static constexpr uint32_t SCRATCH7 = 0x28;  // Scratch register
static constexpr uint32_t TICK = 0x2c;      // Controls the tick generator

// CTRL bits:
static constexpr uint32_t TRIGGER = 1u << 31;
static constexpr uint32_t ENABLE = 1 << 30;
static constexpr uint32_t PAUSE_DBG1 = 1 << 26;
static constexpr uint32_t PAUSE_DBG0 = 1 << 25;
static constexpr uint32_t PAUSE_JTAG = 1 << 24;
static constexpr uint32_t TIME_MASK = 0xffffff;
static constexpr uint32_t TIME_SHIFT = 0;

// LOAD bits
static constexpr uint32_t LOAD_MASK = 0xffffff;
static constexpr uint32_t LOAD_SHIFT = 0;

// REASON bits:
static constexpr uint32_t FORCE = 1 << 1;
static constexpr uint32_t TIMER = 1 << 0;

// TICK bits:
static constexpr uint32_t COUNT_MASK = 0x1ff;
static constexpr uint32_t COUNT_SHIFT = 11;
static constexpr uint32_t RUNNING = 1 << 10;
static constexpr uint32_t TICK_ENABLE = 1 << 9;
static constexpr uint32_t CYCLES_MASK = 0x1ff;
static constexpr uint32_t CYCLES_SHIFT = 0;

// Unused in the TS too; referenced so -Wunused stays quiet.
[[maybe_unused]] static constexpr uint32_t UNUSED_WATCHDOG_CONSTS[] = {COUNT_MASK, COUNT_SHIFT,
                                                                      CYCLES_MASK, CYCLES_SHIFT};

static constexpr double TICK_FREQUENCY =
    2000000;  // Actually 1 MHz, but due to errata RP2040-E1, the timer is decremented twice per tick

RPWatchdog::RPWatchdog(RP2040 &rp2040, const std::string &name)
    : BasePeripheral(rp2040, name),
      /** Called when the watchdog triggers - override with your own soft reset implementation */
      onWatchdogTrigger([this] {
        this->rp2040.logger->warn(this->name, "Watchdog triggered, but no reset handler provided");
      }) {
  timer = std::make_unique<Timer32>(rp2040.clock, TICK_FREQUENCY);
  timer->setMode(TimerMode::Decrement);
  timer->setEnable(false);
  alarm = std::make_unique<Timer32PeriodicAlarm>(*timer, [this] {
    reason = TIMER;
    if (onWatchdogTrigger) {
      onWatchdogTrigger();
    }
  });
  alarm->setTarget(0);
  alarm->setEnable(false);
}

uint32_t RPWatchdog::readUint32(uint32_t offset) {
  switch (offset) {
    case CTRL:
      return (timer->enable() ? ENABLE : 0) | (pauseDbg0 ? PAUSE_DBG0 : 0) |
             (pauseDbg1 ? PAUSE_DBG1 : 0) | (pauseJtag ? PAUSE_JTAG : 0) |
             ((timer->counter() & TIME_MASK) << TIME_SHIFT);

    case REASON:
      return reason;

    case SCRATCH0:
    case SCRATCH1:
    case SCRATCH2:
    case SCRATCH3:
    case SCRATCH4:
    case SCRATCH5:
    case SCRATCH6:
    case SCRATCH7:
      return scratchData[(offset - SCRATCH0) >> 2];

    case TICK:
      // TODO COUNT bits
      return tickEnable ? RUNNING | TICK_ENABLE : 0;
  }
  return BasePeripheral::readUint32(offset);
}

void RPWatchdog::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case CTRL:
      if (value & TRIGGER) {
        reason = FORCE;
        if (onWatchdogTrigger) {
          onWatchdogTrigger();
        }
      }
      enable = !!(value & ENABLE);
      timer->setEnable(enable && tickEnable);
      alarm->setEnable(enable && tickEnable);
      pauseDbg0 = !!(value & PAUSE_DBG0);
      pauseDbg1 = !!(value & PAUSE_DBG1);
      pauseJtag = !!(value & PAUSE_JTAG);
      break;

    case LOAD:
      timer->set((value >> LOAD_SHIFT) & LOAD_MASK);
      break;

    case SCRATCH0:
    case SCRATCH1:
    case SCRATCH2:
    case SCRATCH3:
    case SCRATCH4:
    case SCRATCH5:
    case SCRATCH6:
    case SCRATCH7:
      scratchData[(offset - SCRATCH0) >> 2] = value;
      break;

    case TICK:
      tickEnable = !!(value & TICK_ENABLE);
      timer->setEnable(enable && tickEnable);
      alarm->setEnable(enable && tickEnable);
      // TODO - handle CYCLES (tick also affectes timer)
      break;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
