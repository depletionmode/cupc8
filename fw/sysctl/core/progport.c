/*
 * The card programming port (doc/hardware/sysctl.md, "The card programming
 * port"): the slot mux, raw SWD transfers, and a UART. The protocols on top
 * (the RP2040 flash routines, the ESP ROM bootloader) run in cupc8.py.
 */
#include "sysctl.h"

#define WAIT_RETRIES 100
#define TARGETSEL    0x99               /* a DP write to $C: no ack phase (multi-drop) */

int prog_select(sysctl_t *s, int slot)
{
	if (slot < -1 || slot > 5)
		return ST_ARG;
	s->hal->prog_select(s->ctx, slot);
	return ST_OK;
}

void swd_seq(sysctl_t *s, const uint8_t *bits, int nbits)
{
	for (int i = 0; i < nbits; i += 32) {
		uint32_t w = 0;
		int k = nbits - i < 32 ? nbits - i : 32;
		for (int b = 0; b < k; b++)
			w |= (uint32_t)(bits[(i + b) / 8] >> ((i + b) % 8) & 1) << b;
		s->hal->swd_io(s->ctx, true, &w, k);
	}
}

static int parity(uint32_t v)
{
	v ^= v >> 16;
	v ^= v >> 8;
	v ^= v >> 4;
	v ^= v >> 2;
	v ^= v >> 1;
	return (int)(v & 1);
}

int swd_xfer(sysctl_t *s, uint8_t request, uint32_t *data)
{
	const sysctl_hal *h = s->hal;
	bool read = request & 0x04;
	for (int tries = 0; tries <= WAIT_RETRIES; tries++) {
		uint32_t w = request;
		h->swd_io(s->ctx, true, &w, 8);
		if (request == TARGETSEL) {
			/* the targets listen but none answers: turnaround, 3 undriven
			 * ack cycles, turnaround, then the data */
			uint32_t skip;
			h->swd_io(s->ctx, false, &skip, 5);
			w = *data;
			h->swd_io(s->ctx, true, &w, 32);
			w = (uint32_t)parity(*data);
			h->swd_io(s->ctx, true, &w, 1);
			return SWD_OK;
		}
		uint32_t ack;
		h->swd_io(s->ctx, false, &ack, 3);        /* turnaround included */
		ack &= 7;
		if (ack == SWD_WAIT)
			continue;
		if (ack != SWD_OK) {
			/* FAULT or nothing: no data phase; the host line-resets */
			return ack == SWD_FAULT ? SWD_FAULT : SWD_NONE;
		}
		if (read) {
			uint32_t v, p;
			h->swd_io(s->ctx, false, &v, 32);
			h->swd_io(s->ctx, false, &p, 1);
			w = 0;
			h->swd_io(s->ctx, true, &w, 1);         /* turnaround back, one idle */
			*data = v;
			return (int)(p & 1) == parity(v) ? SWD_OK : SWD_PARITY;
		}
		w = *data;
		h->swd_io(s->ctx, true, &w, 32);          /* turnaround included */
		w = (uint32_t)parity(*data);
		h->swd_io(s->ctx, true, &w, 1);
		return SWD_OK;
	}
	return SWD_WAIT;
}
