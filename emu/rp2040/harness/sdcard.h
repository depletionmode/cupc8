// An SD memory card in SPI mode, and the socket that attaches it to an
// emulated RP2040's SPI1 (the storage card, doc/hardware/storage-card.md).
// Not a port of rp2040js: a test-bench device, like slothost.h.
//
// SdCard is the card: the SPI-mode protocol of the SD Physical Layer
// Simplified Specification ("PLSS"; section numbers are Version 6.00's, the
// text it was checked against; chapter 7 is unchanged in later versions), a
// byte at a time, against the emulated time, backed by a disk image in
// memory. SdSocket plugs a card into the chip: it answers SPI1's transfers
// (RPSPI::onTransmit) after the byte's real duration at the programmed SCK
// rate, reads nCS from its GPIO, and drives the socket's card-detect switch.
// Everything runs on the chip's own clock, so it is as deterministic as the
// rest of the emulator and needs no thread of its own.
//
// What the card does, and where the spec says so:
//   - power-up: 74 clocks with CS high before the first command (6.4.1.1);
//     CMD0 with CS low enters SPI mode; the card is still in SD mode when it
//     arrives, so its CRC must be right, and anything else is ignored (7.2.1,
//     7.2.2)
//   - CRC: in SPI mode, CMD8's CRC is always checked, every other command's
//     (CMD0's too) and written data's only after CMD59 turns CRC on; an error
//     gives R1 "com crc error" whatever the command (7.2.2). Read data always
//     carries a correct CRC16 (4.5)
//   - initialisation (7.2.1, figure 7-2, 4.2.3.1): CMD8 R7 echo (7.3.2.6);
//     ACMD41 answers "in idle state" until `initNs` after the first one. HCS
//     is taken from the first ACMD41 only, and ignored if CMD8 did not come
//     first, so a high-capacity card then never leaves idle. All commands
//     are available in SPI mode (7.2.1)
//   - responses R1, R1b, R2, R3, R7 (7.3.2) after `ncr` bytes of $FF (NCR:
//     0 to 8 bytes in the full spec; the simplified 7.5 is blank)
//   - CMD9/CMD10 as 16-byte data blocks (7.2.6; CSD 1.0 or 2.0, 5.3.2/5.3.3;
//     CID, 5.2), CMD13 (R2), CMD16 (SDSC only; SDHC blocks stay 512, 7.2.3),
//     CMD17/18 reads after `readNs` of access time (4.6.2.1), CMD12 (one
//     stuff byte, then R1b, as cards do), CMD24/25 writes with the start and
//     stop tokens (7.3.3.2) and data response tokens (7.3.3.1), ACMD23,
//     ACMD13 (SD status, 4.10.2), ACMD51 (SCR, 5.6), CMD32/33/38 erase,
//     CMD58 (OCR with CCS, 5.1)
//   - programming busy after each written block (`writeNs`; up to 250 ms on
//     SDHC, 4.6.2.2), a stream of $00 on DO while CS is low (7.2.4, 7.3.2.2);
//     deselecting does not stop it. The block is in the image only when the
//     busy time is over: pulling the card before then loses it
//   - write protection: CSD TMP_WRITE_PROTECT set (5.3); a written block gets
//     the "write error" data response and WP_VIOLATION in R2 (7.3.3.1,
//     7.3.2.3; a microSD socket has no mechanical switch)
//   - addresses: SDHC takes block numbers, SDSC byte addresses (7.2.3);
//     beyond the end is a parameter error, a misaligned SDSC write an
//     address error (7.3.2.1), and a multiple-block read that runs off the
//     end ends with the data error token "out of range" (7.3.3.3)
// Not modelled: CMD6 (high speed), the lock/unlock and security commands,
// CMD1 (illegal: the firmware must use ACMD41), version 1.x cards, CRC
// errors on the line (the emulated wire does not corrupt bits). An SDHC
// image may be smaller than the 2 GB a real SDHC card has (C_SIZE >= 4112,
// 5.3.3), so tests can use small images with block addressing.
//
// Host mistakes that a real card may or may not tolerate are recorded in
// `violations` (the card still does what the spec says): SCK above fOD (400
// kHz) before initialisation is done (4.2, 4.3) or above 25 MHz (TRAN_SPEED
// $32, 5.3), an SPI mode other than 0 or 3 or a frame other than 8 bits, a
// command other than CMD0/CMD55/ACMD41 between ACMD41s (7.2.1), a command
// while the card is busy, SPI1's own CSn on nCS (the PL022 raises it between
// frames, but CS must stay low for a whole transaction), MISO not on SPI1,
// and too few power-up clocks.
#pragma once

#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "clock/clock.h"

namespace rp2040js {
class RP2040;
}

namespace rp2040js::harness {

uint8_t sdCrc7(const uint8_t *p, size_t n);          // the command/register CRC (4.5), unshifted
uint16_t sdCrc16(const uint8_t *p, size_t n);        // the data CRC, CCITT x^16+x^12+x^5+1 (4.5)

class SdCard {
 public:
  struct Options {
    bool highCapacity = true;   // SDHC (CCS=1, block addresses, CSD 2.0) or SDSC (byte addresses, CSD 1.0)
    double initNs = 5e6;        // ACMD41 answers "idle" until this long after the first one (4.2.3: < 1 s)
    double readNs = 100e3;      // access time: a read command to its data token (NAC, 4.6.2.1)
    double writeNs = 1e6;       // programming busy after each written block (4.6.2.2: the host allows 250 ms)
    double eraseNs = 2e6;       // CMD38 busy
    unsigned ncr = 1;           // $FF bytes between a command and its response (NCR: 1..8)
    bool writeProtect = false;  // CSD TMP_WRITE_PROTECT (5.3): writes fail
    bool strictPowerUp = true;  // ignore CMD0 until 74 clocks with CS high (6.4.1.1)
  };
  struct Stats {
    uint64_t commands = 0, blocksRead = 0, blocksWritten = 0, crcErrors = 0, illegal = 0;
    uint64_t deselectedClocks = 0;
    double busyNs = 0;          // total programming time
    double maxHz = 0, maxHzBeforeInit = 0;
  };

  std::vector<uint8_t> data;    // the image (a multiple of 512 bytes)
  Options opt;
  Stats stats;
  std::vector<std::string> violations;
  /** called after blocks change: byte offset and length in `data` */
  std::function<void(uint64_t offset, size_t n)> onWrite;
  /** each command as it is taken: index (ACMD: 64 + index), argument */
  std::function<void(unsigned cmd, uint32_t arg)> onCommand;

  SdCard(std::vector<uint8_t> image, const Options &o);

  /** one byte each way while CS is low: `in` is what the host clocked out at
   * time `now` (ns); the result is the card's DO for that byte */
  uint8_t exchange(uint8_t in, double now);
  /** CS went high (the card releases DO, a partial command is dropped) */
  void deselect();
  /** 8 clocks with CS high */
  void clocksDeselected(unsigned n);
  /** the host's SCK rate for the byte about to be exchanged (checks only) */
  void noteClock(double hz);
  /** how the host's SPI is set up (checks only): SPI mode 0..3, bits per frame */
  void noteFormat(unsigned mode, unsigned bits);

  /** a written block is programmed when its busy time ends: store it if that has passed */
  void settle(double now);
  /** record a host mistake (once) */
  void violation(const std::string &what);

  bool initialised() const { return ready_; }
  bool spiMode() const { return spi_; }
  bool busy(double now) const { return now < busyUntil_; }
  uint64_t blocks() const { return data.size() / 512; }
  const std::vector<uint8_t> &csd() const { return csd_; }
  const std::vector<uint8_t> &cid() const { return cid_; }

 private:
  enum class Rx { Command, WriteToken, WriteData };
  enum class Tx { None, ReadData, MultiRead };
  bool spi_ = false, ready_ = false, crcOn_ = false, app_ = false, cmd8Seen_ = false, hcs_ = false;
  double initStart_ = -1, busyUntil_ = 0, dataAt_ = 0;
  unsigned powerClocks_ = 0;
  uint32_t blockLen_ = 512;
  uint8_t status2_ = 0;                     // R2's second byte (clear on read)
  uint32_t eraseStart_ = 0, eraseEnd_ = 0;
  bool eraseStartSet_ = false, eraseEndSet_ = false;
  std::vector<uint8_t> cmd_;                // the command being received
  std::deque<uint8_t> out_;                 // bytes queued for DO
  Rx rx_ = Rx::Command;
  Tx tx_ = Tx::None;
  std::vector<uint8_t> pending_;            // a register or block to send after dataAt_
  uint64_t addr_ = 0;                       // next block's byte offset (reads and writes)
  uint32_t readLen_ = 512;
  struct {
    bool pending = false;
    uint64_t offset = 0;
    std::vector<uint8_t> bytes;
  } pw_;                                    // the block being programmed
  bool multiWrite_ = false;
  std::vector<uint8_t> wbuf_;
  std::vector<uint8_t> csd_, cid_;

  void execute(double now);
  void respond(std::initializer_list<uint8_t> r);
  uint8_t r1() const;
  void startRead(uint64_t offset, uint32_t len, double now);
  void queueBlock(double now);
  void finishWriteBlock(double now);
  bool toOffset(uint32_t arg, uint64_t &offset, uint32_t len, uint8_t &err) const;
  void buildRegisters();
  void reset();
};

/** The socket on an RP2040: SPI1 on SCK 14, MOSI 15, MISO 12, nCS 13 (a SIO
 * output), card detect on 17 (low = card in), as on the storage card
 * (hw/pins.yaml storage_mcu). An image file backs the card: written blocks
 * go straight through to it, so a host FAT reader sees them at once. */
class SdSocket {
 public:
  struct Pins {
    unsigned spi = 1, sck = 14, mosi = 15, miso = 12, cs = 13, detect = 17;
  };
  SdSocket(RP2040 &mcu, Pins pins);
  explicit SdSocket(RP2040 &mcu) : SdSocket(mcu, Pins{}) {}
  ~SdSocket();
  SdSocket(const SdSocket &) = delete;
  SdSocket &operator=(const SdSocket &) = delete;

  /** push a card in, backed by `image` (read now, written through on every write) */
  void insert(const std::string &image, const SdCard::Options &o);
  /** a card with no file behind it (unit tests) */
  void insert(std::vector<uint8_t> image, const SdCard::Options &o);
  /** pull it out: power is gone at once, a transfer in flight reads $FF */
  void remove();
  SdCard *card() { return card_.get(); }
  /** the SCK rate SPI1 is set to (Hz) */
  double sckHz() const;

 private:
  RP2040 &mcu;
  Pins pins;
  std::unique_ptr<SdCard> card_;
  int fd_ = -1;
  std::unique_ptr<IAlarm> done_;
  uint8_t miso_ = 0xff;
  bool selected_ = false;
  std::function<void()> unlisten_;
  bool csSelected();
  void transmit(uint32_t value);
  void setDetect();
};

}  // namespace rp2040js::harness
