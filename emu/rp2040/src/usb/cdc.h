// Port of rp2040js src/usb/cdc.ts (a host-side USB CDC model attached to
// RPUSBController's callbacks; not reachable from rp2040.ts itself).
#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <vector>

#include "../utils/fifo.h"

namespace rp2040js {

class RPUSBController;

/** `{ in: -1, out: -1 }` */
struct EndpointNumbers {
  int32_t in = -1;
  int32_t out = -1;
};

EndpointNumbers extractEndpointNumbers(const std::vector<uint8_t> &descriptors);

class USBCDC {
 public:
  FIFO txFIFO{512};  // TX_FIFO_SIZE

  std::function<void(const std::vector<uint8_t> &buffer)> onSerialData;
  std::function<void()> onDeviceConnected;

  RPUSBController &usb;

  /** Installs the usb callbacks (onUSBEnabled, onResetReceived, onEndpointWrite, onEndpointRead?) */
  explicit USBCDC(RPUSBController &usb);
  USBCDC(const USBCDC &) = delete;
  USBCDC &operator=(const USBCDC &) = delete;

  void sendSerialByte(uint32_t data);

 private:
  bool initialized = false;
  std::optional<uint32_t> descriptorsSize;  // `number | null`
  std::vector<uint8_t> descriptors;
  int32_t outEndpoint = -1;
  int32_t inEndpoint = -1;

  /** defaults: value = CDC_DTR | CDC_RTS, interfaceNumber = 0 */
  void cdcSetControlLineState(uint32_t value = 0b11, uint32_t interfaceNumber = 0);
};

}  // namespace rp2040js
