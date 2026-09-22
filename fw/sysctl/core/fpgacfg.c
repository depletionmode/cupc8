/*
 * iCE40 SPI-slave configuration (doc/hardware/sysctl.md, "iCE40 SPI-slave
 * load"). The bitstream is staged in RAM and sent in one SS-low burst: the
 * flash it comes from is on the same SPI bus, and TN1248 does not promise
 * that SS may rise in the middle of a bitstream.
 */
#include "sysctl.h"

#include <string.h>

static uint8_t image[FPGA_MAX_IMAGE];
static uint32_t image_len;

static const struct {
	int spi, creset, cdone;
} port[2] = {
	{SPI_CHIPSET_CFG, PIN_CHIPSET_CRESET, PIN_CHIPSET_CDONE},
	{SPI_CPUCARD_CFG, PIN_CPUCARD_CRESET, PIN_CPUCARD_CDONE},
};

uint32_t crc32_ieee(uint32_t crc, const uint8_t *data, int n)
{
	crc = ~crc;
	for (int i = 0; i < n; i++) {
		crc ^= data[i];
		for (int b = 0; b < 8; b++)
			crc = crc >> 1 ^ (0xEDB88320u & -(crc & 1));
	}
	return ~crc;
}

static int load(sysctl_t *s, int target)
{
	const sysctl_hal *h = s->hal;
	uint8_t dummy[13] = {0};

	s->cdone &= (uint8_t)~(1u << target);
	h->spi_select(s->ctx, port[target].spi);       /* SS low selects slave mode */
	h->pin_write(s->ctx, port[target].creset, false);
	h->delay_us(s->ctx, 2);
	h->pin_write(s->ctx, port[target].creset, true);
	h->delay_us(s->ctx, 1200);                      /* CRAM clear, HX4K */
	h->spi_select(s->ctx, SPI_NONE);
	h->spi_xfer(s->ctx, dummy, 0, 1);               /* 8 clocks with SS high */
	h->spi_select(s->ctx, port[target].spi);
	h->spi_xfer(s->ctx, image, 0, (int)image_len);
	h->spi_select(s->ctx, SPI_NONE);
	h->spi_xfer(s->ctx, dummy, 0, sizeof dummy);    /* ≥ 100 clocks to start up */
	if (!h->pin_read(s->ctx, port[target].cdone))
		return ST_TIMEOUT;
	s->cdone |= (uint8_t)(1u << target);
	return ST_OK;
}

int fpga_boot(sysctl_t *s, int target)
{
	uint8_t hdr[16];
	uint32_t slot = (uint32_t)target * FL_SLOT_SIZE;

	if (target < 0 || target > 1)
		return ST_ARG;
	fl_read(s, slot, hdr, sizeof hdr);
	uint32_t len = hdr[4] | hdr[5] << 8 | hdr[6] << 16 | (uint32_t)hdr[7] << 24;
	uint32_t crc = hdr[8] | hdr[9] << 8 | hdr[10] << 16 | (uint32_t)hdr[11] << 24;
	if (memcmp(hdr, "C8BS", 4) != 0 || len == 0 || len > FPGA_MAX_IMAGE)
		return ST_NOIMAGE;
	fl_read(s, slot + FL_IMAGE_OFS, image, (int)len);
	if (crc32_ieee(0, image, (int)len) != crc)
		return ST_NOIMAGE;
	image_len = len;
	return load(s, target);
}

void fpga_load_begin(sysctl_t *s, int target)
{
	(void)s;
	(void)target;
	image_len = 0;
}

int fpga_load_data(sysctl_t *s, int target, const uint8_t *data, int n)
{
	(void)s;
	(void)target;
	if (image_len + (uint32_t)n > FPGA_MAX_IMAGE)
		return ST_ARG;
	memcpy(image + image_len, data, (size_t)n);
	image_len += (uint32_t)n;
	return ST_OK;
}

int fpga_load_end(sysctl_t *s, int target)
{
	if (target < 0 || target > 1 || image_len == 0)
		return ST_ARG;
	return load(s, target);
}
