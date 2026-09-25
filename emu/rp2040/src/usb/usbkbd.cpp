// Port of test/emu/usbkbd.mjs
#include "usbkbd.h"

#include <algorithm>

namespace rp2040js {

static const std::vector<uint32_t> BOOT_KEYBOARD_REPORT = {
    0x05, 0x01, 0x09, 0x06, 0xa1, 0x01, 0x05, 0x07, 0x19, 0xe0, 0x29, 0xe7, 0x15, 0x00, 0x25, 0x01,
    0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01, 0x75, 0x08, 0x81, 0x01, 0x95, 0x05, 0x75, 0x01,
    0x05, 0x08, 0x19, 0x01, 0x29, 0x05, 0x91, 0x02, 0x95, 0x01, 0x75, 0x03, 0x91, 0x01, 0x95, 0x06,
    0x75, 0x08, 0x15, 0x00, 0x25, 0x65, 0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xc0,
};

// `Uint8Array.from(bytes.slice(0, length))`
static std::vector<uint8_t> toBytes(const std::vector<uint32_t> &bytes, uint32_t length) {
  const size_t n = std::min(static_cast<size_t>(length), bytes.size());
  std::vector<uint8_t> result;
  result.reserve(n);
  for (auto it = bytes.begin(); it != bytes.begin() + static_cast<std::ptrdiff_t>(n); ++it)
    result.push_back(static_cast<uint8_t>(*it));  // ToUint8
  return result;
}

UsbKeyboard::UsbKeyboard() : UsbKeyboard(Options{}) {}

UsbKeyboard::UsbKeyboard(Options options) {
  const uint32_t speed = options.speed, interval = options.interval;
  speed_ = speed;
  mps0 = speed == 1 ? 8 : 64;
  device = {18, 1, 0x10, 0x01, 0, 0, 0, mps0, 0x09, 0x12, 0x01, 0x00, 0x00, 0x01, 0, 0, 0, 1};
  const std::vector<uint32_t> &report = BOOT_KEYBOARD_REPORT;
  reportDesc = report;
  config = {
      9, 2, 34, 0, 1, 1, 0, 0xa0, 50,
      9, 4, 0, 0, 1, 3, 1, 1, 0,  // HID, boot, keyboard
      9, 0x21, 0x11, 0x01, 0, 1, 0x22, static_cast<uint32_t>(report.size()), 0,
      7, 5, 0x81, 3, 8, 0, interval,
  };
  busReset();
  leds.clear();  // every LED output report, in order
  protocol = 1;  // 1 report, 0 boot
  reports.clear();
  log.clear();
}

void UsbKeyboard::busReset() {
  addr = 0;
  pendingAddr.reset();
  configured = 0;
  ctrl.reset();
}

void UsbKeyboard::press(uint32_t mods, const std::vector<uint32_t> &keys) {
  // [mods, 0, ...keys, 0, 0, 0, 0, 0, 0].slice(0, 8)
  std::vector<uint32_t> r = {mods, 0};
  r.insert(r.end(), keys.begin(), keys.end());
  r.insert(r.end(), {0, 0, 0, 0, 0, 0});
  reports.push_back(toBytes(r, 8));
}

void UsbKeyboard::press(uint32_t mods, std::initializer_list<uint32_t> keys) {
  press(mods, std::vector<uint32_t>(keys));
}

USBHostDevice::Handshake UsbKeyboard::setup(uint32_t addr, const std::vector<uint8_t> &p) {
  if (addr != this->addr) return Handshake::ack;  // not us: nothing answers
  const uint32_t type = p[0], req = p[1], value = p[2] | (p[3] << 8), length = p[6] | (p[7] << 8);
  log.push_back({type, req, value, length});
  auto reply = [length](const std::vector<uint32_t> &bytes) {
    Ctrl c;
    c.in = toBytes(bytes, length);
    c.pos = 0;
    return c;
  };
  auto statusOnly = [](std::function<void()> status) {
    Ctrl c;
    c.status = std::move(status);
    return c;
  };
  ctrl.reset();
  if (type == 0x80 && req == 6) {  // GET_DESCRIPTOR
    const uint32_t kind = value >> 8;
    if (kind == 1)
      ctrl = reply(device);
    else if (kind == 2)
      ctrl = reply(config);
    else
      return Handshake::stall;  // no strings
  } else if (type == 0x81 && req == 6 && value >> 8 == 0x22) {
    ctrl = reply(reportDesc);
  } else if (type == 0x00 && req == 5) {  // SET_ADDRESS (after status)
    ctrl = statusOnly([this, value] { this->addr = value & 0x7f; });
  } else if (type == 0x00 && req == 9) {  // SET_CONFIGURATION
    ctrl = statusOnly([this, value] { configured = value; });
  } else if (type == 0x21 && req == 0x0a) {  // SET_IDLE
    ctrl = statusOnly([] {});
  } else if (type == 0x21 && req == 0x0b) {  // SET_PROTOCOL
    ctrl = statusOnly([this, value] { protocol = value; });
  } else if (type == 0x21 && req == 0x09) {  // SET_REPORT: the LEDs
    Ctrl c;
    c.out = std::vector<uint8_t>();
    c.length = length;
    // `c.status = () => this.leds.push(c.out[0])`: in() runs that for a ctrl with `out`
    ctrl = std::move(c);
  } else {
    return Handshake::stall;
  }
  return Handshake::ack;
}

USBHostDevice::InResult UsbKeyboard::in(uint32_t addr, uint32_t ep, uint32_t maxLen) {
  if (addr != this->addr) return {Handshake::nak, {}};
  if (ep == 0) {
    if (!ctrl) return {Handshake::stall, {}};
    Ctrl &c = *ctrl;
    if (c.in) {
      // c.in.subarray(c.pos, c.pos + Math.min(this.mps0, maxLen))
      const std::vector<uint8_t> &data = *c.in;
      const size_t begin = std::min(c.pos, data.size());
      const size_t end = std::min(c.pos + std::min(mps0, maxLen), data.size());
      std::vector<uint8_t> chunk(data.begin() + static_cast<std::ptrdiff_t>(begin),
                                 data.begin() + static_cast<std::ptrdiff_t>(std::max(begin, end)));
      c.pos += chunk.size();
      return {Handshake::ack, std::move(chunk)};
    }
    // status stage of a no-data or OUT-data request
    Ctrl done = std::move(*ctrl);
    ctrl.reset();
    if (done.out) {
      // SET_REPORT: `this.leds.push(c.out[0])` (undefined when no data came)
      leds.push_back(done.out->empty() ? -1 : static_cast<int32_t>((*done.out)[0]));
    } else {
      done.status();
    }
    return {Handshake::ack, {}};
  }
  if (ep == 1 && configured) {
    if (reports.empty()) return {Handshake::nak, {}};
    std::vector<uint8_t> report = std::move(reports.front());
    reports.pop_front();
    return {Handshake::ack, std::move(report)};
  }
  return {Handshake::stall, {}};
}

USBHostDevice::Handshake UsbKeyboard::out(uint32_t addr, uint32_t ep, const std::vector<uint8_t> &data) {
  if (addr != this->addr || ep != 0 || !ctrl) return Handshake::stall;
  if (ctrl->out && ctrl->out->size() < ctrl->length) {
    ctrl->out->insert(ctrl->out->end(), data.begin(), data.end());  // data stage
    return Handshake::ack;
  }
  ctrl.reset();  // status stage after IN data
  return Handshake::ack;
}

}  // namespace rp2040js
