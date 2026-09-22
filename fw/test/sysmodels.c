#include "sysmodels.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------ SST39 */

void sst39_init(sst39_t *m)
{
	memset(m, 0, sizeof *m);
	memset(m->mem, 0xFF, sizeof m->mem);
	m->device_id = 0xD7;
	m->t_bp = 20;
	m->t_se = 25000;
	m->t_sce = 100000;
}

uint8_t sst39_read(sst39_t *m, uint32_t addr, uint64_t now)
{
	addr &= (1u << 19) - 1;
	if (now < m->busy_until) {
		m->toggle ^= 0x40;                /* DQ6 toggles on every read */
		return (uint8_t)((m->busy_kind == 1 ? m->busy_d7 : 0) | m->toggle);
	}
	if (m->id_mode)
		return addr % 2 == 0 ? 0xBF : m->device_id;
	return m->mem[addr];
}

void sst39_write(sst39_t *m, uint32_t addr, uint8_t d, uint64_t now)
{
	uint32_t low15 = addr & 0x7FFF;
	addr &= (1u << 19) - 1;
	m->writes++;
	if (now < m->busy_until)
		return;                           /* writes while busy are ignored */
	/* single-cycle ID exit, except as the data of a program sequence (step 3),
	 * where $F0 is just a byte to program */
	if (d == 0xF0 && m->step != 2 && m->step != 3) {
		m->id_mode = false;
		m->step = 0;
		return;
	}
	switch (m->step) {
	case 0:
		m->step = low15 == 0x5555 && d == 0xAA ? 1 : 0;
		break;
	case 1:
		m->step = low15 == 0x2AAA && d == 0x55 ? 2 : 0;
		break;
	case 2:
		m->step = 0;
		if (low15 == 0x5555) {
			switch (d) {
			case 0xA0: m->step = 3; break;
			case 0x80: m->erase_armed = true; break;
			case 0x90: m->id_mode = true; break;
			case 0xF0: m->id_mode = false; break;
			case 0x10:
				if (m->erase_armed) {
					m->erase_armed = false;
					memset(m->mem, 0xFF, sizeof m->mem);
					m->busy_until = now + m->t_sce;
					m->busy_kind = 2;
				}
				break;
			case 0x30:
				m->erase_armed = false;
				break;
			}
		} else if (m->erase_armed && d == 0x30) {
			m->erase_armed = false;
			memset(m->mem + (addr & ~4095u), 0xFF, 4096);
			m->busy_until = now + m->t_se;
			m->busy_kind = 2;
		}
		break;
	case 3: {
		uint8_t keep = addr == m->stuck_addr ? m->stuck_mask : 0;
		m->mem[addr] &= (uint8_t)(d | keep);  /* NOR: program only clears bits */
		m->busy_d7 = (uint8_t)(~d & 0x80);
		m->busy_until = now + m->t_bp;
		m->busy_kind = 1;
		m->step = 0;
		break;
	}
	}
}

/* ----------------------------------------------------------------- W25Q32 */

void w25q_init(w25q_t *m)
{
	memset(m, 0, sizeof *m);
	memset(m->mem, 0xFF, sizeof m->mem);
	m->stuck_addr = 0xFFFFFFFF;
}

static bool w25q_busy(w25q_t *m, uint64_t now) { return now < m->busy_until; }

void w25q_select(w25q_t *m, bool sel, uint64_t now)
{
	if (sel) {
		m->n = 0;
		m->page_n = 0;
		return;
	}
	/* program and erase happen when /CS rises */
	if (m->n == 0 || w25q_busy(m, now))
		return;
	if (m->cmd == 0x02 && m->n >= 5 && m->wel) {
		uint32_t base = m->addr & ~0xFFu;
		for (int i = 0; i < m->page_n; i++) {
			/* past the end of the page the address wraps within it */
			uint32_t a = base | ((m->addr + (uint32_t)i) & 0xFF);
			uint8_t keep = a == m->stuck_addr ? m->stuck_mask : 0;
			m->mem[a] &= (uint8_t)(m->page[i] | keep);
		}
		m->busy_until = now + 700;
		m->wel = false;
	} else if (m->cmd == 0x20 && m->n == 4 && m->wel) {
		memset(m->mem + (m->addr & ~4095u), 0xFF, 4096);
		m->busy_until = now + 45000;
		m->wel = false;
	} else if (m->cmd == 0x06 && m->n == 1) {
		m->wel = true;
	} else if (m->cmd == 0x04 && m->n == 1) {
		m->wel = false;
	}
}

uint8_t w25q_byte(w25q_t *m, uint8_t mosi, uint64_t now)
{
	uint8_t out = 0xFF;
	int i = m->n++;
	if (i == 0) {
		m->cmd = mosi;
		m->addr = 0;
		/* only the status register answers while busy */
		if (w25q_busy(m, now) && mosi != 0x05) {
			m->violations++;
			m->cmd = 0;
		}
		return out;
	}
	switch (m->cmd) {
	case 0x05:
		out = (uint8_t)((w25q_busy(m, now) ? 0x01 : 0) | (m->wel ? 0x02 : 0));
		break;
	case 0x9F: {
		static const uint8_t id[3] = {0xEF, 0x40, 0x16};
		out = i <= 3 ? id[i - 1] : 0xFF;
		break;
	}
	case 0x03:
	case 0x02:
	case 0x20:
		if (i <= 3) {
			m->addr = m->addr << 8 | mosi;
		} else if (m->cmd == 0x03) {
			out = m->mem[(m->addr + (uint32_t)(i - 4)) & ((4u << 20) - 1)];
		} else if (m->cmd == 0x02 && m->page_n < 256) {
			m->page[m->page_n++] = mosi;
		}
		break;
	}
	return out;
}

/* ------------------------------------------- iCE40 booting from its flash */

void ice40_init(ice40_t *m, w25q_t *flash, const uint8_t *expect, int len)
{
	memset(m, 0, sizeof *m);
	m->flash = flash;
	m->expect = expect;
	m->expect_len = len;
	m->creset = true;
	m->booting = true;                    /* powered up: boots straight away */
	m->boot_us = 200000;
}

void ice40_creset(ice40_t *m, bool level, uint64_t now)
{
	if (!level) {
		m->cdone = false;
		m->booting = false;
	} else if (!m->creset) {
		m->booting = true;                /* released: read the flash again */
		m->t_release = now;
	}
	m->creset = level;
}

void ice40_tick(ice40_t *m, uint64_t now)
{
	if (!m->booting || now - m->t_release < m->boot_us)
		return;
	m->booting = false;
	m->cdone = memcmp(m->flash->mem, m->expect, (size_t)m->expect_len) == 0;
	if (m->cdone)
		m->loads++;
}

/* ----------------------------------------------------------------- bridge */

enum { B_CMD, B_ARG, B_WDATA, B_STREAM, B_TRACE, B_CTL, B_IGNORE };

void bridge_init(bridge_t *m, sst39_t *rom)
{
	memset(m, 0, sizeof *m);
	m->rom = rom;
	for (int i = 0; i < 65536; i++)
		m->ram[i] = (uint8_t)(i * 13 + 5);    /* power-up contents are not zero */
}

void bridge_select(bridge_t *m, bool sel)
{
	(void)sel;
	m->state = B_CMD;                     /* /CS high resets the frame */
	m->tx_cur = 0;
	m->tx_next = 0;
}

static uint8_t bridge_status(bridge_t *m)
{
	/* bits 5:3 are reserved: presence and ID are on sysctl's expander */
	return (uint8_t)((m->ctl & 0x01) | (m->ctl & 0x40 ? 0x80 : 0));
}

static uint8_t mem_rd(bridge_t *m, uint64_t now)
{
	return m->cmd == 0x03 ? sst39_read(m->rom, m->addr, now) : m->ram[m->addr & 0xFFFF];
}

/* one SPI byte; the response to byte k goes out in byte k+2 (see bridge.vhd) */
uint8_t bridge_byte(bridge_t *m, uint8_t b, uint64_t now)
{
	if (!m->configured)
		return 0xFF;                      /* an unconfigured FPGA leaves MISO floating high */
	uint8_t out = m->tx_cur;
	int next = -1;

	switch (m->state) {
	case B_CMD:
		m->cmd = b;
		m->argn = 0;
		m->addr = 0;
		switch (b) {
		case 0x01: case 0x02: case 0x03: case 0x04: m->state = B_ARG; break;
		case 0x05: next = bridge_status(m); break;
		case 0x06: next = m->gpo; break;
		case 0x07: m->state = B_CTL; break;
		case 0x08:
			m->tcount = m->trace_count;
			m->lost_snap = m->trace_lost;
			m->trace_lost = false;
			next = m->tcount & 0xFF;
			m->thdr = true;
			m->tbyte = 0;
			m->state = B_TRACE;
			break;
		default: m->state = B_IGNORE; break;
		}
		break;
	case B_ARG: {
		int i = m->argn++;
		if (m->cmd == 0x01 || m->cmd == 0x02) {
			if (i < 2) {
				m->addr |= (uint32_t)b << (8 * i);
			} else {
				m->len = b + 1;
				if (m->cmd == 0x01) {
					m->state = B_WDATA;
				} else {
					next = mem_rd(m, now);
					m->state = B_STREAM;
				}
			}
		} else if (i < 3) {
			m->addr |= (uint32_t)b << (8 * i);
		} else if (m->cmd == 0x04) {
			m->ctl_when_busw = m->ctl;
			sst39_write(m->rom, m->addr, b, now);
			m->state = B_IGNORE;
		} else {
			m->len = b + 1;
			next = mem_rd(m, now);
			m->state = B_STREAM;
		}
		break;
	}
	case B_WDATA:
		if (m->len > 0) {
			m->ram[m->addr & 0xFFFF] = b;
			m->addr++;
			m->len--;
		}
		break;
	case B_STREAM:
		if (m->len > 1) {
			m->addr++;
			m->len--;
			next = mem_rd(m, now);
		} else {
			m->len = 0;
			m->state = B_IGNORE;
		}
		break;
	case B_TRACE:
		if (m->thdr) {
			next = (m->lost_snap ? 0x80 : 0) | (m->tcount >> 8 & 0x03);
			m->thdr = false;
		} else if (m->tcount > 0) {
			uint32_t e = m->trace[m->trace_head];
			next = (int)(e >> (8 * m->tbyte) & 0xFF);
			if (++m->tbyte == 4) {
				m->tbyte = 0;
				m->trace_head = (m->trace_head + 1) % 512;
				m->trace_count--;
				m->tcount--;
			}
		}
		break;
	case B_CTL:
		m->ctl = b;
		m->ctl_writes++;
		m->state = B_IGNORE;
		break;
	}
	m->tx_cur = m->tx_next;
	m->tx_next = next < 0 ? 0 : (uint8_t)next;
	return out;
}

void bridge_trace_push(bridge_t *m, uint16_t a, uint8_t d, uint8_t flags)
{
	if (m->trace_count == 512) {
		m->trace_head = (m->trace_head + 1) % 512;   /* overwrite the oldest */
		m->trace_count--;
		m->trace_lost = true;
	}
	int tail = (m->trace_head + m->trace_count) % 512;
	m->trace[tail] = a | (uint32_t)d << 16 | (uint32_t)flags << 24;
	m->trace_count++;
}

/* ---------------------------------------------------------------- TCA9555 */

void tca_init(tca_t *m, uint8_t pulled0, uint8_t pulled1)
{
	memset(m, 0, sizeof *m);
	m->reg[2] = m->reg[3] = 0xFF;         /* output registers reset high */
	m->reg[6] = m->reg[7] = 0xFF;         /* every pin an input */
	m->pulled[0] = pulled0;
	m->pulled[1] = pulled1;
	m->ext[0] = pulled0;
	m->ext[1] = pulled1;
}

uint8_t tca_pins(tca_t *m, int port)
{
	uint8_t cfg = m->reg[6 + port];
	return (uint8_t)((m->reg[2 + port] & ~cfg) | (m->ext[port] & cfg));
}

int tca_write(tca_t *m, const uint8_t *data, int n)
{
	if (n < 1 || data[0] > 7)
		return -1;
	/* registers come in pairs; the pointer toggles within a pair */
	uint8_t r = data[0];
	for (int i = 1; i < n; i++) {
		if (r >= 2)                       /* input registers are read-only */
			m->reg[r] = data[i];
		r ^= 1;
	}
	return 0;
}

int tca_read(tca_t *m, uint8_t reg, uint8_t *data, int n)
{
	if (reg > 7)
		return -1;
	m->reg[0] = tca_pins(m, 0);
	m->reg[1] = tca_pins(m, 1);
	for (int i = 0; i < n; i++) {
		data[i] = m->reg[reg];
		reg ^= 1;
	}
	return 0;
}
