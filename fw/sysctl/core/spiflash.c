/*
 * The W25Q32 configuration flash (doc/hardware/sysctl.md, "Configuration
 * flash"): 4 KB sector erase, 256-byte page program.
 */
#include "sysctl.h"

#define SECTOR 4096u
#define PAGE   256u

static void cmd(sysctl_t *s, const uint8_t *tx, uint8_t *rx, int n)
{
	s->hal->spi_select(s->ctx, SPI_FLASH);
	s->hal->spi_xfer(s->ctx, tx, rx, n);
	s->hal->spi_select(s->ctx, SPI_NONE);
}

static void write_enable(sysctl_t *s)
{
	uint8_t c = 0x06;
	cmd(s, &c, 0, 1);
}

static int wait_ready(sysctl_t *s, uint32_t timeout_ms)
{
	uint32_t start = s->hal->now_ms(s->ctx);
	for (;;) {
		uint8_t tx[2] = {0x05, 0}, rx[2];
		cmd(s, tx, rx, 2);
		if (!(rx[1] & 0x01))
			return ST_OK;
		if (s->hal->now_ms(s->ctx) - start > timeout_ms)
			return ST_TIMEOUT;
		s->hal->delay_us(s->ctx, 100);
	}
}

void fl_read(sysctl_t *s, uint32_t addr, uint8_t *data, int n)
{
	uint8_t hdr[4] = {0x03, (uint8_t)(addr >> 16), (uint8_t)(addr >> 8), (uint8_t)addr};
	s->hal->spi_select(s->ctx, SPI_FLASH);
	s->hal->spi_xfer(s->ctx, hdr, 0, 4);
	s->hal->spi_xfer(s->ctx, 0, data, n);
	s->hal->spi_select(s->ctx, SPI_NONE);
}

int fl_erase(sysctl_t *s, uint32_t addr, uint32_t len)
{
	uint32_t end = addr + len;
	for (uint32_t sa = addr & ~(SECTOR - 1); sa < end; sa += SECTOR) {
		uint8_t tx[4] = {0x20, (uint8_t)(sa >> 16), (uint8_t)(sa >> 8), (uint8_t)sa};
		write_enable(s);
		cmd(s, tx, 0, 4);
		int r = wait_ready(s, 500);           /* tSE max 400 ms */
		if (r != ST_OK)
			return r;
	}
	return ST_OK;
}

int fl_program(sysctl_t *s, uint32_t addr, const uint8_t *data, int n, uint32_t *bad)
{
	uint8_t back[PAGE];
	int done = 0;
	while (done < n) {
		/* a page program must not cross a page boundary: it would wrap */
		uint32_t a = addr + (uint32_t)done;
		int k = (int)(PAGE - (a & (PAGE - 1)));
		if (k > n - done)
			k = n - done;
		uint8_t hdr[4] = {0x02, (uint8_t)(a >> 16), (uint8_t)(a >> 8), (uint8_t)a};
		write_enable(s);
		s->hal->spi_select(s->ctx, SPI_FLASH);
		s->hal->spi_xfer(s->ctx, hdr, 0, 4);
		s->hal->spi_xfer(s->ctx, data + done, 0, k);
		s->hal->spi_select(s->ctx, SPI_NONE);
		int r = wait_ready(s, 10);            /* tPP max 3 ms */
		if (r != ST_OK)
			return r;
		fl_read(s, a, back, k);
		for (int i = 0; i < k; i++)
			if (back[i] != data[done + i]) {
				*bad = a + (uint32_t)i;
				return ST_VERIFY;
			}
		done += k;
	}
	return ST_OK;
}
