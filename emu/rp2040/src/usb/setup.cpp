// Port of rp2040js src/usb/setup.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "setup.h"

#include "../utils/js.h"

namespace rp2040js {

std::vector<uint8_t> createSetupPacket(const ISetupPacketParams &params) {
  // TODO(port): usb/setup.ts
  //   export function createSetupPacket(params: ISetupPacketParams) {
  //     const setupPacket = new Uint8Array(8);
  //     setupPacket[0] = (params.dataDirection << 7) | (params.type << 5) | params.recipient;
  //     setupPacket[1] = params.bRequest;
  //     setupPacket[2] = params.wValue & 0xff;
  //     setupPacket[3] = (params.wValue >> 8) & 0xff;
  //     setupPacket[4] = params.wIndex & 0xff;
  //     setupPacket[5] = (params.wIndex >> 8) & 0xff;
  //     setupPacket[6] = params.wLength & 0xff;
  //     setupPacket[7] = (params.wLength >> 8) & 0xff;
  //     return setupPacket;
  //   }
  (void)params;
  return {};
}

std::vector<uint8_t> setDeviceAddressPacket(uint32_t address) {
  // TODO(port): usb/setup.ts
  //   export function setDeviceAddressPacket(address: number) {
  //     return createSetupPacket({
  //       dataDirection: DataDirection.HostToDevice,
  //       type: SetupType.Standard,
  //       recipient: SetupRecipient.Device,
  //       bRequest: SetupRequest.SetAddress,
  //       wValue: address,
  //       wIndex: 0,
  //       wLength: 0,
  //     });
  //   }
  (void)address;
  return {};
}

std::vector<uint8_t> getDescriptorPacket(DescriptorType type, uint32_t length, uint32_t index) {
  // TODO(port): usb/setup.ts
  //   export function getDescriptorPacket(type: DescriptorType, length: number, index = 0) {
  //     return createSetupPacket({
  //       dataDirection: DataDirection.DeviceToHost,
  //       type: SetupType.Standard,
  //       recipient: SetupRecipient.Device,
  //       bRequest: SetupRequest.GetDescriptor,
  //       wValue: type << 8,
  //       wIndex: index,
  //       wLength: length,
  //     });
  //   }
  (void)type;
  (void)length;
  (void)index;
  return {};
}

std::vector<uint8_t> setDeviceConfigurationPacket(uint32_t configurationNumber) {
  // TODO(port): usb/setup.ts
  //   export function setDeviceConfigurationPacket(configurationNumber: number) {
  //     return createSetupPacket({
  //       dataDirection: DataDirection.HostToDevice,
  //       type: SetupType.Standard,
  //       recipient: SetupRecipient.Device,
  //       bRequest: SetupRequest.SetDeviceConfiguration,
  //       wValue: configurationNumber,
  //       wIndex: 0,
  //       wLength: 0,
  //     });
  //   }
  (void)configurationNumber;
  return {};
}

}  // namespace rp2040js
