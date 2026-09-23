/*
 * The chipset's bus bridge (doc/hardware/memory-map.md, "In-system
 * programming"). One command per BR_CS_n frame; every response is preceded
 * by one dummy byte. Transfers are at most 256 bytes a frame.
 */
#include "sysctl.h"

#include <string.h>

static void frame(sysctl_t *s, const uint8_t *tx, uint8_t *rx, int n)
{
	s->hal->spi_select(s->ctx, SPI_BRIDGE);
	s->hal->spi_xfer(s->ctx, tx, rx, n);
	s->hal->spi_select(s->ctx, SPI_NONE);
}

static uint8_t one_byte(sysctl_t *s, uint8_t cmd)
{
	uint8_t tx[3] = {cmd}, rx[3];
	frame(s, tx, rx, 3);                  /* cmd, dummy, answer */
	return rx[2];
}

uint8_t br_status(sysctl_t *s) { return one_byte(s, 0x05); }
uint8_t br_gpo(sysctl_t *s) { return one_byte(s, 0x06); }

void br_cpu_ctl(sysctl_t *s, uint8_t ctl)
{
	uint8_t tx[2] = {0x07, ctl};
	frame(s, tx, 0, 2);
}

void br_ram_write(sysctl_t *s, uint16_t addr, const uint8_t *data, int n)
{
	uint8_t tx[4 + 256];
	while (n > 0) {
		int k = n > 256 ? 256 : n;
		tx[0] = 0x01;
		tx[1] = (uint8_t)addr;
		tx[2] = (uint8_t)(addr >> 8);
		tx[3] = (uint8_t)(k - 1);
		memcpy(tx + 4, data, (size_t)k);
		frame(s, tx, 0, 4 + k);
		addr = (uint16_t)(addr + k);
		data += k;
		n -= k;
	}
}

void br_ram_read(sysctl_t *s, uint16_t addr, uint8_t *data, int n)
{
	static uint8_t tx[5 + 256], rx[5 + 256];     /* not on the RP2040's 2 KB stack */
	while (n > 0) {
		int k = n > 256 ? 256 : n;
		/* a frame may wrap past $ffff; the bridge's address does too */
		tx[0] = 0x02;
		tx[1] = (uint8_t)addr;
		tx[2] = (uint8_t)(addr >> 8);
		tx[3] = (uint8_t)(k - 1);
		memset(tx + 4, 0, (size_t)k + 1);
		frame(s, tx, rx, 5 + k);
		memcpy(data, rx + 5, (size_t)k);
		addr = (uint16_t)(addr + k);
		data += k;
		n -= k;
	}
}

void br_rom_read(sysctl_t *s, uint32_t addr, uint8_t *data, int n)
{
	static uint8_t tx[6 + 256], rx[6 + 256];
	while (n > 0) {
		int k = n > 256 ? 256 : n;
		tx[0] = 0x03;
		tx[1] = (uint8_t)addr;
		tx[2] = (uint8_t)(addr >> 8);
		tx[3] = (uint8_t)(addr >> 16);
		tx[4] = (uint8_t)(k - 1);
		memset(tx + 5, 0, (size_t)k + 1);
		frame(s, tx, rx, 6 + k);
		memcpy(data, rx + 6, (size_t)k);
		addr += (uint32_t)k;
		data += k;
		n -= k;
	}
}

void br_rom_busw(sysctl_t *s, uint32_t addr, uint8_t data)
{
	uint8_t tx[5] = {0x04, (uint8_t)addr, (uint8_t)(addr >> 8), (uint8_t)(addr >> 16), data};
	frame(s, tx, 0, 5);
}

int br_trace(sysctl_t *s, uint8_t *out)
{
	/* the count comes first, then that many entries in the same frame.
	 * static: 2 KB is the whole default stack on the RP2040 */
	static uint8_t tx[4 + 512 * 4], rx[4 + 512 * 4];
	tx[0] = 0x08;
	s->hal->spi_select(s->ctx, SPI_BRIDGE);
	s->hal->spi_xfer(s->ctx, tx, rx, 4);      /* cmd, dummy, count lo, count hi */
	int count = (rx[2] | rx[3] << 8) & 0x3ff;
	if (count > 512)
		count = 512;
	s->hal->spi_xfer(s->ctx, tx + 4, rx + 4, count * 4);
	s->hal->spi_select(s->ctx, SPI_NONE);
	out[0] = rx[2];
	out[1] = rx[3];
	memcpy(out + 2, rx + 4, (size_t)count * 4);
	return 2 + count * 4;
}
