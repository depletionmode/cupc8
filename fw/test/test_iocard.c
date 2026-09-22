/* IOC-001/003/004 (host part): IO card core (doc/hardware/io-card.md). */
#include <string.h>

#include "check.h"
#include "iocard.h"

static iocard_t io;
static uint8_t leds_seen = 0xFF;
static void leds(iocard_t *c, uint8_t l) { (void)c; leds_seen = l; }

static void rep(uint32_t t, uint8_t mods, uint8_t k0, uint8_t k1)
{
	uint8_t r[8] = {mods, 0, k0, k1, 0, 0, 0, 0};
	io_report(&io, r, t);
}
/* press and release one key */
static void tap(uint8_t mods, uint8_t usage)
{
	rep(0, mods, usage, 0);
	rep(0, mods, 0, 0);
}

static int frame_read(uint8_t op, const uint8_t *args, int nargs, uint8_t *out, int n)
{
	uint8_t f[8] = {op};
	if (nargs)
		memcpy(f + 1, args, (size_t)nargs);
	card_frame(&io.card, f, 0, 1 + nargs);
	uint8_t mosi[20] = {CARD_OP_READ}, miso[20];
	card_frame(&io.card, mosi, miso, 2 + n);
	memcpy(out, miso + 2, (size_t)n);
	return miso[1];
}

static uint8_t getkey(void)
{
	uint8_t r;
	frame_read(0x00, 0, 0, &r, 1);
	return r;
}

static uint8_t status(void)
{
	uint8_t st;             /* an empty frame: just the status byte */
	card_select(&io.card, true);
	st = card_next_miso(&io.card);
	card_select(&io.card, false);
	return st;
}

static void keymap(void)
{
	/* letters: plain, shift, caps, caps+shift, ctrl */
	for (uint8_t u = 0x04; u <= 0x1D; u++) {
		CHECK_EQ(io_translate(&io, u, 0), 'a' + (u - 4));
		CHECK_EQ(io_translate(&io, u, 0x02), 'A' + (u - 4));      /* left shift */
		CHECK_EQ(io_translate(&io, u, 0x20), 'A' + (u - 4));      /* right shift */
		CHECK_EQ(io_translate(&io, u, 0x01), 1 + (u - 4));        /* ctrl */
	}
	io.caps = true;
	CHECK_EQ(io_translate(&io, 0x04, 0), 'A');
	CHECK_EQ(io_translate(&io, 0x04, 0x02), 'a');
	CHECK_EQ(io_translate(&io, 0x1E, 0), '1');                    /* caps doesn't shift digits */
	io.caps = false;
	/* digits and shifted symbols */
	const char *d = "1234567890", *s = "!@#$%^&*()";
	for (int i = 0; i < 10; i++) {
		CHECK_EQ(io_translate(&io, (uint8_t)(0x1E + i), 0), d[i]);
		CHECK_EQ(io_translate(&io, (uint8_t)(0x1E + i), 0x02), s[i]);
	}
	/* punctuation */
	const uint8_t pu[] = {0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38};
	const char *pp = "-=[]\\;'`,./", *ps = "_+{}|:\"~<>?";
	for (int i = 0; i < 11; i++) {
		CHECK_EQ(io_translate(&io, pu[i], 0), pp[i]);
		CHECK_EQ(io_translate(&io, pu[i], 0x02), ps[i]);
	}
	/* control keys */
	CHECK_EQ(io_translate(&io, 0x28, 0), '\r');
	CHECK_EQ(io_translate(&io, 0x29, 0), 0x1B);
	CHECK_EQ(io_translate(&io, 0x2A, 0), 0x08);
	CHECK_EQ(io_translate(&io, 0x2B, 0), 0x09);
	CHECK_EQ(io_translate(&io, 0x2C, 0), ' ');
	CHECK_EQ(io_translate(&io, 0x4C, 0), 0x7F);
	/* F1-F12, navigation */
	for (int i = 0; i < 12; i++)
		CHECK_EQ(io_translate(&io, (uint8_t)(0x3A + i), 0), 0x91 + i);
	CHECK_EQ(io_translate(&io, 0x52, 0), 0x80);
	CHECK_EQ(io_translate(&io, 0x51, 0), 0x81);
	CHECK_EQ(io_translate(&io, 0x50, 0), 0x82);
	CHECK_EQ(io_translate(&io, 0x4F, 0), 0x83);
	CHECK_EQ(io_translate(&io, 0x4A, 0), 0x84);
	CHECK_EQ(io_translate(&io, 0x4D, 0), 0x85);
	CHECK_EQ(io_translate(&io, 0x4B, 0), 0x86);
	CHECK_EQ(io_translate(&io, 0x4E, 0), 0x87);
	CHECK_EQ(io_translate(&io, 0x49, 0), 0x88);
	/* keypad with Num Lock on (power-on default) and off */
	CHECK(io.num, "Num Lock should be on at power-up");
	CHECK_EQ(io_translate(&io, 0x59, 0), '1');
	CHECK_EQ(io_translate(&io, 0x62, 0), '0');
	CHECK_EQ(io_translate(&io, 0x63, 0), '.');
	CHECK_EQ(io_translate(&io, 0x55, 0), '*');
	CHECK_EQ(io_translate(&io, 0x58, 0), '\r');
	io.num = false;
	CHECK_EQ(io_translate(&io, 0x59, 0), 0x85);                   /* End */
	CHECK_EQ(io_translate(&io, 0x60, 0), 0x80);                   /* Up */
	CHECK_EQ(io_translate(&io, 0x5D, 0), 0xFF);                   /* 5: nothing */
	CHECK_EQ(io_translate(&io, 0x63, 0), 0x7F);                   /* Delete */
	io.num = true;
	/* never produces $FF for a real key */
	for (int u = 4; u < 0x65; u++)
		if (io_translate(&io, (uint8_t)u, 0) == 0xFF)
			CHECK(u == 0x39 || u == 0x46 || u == 0x47 || u == 0x48 || u == 0x53 || u == 0x5D || u == 0x64,
			      "usage $%02x has no mapping", u);
}

static void events(void)
{
	io_reset(&io);
	/* typing through the FIFO */
	tap(0, 0x0B);                        /* h */
	tap(0x02, 0x0C);                     /* I */
	CHECK_EQ(io.count, 2);
	CHECK(card_irq(&io.card) == false, "IRQ before IRQ_EN");
	uint8_t en[2] = {CARD_OP_IRQ_EN, 1};
	card_frame(&io.card, en, 0, 2);
	CHECK(card_irq(&io.card), "IRQ while the FIFO has keys");
	CHECK_EQ(status() & 0x0F, 2);
	CHECK_EQ(getkey(), 'h');
	CHECK_EQ(getkey(), 'I');
	CHECK_EQ(getkey(), 0xFF);
	CHECK(!card_irq(&io.card), "IRQ with an empty FIFO");

	/* Caps Lock toggles and drives the LEDs */
	tap(0, 0x39);
	CHECK(io.caps, "caps on");
	CHECK_EQ(leds_seen, 3);
	tap(0, 0x04);
	CHECK_EQ(getkey(), 'A');
	tap(0, 0x39);
	CHECK_EQ(leds_seen, 1);

	/* several keys in one report each produce one byte; held keys don't repeat bytes */
	rep(0, 0, 0x04, 0x05);
	rep(0, 0, 0x04, 0x05);
	rep(0, 0, 0x05, 0);
	rep(0, 0, 0, 0);
	CHECK_EQ(io.count, 2);
	CHECK_EQ(getkey(), 'a');
	CHECK_EQ(getkey(), 'b');

	/* ErrorRollOver reports are ignored */
	rep(0, 0, 0x04, 0);
	rep(0, 0, 0x01, 0x01);
	rep(0, 0, 0x04, 0);
	rep(0, 0, 0, 0);
	CHECK_EQ(io.count, 1);
	getkey();

	/* typematic: 500 ms delay, 30 ms rate */
	rep(1000, 0, 0x04, 0);
	io_poll(&io, 1499);
	CHECK_EQ(io.count, 1);
	io_poll(&io, 1500);
	CHECK_EQ(io.count, 2);
	io_poll(&io, 1529);
	CHECK_EQ(io.count, 2);
	io_poll(&io, 1530);
	CHECK_EQ(io.count, 3);
	rep(1540, 0, 0, 0);
	io_poll(&io, 2000);
	CHECK_EQ(io.count, 3);
	/* SETREPEAT 0 turns repeat off */
	uint8_t sr[3] = {0x03, 0, 0};
	card_frame(&io.card, sr, 0, 3);
	rep(3000, 0, 0x04, 0);
	io_poll(&io, 9000);
	CHECK_EQ(io.count, 4);
	rep(9000, 0, 0, 0);

	/* FLUSH */
	uint8_t fl[1] = {0x05};
	card_frame(&io.card, fl, 0, 1);
	CHECK_EQ(io.count, 0);

	/* overflow: drop the newest, flag sticky until the FIFO empties */
	for (int i = 0; i < 70; i++)
		tap(0, 0x04);
	CHECK_EQ(io.count, 64);
	CHECK(status() & 0x40, "OVERFLOW flag");
	uint8_t r[16];
	CHECK_EQ(frame_read(0x01, (uint8_t[]){16}, 1, r, 16), 16);
	CHECK(status() & 0x40, "OVERFLOW cleared too early");
	for (int i = 0; i < 48; i++) getkey();
	CHECK(!(status() & 0x40), "OVERFLOW not cleared when empty");
	/* GETKEYS pads with $FF */
	tap(0, 0x05);
	frame_read(0x01, (uint8_t[]){3}, 1, r, 3);
	CHECK(r[0] == 'b' && r[1] == 0xFF && r[2] == 0xFF, "GETKEYS padding");

	/* GETMODS */
	rep(0, 0x22, 0, 0);
	frame_read(0x02, 0, 0, r, 1);
	CHECK_EQ(r[0], 0x22);
	rep(0, 0, 0, 0);

	/* raw mode: usage + pressed flag, modifiers as $E0-$E7 */
	uint8_t raw[2] = {0x04, 1};
	card_frame(&io.card, raw, 0, 2);
	rep(0, 0x02, 0x04, 0);
	rep(0, 0, 0, 0);
	uint8_t want[] = {0xE1, 1, 0x04, 1, 0xE1, 0, 0x04, 0};
	CHECK_EQ(io.count, 8);
	for (int i = 0; i < 8; i++)
		CHECK_EQ(getkey(), want[i]);

	/* status bits: connected, VBUS fault */
	io_connected(&io, true);
	io_vbus_fault(&io, true);
	CHECK_EQ(status() & 0x30, 0x30);

	/* malformed commands are counted */
	uint32_t e = io.card.errors;
	uint8_t bad[1] = {0x03};
	card_frame(&io.card, bad, 0, 1);
	uint8_t unk[1] = {0x42};
	card_frame(&io.card, unk, 0, 1);
	CHECK_EQ(io.card.errors, e + 2);

	/* IDENT */
	CHECK_EQ(frame_read(CARD_OP_IDENT, 0, 0, r, 4), 4);
	CHECK(r[0] == CARD_TYPE_IO && r[3] == CARD_IDENT_SIG, "IDENT");
}

int main(void)
{
	io_init(&io);
	io.set_leds = leds;
	keymap();
	events();
	return check_report("IOC-001/003 io card core");
}
