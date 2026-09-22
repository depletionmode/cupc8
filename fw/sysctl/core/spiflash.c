/*
 * The FPGAs' configuration flashes (W25Q, doc/hardware/sysctl.md): 4 KB
 * sector erase, 256-byte page program. `target` picks the bus: FL0 is the
 * chipset's flash, FL1 the CPU card's. The FPGA must be held in reset.
 */
#include "sysctl.h"

#define SECTOR 4096u
#define PAGE   256u

static int bus(int target)
{
	return target == FPGA_CHIPSET ? SPI_FL0 : SPI_FL1;
}

static void cmd(sysctl_t *s, int target, const uint8_t *tx, uint8_t *rx, int n)
{
	s->hal->spi_select(s->ctx, bus(target));
	s->hal->spi_xfer(s->ctx, tx, rx, n);
	s->hal->spi_select(s->ctx, SPI_NONE);
}

static void write_enable(sysctl_t *s, int target)
{
	uint8_t c = 0x06;
	cmd(s, target, &c, 0, 1);
}

static int wait_ready(sysctl_t *s, int target, uint32_t timeout_ms)
{
	uint32_t start = s->hal->now_ms(s->ctx);
	for (;;) {
		uint8_t tx[2] = {0x05, 0}, rx[2];
		cmd(s, target, tx, rx, 2);
		if (!(rx[1] & 0x01))
			return ST_OK;
		if (s->hal->now_ms(s->ctx) - start > timeout_ms)
			return ST_TIMEOUT;
		s->hal->delay_us(s->ctx, 100);
	}
}

void fl_id(sysctl_t *s, int target, uint8_t id[3])
{
	uint8_t tx[4] = {0x9F}, rx[4];
	cmd(s, target, tx, rx, 4);
	id[0] = rx[1];
	id[1] = rx[2];
	id[2] = rx[3];
}

void fl_read(sysctl_t *s, int target, uint32_t addr, uint8_t *data, int n)
{
	uint8_t hdr[4] = {0x03, (uint8_t)(addr >> 16), (uint8_t)(addr >> 8), (uint8_t)addr};
	s->hal->spi_select(s->ctx, bus(target));
	s->hal->spi_xfer(s->ctx, hdr, 0, 4);
	s->hal->spi_xfer(s->ctx, 0, data, n);
	s->hal->spi_select(s->ctx, SPI_NONE);
}

int fl_erase(sysctl_t *s, int target, uint32_t addr, uint32_t len)
{
	uint32_t end = addr + len;
	for (uint32_t sa = addr & ~(SECTOR - 1); sa < end; sa += SECTOR) {
		uint8_t tx[4] = {0x20, (uint8_t)(sa >> 16), (uint8_t)(sa >> 8), (uint8_t)sa};
		write_enable(s, target);
		cmd(s, target, tx, 0, 4);
		int r = wait_ready(s, target, 500);   /* tSE max 400 ms */
		if (r != ST_OK)
			return r;
	}
	return ST_OK;
}

int fl_program(sysctl_t *s, int target, uint32_t addr, const uint8_t *data, int n, uint32_t *bad)
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
		write_enable(s, target);
		s->hal->spi_select(s->ctx, bus(target));
		s->hal->spi_xfer(s->ctx, hdr, 0, 4);
		s->hal->spi_xfer(s->ctx, data + done, 0, k);
		s->hal->spi_select(s->ctx, SPI_NONE);
		int r = wait_ready(s, target, 10);    /* tPP max 3 ms */
		if (r != ST_OK)
			return r;
		fl_read(s, target, a, back, k);
		for (int i = 0; i < k; i++)
			if (back[i] != data[done + i]) {
				*bad = a + (uint32_t)i;
				return ST_VERIFY;
			}
		done += k;
	}
	return ST_OK;
}
