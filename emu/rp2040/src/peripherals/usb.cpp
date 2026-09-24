// Port of rp2040js src/peripherals/usb.ts (with the cupc8 patch: host mode)
#include "usb.h"

#include <algorithm>
#include <stdexcept>
#include <utility>

#include "../irq.h"
#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

static constexpr uint32_t ENDPOINT_COUNT = 16;

// USB DPSRAM Registers
static constexpr uint32_t EP1_IN_CONTROL = 0x8;
static constexpr uint32_t EP0_IN_BUFFER_CONTROL = 0x80;
static constexpr uint32_t EP0_OUT_BUFFER_CONTROL = 0x84;
static constexpr uint32_t EP15_OUT_BUFFER_CONTROL = 0xfc;

// Endpoint Control bits
static constexpr uint32_t USB_CTRL_DOUBLE_BUF = 1 << 30;
static constexpr uint32_t USB_CTRL_INTERRUPT_PER_TRANSFER = 1 << 29;

// Buffer Control bits
static constexpr uint32_t USB_BUF_CTRL_AVAILABLE = 1 << 10;
static constexpr uint32_t USB_BUF_CTRL_FULL = 1 << 15;
static constexpr uint32_t USB_BUF_CTRL_LEN_MASK = 0x3ff;
// Buffer1
static constexpr uint32_t USB_BUF1_SHIFT = 16;
static constexpr uint32_t USB_BUF1_OFFSET = 64;

// USB Peripheral Register
static constexpr uint32_t ADDR_ENDP = 0x0;
static constexpr uint32_t MAIN_CTRL = 0x40;
static constexpr uint32_t SOF_RD = 0x48;
static constexpr uint32_t SIE_CTRL = 0x4c;
static constexpr uint32_t SIE_STATUS = 0x50;
static constexpr uint32_t INT_EP_CTRL = 0x54;
static constexpr uint32_t USB_PWR = 0x78;
static constexpr uint32_t BUFF_STATUS = 0x58;
static constexpr uint32_t BUFF_CPU_SHOULD_HANDLE = 0x5c;
static constexpr uint32_t USB_MUXING = 0x74;
static constexpr uint32_t INTR = 0x8c;
static constexpr uint32_t INTE = 0x90;
static constexpr uint32_t INTF = 0x94;
static constexpr uint32_t INTS = 0x98;

// MAIN_CTRL bits
// JS-SIGN: `1 << 31` is -2147483648 in TS, so mainCtrl reads back negative
// when SIM_TIMING is set; the bus only sees the bit pattern.
static constexpr uint32_t SIM_TIMING = 1u << 31;
static constexpr uint32_t HOST_NDEVICE = 1 << 1;
static constexpr uint32_t CONTROLLER_EN = 1 << 0;

// SIE_STATUS bits
static constexpr uint32_t SIE_DATA_SEQ_ERROR = 1u << 31;
static constexpr uint32_t SIE_ACK_REC = 1 << 30;
static constexpr uint32_t SIE_STALL_REC = 1 << 29;
static constexpr uint32_t SIE_NAK_REC = 1 << 28;
static constexpr uint32_t SIE_RX_TIMEOUT = 1 << 27;
static constexpr uint32_t SIE_RX_OVERFLOW = 1 << 26;
static constexpr uint32_t SIE_BIT_STUFF_ERROR = 1 << 25;
static constexpr uint32_t SIE_CRC_ERROR = 1 << 24;
static constexpr uint32_t SIE_BUS_RESET = 1 << 19;
static constexpr uint32_t SIE_TRANS_COMPLETE = 1 << 18;
static constexpr uint32_t SIE_SETUP_REC = 1 << 17;
static constexpr uint32_t SIE_CONNECTED = 1 << 16;
static constexpr uint32_t SIE_RESUME = 1 << 11;
static constexpr uint32_t SIE_VBUS_OVER_CURR = 1 << 10;
static constexpr uint32_t SIE_SPEED = 1 << 9;
static constexpr uint32_t SIE_SUSPENDED = 1 << 4;
static constexpr uint32_t SIE_LINE_STATE_MASK = 0x3;
static constexpr uint32_t SIE_LINE_STATE_SHIFT = 2;
static constexpr uint32_t SIE_VBUS_DETECTED = 1 << 0;

// USB_MUXING bits
static constexpr uint32_t SOFTCON = 1 << 3;
static constexpr uint32_t TO_DIGITAL_PAD = 1 << 2;
static constexpr uint32_t TO_EXTPHY = 1 << 1;
static constexpr uint32_t TO_PHY = 1 << 0;

// INTR bits
static constexpr uint32_t INTR_BUFF_STATUS = 1 << 4;

// SIE Line states
enum SIELineState : uint32_t {
  SE0 = 0b00,
  J = 0b01,
  K = 0b10,
  SE1 = 0b11,
};

static constexpr uint32_t SIE_WRITECLEAR_MASK =
    SIE_DATA_SEQ_ERROR | SIE_ACK_REC | SIE_STALL_REC | SIE_NAK_REC | SIE_RX_TIMEOUT |
    SIE_RX_OVERFLOW | SIE_BIT_STUFF_ERROR | SIE_CONNECTED | SIE_CRC_ERROR | SIE_BUS_RESET |
    SIE_TRANS_COMPLETE | SIE_SETUP_REC | SIE_RESUME;

// unused in the TS too
static_assert(SIE_VBUS_OVER_CURR && SIE_SPEED && SOFTCON && TO_EXTPHY && SE0 == 0 && K && SE1,
              "usb.ts constants");

// `this.rp2040.usbDPRAMView.getUint32(offset, true)` / `setUint32(offset, value, true)`:
// a DataView throws RangeError past the end.
static uint32_t dpramGetUint32(const std::vector<uint8_t> &dpram, uint32_t offset) {
  if (static_cast<size_t>(offset) + 4 > dpram.size()) {
    throw std::range_error("RangeError: Offset is outside the bounds of the DataView");
  }
  return loadLE32(&dpram[offset]);
}
static void dpramSetUint32(std::vector<uint8_t> &dpram, uint32_t offset, uint32_t value) {
  if (static_cast<size_t>(offset) + 4 > dpram.size()) {
    throw std::range_error("RangeError: Offset is outside the bounds of the DataView");
  }
  storeLE32(&dpram[offset], value);
}
// `usbDPRAM.slice(begin, end)`: clamped to the array.
static std::vector<uint8_t> dpramSlice(const std::vector<uint8_t> &dpram, size_t begin, size_t end) {
  begin = std::min(begin, dpram.size());
  end = std::min(end, dpram.size());
  if (end <= begin) {
    return {};
  }
  return std::vector<uint8_t>(dpram.begin() + static_cast<std::ptrdiff_t>(begin),
                              dpram.begin() + static_cast<std::ptrdiff_t>(end));
}
// `usbDPRAM.set(source.subarray(0, count), offset)`: TypedArray.set throws RangeError
// when the source does not fit.
static void dpramSet(std::vector<uint8_t> &dpram, const std::vector<uint8_t> &source, size_t count,
                     size_t offset) {
  count = std::min(count, source.size());
  if (count + offset > dpram.size()) {
    throw std::range_error("RangeError: offset is out of bounds");
  }
  std::copy(source.begin(), source.begin() + static_cast<std::ptrdiff_t>(count),
            dpram.begin() + static_cast<std::ptrdiff_t>(offset));
}

USBEndpointAlarm::USBEndpointAlarm(std::unique_ptr<IAlarm> alarm) : alarm(std::move(alarm)) {}

void USBEndpointAlarm::schedule(std::vector<uint8_t> buffer, double delayNanos) {
  buffers.push_back(std::move(buffer));
  alarm->schedule(delayNanos);
}

RPUSBController::RPUSBController(RP2040 &rp2040, const std::string &name) : BasePeripheral(rp2040, name) {
  // The TS passes an object literal with getters/setters over the private
  // fields and update() => ctl.checkInterrupts(): that is `hostRegs`.
  host = std::make_unique<USBHostController>(rp2040, hostRegs);
  IClock &clock = rp2040.clock;
  endpointReadAlarms.clear();
  endpointWriteAlarms.clear();
  for (uint32_t i = 0; i < ENDPOINT_COUNT; ++i) {
    endpointReadAlarms.push_back(std::make_unique<USBEndpointAlarm>(clock.createAlarm([this, i] {
      // `buffers.shift()`: undefined (skipped) only when empty; an empty Uint8Array is truthy
      auto &buffers = endpointReadAlarms[i]->buffers;
      if (!buffers.empty()) {
        std::vector<uint8_t> buffer = std::move(buffers.front());
        buffers.pop_front();
        finishRead(i, buffer);
      }
    })));
    endpointWriteAlarms.push_back(std::make_unique<USBEndpointAlarm>(clock.createAlarm([this, i] {
      // for-of over the live array: a buffer pushed by the callback is visited too
      auto &buffers = endpointWriteAlarms[i]->buffers;
      for (size_t k = 0; k < buffers.size(); ++k) {
        const std::vector<uint8_t> buffer = buffers[k];
        if (onEndpointWrite) onEndpointWrite(i, buffer);
      }
      endpointWriteAlarms[i]->buffers.clear();
    })));
  }
  resetAlarm = clock.createAlarm([this] {
    sieStatus |= SIE_BUS_RESET;
    sieStatusUpdated();
  });
}

bool RPUSBController::isHost() const { return !!(mainCtrl & HOST_NDEVICE); }

uint32_t RPUSBController::intStatus() const {
  const uint32_t raw = isHost() ? host->intRaw() : intRaw;
  return (raw & intEnable) | intForce;
}

void RPUSBController::attachDevice(USBHostDevice *device) { host->attach(device); }

void RPUSBController::detachDevice() { host->detach(); }

uint32_t RPUSBController::readUint32(uint32_t offset) {
  if (offset >= 0x04 && offset <= 0x3c) {
    return host->intEpAddr[(offset >> 2) - 1];
  }
  switch (offset) {
    case SOF_RD:
      return host->sofNumber;
    case SIE_CTRL:
      return sieCtrl;
    case INT_EP_CTRL:
      return host->intEpCtrl;
    case USB_PWR:
      return usbPwr;
    case ADDR_ENDP:
      return addrEndp & 0b1111000000001111111;
    case MAIN_CTRL:
      return mainCtrl;
    case SIE_STATUS:
      return sieStatus;
    case BUFF_STATUS:
      return buffStatus;
    case BUFF_CPU_SHOULD_HANDLE:
      return 0;
    case INTR:
      return intRaw;
    case INTE:
      return intEnable;
    case INTF:
      return intForce;
    case INTS:
      return intStatus();
  }
  return BasePeripheral::readUint32(offset);
}

void RPUSBController::writeUint32(uint32_t offset, uint32_t value) {
  if (offset >= 0x04 && offset <= 0x3c) {
    host->intEpAddr[(offset >> 2) - 1] = value;
    return;
  }
  switch (offset) {
    case SIE_CTRL:
      sieCtrl = isHost() ? host->sieCtrlWritten(value) : value;
      break;
    case INT_EP_CTRL:
      host->intEpCtrl = value & 0xfffe;
      break;
    case USB_PWR:
      usbPwr = value;
      break;
    case ADDR_ENDP:
      addrEndp = value;
      break;
    case MAIN_CTRL:
      mainCtrl = value & (SIM_TIMING | CONTROLLER_EN | HOST_NDEVICE);
      if (value & CONTROLLER_EN && !(value & HOST_NDEVICE)) {
        if (onUSBEnabled) onUSBEnabled();
      }
      break;
    case BUFF_STATUS:
      buffStatus &= ~rawWriteValue;
      buffStatusUpdated();
      break;
    case USB_MUXING:
      // Workaround for busy wait in hw_enumeration_fix_force_ls_j() / hw_enumeration_fix_finish():
      if (value & TO_DIGITAL_PAD && !(value & TO_PHY)) {
        sieStatus |= SIE_CONNECTED;
      }
      break;
    case SIE_STATUS:
      if (isHost()) {
        // writing the SPEED bits acknowledges a connect/disconnect
        if (rawWriteValue & SIE_STATUS_SPEED_MASK) {
          host->connChanged = false;
        }
        sieStatus &= ~(rawWriteValue & SIE_WRITECLEAR_MASK & ~SIE_CONNECTED);
        checkInterrupts();
        break;
      }
      sieStatus &= ~(rawWriteValue & SIE_WRITECLEAR_MASK);
      if (rawWriteValue & SIE_BUS_RESET) {
        if (onResetReceived) onResetReceived();
        sieStatus &= ~(SIE_LINE_STATE_MASK << SIE_LINE_STATE_SHIFT);
        sieStatus |= (SIELineState::J << SIE_LINE_STATE_SHIFT) | SIE_CONNECTED;
      }
      sieStatusUpdated();
      break;
    case INTE:
      intEnable = value & 0xfffff;
      checkInterrupts();
      break;
    case INTF:
      intForce = value & 0xfffff;
      checkInterrupts();
      break;

    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

uint32_t RPUSBController::readEndpointControlReg(uint32_t endpoint, bool out) {
  const uint32_t controlRegOffset = EP1_IN_CONTROL + 8 * (endpoint - 1) + (out ? 4 : 0);
  return dpramGetUint32(rp2040.usbDPRAM, controlRegOffset);
}

uint32_t RPUSBController::getEndpointBufferOffset(uint32_t endpoint, bool out) {
  if (endpoint == 0) {
    return 0x100;
  }
  return readEndpointControlReg(endpoint, out) & 0xffc0;
}

void RPUSBController::DPRAMUpdated(uint32_t offset, uint32_t value) {
  if (isHost()) {
    host->dpramWritten(offset);
    return;
  }
  if (value & USB_BUF_CTRL_AVAILABLE && offset >= EP0_IN_BUFFER_CONTROL &&
      offset <= EP15_OUT_BUFFER_CONTROL) {
    const uint32_t endpoint = (offset - EP0_IN_BUFFER_CONTROL) >> 3;
    const bool bufferOut = offset & 4 ? true : false;
    bool doubleBuffer = false;
    bool interrupt = true;
    if (endpoint != 0) {
      const uint32_t control = readEndpointControlReg(endpoint, bufferOut);
      doubleBuffer = !!(control & USB_CTRL_DOUBLE_BUF);
      interrupt = !!(control & USB_CTRL_INTERRUPT_PER_TRANSFER);
    }

    // `value >> USB_BUF1_SHIFT` is arithmetic in TS; only bits 16..25 are used
    if (doubleBuffer && (value >> USB_BUF1_SHIFT) & USB_BUF_CTRL_AVAILABLE) {
      const uint32_t bufferLength = (value >> USB_BUF1_SHIFT) & USB_BUF_CTRL_LEN_MASK;
      const uint32_t bufferOffset = getEndpointBufferOffset(endpoint, bufferOut) + USB_BUF1_OFFSET;
      debug("Start USB transfer, endPoint=" + std::to_string(endpoint) +
            ", direction=" + (bufferOut ? "out" : "in") + " buffer=" + toHex(bufferOffset) +
            " length=" + std::to_string(bufferLength));
      value &= ~(USB_BUF_CTRL_AVAILABLE << USB_BUF1_SHIFT);
      dpramSetUint32(rp2040.usbDPRAM, offset, value);
      if (bufferOut) {
        if (onEndpointRead) onEndpointRead(endpoint, bufferLength);
      } else {
        value &= ~(USB_BUF_CTRL_FULL << USB_BUF1_SHIFT);
        dpramSetUint32(rp2040.usbDPRAM, offset, value);
        std::vector<uint8_t> buffer =
            dpramSlice(rp2040.usbDPRAM, bufferOffset, static_cast<size_t>(bufferOffset) + bufferLength);
        indicateBufferReady(endpoint, false);
        endpointWriteAlarms[endpoint]->schedule(std::move(buffer), writeDelayMicroseconds * 1000);
      }
    }

    const uint32_t bufferLength = value & USB_BUF_CTRL_LEN_MASK;
    const uint32_t bufferOffset = getEndpointBufferOffset(endpoint, bufferOut);
    debug("Start USB transfer, endPoint=" + std::to_string(endpoint) +
          ", direction=" + (bufferOut ? "out" : "in") + " buffer=" + toHex(bufferOffset) +
          " length=" + std::to_string(bufferLength));
    value &= ~USB_BUF_CTRL_AVAILABLE;
    dpramSetUint32(rp2040.usbDPRAM, offset, value);
    if (bufferOut) {
      if (onEndpointRead) onEndpointRead(endpoint, bufferLength);
    } else {
      value &= ~USB_BUF_CTRL_FULL;
      dpramSetUint32(rp2040.usbDPRAM, offset, value);
      std::vector<uint8_t> buffer =
          dpramSlice(rp2040.usbDPRAM, bufferOffset, static_cast<size_t>(bufferOffset) + bufferLength);
      if (interrupt || !doubleBuffer) {
        indicateBufferReady(endpoint, false);
      }
      endpointWriteAlarms[endpoint]->schedule(std::move(buffer), writeDelayMicroseconds * 1000);
    }
  }
}

void RPUSBController::endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer) {
  endpointReadDone(endpoint, std::move(buffer), readDelayMicroseconds);
}

void RPUSBController::endpointReadDone(uint32_t endpoint, std::vector<uint8_t> buffer, double delay) {
  endpointReadAlarms[endpoint]->schedule(std::move(buffer), delay * 1000);
}

void RPUSBController::finishRead(uint32_t endpoint, const std::vector<uint8_t> &buffer) {
  const uint32_t bufferOffset = getEndpointBufferOffset(endpoint, true);
  const uint32_t bufControlReg = EP0_OUT_BUFFER_CONTROL + endpoint * 8;
  uint32_t bufControl = dpramGetUint32(rp2040.usbDPRAM, bufControlReg);
  const uint32_t requestedLength = bufControl & USB_BUF_CTRL_LEN_MASK;
  const uint32_t newLength = std::min(static_cast<uint32_t>(buffer.size()), requestedLength);
  bufControl |= USB_BUF_CTRL_FULL;
  bufControl = (bufControl & ~USB_BUF_CTRL_LEN_MASK) | (newLength & USB_BUF_CTRL_LEN_MASK);
  dpramSetUint32(rp2040.usbDPRAM, bufControlReg, bufControl);
  dpramSet(rp2040.usbDPRAM, buffer, newLength, bufferOffset);
  indicateBufferReady(endpoint, true);
}

void RPUSBController::checkInterrupts() {
  const uint32_t intStatus = this->intStatus();
  rp2040.setInterrupt(IRQ::USBCTRL, !!intStatus);
}

void RPUSBController::resetDevice() {
  resetAlarm->schedule(10'000'000);  // USB reset takes ~10ms
}

void RPUSBController::sendSetupPacket(const std::vector<uint8_t> &setupPacket) {
  dpramSet(rp2040.usbDPRAM, setupPacket, setupPacket.size(), 0);
  sieStatus |= SIE_SETUP_REC;
  sieStatusUpdated();
}

void RPUSBController::indicateBufferReady(uint32_t endpoint, bool out) {
  // endpoint 15 OUT is `1 << 31` (negative in TS): the same bit
  buffStatus |= jsShl(1, endpoint * 2 + (out ? 1 : 0));
  buffStatusUpdated();
}

void RPUSBController::buffStatusUpdated() {
  if (buffStatus) {
    intRaw |= INTR_BUFF_STATUS;
  } else {
    intRaw &= ~INTR_BUFF_STATUS;
  }
  checkInterrupts();
}

void RPUSBController::sieStatusUpdated() {
  static constexpr uint32_t intRegisterMap[][2] = {
      {SIE_SETUP_REC, 1 << 16},     {SIE_RESUME, 1 << 15},       {SIE_SUSPENDED, 1 << 14},
      {SIE_CONNECTED, 1 << 13},     {SIE_BUS_RESET, 1 << 12},    {SIE_VBUS_DETECTED, 1 << 11},
      {SIE_STALL_REC, 1 << 10},     {SIE_CRC_ERROR, 1 << 9},     {SIE_BIT_STUFF_ERROR, 1 << 8},
      {SIE_RX_OVERFLOW, 1 << 7},    {SIE_RX_TIMEOUT, 1 << 6},    {SIE_DATA_SEQ_ERROR, 1 << 5},
  };
  for (const auto &entry : intRegisterMap) {
    const uint32_t sieBit = entry[0], intRawBit = entry[1];
    if (sieStatus & sieBit) {
      intRaw |= intRawBit;
    } else {
      intRaw &= ~intRawBit;
    }
  }
  checkInterrupts();
}

}  // namespace rp2040js
