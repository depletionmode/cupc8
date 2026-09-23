/* How card frames reach the ESP32-C3: the slot SPI (the card), or UART1 (the
 * QEMU build, which has no SPI slave). Both queue frames with frames.c and
 * take each frame's MISO preload when the frame before it ends. */
#ifndef TRANSPORT_H
#define TRANSPORT_H

void transport_spi_start(void);
void transport_uart_start(void);

#endif
