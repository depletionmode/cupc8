// `enum DREQChannel` from rp2040js src/peripherals/dma.ts, split out so that
// uart/spi/pio/adc need not include the DMA header. Unscoped (the names are
// prefixed) so a DREQChannel is a plain number as in TS.
#pragma once

#include <cstdint>

namespace rp2040js {

enum DREQChannel : uint32_t {
  DREQ_PIO0_TX0,
  DREQ_PIO0_TX1,
  DREQ_PIO0_TX2,
  DREQ_PIO0_TX3,
  DREQ_PIO0_RX0,
  DREQ_PIO0_RX1,
  DREQ_PIO0_RX2,
  DREQ_PIO0_RX3,
  DREQ_PIO1_TX0,
  DREQ_PIO1_TX1,
  DREQ_PIO1_TX2,
  DREQ_PIO1_TX3,
  DREQ_PIO1_RX0,
  DREQ_PIO1_RX1,
  DREQ_PIO1_RX2,
  DREQ_PIO1_RX3,
  DREQ_SPI0_TX,
  DREQ_SPI0_RX,
  DREQ_SPI1_TX,
  DREQ_SPI1_RX,
  DREQ_UART0_TX,
  DREQ_UART0_RX,
  DREQ_UART1_TX,
  DREQ_UART1_RX,
  DREQ_PWM_WRAP0,
  DREQ_PWM_WRAP1,
  DREQ_PWM_WRAP2,
  DREQ_PWM_WRAP3,
  DREQ_PWM_WRAP4,
  DREQ_PWM_WRAP5,
  DREQ_PWM_WRAP6,
  DREQ_PWM_WRAP7,
  DREQ_I2C0_TX,
  DREQ_I2C0_RX,
  DREQ_I2C1_TX,
  DREQ_I2C1_RX,
  DREQ_ADC,
  DREQ_XIP_STREAM,
  DREQ_XIP_SSITX,
  DREQ_XIP_SSIRX,
  DREQ_MAX,
};

}  // namespace rp2040js
