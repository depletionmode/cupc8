// Port of rp2040js src/usb/setup.ts
#include "setup.h"

namespace rp2040js {

std::vector<uint8_t> createSetupPacket(const ISetupPacketParams &params) {
  std::vector<uint8_t> setupPacket(8);
  // Uint8Array stores: ToUint8 of each value
  setupPacket[0] = static_cast<uint8_t>((static_cast<uint32_t>(params.dataDirection) << 7) |
                                        (static_cast<uint32_t>(params.type) << 5) |
                                        static_cast<uint32_t>(params.recipient));
  setupPacket[1] = static_cast<uint8_t>(params.bRequest);
  setupPacket[2] = static_cast<uint8_t>(params.wValue & 0xff);
  setupPacket[3] = static_cast<uint8_t>((params.wValue >> 8) & 0xff);
  setupPacket[4] = static_cast<uint8_t>(params.wIndex & 0xff);
  setupPacket[5] = static_cast<uint8_t>((params.wIndex >> 8) & 0xff);
  setupPacket[6] = static_cast<uint8_t>(params.wLength & 0xff);
  setupPacket[7] = static_cast<uint8_t>((params.wLength >> 8) & 0xff);
  return setupPacket;
}

std::vector<uint8_t> setDeviceAddressPacket(uint32_t address) {
  return createSetupPacket({
      DataDirection::HostToDevice,
      SetupType::Standard,
      SetupRecipient::Device,
      static_cast<uint32_t>(SetupRequest::SetAddress),
      address,  // wValue
      0,        // wIndex
      0,        // wLength
  });
}

std::vector<uint8_t> getDescriptorPacket(DescriptorType type, uint32_t length, uint32_t index) {
  return createSetupPacket({
      DataDirection::DeviceToHost,
      SetupType::Standard,
      SetupRecipient::Device,
      static_cast<uint32_t>(SetupRequest::GetDescriptor),
      static_cast<uint32_t>(type) << 8,  // wValue
      index,                             // wIndex
      length,                            // wLength
  });
}

std::vector<uint8_t> setDeviceConfigurationPacket(uint32_t configurationNumber) {
  return createSetupPacket({
      DataDirection::HostToDevice,
      SetupType::Standard,
      SetupRecipient::Device,
      static_cast<uint32_t>(SetupRequest::SetDeviceConfiguration),
      configurationNumber,  // wValue
      0,                    // wIndex
      0,                    // wLength
  });
}

}  // namespace rp2040js
