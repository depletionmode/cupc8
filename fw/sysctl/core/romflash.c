/*
 * The SST39VF040 ROM chip, programmed through the bridge
 * (doc/hardware/sysctl.md, "The ROM through the bridge").
 */
#include "sysctl.h"

#define SECTOR 4096u
#define PROGRAM_POLLS 100                 /* ~5 ms of ROM_RDs at 1 MHz; T_BP is 20 µs */

static void unlock(sysctl_t *s)
{
	br_rom_busw(s, 0x5555, 0xAA);
	br_rom_busw(s, 0x2AAA, 0x55);
}

static uint8_t rd(sysctl_t *s, uint32_t addr)
{
	uint8_t b;
	br_rom_read(s, addr, &b, 1);
	return b;
}

/* the CPU must not fetch from a ROM that is half written */
static uint8_t cpu_stop(sysctl_t *s)
{
	uint8_t st = br_status(s);
	uint8_t prev = (uint8_t)((st & 0x01) | (st & 0x80 ? 0x40 : 0));
	br_cpu_ctl(s, (uint8_t)(prev | 0x01));
	return prev;
}

int rom_id(sysctl_t *s, uint8_t *mfr, uint8_t *dev)
{
	uint8_t prev = cpu_stop(s);
	unlock(s);
	br_rom_busw(s, 0x5555, 0x90);
	*mfr = rd(s, 0);
	*dev = rd(s, 1);
	br_rom_busw(s, 0, 0xF0);
	br_cpu_ctl(s, prev);
	return ST_OK;
}

/* DQ6 toggles on every read while the chip is busy */
static int wait_toggle(sysctl_t *s, uint32_t addr, uint32_t timeout_ms)
{
	uint32_t start = s->hal->now_ms(s->ctx);
	uint8_t a = rd(s, addr);
	for (;;) {
		uint8_t b = rd(s, addr);
		if (((a ^ b) & 0x40) == 0)
			return ST_OK;
		if (s->hal->now_ms(s->ctx) - start > timeout_ms)
			return ST_TIMEOUT;
		a = b;
		s->hal->delay_us(s->ctx, 500);
	}
}

int rom_erase(sysctl_t *s, uint32_t addr, uint32_t len)
{
	uint8_t prev = cpu_stop(s);
	int r = ST_OK;
	if (len == 0) {
		unlock(s);
		br_rom_busw(s, 0x5555, 0x80);
		unlock(s);
		br_rom_busw(s, 0x5555, 0x10);
		r = wait_toggle(s, 0, 200);
	} else {
		uint32_t end = addr + len;
		for (uint32_t sa = addr & ~(SECTOR - 1); sa < end && r == ST_OK; sa += SECTOR) {
			unlock(s);
			br_rom_busw(s, 0x5555, 0x80);
			unlock(s);
			br_rom_busw(s, sa, 0x30);
			r = wait_toggle(s, sa, 50);
		}
	}
	br_cpu_ctl(s, prev);
	return r;
}

/* one byte: JEDEC program, then poll DQ7 until it shows the true data */
static bool program_byte(sysctl_t *s, uint32_t addr, uint8_t v)
{
	unlock(s);
	br_rom_busw(s, 0x5555, 0xA0);
	br_rom_busw(s, addr, v);
	for (int i = 0; i < PROGRAM_POLLS; i++) {
		uint8_t b = rd(s, addr);
		if (((b ^ v) & 0x80) == 0)
			return rd(s, addr) == v;          /* DQ7 settles a read before the rest */
	}
	return false;
}

int rom_program(sysctl_t *s, uint32_t addr, const uint8_t *data, int n, uint32_t *bad)
{
	uint8_t prev = cpu_stop(s);
	int r = ST_OK;
	for (int i = 0; i < n; i++) {
		if (data[i] == 0xFF)
			continue;                         /* erased already reads $FF */
		if (!program_byte(s, addr + (uint32_t)i, data[i]) &&
		    !program_byte(s, addr + (uint32_t)i, data[i])) {
			*bad = addr + (uint32_t)i;
			r = ST_VERIFY;
			break;
		}
	}
	br_cpu_ctl(s, prev);
	return r;
}
