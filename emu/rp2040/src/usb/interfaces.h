// Port of rp2040js src/usb/interfaces.ts
#pragma once

#include <cstdint>

namespace rp2040js {

enum class DataDirection : uint32_t {
  HostToDevice,
  DeviceToHost,
};

enum class SetupType : uint32_t {
  Standard,
  Class,
  Vendor,
  Reserved,
};

enum class SetupRecipient : uint32_t {
  Device,
  Interface,
  Endpoint,
  Other,
};

enum class SetupRequest : uint32_t {
  GetStatus,
  ClearFeature,
  Reserved1,
  SetFeature,
  Reserved2,
  SetAddress,
  GetDescriptor,
  SetDescriptor,
  GetConfiguration,
  SetDeviceConfiguration,
  GetInterface,
  SetInterface,
  SynchFrame,
};

enum class DescriptorType : uint32_t {
  Device = 1,
  Configration = 2,
  String = 3,
  Interface = 4,
  Endpoint = 5,
};

struct ISetupPacketParams {
  DataDirection dataDirection;
  SetupType type;
  SetupRecipient recipient;
  uint32_t bRequest;  // SetupRequest | number
  uint32_t wValue;    /* 16 bits */
  uint32_t wIndex;    /* 16 bits */
  uint32_t wLength;   /* 16 bits */
};

}  // namespace rp2040js
