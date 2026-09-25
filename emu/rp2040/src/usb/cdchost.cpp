// Port of test/emu/cdchost.mjs
#include "cdchost.h"

#include <algorithm>

#include "../peripherals/usb.h"
#include "setup.h"

namespace rp2040js {

static constexpr uint32_t CDC_REQUEST_SET_CONTROL_LINE_STATE = 0x22;
static constexpr uint32_t CDC_DTR = 1, CDC_RTS = 2;
static constexpr uint32_t CDC_COMM_CLASS = 2, CDC_DATA_CLASS = 10;
static constexpr uint32_t ENDPOINT_BULK = 2;
static constexpr uint32_t CONFIGURATION_DESCRIPTOR_SIZE = 9;

std::vector<CdcHost::Function> CdcHost::extractPorts(const std::vector<uint8_t> &d) {
  std::vector<Function> ports;
  int32_t comm = -1;
  bool data = false;
  for (size_t i = 0; i < d.size();) {
    const uint32_t len = d[i];
    if (len < 2 || d.size() < i + len) break;
    const uint32_t type = d[i + 1];
    if (type == static_cast<uint32_t>(DescriptorType::Interface) && len == 9) {
      data = false;
      if (d[i + 5] == CDC_COMM_CLASS) {
        comm = d[i + 2];
      } else if (d[i + 5] == CDC_DATA_CLASS && d[i + 4] == 2) {
        data = true;
        ports.push_back({comm, -1, -1});
      }
    }
    if (data && type == static_cast<uint32_t>(DescriptorType::Endpoint) && len == 7 &&
        (d[i + 3] & 3) == ENDPOINT_BULK) {
      if (d[i + 2] & 0x80)
        ports.back().in = d[i + 2] & 0xf;
      else
        ports.back().out = d[i + 2] & 0xf;
    }
    i += len;
  }
  return ports;
}

CdcHost::CdcHost(RPUSBController &usb, size_t nports) : ports(nports), usb(usb) {
  usb.onUSBEnabled = [this] { this->usb.resetDevice(); };
  usb.onResetReceived = [this] { this->usb.sendSetupPacket(setDeviceAddressPacket(1)); };
  usb.onEndpointWrite = [this](uint32_t ep, const std::vector<uint8_t> &buf) {
    if (ep == 0 && buf.empty()) {
      if (!descriptorsSize.has_value()) {
        this->usb.sendSetupPacket(getDescriptorPacket(DescriptorType::Configration, CONFIGURATION_DESCRIPTOR_SIZE));
      } else if (!initialized) {
        // configured: port 0 opens, as USBCDC's one port does
        initialized = true;
        busy = false;
        setLines(0, CDC_DTR | CDC_RTS);
        if (onDeviceConnected) onDeviceConnected();
      } else {
        // a control request's status stage: the next may go
        busy = false;
        next();
      }
    }
    if (ep == 0 && buf.size() > 1) {
      if (buf.size() == CONFIGURATION_DESCRIPTOR_SIZE &&
          buf[1] == static_cast<uint32_t>(DescriptorType::Configration) && !descriptorsSize.has_value()) {
        descriptorsSize = (static_cast<uint32_t>(buf[3]) << 8) | buf[2];
        this->usb.sendSetupPacket(getDescriptorPacket(DescriptorType::Configration, *descriptorsSize));
      } else if (descriptorsSize.has_value() && descriptors.size() < *descriptorsSize) {
        descriptors.insert(descriptors.end(), buf.begin(), buf.end());
      }
      if (descriptorsSize.has_value() && *descriptorsSize == descriptors.size()) {
        const auto found = extractPorts(descriptors);
        for (size_t i = 0; i < found.size() && i < ports.size(); i++) {
          ports[i].comm = found[i].comm;
          ports[i].in = found[i].in;
          ports[i].out = found[i].out;
        }
        this->usb.sendSetupPacket(setDeviceConfigurationPacket(1));
      }
    }
    if (ep != 0) {
      for (auto &p : ports) {
        if (p.in == static_cast<int32_t>(ep)) {
          if (p.onSerialData) p.onSerialData(buf);
          break;
        }
      }
    }
  };
  usb.onEndpointRead = [this](uint32_t ep, uint32_t size) {
    for (auto &p : ports) {
      if (p.out != static_cast<int32_t>(ep)) continue;
      std::vector<uint8_t> b(std::min(size, p.txFIFO.itemCount()));
      for (auto &x : b) x = static_cast<uint8_t>(p.txFIFO.pull());
      this->usb.endpointReadDone(ep, std::move(b));
      return;
    }
  };
}

size_t CdcHost::portCount() const {
  return static_cast<size_t>(std::count_if(ports.begin(), ports.end(), [](const Port &p) { return p.in >= 0; }));
}

void CdcHost::setLines(size_t p, uint32_t value) {
  pending.emplace_back(p, value);
  next();
}

void CdcHost::next() {
  if (busy || !initialized || pending.empty()) return;
  busy = true;
  const auto [p, value] = pending.front();
  pending.pop_front();
  usb.sendSetupPacket(createSetupPacket({
      DataDirection::HostToDevice,
      SetupType::Class,
      SetupRecipient::Interface,
      CDC_REQUEST_SET_CONTROL_LINE_STATE,
      value,
      static_cast<uint32_t>(ports[p].comm) & 0xffff,
      0,
  }));
}

}  // namespace rp2040js
