// Port of test/emu/usbkbd.mjs (cupc8's test-side device, not an rp2040js module):
// a USB HID boot keyboard for the emulated RP2040's host port (the patched
// rp2040js USBHostController): control transfers on EP0, reports on EP1 IN.
// It records what the host did to it (address, configuration, protocol,
// LED output reports) so tests can check the card drove it correctly.
#pragma once

#include <cstdint>
#include <deque>
#include <functional>
#include <initializer_list>
#include <optional>
#include <vector>

#include "../peripherals/usb-host.h"

namespace rp2040js {

class UsbKeyboard : public USBHostDevice {
 public:
  /** `{ speed = 1, interval = 10 }` */
  struct Options {
    uint32_t speed = 1;
    uint32_t interval = 10;
  };

  /** one `{ type, req, value, length }` entry of `log` */
  struct LogEntry {
    uint32_t type;
    uint32_t req;
    uint32_t value;
    uint32_t length;
  };

  /**
   * `this.ctrl`: the control transfer in progress. The JS object is one of
   * `{ in, pos }`, `{ status }` or `{ out, length, status }`.
   */
  struct Ctrl {
    std::optional<std::vector<uint8_t>> in;   // `in: Uint8Array`
    size_t pos = 0;
    std::optional<std::vector<uint8_t>> out;  // `out: number[]`
    uint32_t length = 0;
    std::function<void()> status;
  };

  // speed 1 = low speed (most keyboards; 8-byte EP0), 2 = full speed
  uint32_t speed_;
  uint32_t mps0;
  std::vector<uint32_t> device;
  std::vector<uint32_t> reportDesc;
  std::vector<uint32_t> config;

  uint32_t addr = 0;
  std::optional<uint32_t> pendingAddr;  // `null`; never set otherwise (as in the JS)
  uint32_t configured = 0;
  std::optional<Ctrl> ctrl;             // `null` when empty

  /** every LED output report, in order; -1 is `undefined` (a SET_REPORT with no data) */
  std::vector<int32_t> leds;
  uint32_t protocol = 1;  // 1 report, 0 boot
  std::deque<std::vector<uint8_t>> reports;
  std::vector<LogEntry> log;

  UsbKeyboard();
  explicit UsbKeyboard(Options options);
  UsbKeyboard(const UsbKeyboard &) = delete;
  UsbKeyboard &operator=(const UsbKeyboard &) = delete;

  uint32_t speed() const override { return speed_; }
  void busReset() override;

  // queue HID boot reports: [mods, 0, k1..k6]
  void press(uint32_t mods, const std::vector<uint32_t> &keys);
  void press(uint32_t mods, std::initializer_list<uint32_t> keys = {});

  Handshake setup(uint32_t addr, const std::vector<uint8_t> &p) override;
  InResult in(uint32_t addr, uint32_t ep, uint32_t maxLen) override;
  Handshake out(uint32_t addr, uint32_t ep, const std::vector<uint8_t> &data) override;
};

}  // namespace rp2040js
