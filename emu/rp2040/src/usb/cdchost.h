// Port of test/emu/cdchost.mjs (cupc8's, not an rp2040js module): the PC's
// side of a composite USB device with CDC serial ports. rp2040js's USBCDC
// (cdc.h), which knows one port, grown to every CDC function in the
// configuration descriptor; the system card has two (the sysctl protocol and
// the console, doc/proposals/usb-console.md).
//
// Enumeration is USBCDC's, step for step; then DTR|RTS on port 0 and
// onDeviceConnected. Later control requests (setLines) each wait for the
// previous one's status stage.
#pragma once

#include <cstdint>
#include <deque>
#include <functional>
#include <optional>
#include <utility>
#include <vector>

#include "../utils/fifo.h"

namespace rp2040js {

class RPUSBController;

class CdcHost {
 public:
  struct Port {
    FIFO txFIFO{512};
    std::function<void(const std::vector<uint8_t> &buffer)> onSerialData;
    int32_t comm = -1, in = -1, out = -1;  // interface, endpoints
  };
  struct Function {
    int32_t comm, in, out;
  };

  std::vector<Port> ports;
  std::function<void()> onDeviceConnected;
  RPUSBController &usb;

  CdcHost(RPUSBController &usb, size_t nports = 2);
  CdcHost(const CdcHost &) = delete;
  CdcHost &operator=(const CdcHost &) = delete;

  // the CDC functions the device has (known once configured)
  size_t portCount() const;
  // SET_CONTROL_LINE_STATE on port p's communication interface
  void setLines(size_t p, uint32_t value);
  // DTR|RTS (a terminal has it open) or nothing
  void open(size_t p, bool on) { setLines(p, on ? 3 : 0); }
  void sendSerialByte(uint32_t data, size_t p = 0) { ports[p].txFIFO.push(data); }

  static std::vector<Function> extractPorts(const std::vector<uint8_t> &descriptors);

 private:
  bool initialized = false, busy = false;
  std::optional<uint32_t> descriptorsSize;
  std::vector<uint8_t> descriptors;
  std::deque<std::pair<size_t, uint32_t>> pending;
  void next();
};

}  // namespace rp2040js
