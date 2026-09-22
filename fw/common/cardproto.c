#include "cardproto.h"

#include <string.h>

void card_init(card_t *c, const card_ops_t *ops, void *priv)
{
	memset(c, 0, sizeof *c);
	c->ops = ops;
	c->priv = priv;
	c->resp_len = -1;
	c->next_out = 0;
}

void card_respond(card_t *c, const uint8_t *data, int len)
{
	if (len > CARD_RESP_MAX)
		len = CARD_RESP_MAX;
	memcpy(c->resp, data, (size_t)len);
	c->resp_len = len;
	c->resp_ready = true;
}

void card_respond_pending(card_t *c)
{
	c->resp_len = -1;
	c->resp_ready = false;
}

bool card_irq(card_t *c)
{
	return c->irq_en && c->ops->irq && c->ops->irq(c);
}

static bool streaming(const card_t *c)
{
	return c->ops->frame_byte != 0;
}

static void common_command(card_t *c, const uint8_t *frame, int len)
{
	switch (frame[0]) {
	case CARD_OP_IDENT: {
		uint8_t r[4] = { c->ops->type, c->ops->fw_major, c->ops->fw_minor, CARD_IDENT_SIG };
		card_respond(c, r, 4);
		break;
	}
	case CARD_OP_SOFT_RESET:
		c->irq_en = false;
		if (c->ops->soft_reset)
			c->ops->soft_reset(c);
		card_respond_pending(c);
		break;
	case CARD_OP_IRQ_EN:
		if (len >= 2)
			c->irq_en = frame[1] != 0;
		else
			c->errors++;
		break;
	default:
		break;          /* $F3-$FD: reserved, ignored */
	}
}

void card_select(card_t *c, bool selected)
{
	if (selected == c->selected)
		return;
	c->selected = selected;
	if (selected) {
		/* a frame starts: the status byte goes out first */
		c->pos = 0;
		c->frame_len = 0;
		c->frame_overflow = false;
		c->next_out = c->ops->status ? (uint8_t)(c->ops->status(c) & 0x7F) : 0;
		return;
	}

	/* CS rose: the frame ends */
	if (c->pos == 0)
		return;                                 /* empty frame */
	if (c->opcode == CARD_OP_READ || c->opcode == 0xFF)
		return;                                 /* READ is not a command; $FF is never an opcode */
	if (c->opcode >= 0xF0) {
		/* common opcodes are always buffered (they're short) */
		c->resp_len = -1;
		c->resp_ready = false;
		common_command(c, c->frame, c->frame_len);
		return;
	}
	if (streaming(c)) {
		c->ops->frame_end(c);
		return;
	}
	if (c->frame_overflow) {
		c->errors++;
		return;
	}
	c->resp_len = -1;                       /* a new command discards any unread response */
	c->resp_ready = false;
	if (c->ops->command)
		c->ops->command(c, c->frame, c->frame_len);
}

uint8_t card_next_miso(card_t *c)
{
	return c->next_out;
}

void card_mosi(card_t *c, uint8_t b)
{
	if (!c->selected)
		return;
	if (c->pos == 0) {
		c->opcode = b;
		if (b == CARD_OP_READ) {
			/* RESP_LEN goes out next; 0 = not ready */
			c->read_pos = 0;
			c->next_out = c->resp_ready ? (uint8_t)c->resp_len : 0;
		} else {
			c->next_out = 0;
			if (b < 0xF0 && b != 0xFF && streaming(c)) {
				c->resp_len = -1;
				c->resp_ready = false;
				c->ops->frame_begin(c);
			}
		}
	} else if (c->opcode == CARD_OP_READ) {
		/* slot pos just finished; decide the byte for slot pos+1 */
		if (c->resp_ready && c->read_pos < c->resp_len)
			c->next_out = c->resp[c->read_pos++];
		else
			c->next_out = 0;
	} else {
		c->next_out = 0;
	}

	if (c->opcode != CARD_OP_READ) {
		if (streaming(c) && c->opcode < 0xF0) {
			c->ops->frame_byte(c, b);
		} else if (c->frame_len < CARD_FRAME_MAX) {
			c->frame[c->frame_len++] = b;
		} else {
			c->frame_overflow = true;
		}
	}
	c->pos++;
}

void card_frame(card_t *c, const uint8_t *mosi, uint8_t *miso, int len)
{
	card_select(c, true);
	for (int i = 0; i < len; i++) {
		uint8_t out = card_next_miso(c);
		if (miso)
			miso[i] = out;
		card_mosi(c, mosi[i]);
	}
	card_select(c, false);
}
