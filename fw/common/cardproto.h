/*
 * Common CUPC/8 card protocol (doc/hardware/slot.md), host- and MCU-neutral.
 *
 * The byte-level SPI slave feeds this engine:
 *   card_select(c, true)       CS_n fell: a frame starts
 *   out = card_next_miso(c)    the byte to shift out in the coming slot
 *   card_mosi(c, byte)         the byte the host shifted in during that slot
 *   card_select(c, false)      CS_n rose: the frame ends (and is dispatched)
 *
 * The first MISO byte of a frame is the card's status byte (bit 7 always 0).
 * A command frame is dispatched when CS_n rises. Its response, if any, is
 * collected with a READ frame ($FE): RESP_LEN, then RESP_LEN bytes. RESP_LEN
 * 0 means "not ready yet"; a new command discards an unread response.
 * Common opcodes $F0-$F2 are handled here; everything else goes to the card.
 */
#ifndef CARDPROTO_H
#define CARDPROTO_H

#include <stdbool.h>
#include <stdint.h>

#define CARD_FRAME_MAX   8192          /* longest frame accepted (GPU BLIT8) */
#define CARD_RESP_MAX    255

#define CARD_OP_IDENT      0xF0
#define CARD_OP_SOFT_RESET 0xF1
#define CARD_OP_IRQ_EN     0xF2
#define CARD_OP_READ       0xFE
#define CARD_IDENT_SIG     0xC8

#define CARD_TYPE_GPU  0x01
#define CARD_TYPE_IO   0x02
#define CARD_TYPE_WIFI 0x03
#define CARD_TYPE_STORAGE 0x04

typedef struct card card_t;

typedef struct {
	uint8_t type, fw_major, fw_minor;
	/* status byte for the next frame (bit 7 is forced to 0) */
	uint8_t (*status)(card_t *c);
	/* A complete command frame (frame[0] = opcode). Either set a response
	 * now with card_respond(), later (deferred work), or not at all. */
	void (*command)(card_t *c, const uint8_t *frame, int len);
	/* optional: streaming frames (the GPU writes bytes straight into its FIFO).
	 * If set, frames are passed byte by byte and `command` is not used. */
	void (*frame_begin)(card_t *c);
	void (*frame_byte)(card_t *c, uint8_t b);
	void (*frame_end)(card_t *c);
	void (*soft_reset)(card_t *c);
	/* the card's own IRQ condition (the engine gates it with IRQ_EN) */
	bool (*irq)(card_t *c);
} card_ops_t;

struct card {
	const card_ops_t *ops;
	void *priv;

	bool selected;
	bool irq_en;
	int pos;                           /* byte index within the frame */
	uint8_t opcode;
	uint8_t next_out;                  /* MISO byte for the coming slot */

	uint8_t frame[CARD_FRAME_MAX];     /* buffered frames (non-streaming cards) */
	int frame_len;
	bool frame_overflow;

	uint8_t resp[CARD_RESP_MAX];
	int resp_len;                      /* -1: no response pending or ready */
	bool resp_ready;
	int read_pos;

	uint32_t errors;                   /* malformed frames, overflows */
};

void card_init(card_t *c, const card_ops_t *ops, void *priv);
void card_select(card_t *c, bool selected);
uint8_t card_next_miso(card_t *c);
void card_mosi(card_t *c, uint8_t b);
/* IRQ_n level (true = asserted) */
bool card_irq(card_t *c);

/* for card implementations */
void card_respond(card_t *c, const uint8_t *data, int len);   /* response ready */
void card_respond_pending(card_t *c);                          /* expect one later */

/* Convenience for hosts (simulator, tests): one whole frame, returns MISO bytes */
void card_frame(card_t *c, const uint8_t *mosi, uint8_t *miso, int len);

#endif
