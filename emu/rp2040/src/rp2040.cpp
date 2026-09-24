// Port of rp2040js src/rp2040.ts (with the cupc8 dual-core patch).
#include "rp2040.h"

#include <algorithm>
#include <limits>
#include <stdexcept>

#include "peripherals/busctrl.h"
#include "peripherals/clocks.h"
#include "peripherals/io.h"
#include "peripherals/pads.h"
#include "peripherals/psm.h"
#include "peripherals/reset.h"
#include "peripherals/rtc.h"
#include "peripherals/ssi.h"
#include "peripherals/syscfg.h"
#include "peripherals/sysinfo.h"
#include "peripherals/tbman.h"
#include "peripherals/timer.h"
#include "peripherals/watchdog.h"
#include "utils/js.h"

namespace rp2040js {

static const char *const LOG_NAME = "RP2040";

// The largest `address >>> 14` that has a peripheral (0x50300 >> 2), plus one.
static constexpr uint32_t PERIPHERAL_TABLE_SIZE = (0x50300 >> 2) + 1;

RP2040::RP2040() : ownedClock(std::make_unique<SimulationClock>()), clock(*ownedClock) { init(); }

RP2040::RP2040(IClock &clock) : clock(clock) { init(); }

void RP2040::init() {
  // The rest of the `peripherals` initialiser: the peripherals created in it.
  auto own = [this](std::unique_ptr<Peripheral> p) {
    Peripheral *raw = p.get();
    ownedPeripherals.push_back(std::move(p));
    return raw;
  };
  peripherals[0x18000] = own(std::make_unique<RPSSI>(*this, "SSI"));
  peripherals[0x40000] = own(std::make_unique<RP2040SysInfo>(*this, "SYSINFO_BASE"));
  peripherals[0x40004] = own(std::make_unique<RP2040SysCfg>(*this, "SYSCFG"));
  peripherals[0x40008] = own(std::make_unique<RPClocks>(*this, "CLOCKS_BASE"));
  peripherals[0x4000c] = own(std::make_unique<RPReset>(*this, "RESETS_BASE"));
  peripherals[0x40010] = own(std::make_unique<RPPSM>(*this, "PSM_BASE"));
  peripherals[0x40014] = own(std::make_unique<RPIO>(*this, "IO_BANK0_BASE"));
  peripherals[0x40018] = own(std::make_unique<UnimplementedPeripheral>(*this, "IO_QSPI_BASE"));
  peripherals[0x4001c] = own(std::make_unique<RPPADS>(*this, "PADS_BANK0_BASE", IIOBank::bank0));
  peripherals[0x40020] = own(std::make_unique<RPPADS>(*this, "PADS_QSPI_BASE", IIOBank::qspi));
  peripherals[0x40024] = own(std::make_unique<UnimplementedPeripheral>(*this, "XOSC_BASE"));
  peripherals[0x40028] = own(std::make_unique<UnimplementedPeripheral>(*this, "PLL_SYS_BASE"));
  peripherals[0x4002c] = own(std::make_unique<UnimplementedPeripheral>(*this, "PLL_USB_BASE"));
  peripherals[0x40030] = own(std::make_unique<RPBUSCTRL>(*this, "BUSCTRL_BASE"));
  peripherals[0x40034] = &uart[0];
  peripherals[0x40038] = &uart[1];
  peripherals[0x4003c] = &spi[0];
  peripherals[0x40040] = &spi[1];
  peripherals[0x40044] = &i2c[0];
  peripherals[0x40048] = &i2c[1];
  peripherals[0x4004c] = &adc;
  peripherals[0x40050] = &pwm;
  peripherals[0x40054] = own(std::make_unique<RPTimer>(*this, "TIMER_BASE"));
  peripherals[0x40058] = own(std::make_unique<RPWatchdog>(*this, "WATCHDOG_BASE"));
  peripherals[0x4005c] = own(std::make_unique<RP2040RTC>(*this, "RTC_BASE"));
  peripherals[0x40060] = own(std::make_unique<UnimplementedPeripheral>(*this, "ROSC_BASE"));
  peripherals[0x40064] =
      own(std::make_unique<UnimplementedPeripheral>(*this, "VREG_AND_CHIP_RESET_BASE"));
  peripherals[0x4006c] = own(std::make_unique<RPTBMAN>(*this, "TBMAN_BASE"));
  peripherals[0x50000] = &dma;
  peripherals[0x50110] = &usbCtrl;
  peripherals[0x50200] = &pio[0];
  peripherals[0x50300] = &pio[1];

  peripheralTable.assign(PERIPHERAL_TABLE_SIZE, nullptr);
  for (const auto &entry : peripherals) {
    peripheralTable[entry.first >> 2] = entry.second;
  }

  // constructor body
  reset();
}

void RP2040::loadBootrom(const std::vector<uint32_t> &bootromData) {
  if (bootromData.size() > bootrom.size()) {
    throw std::range_error("RangeError: offset is out of bounds");  // TypedArray.set
  }
  std::copy(bootromData.begin(), bootromData.end(), bootrom.begin());
  core1Held = false;
  reset();
}

void RP2040::reset() {
  core0.reset();
  resetCore1();
  pwm.reset();
  std::fill(flash.begin(), flash.end(), 0xff);
}

// DataView accessors throw RangeError past the end of the buffer.
static void checkView(size_t offset, size_t size, size_t length) {
  if (offset + size > length) {
    throw std::range_error("RangeError: Offset is outside the bounds of the DataView");
  }
}

uint32_t RP2040::readUint32(uint32_t address) {
  address = address >> 0;  // round to 32-bits, unsigned
  if (address & 0x3) {
    logger->error(LOG_NAME,
                  "read from address " + toHex(address) + ", which is not 32 bit aligned");
  }

  if (address < bootrom.size() * 4) {
    // `bootrom[address / 4]`: a fractional index reads undefined (-> 0)
    return address & 0x3 ? 0 : bootrom[address / 4];
  } else if (address >= FLASH_START_ADDRESS && address < FLASH_END_ADDRESS) {
    // Flash is mirrored four times:
    // - 0x10000000 XIP
    // - 0x11000000 XIP_NOALLOC
    // - 0x12000000 XIP_NOCACHE
    // - 0x13000000 XIP_NOCACHE_NOALLOC
    const uint32_t offset = address & 0x00ffffff;
    checkView(offset, 4, flash.size());
    return loadLE32(&flash[offset]);
  } else if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    checkView(address - RAM_START_ADDRESS, 4, sram.size());
    return loadLE32(&sram[address - RAM_START_ADDRESS]);
  } else if (address >= DPRAM_START_ADDRESS && address < DPRAM_START_ADDRESS + usbDPRAM.size()) {
    checkView(address - DPRAM_START_ADDRESS, 4, usbDPRAM.size());
    return loadLE32(&usbDPRAM[address - DPRAM_START_ADDRESS]);
  } else if (address >> 12 == 0xe000e) {
    return ppb.readUint32(address & 0xfff);
  } else if (address >= SIO_START_ADDRESS && address - SIO_START_ADDRESS < 0x10000000) {
    return sio.readUint32(address - SIO_START_ADDRESS);
  }

  Peripheral *peripheral = findPeripheral(address);
  if (peripheral) {
    return peripheral->readUint32(address & 0x3fff);
  }

  logger->warn(LOG_NAME, "Read from invalid memory address: " + toHex(address));
  return 0xffffffff;
}

Peripheral *RP2040::findPeripheral(uint32_t address) const {
  // `this.peripherals[(address >>> 14) << 2]`
  const uint32_t index = address >> 14;
  return index < peripheralTable.size() ? peripheralTable[index] : nullptr;
}

uint32_t RP2040::readUint16(uint32_t address) {
  if (address >= FLASH_START_ADDRESS && address < FLASH_START_ADDRESS + flash.size()) {
    checkView(address - FLASH_START_ADDRESS, 2, flash.size());
    return loadLE16(&flash[address - FLASH_START_ADDRESS]);
  } else if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    checkView(address - RAM_START_ADDRESS, 2, sram.size());
    return loadLE16(&sram[address - RAM_START_ADDRESS]);
  }

  const uint32_t value = readUint32(address & 0xfffffffc);
  return address & 0x2 ? (value & 0xffff0000) >> 16 : value & 0xffff;
}

uint32_t RP2040::readUint8(uint32_t address) {
  if (address >= FLASH_START_ADDRESS && address < FLASH_START_ADDRESS + flash.size()) {
    return flash[address - FLASH_START_ADDRESS];
  } else if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    return sram[address - RAM_START_ADDRESS];
  }

  const uint32_t value = readUint16(address & 0xfffffffe);
  return (address & 0x1 ? (value & 0xff00) >> 8 : value & 0xff) >> 0;
}

void RP2040::writeUint32(uint32_t address, uint32_t value) {
  address = address >> 0;
  Peripheral *peripheral = findPeripheral(address);
  if (peripheral) {
    const uint32_t atomicType = (address & 0x3000) >> 12;
    const uint32_t offset = address & 0xfff;
    peripheral->writeUint32Atomic(offset, value, atomicType);
  } else if (address < bootrom.size() * 4) {
    // `bootrom[address / 4] = value`: a fractional index is a no-op
    if (!(address & 0x3)) {
      bootrom[address / 4] = value;
    }
  } else if (address >= FLASH_START_ADDRESS && address < FLASH_START_ADDRESS + flash.size()) {
    checkView(address - FLASH_START_ADDRESS, 4, flash.size());
    storeLE32(&flash[address - FLASH_START_ADDRESS], value);
  } else if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    checkView(address - RAM_START_ADDRESS, 4, sram.size());
    storeLE32(&sram[address - RAM_START_ADDRESS], value);
  } else if (address >= DPRAM_START_ADDRESS && address < DPRAM_START_ADDRESS + usbDPRAM.size()) {
    const uint32_t offset = address - DPRAM_START_ADDRESS;
    checkView(offset, 4, usbDPRAM.size());
    storeLE32(&usbDPRAM[offset], value);
    usbCtrl.DPRAMUpdated(offset, value);
  } else if (address >= SIO_START_ADDRESS && address - SIO_START_ADDRESS < 0x10000000) {
    sio.writeUint32(address - SIO_START_ADDRESS, value);
  } else if (address >> 12 == 0xe000e) {
    ppb.writeUint32(address & 0xfff, value);
  } else {
    logger->warn(LOG_NAME, "Write to undefined address: " + toHex(address));
  }
}

void RP2040::writeUint8(uint32_t address, uint32_t value) {
  if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    sram[address - RAM_START_ADDRESS] = static_cast<uint8_t>(value);
    return;
  }

  const uint32_t alignedAddress = (address & 0xfffffffc) >> 0;
  const uint32_t offset = address & 0x3;
  Peripheral *peripheral = findPeripheral(address);
  if (peripheral) {
    const uint32_t atomicType = (alignedAddress & 0x3000) >> 12;
    const uint32_t offset = alignedAddress & 0xfff;
    peripheral->writeUint32Atomic(
        offset,
        (value & 0xff) | ((value & 0xff) << 8) | ((value & 0xff) << 16) | ((value & 0xff) << 24),
        atomicType);
    return;
  }
  const uint32_t originalValue = readUint32(alignedAddress);
  uint8_t newValue[4];
  storeLE32(newValue, originalValue);
  newValue[offset] = static_cast<uint8_t>(value);  // DataView.setUint8
  writeUint32(alignedAddress, loadLE32(newValue));
}

void RP2040::writeUint16(uint32_t address, uint32_t value) {
  // we assume that addess is 16-bit aligned.
  // Ideally we should generate a fault if not!

  if (address >= RAM_START_ADDRESS && address < RAM_START_ADDRESS + sram.size()) {
    checkView(address - RAM_START_ADDRESS, 2, sram.size());
    storeLE16(&sram[address - RAM_START_ADDRESS], static_cast<uint16_t>(value));
    return;
  }

  const uint32_t alignedAddress = (address & 0xfffffffc) >> 0;
  const uint32_t offset = address & 0x3;
  Peripheral *peripheral = findPeripheral(address);
  if (peripheral) {
    const uint32_t atomicType = (alignedAddress & 0x3000) >> 12;
    const uint32_t offset = alignedAddress & 0xfff;
    peripheral->writeUint32Atomic(offset, (value & 0xffff) | ((value & 0xffff) << 16), atomicType);
    return;
  }
  const uint32_t originalValue = readUint32(alignedAddress);
  uint8_t newValue[4];
  storeLE32(newValue, originalValue);
  checkView(offset, 2, 4);  // DataView.setUint16(3, ...) throws
  storeLE16(&newValue[offset], static_cast<uint16_t>(value));
  writeUint32(alignedAddress, loadLE32(newValue));
}

uint32_t RP2040::gpioValues() const {
  uint32_t result = 0;
  for (uint32_t gpioIndex = 0; gpioIndex < gpio.size(); gpioIndex++) {
    if (gpio[gpioIndex].inputValue()) {
      result |= 1u << gpioIndex;
    }
  }
  return result;
}


void RP2040::resetCore1() {
  CortexM0Core &core1 = this->core1;
  core1.registers.fill(0);
  core1.VTOR = 0;
  core1.PM = false;
  core1.IPSR = 0;
  core1.pendingInterrupts = 0;
  core1.enabledInterrupts = 0;
  core1.waiting = false;
  core1.eventRegistered = false;
  const uint32_t saved = coreIndex;
  coreIndex = 1;
  core1.reset();
  coreIndex = saved;
}

void RP2040::setInterrupt(uint32_t irq, bool value) {
  core0.setInterrupt(irq, value);
  core1.setInterrupt(irq, value);
}

void RP2040::sendEvent() {
  for (CortexM0Core *core : cores) {
    core->eventRegistered = true;
    if (core->waitingForEvent) {
      core->waiting = false;
      core->waitingForEvent = false;
      core->eventRegistered = false;
    }
  }
}

void RP2040::updateIOInterrupt() {
  bool interruptValue = false;
  for (const GPIOPin &pin : gpio) {
    if (pin.irqValue()) {
      interruptValue = true;
    }
  }
  setInterrupt(IRQ::IO_BANK0, interruptValue);
}

bool RP2040::running(uint32_t i) const { return !cores[i]->waiting && !(i == 1 && core1Held); }

double RP2040::step() {
  const bool run0 = running(0), run1 = running(1);
  if (!run0 && !run1) {
    return 0;
  }
  const uint32_t i = run0 && run1 ? (coreTime[0] <= coreTime[1] ? 0 : 1) : run0 ? 0 : 1;
  if (coreTime[i] < now) {
    coreTime[i] = now;  // it was asleep: it starts from now
  }
  coreIndex = i;
  sio.selectCore(i);
  CortexM0Core &core = *cores[i];
  coreTime[i] +=
      core.executeInstructionOverride ? core.executeInstructionOverride() : core.executeInstruction();
  coreIndex = 0;
  sio.selectCore(0);
  double t = std::numeric_limits<double>::infinity();
  for (uint32_t c = 0; c < 2; c++) {
    if (running(c)) {
      t = std::min(t, coreTime[c]);
    }
  }
  if (t == std::numeric_limits<double>::infinity()) {
    t = coreTime[i];
  }
  const double delta = std::max(0.0, t - now);
  now += delta;
  return delta;
}

void RP2040::idle(double cycles) { now += cycles; }

bool RP2040::waiting() const { return core0.waiting && (core1.waiting || core1Held); }

}  // namespace rp2040js
