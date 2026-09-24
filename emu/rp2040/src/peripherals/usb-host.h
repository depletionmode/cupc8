// Port of rp2040js src/peripherals/usb-host.ts (cupc8 patch: host mode)
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <vector>

#include "../clock/clock.h"

namespace rp2040js {

class RP2040;

/**
 * A USB device plugged into the RP2040's port while it is in host mode.
 * Every call is one transaction to `addr`/`ep`; the model answers with data,
 * or 'nak' / 'stall'.
 */
class USBHostDevice {
 public:
  /** the TS string results 'ack' | 'nak' | 'stall' */
  enum class Handshake { ack, nak, stall };
  /** `Uint8Array | 'nak' | 'stall'`: handshake == ack means "data" */
  struct InResult {
    Handshake handshake;
    std::vector<uint8_t> data;
  };

  virtual ~USBHostDevice() = default;
  /** 1 = low speed, 2 = full speed */
  virtual uint32_t speed() const = 0;
  virtual void busReset() = 0;
  /** 'ack' | 'stall' */
  virtual Handshake setup(uint32_t addr, const std::vector<uint8_t> &packet) = 0;
  virtual InResult in(uint32_t addr, uint32_t ep, uint32_t maxLen) = 0;
  virtual Handshake out(uint32_t addr, uint32_t ep, const std::vector<uint8_t> &data) = 0;
};

// SIE_CTRL
constexpr uint32_t SIE_CTRL_START_TRANS = 1 << 0;
constexpr uint32_t SIE_CTRL_RESET_BUS = 1 << 13;

// SIE_STATUS
constexpr uint32_t SIE_STATUS_SPEED_SHIFT = 8;
constexpr uint32_t SIE_STATUS_SPEED_MASK = 3 << 8;

/**
 * The `regs` object literal RPUSBController passes in (getters/setters over
 * its private fields, plus update()).
 */
class USBHostRegs {
 public:
  virtual ~USBHostRegs() = default;
  virtual uint32_t addrEndp() const = 0;
  virtual uint32_t sieStatus() const = 0;
  virtual void setSieStatus(uint32_t v) = 0;
  virtual uint32_t buffStatus() const = 0;
  virtual void setBuffStatus(uint32_t v) = 0;
  virtual void update() = 0;
};

/** The host side of RPUSBController (MAIN_CTRL.HOST_NDEVICE). */
class USBHostController {
 public:
  /** `USBHostDevice | null`; not owned: the caller keeps the device alive while attached */
  USBHostDevice *device = nullptr;
  bool connChanged = false;
  uint32_t sofNumber = 0;
  uint32_t intEpCtrl = 0;
  std::array<uint32_t, 15> intEpAddr{};  // `new Uint32Array(15)`

  USBHostController(RP2040 &rp2040, USBHostRegs &regs);
  USBHostController(const USBHostController &) = delete;
  USBHostController &operator=(const USBHostController &) = delete;

  void attach(USBHostDevice *device);
  void detach();

  /** host-mode INTR bits */
  uint32_t intRaw() const;

  /** returns the value to store in SIE_CTRL */
  uint32_t sieCtrlWritten(uint32_t value);

  /** a DPRAM word was written */
  void dpramWritten(uint32_t offset);

 private:
  std::array<uint32_t, 15> intEpPollDue{};

  // EPX: the one non-interrupt transfer in flight
  bool epxActive = false;
  bool epxIn = false;
  uint32_t epxBuf = 0;  // which half of a double buffer comes next
  uint32_t epxAddr = 0;
  uint32_t epxEp = 0;
  std::unique_ptr<IAlarm> epxAlarm;
  std::unique_ptr<IAlarm> setupAlarm;
  std::function<void()> setupDone;  // `(() => void) | null`
  std::unique_ptr<IAlarm> frameAlarm;

  RP2040 &rp2040;
  USBHostRegs &regs;

  /** `this.rp2040.usbDPRAMView`: the DPRAM bytes (use loadLE32/storeLE32) */
  uint8_t *dpram();

  void setSpeed(uint32_t speed);
  void later(std::function<void()> fn);
  void status(uint32_t bits);
  void bufferDone(uint32_t bit);
  // One packet on EPX, into or out of the buffer half that is available.
  void epxService();
  void frame();
};

}  // namespace rp2040js
