/*
 * The USB console (doc/proposals/usb-console.md): the kernel's terminal on
 * the card's second USB serial port, through two rings in the API block.
 *
 * Only while a PC has that port open (DTR), every CON_POLL_MS: set HOST in
 * CON_FLAGS, send the bytes between CON_OUT_TAIL and CON_OUT_HEAD to the PC
 * (the kernel's \n as CR LF) and move CON_OUT_TAIL past them; put what the
 * PC typed into CON_IN as room allows (CR is Enter; the LF of a CR LF is
 * dropped, a lone LF is Enter) and move CON_IN_HEAD. Each side writes only
 * its own index, and only after the data it covers: the bridge's writes are
 * atomic per byte, not across bytes. On close, clear HOST, so the kernel
 * stops waiting on a full ring. With the port closed there is no bridge
 * traffic at all.
 *
 * The indices are read from RAM on every poll, not cached: the kernel zeroes
 * them (and CON_FLAGS) when it boots, and the card finds HOST clear and sets
 * it again.
 */
#include "sysctl.h"

static void set_flags(sysctl_t *s, uint8_t f)
{
	br_ram_write(s, CON_FLAGS, &f, 1);
	s->con_host = f & CON_HOST;
}

/* copy n bytes out of a ring starting at index i (it wraps once at most) */
static void ring_read(sysctl_t *s, uint16_t base, int size, int i, uint8_t *d, int n)
{
	int k = size - i < n ? size - i : n;
	br_ram_read(s, (uint16_t)(base + i), d, k);
	if (n > k)
		br_ram_read(s, base, d + k, n - k);
}

static void ring_write(sysctl_t *s, uint16_t base, int size, int i, const uint8_t *d, int n)
{
	int k = size - i < n ? size - i : n;
	br_ram_write(s, (uint16_t)(base + i), d, k);
	if (n > k)
		br_ram_write(s, base, d + k, n - k);
}

/* CON_OUT to the PC; returns the new tail */
static int con_out(sysctl_t *s, int head, int tail)
{
	uint8_t ring[CON_OUT_SIZE], usb[2 * CON_OUT_SIZE];
	int n = (head - tail) & (CON_OUT_SIZE - 1);
	int room = s->hal->con_room(s->ctx);
	if (n > room)
		n = room;                     /* every byte is at least one out */
	if (n == 0)
		return tail;
	ring_read(s, CON_OUT, CON_OUT_SIZE, tail, ring, n);
	int taken = 0, u = 0;
	for (; taken < n; taken++) {
		if (ring[taken] == '\n') {
			if (u + 2 > room)
				break;
			usb[u++] = '\r';
		}
		usb[u++] = ring[taken];
	}
	s->hal->con_write(s->ctx, usb, u);
	return (tail + taken) & (CON_OUT_SIZE - 1);
}

/* the PC's bytes to CON_IN; returns the new head */
static int con_in(sysctl_t *s, int head, int tail)
{
	uint8_t pc[CON_IN_SIZE], keys[CON_IN_SIZE];
	int room = (tail - head - 1) & (CON_IN_SIZE - 1);
	if (room == 0)
		return head;
	int n = s->hal->con_read(s->ctx, pc, room), k = 0;
	for (int i = 0; i < n; i++) {
		uint8_t b = pc[i];
		bool after_cr = s->con_cr;
		s->con_cr = b == '\r';
		if (b == '\n') {
			if (after_cr)
				continue;             /* CR LF: one Enter */
			b = '\r';
		}
		keys[k++] = b;
	}
	if (k == 0)
		return head;
	ring_write(s, CON_IN, CON_IN_SIZE, head, keys, k);
	return (head + k) & (CON_IN_SIZE - 1);
}

void con_poll(sysctl_t *s)
{
	const sysctl_hal *h = s->hal;
	if (!h->con_open(s->ctx)) {
		/* closed: say so once, then leave the bus alone */
		if (s->con_host && sysctl_chipset_up(s))
			set_flags(s, 0);
		s->con_host = false;
		s->con_cr = false;
		return;
	}
	if (!sysctl_chipset_up(s)) {
		s->con_host = false;          /* set it again once the chipset is back */
		return;
	}
	uint32_t now = h->now_ms(s->ctx);
	if (s->con_host && now - s->con_last_ms < CON_POLL_MS)
		return;
	s->con_last_ms = now;

	/* CON_OUT_HEAD, CON_OUT_TAIL, CON_IN_HEAD, CON_IN_TAIL, CON_FLAGS */
	uint8_t ix[5];
	br_ram_read(s, CON_OUT_HEAD, ix, 5);
	if (!(ix[4] & CON_HOST))
		set_flags(s, CON_HOST);       /* opened, or the kernel zeroed it at boot */
	s->con_host = true;

	int out_head = ix[0] & (CON_OUT_SIZE - 1), out_tail = ix[1] & (CON_OUT_SIZE - 1);
	int t = con_out(s, out_head, out_tail);
	if (t != out_tail) {
		uint8_t b = (uint8_t)t;
		br_ram_write(s, CON_OUT_TAIL, &b, 1);
	}
	int in_head = ix[2] & (CON_IN_SIZE - 1), in_tail = ix[3] & (CON_IN_SIZE - 1);
	int hd = con_in(s, in_head, in_tail);
	if (hd != in_head) {
		uint8_t b = (uint8_t)hd;
		br_ram_write(s, CON_IN_HEAD, &b, 1);
	}
}
