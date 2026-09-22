/* CARD-001: common card protocol engine (doc/hardware/slot.md). */
#include <string.h>

#include "cardproto.h"
#include "check.h"

/* a dummy card: echoes command frames back as the response of opcode $01 */
static int commands, resets;
static uint8_t status_value = 0xFF;          /* bit 7 must be masked off */
static bool dummy_irq_line;

static uint8_t d_status(card_t *c) { (void)c; return status_value; }
static void d_command(card_t *c, const uint8_t *f, int len)
{
	commands++;
	if (f[0] == 0x01)
		card_respond(c, f, len);                  /* echo */
	else if (f[0] == 0x02)
		card_respond_pending(c);                  /* response later */
}
static void d_reset(card_t *c) { (void)c; resets++; }
static bool d_irq(card_t *c) { (void)c; return dummy_irq_line; }

static const card_ops_t dummy_ops = {
	.type = 0x42, .fw_major = 3, .fw_minor = 7,
	.status = d_status, .command = d_command, .soft_reset = d_reset, .irq = d_irq,
};

static card_t card;

/* READ frame: returns RESP_LEN and fills out[] */
static int do_read(uint8_t *out, int max)
{
	uint8_t mosi[2 + CARD_RESP_MAX] = {CARD_OP_READ}, miso[2 + CARD_RESP_MAX];
	card_frame(&card, mosi, miso, 2 + max);
	memcpy(out, miso + 2, (size_t)max);
	return miso[1];
}

int main(void)
{
	uint8_t miso[64], r[CARD_RESP_MAX];
	card_init(&card, &dummy_ops, 0);

	/* status byte comes out first, bit 7 forced to 0 */
	uint8_t nop[1] = {0x00};
	card_frame(&card, nop, miso, 1);
	CHECK_EQ(miso[0], 0x7F);
	status_value = 0x15;
	card_frame(&card, nop, miso, 1);
	CHECK_EQ(miso[0], 0x15);

	/* IDENT, then READ */
	uint8_t ident[1] = {CARD_OP_IDENT};
	card_frame(&card, ident, 0, 1);
	CHECK_EQ(do_read(r, 4), 4);
	CHECK(r[0] == 0x42 && r[1] == 3 && r[2] == 7 && r[3] == CARD_IDENT_SIG,
	      "ident %02x %02x %02x %02x", r[0], r[1], r[2], r[3]);
	/* reading again returns the same response (retries are safe) */
	CHECK_EQ(do_read(r, 4), 4);
	CHECK_EQ(r[3], CARD_IDENT_SIG);

	/* a card command with an echo response */
	uint8_t cmd[5] = {0x01, 0xAA, 0xBB, 0xCC, 0xDD};
	int before = commands;
	card_frame(&card, cmd, miso, 5);
	CHECK_EQ(commands, before + 1);
	for (int i = 1; i < 5; i++)
		CHECK_EQ(miso[i], 0);                     /* command frames return $00 after status */
	CHECK_EQ(do_read(r, 5), 5);
	CHECK(memcmp(r, cmd, 5) == 0, "echo mismatch");

	/* deferred response: RESP_LEN 0 until the card responds */
	uint8_t pend[1] = {0x02};
	card_frame(&card, pend, 0, 1);
	CHECK_EQ(do_read(r, 1), 0);
	uint8_t late[2] = {9, 8};
	card_respond(&card, late, 2);
	CHECK_EQ(do_read(r, 2), 2);
	CHECK(r[0] == 9 && r[1] == 8, "late response");

	/* a new command discards an unread response */
	card_frame(&card, cmd, 0, 5);
	uint8_t other[1] = {0x03};
	card_frame(&card, other, 0, 1);
	CHECK_EQ(do_read(r, 5), 0);

	/* READ and $FF are never dispatched as commands */
	before = commands;
	uint8_t ff[3] = {0xFF, 0xFF, 0xFF};
	card_frame(&card, ff, 0, 3);
	uint8_t rd[3] = {CARD_OP_READ, 0, 0};
	card_frame(&card, rd, 0, 3);
	CHECK_EQ(commands, before);

	/* an empty frame (CS pulse) does nothing */
	card_select(&card, true);
	card_select(&card, false);
	CHECK_EQ(commands, before);

	/* IRQ_EN gates the card's IRQ; power-on default is off */
	dummy_irq_line = true;
	CHECK(!card_irq(&card), "IRQ asserted before IRQ_EN");
	uint8_t en[2] = {CARD_OP_IRQ_EN, 1};
	card_frame(&card, en, 0, 2);
	CHECK(card_irq(&card), "IRQ not asserted after IRQ_EN");
	uint8_t en_short[1] = {CARD_OP_IRQ_EN};
	uint32_t errs = card.errors;
	card_frame(&card, en_short, 0, 1);
	CHECK_EQ(card.errors, errs + 1);

	/* SOFT_RESET: card reset hook runs, IRQ_EN returns to off */
	uint8_t sr[1] = {CARD_OP_SOFT_RESET};
	card_frame(&card, sr, 0, 1);
	CHECK_EQ(resets, 1);
	CHECK(!card_irq(&card), "IRQ_EN survived SOFT_RESET");

	/* resync: bytes before CS rises belong to one frame only */
	uint8_t part[2] = {0x01, 0x77};
	card_frame(&card, part, 0, 2);
	CHECK_EQ(do_read(r, 2), 2);
	CHECK_EQ(r[1], 0x77);

	/* reserved common opcodes are ignored */
	before = commands;
	uint8_t res[1] = {0xF5};
	card_frame(&card, res, 0, 1);
	CHECK_EQ(commands, before);

	/* oversized frames are dropped and counted */
	static uint8_t big[CARD_FRAME_MAX + 10];
	big[0] = 0x01;
	errs = card.errors;
	before = commands;
	card_frame(&card, big, 0, (int)sizeof big);
	CHECK_EQ(commands, before);
	CHECK_EQ(card.errors, errs + 1);

	return check_report("CARD-001 cardproto");
}
