/*
 * The slot SPI slave for RP2040 cards (doc/hardware/slot.md), under the
 * common card engine (fw/common/cardproto.h).
 *
 * PIO shifts the bytes; DMA streams every MOSI byte into a ring and feeds
 * the MISO bytes preloaded for the frame. When CS_n rises, an interrupt
 * queues the frame, preloads the next frame's MISO (status byte, then
 * RESP_LEN and the response if one is ready) and re-arms, well inside the
 * 20 us the host leaves between frames. slotspi_poll() then replays queued
 * frames through the card engine from the main loop.
 */
#ifndef SLOTSPI_H
#define SLOTSPI_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"

/* The status byte for the next frame, from the interrupt. queued_bytes and
 * queued_frames count what the host has sent but slotspi_poll() has not
 * replayed yet (the GPU subtracts them from its FIFO space). */
typedef uint8_t (*slotspi_status_fn)(card_t *c, uint32_t queued_bytes, uint32_t queued_frames);

void slotspi_init(card_t *c, slotspi_status_fn status);

/* Replay every queued frame into the card engine, and update SLOT_nIRQ.
 * Returns the number of frames replayed. */
int slotspi_poll(void);

/* Bracket any change to the card's response outside slotspi_poll() (deferred
 * work calling card_respond()): while busy, a preload offers no response.
 * Afterwards, call slotspi_refresh() if anything changed. */
void slotspi_busy(bool busy);

/* Re-arm the next frame's preload now (new status or response), if no frame
 * is in progress */
void slotspi_refresh(void);

/* SLOT_nIRQ from card_irq(); slotspi_poll() calls it too */
void slotspi_update_irq(void);

extern volatile uint32_t slotspi_errors;       /* dropped frames */

#endif
