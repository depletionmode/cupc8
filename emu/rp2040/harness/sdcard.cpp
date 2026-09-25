// An SD card in SPI mode and its socket on an RP2040: see sdcard.h.
#include "sdcard.h"

#include <fcntl.h>
#include <unistd.h>

#include <algorithm>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>

#include "rp2040.h"

namespace rp2040js::harness {

// R1 bits (7.3.2.1)
static constexpr uint8_t R1_IDLE = 0x01, R1_ERASE_SEQ = 0x10, R1_ILLEGAL = 0x04, R1_CRC = 0x08,
                         R1_ADDRESS = 0x20, R1_PARAMETER = 0x40;
// R2's second byte (7.3.2.3)
static constexpr uint8_t R2_ERROR = 0x04, R2_WP_VIOLATION = 0x20, R2_OUT_OF_RANGE = 0x80;
// tokens (7.3.3)
static constexpr uint8_t START_BLOCK = 0xfe, START_MULTI_WRITE = 0xfc, STOP_TRAN = 0xfd;
static constexpr uint8_t DATA_ACCEPTED = 0x05, DATA_CRC_ERROR = 0x0b, DATA_WRITE_ERROR = 0x0d;
static constexpr uint8_t ERROR_TOKEN_OUT_OF_RANGE = 0x08;
static constexpr uint32_t FUNCTION_SPI = 1;

uint8_t sdCrc7(const uint8_t *p, size_t n) {
  uint8_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    uint8_t b = p[i];
    for (int j = 0; j < 8; j++) {
      crc = static_cast<uint8_t>(crc << 1);
      if ((b ^ crc) & 0x80) crc ^= 0x09;
      b = static_cast<uint8_t>(b << 1);
    }
  }
  return crc & 0x7f;
}

uint16_t sdCrc16(const uint8_t *p, size_t n) {
  uint16_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    crc ^= static_cast<uint16_t>(p[i] << 8);
    for (int j = 0; j < 8; j++) crc = static_cast<uint16_t>(crc & 0x8000 ? (crc << 1) ^ 0x1021 : crc << 1);
  }
  return crc;
}

// ------------------------------------------------------------ the card

SdCard::SdCard(std::vector<uint8_t> image, const Options &o) : data(std::move(image)), opt(o) {
  if (data.empty() || data.size() % 512) throw std::runtime_error("SdCard: the image must be a non-empty multiple of 512 bytes");
  if (opt.highCapacity && data.size() < 512 * 1024)
    throw std::runtime_error("SdCard: an SDHC image must be at least 512 KB (CSD 2.0 counts 512 KB units)");
  if (opt.ncr < 1 || opt.ncr > 8) throw std::runtime_error("SdCard: NCR is 1 to 8 bytes (7.5.4)");
  buildRegisters();
}

// a register's field [hi:lo], bit 127 the MSB of byte 0
static void putBits(std::vector<uint8_t> &r, int hi, int lo, uint64_t v) {
  for (int b = lo; b <= hi; b++)
    if ((v >> (b - lo)) & 1) r[15 - b / 8] |= static_cast<uint8_t>(1u << (b % 8));
}

void SdCard::buildRegisters() {
  csd_.assign(16, 0);
  const uint64_t size = data.size();
  if (opt.highCapacity) {  // CSD 2.0 (5.3.3)
    putBits(csd_, 127, 126, 1);
    putBits(csd_, 119, 112, 0x0e);   // TAAC 1.0 ms
    putBits(csd_, 103, 96, 0x32);    // TRAN_SPEED 25 MHz
    putBits(csd_, 95, 84, 0x5b5);    // CCC
    putBits(csd_, 83, 80, 9);        // READ_BL_LEN 512
    putBits(csd_, 69, 48, size / (512 * 1024) - 1);  // C_SIZE: (C_SIZE + 1) * 512 KB
  } else {  // CSD 1.0 (5.3.2): (C_SIZE + 1) * 2^(C_SIZE_MULT + 2) * 2^READ_BL_LEN, the largest that fits
    unsigned bl = 9, mult = 0;
    uint64_t cs = 0;
    for (unsigned b = 9; b <= 11 && !cs; b++)
      for (int m = 7; m >= 0; m--) {
        const uint64_t unit = (1ull << (m + 2)) << b;
        if (size / unit >= 1 && size / unit <= 4096) {
          bl = b, mult = static_cast<unsigned>(m), cs = size / unit;
          break;
        }
      }
    if (!cs) throw std::runtime_error("SdCard: an SDSC image must be 2 GB or less");
    putBits(csd_, 119, 112, 0x0e);
    putBits(csd_, 103, 96, 0x32);
    putBits(csd_, 95, 84, 0x5f5);
    putBits(csd_, 83, 80, bl);       // READ_BL_LEN
    putBits(csd_, 79, 79, 1);        // READ_BL_PARTIAL (always 1 on SDSC)
    putBits(csd_, 73, 62, cs - 1);   // C_SIZE
    putBits(csd_, 61, 50, 0xfff);    // VDD currents: the maxima
    putBits(csd_, 49, 47, mult);     // C_SIZE_MULT
  }
  putBits(csd_, 46, 46, 1);          // ERASE_BLK_EN
  putBits(csd_, 45, 39, 0x7f);       // SECTOR_SIZE
  putBits(csd_, 28, 26, 2);          // R2W_FACTOR
  putBits(csd_, 25, 22, 9);          // WRITE_BL_LEN 512
  putBits(csd_, 12, 12, opt.writeProtect ? 1 : 0);  // TMP_WRITE_PROTECT
  csd_[15] = static_cast<uint8_t>(sdCrc7(csd_.data(), 15) << 1 | 1);

  cid_.assign(16, 0);                // CID (5.2)
  putBits(cid_, 127, 120, 0xc8);     // MID
  putBits(cid_, 119, 104, ('C' << 8) | 'U');  // OID
  const char *pnm = "CUPC8";
  for (int i = 0; i < 5; i++) putBits(cid_, 103 - 8 * i, 96 - 8 * i, static_cast<uint8_t>(pnm[i]));
  putBits(cid_, 63, 56, 0x10);       // PRV 1.0
  putBits(cid_, 55, 24, 0x00c0ffee); // PSN
  putBits(cid_, 19, 8, (26 << 4) | 9);  // MDT 2026-09
  cid_[15] = static_cast<uint8_t>(sdCrc7(cid_.data(), 15) << 1 | 1);
}

void SdCard::violation(const std::string &what) {
  if (std::find(violations.begin(), violations.end(), what) == violations.end()) violations.push_back(what);
}

uint8_t SdCard::r1() const { return ready_ ? 0 : R1_IDLE; }

void SdCard::respond(std::initializer_list<uint8_t> r) {
  for (unsigned i = 0; i < opt.ncr; i++) out_.push_back(0xff);
  out_.insert(out_.end(), r.begin(), r.end());
}

// a block's byte offset from a read/write argument (7.2.3): SDHC block
// numbers, SDSC byte addresses; `err` the R1 bits if it is not allowed
bool SdCard::toOffset(uint32_t arg, uint64_t &offset, uint32_t len, uint8_t &err) const {
  offset = opt.highCapacity ? static_cast<uint64_t>(arg) * 512 : arg;
  if (offset + len > data.size()) {
    err = R1_PARAMETER;  // "the command's argument (e.g. address, block length) was outside the allowed range"
    return false;
  }
  // SDSC: READ_BLK_MISALIGN = 0, a partial block must stay within one physical block
  if (!opt.highCapacity && offset / 512 != (offset + len - 1) / 512) {
    err = R1_ADDRESS;
    return false;
  }
  return true;
}

void SdCard::settle(double now) {
  if (pw_.pending && now >= busyUntil_) {
    std::memcpy(data.data() + pw_.offset, pw_.bytes.data(), 512);
    pw_.pending = false;
    if (onWrite) onWrite(pw_.offset, 512);
  }
}

void SdCard::startRead(uint64_t offset, uint32_t len, double now) {
  addr_ = offset;
  readLen_ = len;
  pending_.clear();
  dataAt_ = now + opt.readNs;
}

// the next data block onto DO: a register, or a block of the image
void SdCard::queueBlock(double now) {
  const Tx was = tx_;
  tx_ = Tx::None;
  const std::vector<uint8_t> *src = &pending_;
  std::vector<uint8_t> block;
  if (pending_.empty()) {
    if (addr_ + readLen_ > data.size()) {  // a multiple-block read ran off the end (7.3.3.3)
      status2_ |= R2_OUT_OF_RANGE;
      out_.push_back(ERROR_TOKEN_OUT_OF_RANGE);
      return;
    }
    block.assign(data.begin() + static_cast<long>(addr_), data.begin() + static_cast<long>(addr_ + readLen_));
    src = &block;
    addr_ += readLen_;
    stats.blocksRead++;
    if (was == Tx::MultiRead) {
      tx_ = Tx::MultiRead;
      dataAt_ = now;  // the next block follows at once (a real card may insert NAC bytes)
    }
  }
  out_.push_back(START_BLOCK);
  out_.insert(out_.end(), src->begin(), src->end());
  const uint16_t crc = sdCrc16(src->data(), src->size());
  out_.push_back(static_cast<uint8_t>(crc >> 8));
  out_.push_back(static_cast<uint8_t>(crc));
  pending_.clear();
}

void SdCard::finishWriteBlock(double now) {
  rx_ = multiWrite_ ? Rx::WriteToken : Rx::Command;
  const uint16_t crc = static_cast<uint16_t>(wbuf_[512] << 8 | wbuf_[513]);
  if (crcOn_ && sdCrc16(wbuf_.data(), 512) != crc) {
    stats.crcErrors++;
    out_.push_back(DATA_CRC_ERROR);
    return;
  }
  if (opt.writeProtect) {
    status2_ |= R2_WP_VIOLATION;
    out_.push_back(DATA_WRITE_ERROR);
    return;
  }
  if (addr_ + 512 > data.size()) {  // a multiple-block write ran off the end
    status2_ |= R2_OUT_OF_RANGE;
    out_.push_back(DATA_WRITE_ERROR);
    return;
  }
  // programmed when the busy time is over (settle): power lost before then loses the block
  pw_.pending = true;
  pw_.offset = addr_;
  pw_.bytes.assign(wbuf_.begin(), wbuf_.begin() + 512);
  addr_ += 512;
  stats.blocksWritten++;
  out_.push_back(DATA_ACCEPTED);
  busyUntil_ = now + opt.writeNs;
  stats.busyNs += opt.writeNs;
}

void SdCard::reset() {
  ready_ = false;
  crcOn_ = false;
  app_ = false;
  cmd8Seen_ = false;
  hcs_ = false;
  initStart_ = -1;
  blockLen_ = 512;
  status2_ = 0;
  eraseStartSet_ = eraseEndSet_ = false;
  out_.clear();
  rx_ = Rx::Command;
  tx_ = Tx::None;
  pending_.clear();
  multiWrite_ = false;
}

uint8_t SdCard::exchange(uint8_t in, double now) {
  settle(now);
  // DO: a queued response or token, then data once its access time is up,
  // then $00 while programming, else released ($FF)
  uint8_t o = 0xff;
  if (out_.empty() && tx_ != Tx::None && now >= dataAt_) queueBlock(now);
  if (!out_.empty()) {
    o = out_.front();
    out_.pop_front();
  } else if (now < busyUntil_) {
    o = 0x00;
  }

  // DI
  switch (rx_) {
    case Rx::WriteData:
      wbuf_.push_back(in);
      if (wbuf_.size() == 514) finishWriteBlock(now);
      return o;
    case Rx::WriteToken:
      if (in == 0xff) return o;
      if (now < busyUntil_) {
        violation("a data token while the card was busy (it ignores DI until DO goes high, 7.2.4)");
        return o;
      }
      if (in == (multiWrite_ ? START_MULTI_WRITE : START_BLOCK)) {
        rx_ = Rx::WriteData;
        wbuf_.clear();
      } else if (multiWrite_ && in == STOP_TRAN) {
        rx_ = Rx::Command;
        multiWrite_ = false;
        out_.push_back(0xff);                 // Nbr, then busy (7.5.3)
        busyUntil_ = std::max(busyUntil_, now + 20e3);
      } else if ((in & 0xc0) == 0x40) {
        rx_ = Rx::Command;                    // a command instead of data: the write is over
        multiWrite_ = false;
        break;
      }
      return o;
    case Rx::Command:
      break;
  }
  if (cmd_.empty()) {
    if ((in & 0xc0) != 0x40) return o;        // no start bit: idle $FF (or anything else) is ignored
    if (spi_ && now < busyUntil_) {
      violation("a command while the card was busy (it ignores DI until DO goes high, 7.2.4)");
      return o;
    }
  }
  cmd_.push_back(in);
  if (cmd_.size() == 6) {
    execute(now);
    cmd_.clear();
  }
  return o;
}

void SdCard::execute(double now) {
  const uint8_t c = cmd_[0] & 0x3f;
  const uint32_t arg = static_cast<uint32_t>(cmd_[1]) << 24 | cmd_[2] << 16 | cmd_[3] << 8 | cmd_[4];
  const bool crcOk = static_cast<uint8_t>(sdCrc7(cmd_.data(), 5) << 1 | 1) == cmd_[5];
  stats.commands++;

  if (!spi_) {
    // still in SD mode: only CMD0 with CS low, and a correct CRC, is heard (7.2.1, 7.2.2)
    if (c != 0) return;
    if (!crcOk) {
      stats.crcErrors++;
      return;
    }
    if (powerClocks_ < 74) {
      violation("CMD0 before 74 clocks with CS high after power-up (6.4.1)");
      if (opt.strictPowerUp) return;
    }
    if (onCommand) onCommand(0, arg);
    spi_ = true;
    reset();
    respond({R1_IDLE});
    return;
  }

  // an ACMD is a command after CMD55; an index with no ACMD is the plain command (4.3.9)
  const bool acmd = app_ && (c == 13 || c == 23 || c == 41 || c == 51);
  app_ = false;
  if (onCommand) onCommand(acmd ? 64 + c : c, arg);

  out_.clear();
  tx_ = Tx::None;
  // in SPI mode CMD8's CRC is always checked, every other command's (CMD0's
  // too) only after CMD59 turned CRC on (7.2.2)
  if (!crcOk && (c == 8 || crcOn_)) {
    stats.crcErrors++;
    respond({static_cast<uint8_t>(r1() | R1_CRC)});
    return;
  }
  // "While repeating ACMD41, the host shall not issue another command except CMD0" (7.2.1)
  if (!ready_ && initStart_ >= 0 && !(c == 0 || c == 55 || (acmd && c == 41)))
    violation("CMD" + std::to_string(c) + " between ACMD41s before initialisation completed (7.2.1)");

  uint64_t offset = 0;
  uint8_t err = 0;
  if (acmd) {
    switch (c) {
      case 41: {  // SD_SEND_OP_COND (4.2.3.1): HCS is bit 30
        // HCS (bit 30) is looked at in the first ACMD41 only, and ignored
        // unless CMD8 came first; a high-capacity card then stays idle (7.2.1, 4.2.3.1)
        if (initStart_ < 0) {
          initStart_ = now;
          hcs_ = cmd8Seen_ && (arg & (1u << 30));
        }
        const bool can = !opt.highCapacity || hcs_;
        if (can && now - initStart_ >= opt.initNs) ready_ = true;
        respond({r1()});
        return;
      }
      case 13:  // SD_STATUS: R2, then a 64-byte block (4.10.2), all defaults here (1-bit bus)
        respond({r1(), status2_});
        status2_ = 0;
        pending_.assign(64, 0);
        tx_ = Tx::ReadData;
        dataAt_ = now;
        return;
      case 23:  // SET_WR_BLK_ERASE_COUNT: a hint for the next CMD25
        respond({r1()});
        return;
      case 51:  // SEND_SCR (5.6): SD_SPEC 2 with SD_SPEC3, security by capacity, 1- and 4-bit
        respond({r1()});
        pending_ = {0x02, static_cast<uint8_t>((opt.highCapacity ? 3 : 2) << 4 | 0x05), 0x80, 0, 0, 0, 0, 0};
        tx_ = Tx::ReadData;
        dataAt_ = now;
        return;
    }
  }
  switch (c) {
    case 0:  // GO_IDLE_STATE: back to idle, still in SPI mode
      reset();
      respond({R1_IDLE});
      return;
    case 8:  // SEND_IF_COND: R7 echoes the voltage (if 2.7-3.6 V) and the check pattern
      cmd8Seen_ = true;
      respond({r1(), 0x00, 0x00, static_cast<uint8_t>(((arg >> 8) & 0xf) == 1 ? 1 : 0), static_cast<uint8_t>(arg)});
      return;
    case 55:  // APP_CMD
      app_ = true;
      respond({r1()});
      return;
    case 58: {  // READ_OCR (5.1): bit 31 powered up, bit 30 CCS (valid once powered up), 2.7-3.6 V
      const uint32_t ocr = 0x00ff8000u | (ready_ ? 1u << 31 : 0) | (ready_ && opt.highCapacity ? 1u << 30 : 0);
      respond({r1(), static_cast<uint8_t>(ocr >> 24), static_cast<uint8_t>(ocr >> 16), static_cast<uint8_t>(ocr >> 8),
               static_cast<uint8_t>(ocr)});
      return;
    }
    case 59:  // CRC_ON_OFF
      crcOn_ = arg & 1;
      respond({r1()});
      return;
    case 9:   // SEND_CSD
    case 10:  // SEND_CID
      respond({r1()});
      pending_ = c == 9 ? csd_ : cid_;
      tx_ = Tx::ReadData;
      dataAt_ = now;
      return;
    case 13:  // SEND_STATUS: R2
      respond({r1(), status2_});
      status2_ = 0;
      return;
    case 16:  // SET_BLOCKLEN: SDHC blocks are 512 whatever is set (7.2.3)
      if (!opt.highCapacity) {
        if (arg == 0 || arg > 512) {
          respond({static_cast<uint8_t>(r1() | R1_PARAMETER)});
          return;
        }
        blockLen_ = arg;
      }
      respond({r1()});
      return;
    case 17:  // READ_SINGLE_BLOCK
    case 18:  // READ_MULTIPLE_BLOCK
      if (!toOffset(arg, offset, blockLen_, err)) {
        respond({static_cast<uint8_t>(r1() | err)});
        return;
      }
      respond({r1()});
      startRead(offset, blockLen_, now);
      tx_ = c == 17 ? Tx::ReadData : Tx::MultiRead;
      return;
    case 12: {  // STOP_TRANSMISSION: one stuff byte, then R1b (7.5.2.2)
      out_.push_back(0xff);
      respond({r1()});
      busyUntil_ = std::max(busyUntil_, now + 5e3);
      return;
    }
    case 24:  // WRITE_BLOCK
    case 25:  // WRITE_MULTIPLE_BLOCK
      if (!opt.highCapacity && blockLen_ != 512) {  // WRITE_BL_PARTIAL = 0
        respond({static_cast<uint8_t>(r1() | R1_PARAMETER)});
        return;
      }
      if (!toOffset(arg, offset, 512, err) || offset % 512) {
        respond({static_cast<uint8_t>(r1() | (err ? err : R1_ADDRESS))});
        return;
      }
      respond({r1()});
      addr_ = offset;
      multiWrite_ = c == 25;
      rx_ = Rx::WriteToken;
      return;
    case 32:  // ERASE_WR_BLK_START_ADDR
    case 33:  // ERASE_WR_BLK_END_ADDR
      if (!toOffset(arg, offset, 1, err)) {
        respond({static_cast<uint8_t>(r1() | err)});
        return;
      }
      (c == 32 ? eraseStart_ : eraseEnd_) = offset / 512;
      (c == 32 ? eraseStartSet_ : eraseEndSet_) = true;
      respond({r1()});
      return;
    case 38: {  // ERASE: R1b; erased blocks read $00 (SCR DATA_STAT_AFTER_ERASE = 0)
      if (!eraseStartSet_ || !eraseEndSet_ || eraseEnd_ < eraseStart_) {
        respond({static_cast<uint8_t>(r1() | R1_ERASE_SEQ)});
        return;
      }
      eraseStartSet_ = eraseEndSet_ = false;
      if (opt.writeProtect) {
        status2_ |= R2_WP_VIOLATION;
        respond({r1()});
        return;
      }
      std::fill(data.begin() + static_cast<long>(eraseStart_ * 512), data.begin() + static_cast<long>((eraseEnd_ + 1) * 512), 0);
      if (onWrite) onWrite(eraseStart_ * 512, (eraseEnd_ - eraseStart_ + 1) * 512);
      respond({r1()});
      busyUntil_ = std::max(busyUntil_, now + opt.eraseNs);
      return;
    }
    default:
      stats.illegal++;
      respond({static_cast<uint8_t>(r1() | R1_ILLEGAL)});
      return;
  }
}

void SdCard::deselect() {
  // DO is released; a partial command, a response not yet read, a block
  // being received or sent are dropped. Programming goes on (7.2.4), and a
  // multiple-block write may go on between blocks.
  cmd_.clear();
  out_.clear();
  tx_ = Tx::None;
  if (rx_ == Rx::WriteData) rx_ = multiWrite_ ? Rx::WriteToken : Rx::Command;
  if (rx_ == Rx::WriteToken && !multiWrite_) rx_ = Rx::Command;
}

void SdCard::clocksDeselected(unsigned n) {
  stats.deselectedClocks += n;
  if (powerClocks_ < 74) powerClocks_ += n;
}

void SdCard::noteClock(double hz) {
  stats.maxHz = std::max(stats.maxHz, hz);
  if (!ready_) {
    stats.maxHzBeforeInit = std::max(stats.maxHzBeforeInit, hz);
    if (hz > 400e3 * 1.0001) violation("SCK above 400 kHz before the card is initialised (4.2.1, 6.4.1)");
  }
  if (hz > 25e6 * 1.0001) violation("SCK above 25 MHz (TRAN_SPEED, default speed)");
}

void SdCard::noteFormat(unsigned mode, unsigned bits) {
  if (bits != 8) violation("SPI frames of " + std::to_string(bits) + " bits (the card counts bytes)");
  if (mode != 0 && mode != 3) violation("SPI mode " + std::to_string(mode) + " (SD samples on the rising edge: mode 0 or 3)");
}

// ------------------------------------------------------------ the socket

SdSocket::SdSocket(RP2040 &mcu_, Pins pins_) : mcu(mcu_), pins(pins_) {
  mcu.spi[pins.spi].onTransmit = [this](uint32_t v) { transmit(v); };
  done_ = mcu.clock.createAlarm([this] { mcu.spi[pins.spi].completeTransmit(miso_); });
  unlisten_ = mcu.gpio[pins.cs].addListener([this](GPIOPinState s, GPIOPinState) {
    if (s != GPIOPinState::Low && selected_) {
      selected_ = false;
      if (card_) card_->deselect();
    }
  });
  setDetect();
}

SdSocket::~SdSocket() {
  if (card_) card_->settle(mcu.clock.nanos());
  if (fd_ >= 0) ::close(fd_);
  if (unlisten_) unlisten_();
  mcu.spi[pins.spi].onTransmit = [this](uint32_t) { mcu.spi[pins.spi].completeTransmit(0); };
}

void SdSocket::insert(std::vector<uint8_t> image, const SdCard::Options &o) {
  remove();
  card_ = std::make_unique<SdCard>(std::move(image), o);
  selected_ = false;
  setDetect();
}

void SdSocket::insert(const std::string &image, const SdCard::Options &o) {
  std::ifstream in(image, std::ios::binary);
  if (!in) throw std::runtime_error("SdSocket: cannot read " + image);
  std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  insert(std::move(bytes), o);
  fd_ = ::open(image.c_str(), O_WRONLY);
  if (fd_ < 0) throw std::runtime_error("SdSocket: cannot write " + image);
  card_->onWrite = [this](uint64_t offset, size_t n) {
    if (::pwrite(fd_, card_->data.data() + offset, n, static_cast<off_t>(offset)) != static_cast<ssize_t>(n))
      throw std::runtime_error("SdSocket: writing the image failed");
  };
}

void SdSocket::remove() {
  if (card_) card_->settle(mcu.clock.nanos());  // a block still programming is lost
  card_.reset();
  if (fd_ >= 0) ::close(fd_);
  fd_ = -1;
  miso_ = 0xff;
  selected_ = false;
  setDetect();
}

void SdSocket::setDetect() { mcu.gpio[pins.detect].setInputValue(!card_); }

double SdSocket::sckHz() const { return mcu.spi[pins.spi].clockFrequency(); }

bool SdSocket::csSelected() {
  GPIOPin &p = mcu.gpio[pins.cs];
  if (p.functionSelect() == FUNCTION_SPI) {
    if (card_) card_->violation("nCS on SPI1's own CSn: it goes high between frames; drive it as a GPIO (7.2)");
    return false;
  }
  return p.outputEnable() && !p.outputValue();  // undriven: the 10k pull-up
}

void SdSocket::transmit(uint32_t value) {
  RPSPI &spi = mcu.spi[pins.spi];
  const double hz = spi.clockFrequency();
  const unsigned bits = spi.dataBits();
  uint8_t out = 0xff;  // DAT0's pull-up
  if (card_) {
    auto fn = [&](unsigned pin) { return mcu.gpio[pin].functionSelect(); };
    if (fn(pins.miso) != FUNCTION_SPI) card_->violation("MISO (GPIO" + std::to_string(pins.miso) + ") is not on SPI1");
    if (fn(pins.sck) == FUNCTION_SPI && fn(pins.mosi) == FUNCTION_SPI) {
      const uint32_t cr0 = spi.readUint32(0);  // SSPCR0: SPO bit 6, SPH bit 7
      card_->noteClock(hz);
      card_->noteFormat(((cr0 >> 6) & 1) << 1 | ((cr0 >> 7) & 1), bits);
      if (csSelected()) {
        selected_ = true;
        out = card_->exchange(static_cast<uint8_t>(value), mcu.clock.nanos());
      } else {
        if (selected_) {
          selected_ = false;
          card_->deselect();
        }
        card_->clocksDeselected(bits);
      }
    }
  }
  miso_ = out;
  // the frame takes its bits at the programmed SCK rate
  done_->schedule(hz > 0 ? bits * 1e9 / hz : 0);
}

}  // namespace rp2040js::harness
