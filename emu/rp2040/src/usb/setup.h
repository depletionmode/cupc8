// Port of rp2040js src/usb/setup.ts
#pragma once

#include <cstdint>
#include <vector>

#include "interfaces.h"

namespace rp2040js {

/** Returns `new Uint8Array(8)` filled in. */
std::vector<uint8_t> createSetupPacket(const ISetupPacketParams &params);
std::vector<uint8_t> setDeviceAddressPacket(uint32_t address);
std::vector<uint8_t> getDescriptorPacket(DescriptorType type, uint32_t length, uint32_t index = 0);
std::vector<uint8_t> setDeviceConfigurationPacket(uint32_t configurationNumber);

}  // namespace rp2040js
