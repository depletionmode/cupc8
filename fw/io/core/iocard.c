#include "iocard.h"

#include <string.h>

#define IO_FW_MAJOR 1
#define IO_FW_MINOR 0

#define MOD_CTRL  0x11      /* left | right */
#define MOD_SHIFT 0x22

/* US layout, HID usages $04-$38: unshifted and shifted */
static const char us_plain[] = "abcdefghijklmnopqrstuvwxyz1234567890\r\x1b\b\t -=[]\\#;'`,./";
static const char us_shift[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()\r\x1b\b\t _+{}|~:\"~<>?";

/* ------------------------------------------------------------------ FIFO */

static void push(iocard_t *io, uint8_t b)
{
	if (io->count >= IO_FIFO_SIZE) {
		io->overflow = true;            /* drop the newest */
		return;
	}
	io->fifo[(io->head + io->count) % IO_FIFO_SIZE] = b;
	io->count++;
}

static uint8_t pop(iocard_t *io)
{
	if (io->count == 0)
		return IO_KEY_NONE;
	uint8_t b = io->fifo[io->head];
	io->head = (uint8_t)((io->head + 1) % IO_FIFO_SIZE);
	io->count--;
	if (io->count == 0)
		io->overflow = false;           /* cleared by the read that empties the FIFO */
	return b;
}

/* ------------------------------------------------------------------ keymap */

uint8_t io_translate(const iocard_t *io, uint8_t u, uint8_t mods)
{
	bool shift = mods & MOD_SHIFT, ctrl = mods & MOD_CTRL;

	if (u >= 0x04 && u <= 0x1D) {                       /* letters */
		if (ctrl)
			return (uint8_t)(u - 0x04 + 1);             /* Ctrl+A..Z = $01-$1A */
		bool upper = shift != io->caps;
		return (uint8_t)(upper ? us_shift[u - 4] : us_plain[u - 4]);
	}
	if (u >= 0x1E && u <= 0x38)
		return (uint8_t)(shift ? us_shift[u - 4] : us_plain[u - 4]);
	if (u >= 0x3A && u <= 0x45)
		return (uint8_t)(IO_KEY_F1 + (u - 0x3A));        /* F1-F12 */
	switch (u) {
	case 0x49: return IO_KEY_INSERT;
	case 0x4A: return IO_KEY_HOME;
	case 0x4B: return IO_KEY_PGUP;
	case 0x4C: return 0x7F;                             /* Delete */
	case 0x4D: return IO_KEY_END;
	case 0x4E: return IO_KEY_PGDN;
	case 0x4F: return IO_KEY_RIGHT;
	case 0x50: return IO_KEY_LEFT;
	case 0x51: return IO_KEY_DOWN;
	case 0x52: return IO_KEY_UP;
	case 0x54: return '/';
	case 0x55: return '*';
	case 0x56: return '-';
	case 0x57: return '+';
	case 0x58: return '\r';                             /* keypad Enter */
	}
	if (u >= 0x59 && u <= 0x63) {                       /* keypad 1-9, 0, . */
		static const char digits[] = "1234567890.";
		static const uint8_t nav[] = {
			IO_KEY_END, IO_KEY_DOWN, IO_KEY_PGDN, IO_KEY_LEFT, IO_KEY_NONE, IO_KEY_RIGHT,
			IO_KEY_HOME, IO_KEY_UP, IO_KEY_PGUP, IO_KEY_INSERT, 0x7F,
		};
		return io->num ? (uint8_t)digits[u - 0x59] : nav[u - 0x59];
	}
	return IO_KEY_NONE;
}

static bool is_lock(uint8_t u) { return u == 0x39 || u == 0x53; }

static void update_leds(iocard_t *io)
{
	if (io->set_leds)
		io->set_leds(io, (uint8_t)((io->num ? 1 : 0) | (io->caps ? 2 : 0)));
}

static void key_down(iocard_t *io, uint8_t u, uint32_t now)
{
	if (io->mode == 1) {
		push(io, u);
		push(io, 1);
	}
	if (u == 0x39) { io->caps = !io->caps; update_leds(io); }
	if (u == 0x53) { io->num = !io->num; update_leds(io); }
	if (io->mode == 0 && !is_lock(u)) {
		uint8_t b = io_translate(io, u, io->mods);
		if (b != IO_KEY_NONE)
			push(io, b);
	}
	if (!is_lock(u) && io->repeat_delay) {
		io->repeat_usage = u;
		io->repeat_at = now + io->repeat_delay * 10u;
	}
}

static void key_up(iocard_t *io, uint8_t u)
{
	if (io->mode == 1) {
		push(io, u);
		push(io, 0);
	}
	if (io->repeat_usage == u)
		io->repeat_usage = 0;
}

static bool contains(const uint8_t *keys, uint8_t u)
{
	for (int i = 0; i < 6; i++)
		if (keys[i] == u)
			return true;
	return false;
}

void io_report(iocard_t *io, const uint8_t rep[8], uint32_t now)
{
	const uint8_t *k = rep + 2;
	for (int i = 0; i < 6; i++)
		if (k[i] == 0x01)
			return;                     /* ErrorRollOver: keep the previous state */

	/* modifier changes (raw mode reports them as usages $E0-$E7) */
	uint8_t changed = io->mods ^ rep[0];
	for (int b = 0; b < 8; b++)
		if (changed & (1 << b) && io->mode == 1) {
			push(io, (uint8_t)(0xE0 + b));
			push(io, (rep[0] >> b) & 1);
		}
	io->mods = rep[0];

	for (int i = 0; i < 6; i++)
		if (io->keys[i] >= 0x04 && !contains(k, io->keys[i]))
			key_up(io, io->keys[i]);
	for (int i = 0; i < 6; i++)
		if (k[i] >= 0x04 && !contains(io->keys, k[i]))
			key_down(io, k[i], now);
	memcpy(io->keys, k, 6);
}

void io_poll(iocard_t *io, uint32_t now)
{
	if (!io->repeat_usage || !io->repeat_delay || io->mode != 0)
		return;
	if ((int32_t)(now - io->repeat_at) >= 0) {
		uint8_t b = io_translate(io, io->repeat_usage, io->mods);
		if (b != IO_KEY_NONE)
			push(io, b);
		io->repeat_at = now + (io->repeat_rate ? io->repeat_rate : 1) * 10u;
	}
}

void io_connected(iocard_t *io, bool connected)
{
	io->connected = connected;
	if (!connected) {
		memset(io->keys, 0, sizeof io->keys);
		io->mods = 0;
		io->repeat_usage = 0;
	} else {
		update_leds(io);
	}
}

void io_vbus_fault(iocard_t *io, bool fault) { io->vbus_fault = fault; }

/* ------------------------------------------------------------------ card glue */

static uint8_t status(card_t *c)
{
	iocard_t *io = c->priv;
	return (uint8_t)((io->overflow ? 0x40 : 0) | (io->connected ? 0x20 : 0) |
	                 (io->vbus_fault ? 0x10 : 0) | (io->count > 15 ? 15 : io->count));
}

static void command(card_t *c, const uint8_t *f, int len)
{
	iocard_t *io = c->priv;
	uint8_t r[16];
	switch (f[0]) {
	case 0x00:                                          /* GETKEY */
		r[0] = pop(io);
		card_respond(c, r, 1);
		break;
	case 0x01: {                                        /* GETKEYS n */
		if (len < 2 || f[1] < 1 || f[1] > 16) { c->errors++; break; }
		for (int i = 0; i < f[1] && i < (int)sizeof r; i++)   /* f[1] <= 16: the bound is for the compiler */
			r[i] = pop(io);
		card_respond(c, r, f[1]);
		break;
	}
	case 0x02:                                          /* GETMODS */
		card_respond(c, &io->mods, 1);
		break;
	case 0x03:                                          /* SETREPEAT delay, rate */
		if (len < 3) { c->errors++; break; }
		io->repeat_delay = f[1];
		io->repeat_rate = f[2];
		if (!f[1])
			io->repeat_usage = 0;
		break;
	case 0x04:                                          /* SETMODE */
		if (len < 2) { c->errors++; break; }
		io->mode = f[1] ? 1 : 0;
		break;
	case 0x05:                                          /* FLUSH */
		io->count = 0;
		io->overflow = false;
		break;
	default:
		c->errors++;
		break;
	}
}

static bool irq(card_t *c) { return ((iocard_t *)c->priv)->count != 0; }
static void soft_reset(card_t *c) { io_reset(c->priv); }

static const card_ops_t io_ops = {
	.type = CARD_TYPE_IO, .fw_major = IO_FW_MAJOR, .fw_minor = IO_FW_MINOR,
	.status = status, .command = command, .soft_reset = soft_reset, .irq = irq,
};

void io_reset(iocard_t *io)
{
	io->head = io->count = 0;
	io->overflow = false;
	io->mode = 0;
	io->repeat_delay = 50;
	io->repeat_rate = 3;
	io->repeat_usage = 0;
	io->caps = false;
	io->num = true;
	update_leds(io);
}

void io_init(iocard_t *io)
{
	memset(io, 0, sizeof *io);
	card_init(&io->card, &io_ops, io);
	io_reset(io);
}
