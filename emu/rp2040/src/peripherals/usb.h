// Port of rp2040js src/peripherals/usb.ts (with the cupc8 patch: host mode)
#pragma once

#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "../clock/clock.h"
#include "peripheral.h"
#include "usb-host.h"

namespace rp2040js {

class USBEndpointAlarm {
 public:
  /** `Uint8Array[]`; the read alarm shift()s from the front */
  std::deque<std::vector<uint8_t>> buffers;

  const std::unique_ptr<IAlarm> alarm;

  explicit USBEndpointAlarm(std::unique_ptr<IAlarm> alarm);

  void schedule(std::vector<uint8_t> buffer, double delayNanos);
};

class RPUSBController : public BasePeripheral {
 public:
  /** host mode (MAIN_CTRL.HOST_NDEVICE): a device model on the port */
  std::unique_ptr<USBHostController> host;

  std::function<void()> onUSBEnabled;
  std::function<void()> onResetReceived;
  std::function<void(uint32_t endpoint, const std::vector<uint8_t> &buffer)> onEndpointWrite;
  std::function<void(uint32_t endpoint, uint32_t byteCount)> onEndpointRead;

  double readDelayMicroseconds = 10;
  double writeDelayMicroseconds = 10;  // Determined empirically

  RPUSBController(RP2040 &rp2040, const std::string &name);

  bool isHost() const;
  uint32_t intStatus() const;

  /** Plug a device into the port (host mode) */
  void attachDevice(USBHostDevice *device);
  void detachDevice();

  uint32_t readUint32(uint32_t offset) override;
  void writeUint32(uint32_t offset, uint32_t value) override;

  void DPRAMUpdated(uint32_t offset, uint32_t value);

  /** `delay = this.readDelayMicroseconds` */
  void endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer);
  void endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer, double delay);

  void checkInterrupts();
  void resetDevice();
  void sendSetupPacket(const std::vector<uint8_t> &setupPacket);

 private:
  uint32_t addrEndp = 0;
  uint32_t mainCtrl = 0;
  uint32_t intRaw = 0;
  uint32_t intEnable = 0;
  uint32_t intForce = 0;
  uint32_t sieStatus = 0;
  uint32_t buffStatus = 0;
  uint32_t sieCtrl = 0;
  uint32_t usbPwr = 0;

  std::vector<std::unique_ptr<USBEndpointAlarm>> endpointReadAlarms;
  std::vector<std::unique_ptr<USBEndpointAlarm>> endpointWriteAlarms;
  std::unique_ptr<IAlarm> resetAlarm;

  /** The `regs` object literal handed to USBHostController (a nested class sees the private fields). */
  class HostRegs : public USBHostRegs {
   public:
    explicit HostRegs(RPUSBController &ctl) : ctl(ctl) {}
    uint32_t addrEndp() const override { return ctl.addrEndp; }
    uint32_t sieStatus() const override { return ctl.sieStatus; }
    void setSieStatus(uint32_t v) override { ctl.sieStatus = v; }
    uint32_t buffStatus() const override { return ctl.buffStatus; }
    void setBuffStatus(uint32_t v) override { ctl.buffStatus = v; }
    void update() override { ctl.checkInterrupts(); }

   private:
    RPUSBController &ctl;
  };
  HostRegs hostRegs{*this};

  uint32_t readEndpointControlReg(uint32_t endpoint, bool out);
  uint32_t getEndpointBufferOffset(uint32_t endpoint, bool out);
  void finishRead(uint32_t endpoint, const std::vector<uint8_t> &buffer);
  void indicateBufferReady(uint32_t endpoint, bool out);
  void buffStatusUpdated();
  void sieStatusUpdated();
};

}  // namespace rp2040js
