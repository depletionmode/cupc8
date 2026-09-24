// Port of rp2040js src/rp2040.ts (with the cupc8 dual-core patch).
#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <vector>

#include "clock/clock.h"
#include "clock/simulation-clock.h"
#include "cortex-m0-core.h"
#include "gpio-pin.h"
#include "irq.h"
#include "peripherals/adc.h"
#include "peripherals/dma.h"
#include "peripherals/i2c.h"
#include "peripherals/peripheral.h"
#include "peripherals/pio.h"
#include "peripherals/ppb.h"
#include "peripherals/pwm.h"
#include "peripherals/spi.h"
#include "peripherals/uart.h"
#include "peripherals/usb.h"
#include "sio.h"
#include "utils/logging.h"

namespace rp2040js {

constexpr uint32_t FLASH_START_ADDRESS = 0x10000000;
constexpr uint32_t FLASH_END_ADDRESS = 0x14000000;
constexpr uint32_t RAM_START_ADDRESS = 0x20000000;
constexpr uint32_t APB_START_ADDRESS = 0x40000000;
constexpr uint32_t DPRAM_START_ADDRESS = 0x50100000;
constexpr uint32_t SIO_START_ADDRESS = 0xd0000000;

class RP2040 {
 private:
  /** Owns the default `new SimulationClock()` when no clock is passed in. */
  std::unique_ptr<IClock> ownedClock;

 public:
  /** `constructor(readonly clock: IClock = new SimulationClock())`; must outlive the RP2040 */
  IClock &clock;

  static constexpr uint32_t KB = 1024;
  static constexpr uint32_t MB = 1024 * KB;
  static constexpr uint32_t MHz = 1000000;

  std::vector<uint32_t> bootrom = std::vector<uint32_t>(4 * KB);
  std::vector<uint8_t> sram = std::vector<uint8_t>(264 * KB);
  // sramView / flashView / usbDPRAMView: loadLE32/storeLE32 on these bytes.
  // flash16 (a Uint16Array view nothing in the chip uses) is not ported.
  std::vector<uint8_t> flash = std::vector<uint8_t>(16 * MB);
  std::vector<uint8_t> usbDPRAM = std::vector<uint8_t>(4 * KB);

  /**
   * `public logger: Logger = new ConsoleLogger(LogLevel.Debug, true)`.
   * Declared before the peripherals (TS initialises it after them) so that it
   * exists while they are constructed; TS would crash if one logged there.
   */
  std::shared_ptr<Logger> logger = std::make_shared<ConsoleLogger>(LogLevel::Debug, true);

  CortexM0Core core0{*this};
  CortexM0Core core1{*this};
  std::array<CortexM0Core *, 2> cores = {&core0, &core1};
  /** the core executing the current instruction (0 outside step()) */
  uint32_t coreIndex = 0;
  /** PSM FRCE_OFF holds core 1 off; so does having no bootrom for it to wait in */
  bool core1Held = true;
  CortexM0Core &core() { return *cores[coreIndex]; }

  /* Clocks */
  double clkSys = 125 * MHz;
  double clkPeri = 125 * MHz;

  RPPPB ppb{*this, "PPB"};
  RPSIO sio{*this};

  std::array<RPUART, 2> uart{{
      {*this, "UART0", IRQ::UART0, {DREQ_UART0_RX, DREQ_UART0_TX}},
      {*this, "UART1", IRQ::UART1, {DREQ_UART1_RX, DREQ_UART1_TX}},
  }};
  std::array<RPI2C, 2> i2c{{{*this, "I2C0", IRQ::I2C0}, {*this, "I2C1", IRQ::I2C1}}};
  RPPWM pwm{*this, "PWM_BASE"};
  RPADC adc{*this, "ADC"};

  std::array<GPIOPin, 30> gpio{{
      {*this, 0},
      {*this, 1},
      {*this, 2},
      {*this, 3},
      {*this, 4},
      {*this, 5},
      {*this, 6},
      {*this, 7},
      {*this, 8},
      {*this, 9},
      {*this, 10},
      {*this, 11},
      {*this, 12},
      {*this, 13},
      {*this, 14},
      {*this, 15},
      {*this, 16},
      {*this, 17},
      {*this, 18},
      {*this, 19},
      {*this, 20},
      {*this, 21},
      {*this, 22},
      {*this, 23},
      {*this, 24},
      {*this, 25},
      {*this, 26},
      {*this, 27},
      {*this, 28},
      {*this, 29},
  }};

  std::array<GPIOPin, 6> qspi{{
      {*this, 0, "SCLK"},
      {*this, 1, "SS"},
      {*this, 2, "SD0"},
      {*this, 3, "SD1"},
      {*this, 4, "SD2"},
      {*this, 5, "SD3"},
  }};

  RPDMA dma{*this, "DMA"};
  std::array<RPPIO, 2> pio{{
      {*this, "PIO0", IRQ::PIO0_IRQ0, 0},
      {*this, "PIO1", IRQ::PIO1_IRQ0, 1},
  }};
  RPUSBController usbCtrl{*this, "USB"};
  std::array<RPSPI, 2> spi{{
      {*this, "SPI0", IRQ::SPI0, {DREQ_SPI0_RX, DREQ_SPI0_TX}},
      {*this, "SPI1", IRQ::SPI1, {DREQ_SPI1_RX, DREQ_SPI1_TX}},
  }};

  /**
   * `readonly peripherals: { [index: number]: Peripheral }`, keyed by
   * `(address >>> 14) << 2`. Non-owning; the anonymous ones (SSI, SYSINFO,
   * ..., TBMAN) are owned by `ownedPeripherals`.
   */
  std::map<uint32_t, Peripheral *> peripherals;

  // Debugging
  /** TODO in TS: raise HardFault exception */
  std::function<void(uint32_t code)> onBreak = [](uint32_t) {};

  RP2040();
  explicit RP2040(IClock &clock);
  RP2040(const RP2040 &) = delete;
  RP2040 &operator=(const RP2040 &) = delete;

  void loadBootrom(const std::vector<uint32_t> &bootromData);

  void reset();

  uint32_t readUint32(uint32_t address);
  Peripheral *findPeripheral(uint32_t address) const;
  /** We assume the address is 16-bit aligned */
  uint32_t readUint16(uint32_t address);
  uint32_t readUint8(uint32_t address);
  void writeUint32(uint32_t address, uint32_t value);
  void writeUint8(uint32_t address, uint32_t value);
  void writeUint16(uint32_t address, uint32_t value);

  uint32_t gpioValues() const;
  /** not in TS: bring both PIO blocks' fast path up to date (RPPIO::sync) */
  void syncPIO() {
    pio[0].sync();
    pio[1].sync();
  }

  /** (out of line: test_periph_diff observes it with ld --wrap) */
  void setInterrupt(uint32_t irq, bool value);

  /** Core 1 restarts in the bootrom, where it waits for the FIFO launch sequence. */
  void resetCore1();

  /** SEV: signal an event to both cores. */
  void sendEvent();

  void updateIOInterrupt();

  /** One instruction on the core that is behind; returns the cycles by which the chip's time advanced (may be 0). */
  double step() {
    // running(0) / running(1), read from the fields directly
    const bool run0 = !core0.waiting, run1 = !core1.waiting && !core1Held;
    if (!run0 && !run1) {
      return 0;
    }
    const uint32_t i = run0 && run1 ? (coreTime[0] <= coreTime[1] ? 0 : 1) : run0 ? 0 : 1;
    double ti = coreTime[i];
    if (ti < now) {
      coreTime[i] = ti = now;  // it was asleep: it starts from now
    }
    coreIndex = i;
    sio.selectCore(i);
    CortexM0Core &core = i ? core1 : core0;
    ti += core.executeInstructionOverride ? core.executeInstructionOverride() : core.executeInstruction();
    coreTime[i] = ti;
    coreIndex = 0;
    sio.selectCore(0);
    // the earliest running core's time (the one that ran if none is running now)
    const bool r0 = !core0.waiting, r1 = !core1.waiting && !core1Held;
    double t;
    if (r0 && r1) {
      t = std::min(coreTime[0], coreTime[1]);
    } else if (r0 || r1) {
      t = r0 ? coreTime[0] : coreTime[1];
    } else {
      t = ti;
    }
    const double delta = std::max(0.0, t - now);
    now += delta;
    return delta;
  }

  /** Both cores asleep: the chip's time moves on by `cycles`. */
  void idle(double cycles) { now += cycles; }

  bool waiting() const { return core0.waiting && (core1.waiting || core1Held); }

 private:
  std::vector<std::unique_ptr<Peripheral>> ownedPeripherals;
  /** findPeripheral's lookup: peripheralTable[address >>> 14] (the map, flattened) */
  std::vector<Peripheral *> peripheralTable;

  // Each core keeps its own cycle count; step() runs whichever running core is
  // behind, so both run at full speed whatever their instruction mix, and the
  // chip's time is the earliest running core's.
  std::array<double, 2> coreTime = {0, 0};
  double now = 0;

  bool running(uint32_t i) const { return !cores[i]->waiting && !(i == 1 && core1Held); }

  void init();
};

}  // namespace rp2040js
