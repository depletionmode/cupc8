// Port of rp2040js src/usb/cdc.ts
#include "cdc.h"

#include <algorithm>

#include "../peripherals/usb.h"
#include "setup.h"

namespace rp2040js {

// CDC stuff
static constexpr uint32_t CDC_REQUEST_SET_CONTROL_LINE_STATE = 0x22;

static constexpr uint32_t CDC_DTR = 1 << 0;
static constexpr uint32_t CDC_RTS = 1 << 1;

static constexpr uint32_t CDC_DATA_CLASS = 10;
static constexpr uint32_t ENDPOINT_BULK = 2;

static constexpr uint32_t TX_FIFO_SIZE = 512;

static constexpr uint32_t ENDPOINT_ZERO = 0;
static constexpr uint32_t CONFIGURATION_DESCRIPTOR_SIZE = 9;

// the header spells out cdcSetControlLineState's default value and txFIFO's size
static_assert((CDC_DTR | CDC_RTS) == 0b11 && TX_FIFO_SIZE == 512, "cdc.h defaults");

EndpointNumbers extractEndpointNumbers(const std::vector<uint8_t> &descriptors) {
  size_t index = 0;
  bool foundInterface = false;
  EndpointNumbers result;
  while (index < descriptors.size()) {
    const uint32_t len = descriptors[index];
    if (len < 2 || descriptors.size() < index + len) {
      break;
    }
    const uint32_t type = descriptors[index + 1];
    if (type == static_cast<uint32_t>(DescriptorType::Interface) && len == 9) {
      const uint32_t numEndpoints = descriptors[index + 4];
      const uint32_t interfaceClass = descriptors[index + 5];
      foundInterface = numEndpoints == 2 && interfaceClass == CDC_DATA_CLASS;
    }
    if (foundInterface && type == static_cast<uint32_t>(DescriptorType::Endpoint) && len == 7) {
      const uint32_t address = descriptors[index + 2];
      const uint32_t attributes = descriptors[index + 3];
      if ((attributes & 0x3) == ENDPOINT_BULK) {
        if (address & 0x80) {
          result.in = static_cast<int32_t>(address & 0xf);
        } else {
          result.out = static_cast<int32_t>(address & 0xf);
        }
      }
    }
    index += descriptors[index];
  }
  return result;
}

USBCDC::USBCDC(RPUSBController &usb) : usb(usb) {
  this->usb.onUSBEnabled = [this] { this->usb.resetDevice(); };
  this->usb.onResetReceived = [this] { this->usb.sendSetupPacket(setDeviceAddressPacket(1)); };
  this->usb.onEndpointWrite = [this](uint32_t endpoint, const std::vector<uint8_t> &buffer) {
    if (endpoint == ENDPOINT_ZERO && buffer.size() == 0) {
      if (!descriptorsSize.has_value()) {
        this->usb.sendSetupPacket(
            getDescriptorPacket(DescriptorType::Configration, CONFIGURATION_DESCRIPTOR_SIZE));
      }
      // Acknowledgement
      else if (!initialized) {
        cdcSetControlLineState();
        if (onDeviceConnected) onDeviceConnected();
      }
    }
    if (endpoint == ENDPOINT_ZERO && buffer.size() > 1) {
      if (buffer.size() == CONFIGURATION_DESCRIPTOR_SIZE &&
          buffer[1] == static_cast<uint32_t>(DescriptorType::Configration) &&
          !descriptorsSize.has_value()) {
        descriptorsSize = (static_cast<uint32_t>(buffer[3]) << 8) | buffer[2];
        this->usb.sendSetupPacket(getDescriptorPacket(DescriptorType::Configration, *descriptorsSize));
      } else if (descriptorsSize.has_value() && descriptors.size() < *descriptorsSize) {
        descriptors.insert(descriptors.end(), buffer.begin(), buffer.end());
      }
      if (descriptorsSize.has_value() && *descriptorsSize == descriptors.size()) {
        const EndpointNumbers endpoints = extractEndpointNumbers(descriptors);
        inEndpoint = endpoints.in;
        outEndpoint = endpoints.out;

        // Now configure the device
        this->usb.sendSetupPacket(setDeviceConfigurationPacket(1));
      }
    }
    if (static_cast<int64_t>(endpoint) == inEndpoint) {
      if (onSerialData) onSerialData(buffer);
    }
  };
  this->usb.onEndpointRead = [this](uint32_t endpoint, uint32_t size) {
    if (static_cast<int64_t>(endpoint) == outEndpoint) {
      std::vector<uint8_t> buffer(std::min(size, txFIFO.itemCount()));
      for (size_t i = 0; i < buffer.size(); i++) {
        buffer[i] = static_cast<uint8_t>(txFIFO.pull());  // Uint8Array store
      }
      this->usb.endpointReadDone(static_cast<uint32_t>(outEndpoint), std::move(buffer));
    }
  };
}

void USBCDC::cdcSetControlLineState(uint32_t value, uint32_t interfaceNumber) {
  usb.sendSetupPacket(createSetupPacket({
      DataDirection::HostToDevice,
      SetupType::Class,
      SetupRecipient::Device,
      CDC_REQUEST_SET_CONTROL_LINE_STATE,  // bRequest
      value,                               // wValue
      interfaceNumber,                     // wIndex
      0,                                   // wLength
  }));
  initialized = true;
}

void USBCDC::sendSerialByte(uint32_t data) { txFIFO.push(data); }

}  // namespace rp2040js
