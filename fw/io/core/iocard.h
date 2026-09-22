/*
 * CUPC/8 IO card core: USB HID keyboard → byte stream (doc/hardware/io-card.md).
 *
 * Hardware-independent. The RP2040 build feeds it HID boot reports from
 * TinyUSB; the host tests and the simulator feed it synthetic reports.
 */
#ifndef IOCARD_H
#define IOCARD_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"

#define IO_FIFO_SIZE 64

/* key codes produced in ASCII mode for non-printing keys */
enum {
	IO_KEY_UP = 0x80, IO_KEY_DOWN, IO_KEY_LEFT, IO_KEY_RIGHT,
	IO_KEY_HOME, IO_KEY_END, IO_KEY_PGUP, IO_KEY_PGDN, IO_KEY_INSERT,
	IO_KEY_F1 = 0x91,              /* .. F12 = $9C */
	IO_KEY_NONE = 0xFF,
};

typedef struct iocard {
	card_t card;

	uint8_t fifo[IO_FIFO_SIZE];
	uint8_t head, count;
	bool overflow;

	uint8_t mods;                  /* current HID modifier byte */
	uint8_t keys[6];               /* keys in the last accepted report */
	bool caps, num;
	bool connected, vbus_fault;
	uint8_t mode;                  /* 0 ASCII, 1 raw */

	uint8_t repeat_delay, repeat_rate;   /* 10 ms units; delay 0 = off */
	uint8_t repeat_usage;          /* key being held for repeat, 0 = none */
	uint32_t repeat_at;            /* ms timestamp of the next repeat */

	/* optional: drive the keyboard LEDs (bit 0 Num, 1 Caps) */
	void (*set_leds)(struct iocard *io, uint8_t leds);
} iocard_t;

void io_init(iocard_t *io);
void io_reset(iocard_t *io);
void io_connected(iocard_t *io, bool connected);
void io_vbus_fault(iocard_t *io, bool fault);
/* an 8-byte HID boot keyboard report: mods, reserved, 6 key usages */
void io_report(iocard_t *io, const uint8_t report[8], uint32_t now_ms);
/* typematic repeat; call regularly */
void io_poll(iocard_t *io, uint32_t now_ms);
/* ASCII-mode byte for a usage with the given modifiers (IO_KEY_NONE if none) */
uint8_t io_translate(const iocard_t *io, uint8_t usage, uint8_t mods);

#endif
