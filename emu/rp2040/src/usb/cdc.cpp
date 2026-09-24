// Port of rp2040js src/usb/cdc.ts
//
// STUB: every body below still has to be ported from the TS shown in its
// comment (see README.md, "Porting rules"). Bus-facing methods abort so that
// firmware cannot run on a half-ported peripheral without noticing.
#include "cdc.h"

#include "../peripherals/usb.h"
#include "setup.h"
#include "../utils/js.h"

namespace rp2040js {

EndpointNumbers extractEndpointNumbers(const std::vector<uint8_t> &descriptors) {
  // TODO(port): usb/cdc.ts
  //   export function extractEndpointNumbers(descriptors: ArrayLike<number>) {
  //     let index = 0;
  //     let foundInterface = false;
  //     const result = {
  //       in: -1,
  //       out: -1,
  //     };
  //     while (index < descriptors.length) {
  //       const len = descriptors[index];
  //       if (len < 2 || descriptors.length < index + len) {
  //         break;
  //       }
  //       const type = descriptors[index + 1];
  //       if (type === DescriptorType.Interface && len === 9) {
  //         const numEndpoints = descriptors[index + 4];
  //         const interfaceClass = descriptors[index + 5];
  //         foundInterface = numEndpoints === 2 && interfaceClass === CDC_DATA_CLASS;
  //       }
  //       if (foundInterface && type === DescriptorType.Endpoint && len === 7) {
  //         const address = descriptors[index + 2];
  //         const attributes = descriptors[index + 3];
  //         if ((attributes & 0x3) === ENDPOINT_BULK) {
  //           if (address & 0x80) {
  //             result.in = address & 0xf;
  //           } else {
  //             result.out = address & 0xf;
  //           }
  //         }
  //       }
  //       index += descriptors[index];
  //     }
  //     return result;
  //   }
  (void)descriptors;
  return {};
}

USBCDC::USBCDC(RPUSBController &usb) : usb(usb) {
  // TODO(port): usb/cdc.ts
  //   constructor(readonly usb: RPUSBController) {
  //     this.usb.onUSBEnabled = () => {
  //       this.usb.resetDevice();
  //     };
  //     this.usb.onResetReceived = () => {
  //       this.usb.sendSetupPacket(setDeviceAddressPacket(1));
  //     };
  //     this.usb.onEndpointWrite = (endpoint, buffer) => {
  //       if (endpoint === ENDPOINT_ZERO && buffer.length === 0) {
  //         if (this.descriptorsSize == null) {
  //           this.usb.sendSetupPacket(
  //             getDescriptorPacket(DescriptorType.Configration, CONFIGURATION_DESCRIPTOR_SIZE),
  //           );
  //         }
  //         // Acknowledgement
  //         else if (!this.initialized) {
  //           this.cdcSetControlLineState();
  //           this.onDeviceConnected?.();
  //         }
  //       }
  //       if (endpoint === ENDPOINT_ZERO && buffer.length > 1) {
  //         if (
  //           buffer.length === CONFIGURATION_DESCRIPTOR_SIZE &&
  //           buffer[1] === DescriptorType.Configration &&
  //           this.descriptorsSize == null
  //         ) {
  //           this.descriptorsSize = (buffer[3] << 8) | buffer[2];
  //           this.usb.sendSetupPacket(
  //             getDescriptorPacket(DescriptorType.Configration, this.descriptorsSize),
  //           );
  //         } else if (this.descriptorsSize != null && this.descriptors.length < this.descriptorsSize) {
  //           this.descriptors.push(...buffer);
  //         }
  //         if (this.descriptorsSize === this.descriptors.length) {
  //           const endpoints = extractEndpointNumbers(this.descriptors);
  //           this.inEndpoint = endpoints.in;
  //           this.outEndpoint = endpoints.out;
  //
  //           // Now configure the device
  //           this.usb.sendSetupPacket(setDeviceConfigurationPacket(1));
  //         }
  //       }
  //       if (endpoint === this.inEndpoint) {
  //         this.onSerialData?.(buffer);
  //       }
  //     };
  //     this.usb.onEndpointRead = (endpoint, size) => {
  //       if (endpoint === this.outEndpoint) {
  //         const buffer = new Uint8Array(Math.min(size, this.txFIFO.itemCount));
  //         for (let i = 0; i < buffer.length; i++) {
  //           buffer[i] = this.txFIFO.pull();
  //         }
  //         this.usb.endpointReadDone(this.outEndpoint, buffer);
  //       }
  //     };
  //   }
}

void USBCDC::cdcSetControlLineState(uint32_t value, uint32_t interfaceNumber) {
  // TODO(port): usb/cdc.ts
  //   private cdcSetControlLineState(value = CDC_DTR | CDC_RTS, interfaceNumber = 0) {
  //     this.usb.sendSetupPacket(
  //       createSetupPacket({
  //         dataDirection: DataDirection.HostToDevice,
  //         type: SetupType.Class,
  //         recipient: SetupRecipient.Device,
  //         bRequest: CDC_REQUEST_SET_CONTROL_LINE_STATE,
  //         wValue: value,
  //         wIndex: interfaceNumber,
  //         wLength: 0,
  //       }),
  //     );
  //     this.initialized = true;
  //   }
  (void)value;
  (void)interfaceNumber;
}

void USBCDC::sendSerialByte(uint32_t data) {
  // TODO(port): usb/cdc.ts
  //   sendSerialByte(data: number) {
  //     this.txFIFO.push(data);
  //   }
  (void)data;
}

}  // namespace rp2040js
