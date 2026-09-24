// Port of rp2040js src/peripherals/ssi.ts
#include "ssi.h"

namespace rp2040js {

/* See RP2040 datasheet sect 4.10.13 */
static constexpr uint32_t SSI_CTRLR0 = 0x00000000;
static constexpr uint32_t SSI_CTRLR1 = 0x00000004;
static constexpr uint32_t SSI_SSIENR = 0x00000008;
[[maybe_unused]] static constexpr uint32_t SSI_MWCR = 0x0000000c;
[[maybe_unused]] static constexpr uint32_t SSI_SER = 0x00000010;
static constexpr uint32_t SSI_BAUDR = 0x00000014;
[[maybe_unused]] static constexpr uint32_t SSI_TXFTLR = 0x00000018;
[[maybe_unused]] static constexpr uint32_t SSI_RXFTLR = 0x0000001c;
static constexpr uint32_t SSI_TXFLR = 0x00000020;
static constexpr uint32_t SSI_RXFLR = 0x00000024;
static constexpr uint32_t SSI_SR = 0x00000028;
static constexpr uint32_t SSI_SR_TFNF_BITS = 0x00000002;
static constexpr uint32_t SSI_SR_TFE_BITS = 0x00000004;
static constexpr uint32_t SSI_SR_RFNE_BITS = 0x00000008;
[[maybe_unused]] static constexpr uint32_t SSI_IMR = 0x0000002c;
[[maybe_unused]] static constexpr uint32_t SSI_ISR = 0x00000030;
[[maybe_unused]] static constexpr uint32_t SSI_RISR = 0x00000034;
[[maybe_unused]] static constexpr uint32_t SSI_TXOICR = 0x00000038;
[[maybe_unused]] static constexpr uint32_t SSI_RXOICR = 0x0000003c;
[[maybe_unused]] static constexpr uint32_t SSI_RXUICR = 0x00000040;
[[maybe_unused]] static constexpr uint32_t SSI_MSTICR = 0x00000044;
[[maybe_unused]] static constexpr uint32_t SSI_ICR = 0x00000048;
[[maybe_unused]] static constexpr uint32_t SSI_DMACR = 0x0000004c;
[[maybe_unused]] static constexpr uint32_t SSI_DMATDLR = 0x00000050;
[[maybe_unused]] static constexpr uint32_t SSI_DMARDLR = 0x00000054;
/** Identification register */
static constexpr uint32_t SSI_IDR = 0x00000058;
static constexpr uint32_t SSI_VERSION_ID = 0x0000005c;
static constexpr uint32_t SSI_DR0 = 0x00000060;
static constexpr uint32_t SSI_RX_SAMPLE_DLY = 0x000000f0;
static constexpr uint32_t SSI_SPI_CTRL_R0 = 0x000000f4;
static constexpr uint32_t SSI_TXD_DRIVE_EDGE = 0x000000f8;

static constexpr uint32_t CMD_READ_STATUS = 0x05;

uint32_t RPSSI::readUint32(uint32_t offset) {
  switch (offset) {
    case SSI_TXFLR:
      return txflr;
    case SSI_RXFLR:
      return rxflr;
    case SSI_CTRLR0:
      return crtlr0; /*  & 0x017FFFFF = b23,b25..31 reserved */
    case SSI_CTRLR1:
      return crtlr1;
    case SSI_SSIENR:
      return ssienr;
    case SSI_BAUDR:
      return baudr;
    case SSI_SR:
      return SSI_SR_TFE_BITS | SSI_SR_RFNE_BITS | SSI_SR_TFNF_BITS;
    case SSI_IDR:
      return 0x51535049;
    case SSI_VERSION_ID:
      return 0x3430312a;
    case SSI_RX_SAMPLE_DLY:
      return rxsampldly;
    case SSI_TXD_DRIVE_EDGE:
      return txddriveedge;
    case SSI_SPI_CTRL_R0:
      return spictlr0; /* b6,7,10,19..23 reserved */
    case SSI_DR0:
      return dr0;
  }
  return BasePeripheral::readUint32(offset);
}

void RPSSI::writeUint32(uint32_t offset, uint32_t value) {
  switch (offset) {
    case SSI_TXFLR:
      txflr = value;
      return;
    case SSI_RXFLR:
      rxflr = value;
      return;
    case SSI_CTRLR0:
      crtlr0 = value; /*  & 0x017FFFFF = b23,b25..31 reserved */
      return;
    case SSI_CTRLR1:
      crtlr1 = value;
      return;
    case SSI_SSIENR:
      ssienr = value;
      return;
    case SSI_BAUDR:
      baudr = value;
      return;
    case SSI_RX_SAMPLE_DLY:
      rxsampldly = value & 0xff;
      return;
    case SSI_TXD_DRIVE_EDGE:
      txddriveedge = value & 0xff;
      return;
    case SSI_SPI_CTRL_R0:
      spictlr0 = value;
      return;
    case SSI_DR0:
      if (value == CMD_READ_STATUS) {
        dr0 = 0;  // tell stage2 that we completed a write
      }
      return;
    default:
      BasePeripheral::writeUint32(offset, value);
  }
}

}  // namespace rp2040js
