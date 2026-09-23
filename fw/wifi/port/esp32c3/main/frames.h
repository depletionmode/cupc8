/*
 * The slot's frames between a transport (the SPI slave, or UART1 in the QEMU
 * build) and the card engine (fw/common/cardproto.h), for the ESP32-C3.
 *
 * A transport can't change a frame's MISO once it is queued, so it asks for
 * the whole preload when it queues the next frame: the status byte, then
 * RESP_LEN and the response if one is ready and nothing that could change it
 * is queued or running (doc/hardware/slot.md allows this). Received frames
 * are queued from the ISR and replayed into the engine by the task.
 */
#ifndef FRAMES_H
#define FRAMES_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"

#define FRAMES_MAX_LEN 512          /* longest frame the Wi-Fi card takes */

void frames_init(card_t *c);
/* transport (ISR or task): a whole frame arrived; false if the queue is full */
bool frames_received(const uint8_t *mosi, int len);
/* transport: the MISO bytes for the next frame; returns how many */
int frames_preload(uint8_t *miso, int max);
/* task: replay queued frames into the engine; returns how many */
int frames_poll(void);
/* task: bracket changes to the response made outside frames_poll() */
void frames_busy(bool busy);

#endif
