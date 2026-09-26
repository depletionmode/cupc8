/* How card frames reach the ESP32-C3: the slot SPI (the card), or in the QEMU
 * build the lockstep QEMU's stand-in for that SPI slave, else UART1 (a stock
 * QEMU). All queue frames with frames.c and take each frame's MISO preload
 * when the frame before it ends. */
#ifndef TRANSPORT_H
#define TRANSPORT_H

#include <stdbool.h>

void transport_spi_start(void);
void transport_uart_start(void);
/* the lockstep QEMU's slot SPI stand-in; false (and nothing started) without it */
bool transport_slotdev_start(void);

#endif
