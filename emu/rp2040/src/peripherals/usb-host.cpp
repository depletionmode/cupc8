// Port of rp2040js src/peripherals/usb-host.ts (cupc8 patch: host mode)
#include "usb-host.h"

#include <algorithm>
#include <stdexcept>
#include <utility>

#include "../rp2040.h"
#include "../utils/js.h"

namespace rp2040js {

// host DPRAM layout (usb_host_dpram_t)
static constexpr uint32_t SETUP_PACKET = 0x000;
static constexpr uint32_t INT_EP_CTRL = 0x008;  // + 8 * n, n = 0..14 for interrupt endpoint n + 1
static constexpr uint32_t EPX_BUF_CTRL = 0x080;
static constexpr uint32_t INT_EP_BUF_CTRL = 0x088;  // + 8 * n
static constexpr uint32_t EPX_CTRL = 0x100;

// buffer control (per 16-bit half)
static constexpr uint32_t BUF_FULL = 1 << 15;
static constexpr uint32_t BUF_LAST = 1 << 14;
static constexpr uint32_t BUF_AVAILABLE = 1 << 10;
static constexpr uint32_t BUF_LEN_MASK = 0x3ff;

// endpoint control
static constexpr uint32_t EP_DOUBLE_BUF = 1 << 30;
static constexpr uint32_t EP_INT_PER_BUF = 1 << 29;
static constexpr uint32_t EP_INT_PER_DOUBLE_BUF = 1 << 28;
static constexpr uint32_t EP_INTERVAL_SHIFT = 16;
static constexpr uint32_t EP_INTERVAL_MASK = 0x3ff;
static constexpr uint32_t EP_BUF_ADDR_MASK = 0xffc0;

// SIE_CTRL (SIE_CTRL_START_TRANS and SIE_CTRL_RESET_BUS are in the header)
static constexpr uint32_t SIE_CTRL_SEND_SETUP = 1 << 1;
static constexpr uint32_t SIE_CTRL_RECEIVE_DATA = 1 << 3;

// SIE_STATUS (SIE_STATUS_SPEED_SHIFT / _MASK are in the header)
static constexpr uint32_t SIE_STATUS_TRANS_COMPLETE = 1 << 18;
static constexpr uint32_t SIE_STATUS_STALL_REC = 1 << 29;
static constexpr uint32_t SIE_STATUS_ACK_REC = 1 << 30;
static constexpr uint32_t SIE_STATUS_RX_TIMEOUT = 1 << 27;

// INTR bits (host)
static constexpr uint32_t INTR_HOST_CONN_DIS = 1 << 0;
static constexpr uint32_t INTR_TRANS_COMPLETE = 1 << 3;
static constexpr uint32_t INTR_BUFF_STATUS = 1 << 4;
static constexpr uint32_t INTR_ERROR_DATA_SEQ = 1 << 5;
static constexpr uint32_t INTR_ERROR_RX_TIMEOUT = 1 << 6;
static constexpr uint32_t INTR_STALL = 1 << 10;

static constexpr double PACKET_NANOS = 20'000;  // one transaction, roughly, at 12 Mb/s with overhead
static constexpr double NAK_RETRY_NANOS = 125'000;
static constexpr double FRAME_NANOS = 1'000'000;

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
// `usbDPRAM.set(r.subarray(0, len), offset)`: TypedArray.set throws RangeError
// when the source does not fit.
static void dpramSet(std::vector<uint8_t> &dpram, const std::vector<uint8_t> &source, size_t len,
                     size_t offset) {
  const size_t count = std::min(len, source.size());
  if (count + offset > dpram.size()) {
    throw std::range_error("RangeError: offset is out of bounds");
  }
  std::copy(source.begin(), source.begin() + static_cast<std::ptrdiff_t>(count),
            dpram.begin() + static_cast<std::ptrdiff_t>(offset));
}

USBHostController::USBHostController(RP2040 &rp2040, USBHostRegs &regs) : rp2040(rp2040), regs(regs) {
  epxAlarm = rp2040.clock.createAlarm([this] { epxService(); });
  setupAlarm = rp2040.clock.createAlarm([this] {
    std::function<void()> done = std::move(setupDone);
    setupDone = nullptr;
    if (done) done();
  });
  frameAlarm = rp2040.clock.createAlarm([this] { frame(); });
}

uint8_t *USBHostController::dpram() { return rp2040.usbDPRAM.data(); }

void USBHostController::attach(USBHostDevice *device) {
  this->device = device;
  setSpeed(device->speed());
  frameAlarm->schedule(FRAME_NANOS);
}

void USBHostController::detach() {
  device = nullptr;
  epxActive = false;
  setSpeed(0);
}

void USBHostController::setSpeed(uint32_t speed) {
  regs.setSieStatus((regs.sieStatus() & ~SIE_STATUS_SPEED_MASK) | (speed << SIE_STATUS_SPEED_SHIFT));
  connChanged = true;
  regs.update();
}

uint32_t USBHostController::intRaw() const {
  const uint32_t s = regs.sieStatus();
  return (connChanged ? INTR_HOST_CONN_DIS : 0) |
         (s & SIE_STATUS_TRANS_COMPLETE ? INTR_TRANS_COMPLETE : 0) |
         (regs.buffStatus() ? INTR_BUFF_STATUS : 0) | (s & (1u << 31) ? INTR_ERROR_DATA_SEQ : 0) |
         (s & SIE_STATUS_RX_TIMEOUT ? INTR_ERROR_RX_TIMEOUT : 0) |
         (s & SIE_STATUS_STALL_REC ? INTR_STALL : 0);
}

/** SIE_CTRL written: returns the value it keeps (START_TRANS and RESET_BUS clear themselves) */
uint32_t USBHostController::sieCtrlWritten(uint32_t value) {
  if (value & SIE_CTRL_RESET_BUS) {
    if (device) device->busReset();
  }
  if (value & SIE_CTRL_START_TRANS) {
    const uint32_t addr = regs.addrEndp() & 0x7f;
    const uint32_t ep = (regs.addrEndp() >> 16) & 0xf;
    if (value & SIE_CTRL_SEND_SETUP) {
      epxActive = false;
      std::vector<uint8_t> packet = dpramSlice(rp2040.usbDPRAM, SETUP_PACKET, SETUP_PACKET + 8);
      later([this, addr, packet] {
        if (!device) {
          status(SIE_STATUS_RX_TIMEOUT);
        } else if (device->setup(addr, packet) == USBHostDevice::Handshake::stall) {
          status(SIE_STATUS_STALL_REC);
        } else {
          status(SIE_STATUS_TRANS_COMPLETE | SIE_STATUS_ACK_REC);
        }
      });
    } else {
      epxActive = true;
      epxIn = !!(value & SIE_CTRL_RECEIVE_DATA);
      epxBuf = 0;
      epxAddr = addr;
      epxEp = ep;
      epxAlarm->schedule(PACKET_NANOS);
    }
  }
  return value & ~(SIE_CTRL_START_TRANS | SIE_CTRL_RESET_BUS);
}

/** a DPRAM word was written */
void USBHostController::dpramWritten(uint32_t offset) {
  if (offset == EPX_BUF_CTRL && epxActive) {
    epxAlarm->schedule(PACKET_NANOS);
  }
}

void USBHostController::later(std::function<void()> fn) {
  setupDone = std::move(fn);
  setupAlarm->schedule(PACKET_NANOS);
}

void USBHostController::status(uint32_t bits) {
  regs.setSieStatus(regs.sieStatus() | bits);
  regs.update();
}

void USBHostController::bufferDone(uint32_t bit) {
  regs.setBuffStatus(regs.buffStatus() | bit);
  regs.update();
}

// One packet on EPX, into or out of the buffer half that is available.
void USBHostController::epxService() {
  if (!epxActive || !device) {
    return;
  }
  const uint32_t ctrl = loadLE32(dpram() + EPX_CTRL);
  const bool double_ = !!(ctrl & EP_DOUBLE_BUF);
  const uint32_t half = double_ ? epxBuf : 0;
  const uint32_t shift = half ? 16 : 0;
  const uint32_t all = loadLE32(dpram() + EPX_BUF_CTRL);
  uint32_t buf = (all >> shift) & 0xffff;
  if (!(buf & BUF_AVAILABLE)) {
    return;  // wait for the CPU to hand over the buffer
  }
  const uint32_t len = buf & BUF_LEN_MASK;
  const uint32_t data = (ctrl & EP_BUF_ADDR_MASK) + half * 64;
  bool short_ = false;
  if (epxIn) {
    const USBHostDevice::InResult r = device->in(epxAddr, epxEp, len);
    if (r.handshake == USBHostDevice::Handshake::nak) {
      epxAlarm->schedule(NAK_RETRY_NANOS);
      return;
    }
    if (r.handshake == USBHostDevice::Handshake::stall) {
      epxActive = false;
      status(SIE_STATUS_STALL_REC);
      return;
    }
    dpramSet(rp2040.usbDPRAM, r.data, len, data);
    short_ = r.data.size() < len;
    buf = (buf & ~(BUF_AVAILABLE | BUF_LEN_MASK)) | BUF_FULL |
          std::min(static_cast<uint32_t>(r.data.size()), len);
  } else {
    const USBHostDevice::Handshake r =
        device->out(epxAddr, epxEp, dpramSlice(rp2040.usbDPRAM, data, static_cast<size_t>(data) + len));
    if (r == USBHostDevice::Handshake::nak) {
      epxAlarm->schedule(NAK_RETRY_NANOS);
      return;
    }
    if (r == USBHostDevice::Handshake::stall) {
      epxActive = false;
      status(SIE_STATUS_STALL_REC);
      return;
    }
    buf &= ~(BUF_AVAILABLE | BUF_FULL);
  }
  const bool last = !!(buf & BUF_LAST) || short_;
  const uint32_t mask = 0xffffu << shift;
  storeLE32(dpram() + EPX_BUF_CTRL, (all & ~mask) | (buf << shift));
  if (last) {
    epxActive = false;
  }
  // per double buffer: one BUFF_STATUS after both halves (or a short/last first half)
  const bool perDouble = double_ && !!(ctrl & EP_INT_PER_DOUBLE_BUF) && !(ctrl & EP_INT_PER_BUF);
  if (!perDouble || half == 1 || last) {
    bufferDone(1);
  }
  if (last) {
    status(SIE_STATUS_TRANS_COMPLETE);
    return;
  }
  if (double_) {
    epxBuf ^= 1;
  }
  epxAlarm->schedule(PACKET_NANOS);
}

// A 1 ms frame: poll the interrupt endpoints that are due.
void USBHostController::frame() {
  if (!device) {
    return;
  }
  sofNumber = (sofNumber + 1) & 0x7ff;
  for (uint32_t n = 0; n < 15; n++) {
    if (!(intEpCtrl & (1u << (n + 1)))) {
      continue;
    }
    const uint32_t ctrl = loadLE32(dpram() + INT_EP_CTRL + 8 * n);
    const uint32_t interval = ((ctrl >> EP_INTERVAL_SHIFT) & EP_INTERVAL_MASK) + 1;
    // `++this.intEpPollDue[n] < interval`: the expression is old + 1 before the
    // Uint32Array wraps it (unreachable: 2^32 frames)
    if (static_cast<double>(intEpPollDue[n]) + 1 < interval) {
      ++intEpPollDue[n];
      continue;
    }
    ++intEpPollDue[n];
    intEpPollDue[n] = 0;
    uint32_t buf = loadLE32(dpram() + INT_EP_BUF_CTRL + 8 * n);
    if (!(buf & BUF_AVAILABLE)) {
      continue;
    }
    const uint32_t addr = intEpAddr[n] & 0x7f;
    const uint32_t ep = (intEpAddr[n] >> 16) & 0xf;
    const bool out = !!(intEpAddr[n] & (1 << 25));
    const uint32_t len = buf & BUF_LEN_MASK;
    const uint32_t data = ctrl & EP_BUF_ADDR_MASK;
    if (out) {
      const USBHostDevice::Handshake r =
          device->out(addr, ep, dpramSlice(rp2040.usbDPRAM, data, static_cast<size_t>(data) + len));
      if (r != USBHostDevice::Handshake::ack) continue;
      buf &= ~(BUF_AVAILABLE | BUF_FULL);
      storeLE32(dpram() + INT_EP_BUF_CTRL + 8 * n, buf);
      // n = 14: `1 << 31` (negative in TS), the same bit
      bufferDone(1u << (2 * (n + 1) + 1));
    } else {
      const USBHostDevice::InResult r = device->in(addr, ep, len);
      if (r.handshake == USBHostDevice::Handshake::nak || r.handshake == USBHostDevice::Handshake::stall)
        continue;
      dpramSet(rp2040.usbDPRAM, r.data, len, data);
      buf = (buf & ~(BUF_AVAILABLE | BUF_LEN_MASK)) | BUF_FULL |
            std::min(static_cast<uint32_t>(r.data.size()), len);
      storeLE32(dpram() + INT_EP_BUF_CTRL + 8 * n, buf);
      bufferDone(1u << (2 * (n + 1)));
    }
  }
  frameAlarm->schedule(FRAME_NANOS);
}

}  // namespace rp2040js
