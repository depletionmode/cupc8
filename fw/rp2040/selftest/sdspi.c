/*
 * EMU-008 (on firmware): the SD card model in the native emulator driven by
 * the pico-sdk's own hardware_spi and hardware_dma code on SPI1, on the
 * storage card's pins (fw/storage/pins.h). Not the storage card firmware:
 * a small, independent SD SPI-mode host, so the model is proven against the
 * real SDK before that firmware exists. The harness (test/emu/test_sdspi.mjs)
 * gives it an image whose block n is filled with (n + i) & 0xff.
 *
 * Waits for card detect, initialises at 400 kHz (CMD0, CMD8, ACMD41, CMD58),
 * goes to 12.5 MHz, reads CSD, reads block 3 by polling, writes block 5
 * with the pattern 0xa5 ^ i and times the busy, reads block 5 back by DMA.
 * Prints "SDSPI PASS busy=<us> ccs=<0|1> blocks=<n>" or "SDSPI FAIL <why>".
 */
#include <stdio.h>
#include <string.h>

#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"

#define SD spi1

static uint8_t buf[512];

static void cs(bool low) { gpio_put(PIN_SD_NCS, !low); }

static uint8_t xchg(uint8_t b)
{
	uint8_t r;
	spi_write_read_blocking(SD, &b, &r, 1);
	return r;
}

static uint8_t crc7(const uint8_t *p, int n)
{
	uint8_t crc = 0;
	for (int i = 0; i < n; i++) {
		uint8_t b = p[i];
		for (int j = 0; j < 8; j++) {
			crc <<= 1;
			if ((b ^ crc) & 0x80)
				crc ^= 0x09;
			b <<= 1;
		}
	}
	return crc & 0x7f;
}

/* wait for DO high (not busy), up to `us` */
static bool ready(uint32_t us)
{
	absolute_time_t end = make_timeout_time_us(us);
	while (xchg(0xff) != 0xff)
		if (time_reached(end))
			return false;
	return true;
}

static uint8_t cmd(uint8_t idx, uint32_t arg)
{
	uint8_t f[6] = {0x40 | idx, arg >> 24, arg >> 16, arg >> 8, arg, 0};
	f[5] = (uint8_t)(crc7(f, 5) << 1 | 1);
	if (!ready(500000))
		return 0xff;
	spi_write_blocking(SD, f, 6);
	uint8_t r = 0xff;
	for (int i = 0; i < 9 && (r & 0x80); i++)
		r = xchg(0xff);
	return r;
}

static bool token(void)
{
	absolute_time_t end = make_timeout_time_ms(100);
	uint8_t t;
	while ((t = xchg(0xff)) == 0xff)
		if (time_reached(end))
			return false;
	return t == 0xfe;
}

static bool fail(const char *why)
{
	printf("SDSPI FAIL %s\n", why);
	return false;
}

static bool run(void)
{
	cs(false);
	for (int i = 0; i < 10; i++)
		xchg(0xff);
	cs(true);
	if (cmd(0, 0) != 0x01)
		return fail("CMD0");
	if (cmd(8, 0x1aa) != 0x01)
		return fail("CMD8");
	uint8_t r7[4];
	spi_read_blocking(SD, 0xff, r7, 4);
	if (r7[2] != 1 || r7[3] != 0xaa)
		return fail("R7");
	absolute_time_t end = make_timeout_time_ms(1000);
	uint8_t r;
	do {
		cmd(55, 0);
		r = cmd(41, 1u << 30);
	} while (r == 0x01 && !time_reached(end));
	if (r != 0)
		return fail("ACMD41");
	if (cmd(58, 0) != 0)
		return fail("CMD58");
	uint8_t ocr[4];
	spi_read_blocking(SD, 0xff, ocr, 4);
	int ccs = (ocr[0] >> 6) & 1;
	spi_set_baudrate(SD, 12500000);

	if (cmd(9, 0) != 0 || !token())
		return fail("CMD9");
	uint8_t csd[18];
	spi_read_blocking(SD, 0xff, csd, 18);
	uint32_t blocks;
	if ((csd[0] >> 6) == 1) {
		blocks = (((uint32_t)(csd[7] & 0x3f) << 16 | csd[8] << 8 | csd[9]) + 1) * 1024;
	} else {
		uint32_t c_size = (uint32_t)(csd[6] & 3) << 10 | csd[7] << 2 | csd[8] >> 6;
		uint32_t mult = (uint32_t)(csd[9] & 3) << 1 | csd[10] >> 7;
		uint32_t bl = csd[5] & 15;
		blocks = (c_size + 1) << (mult + 2) << bl >> 9;
	}
	uint32_t unit = ccs ? 1 : 512;

	/* block 3 by polling */
	if (cmd(17, 3 * unit) != 0 || !token())
		return fail("CMD17");
	spi_read_blocking(SD, 0xff, buf, 512);
	xchg(0xff);
	xchg(0xff);
	for (int i = 0; i < 512; i++)
		if (buf[i] != (uint8_t)(3 + i))
			return fail("block 3 data");

	/* block 5 written */
	for (int i = 0; i < 512; i++)
		buf[i] = (uint8_t)(0xa5 ^ i);
	if (cmd(24, 5 * unit) != 0)
		return fail("CMD24");
	xchg(0xff);
	xchg(0xfe);
	spi_write_blocking(SD, buf, 512);
	xchg(0xff);
	xchg(0xff);
	if ((xchg(0xff) & 0x1f) != 0x05)
		return fail("data response");
	uint64_t t0 = time_us_64();
	if (!ready(500000))
		return fail("busy");
	uint32_t busy = (uint32_t)(time_us_64() - t0);

	/* block 5 read back by DMA: TX $FF from a fixed byte, RX into buf */
	memset(buf, 0, sizeof buf);
	if (cmd(17, 5 * unit) != 0 || !token())
		return fail("CMD17 (2)");
	static uint8_t ff = 0xff;
	int tx = dma_claim_unused_channel(true), rx = dma_claim_unused_channel(true);
	dma_channel_config c = dma_channel_get_default_config(tx);
	channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
	channel_config_set_read_increment(&c, false);
	channel_config_set_dreq(&c, spi_get_dreq(SD, true));
	dma_channel_configure(tx, &c, &spi_get_hw(SD)->dr, &ff, 512, false);
	c = dma_channel_get_default_config(rx);
	channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
	channel_config_set_read_increment(&c, false);
	channel_config_set_write_increment(&c, true);
	channel_config_set_dreq(&c, spi_get_dreq(SD, false));
	dma_channel_configure(rx, &c, buf, &spi_get_hw(SD)->dr, 512, false);
	dma_start_channel_mask((1u << tx) | (1u << rx));
	dma_channel_wait_for_finish_blocking(rx);
	xchg(0xff);
	xchg(0xff);
	for (int i = 0; i < 512; i++)
		if (buf[i] != (uint8_t)(0xa5 ^ i))
			return fail("block 5 read back by DMA");
	cs(false);
	xchg(0xff);
	printf("SDSPI PASS busy=%lu ccs=%d blocks=%lu\n", (unsigned long)busy, ccs, (unsigned long)blocks);
	return true;
}

int main(void)
{
	stdio_init_all();
	spi_init(SD, 400000);
	gpio_set_function(PIN_SD_SCK, GPIO_FUNC_SPI);
	gpio_set_function(PIN_SD_MOSI, GPIO_FUNC_SPI);
	gpio_set_function(PIN_SD_MISO, GPIO_FUNC_SPI);
	gpio_init(PIN_SD_NCS);
	gpio_put(PIN_SD_NCS, 1);
	gpio_set_dir(PIN_SD_NCS, GPIO_OUT);
	gpio_init(PIN_SD_NDETECT);
	gpio_pull_up(PIN_SD_NDETECT);
	printf("SDSPI waiting for a card\n");
	while (gpio_get(PIN_SD_NDETECT))
		sleep_ms(1);
	sleep_ms(2);
	run();
	for (;;)
		sleep_ms(1000);
}
