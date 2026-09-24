/*
 * SD card, SPI mode (SD Physical Layer Simplified Specification, section 7):
 * CMD0, CMD8, ACMD41 (CMD55 + CMD41), CMD58 to bring it up, CMD9 for its
 * size and write-protect bits, CMD17/CMD24 single-block read and write, and
 * the busy wait after a write. Commands carry their CRC7; data CRCs are not
 * checked (CRC is off in SPI mode unless CMD59 turns it on).
 */
#include "sd_spi.h"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"

#define SD_SPI      spi1
#define SLOW_HZ     400000u             /* identification: <= 400 kHz */
#define FAST_HZ     12500000u           /* data transfer: <= 25 MHz */
#define ACMD        0x80                /* a CMD55 first */

volatile uint32_t sd_spi_last_access;
static bool block_addr;                 /* SDHC/SDXC: the argument is an LBA, not a byte offset */
static uint32_t n_sectors;
static bool protect;

static uint32_t now_ms(void) { return to_ms_since_boot(get_absolute_time()); }

static bool card_in(void) { return !gpio_get(PIN_SD_NDETECT); }

static uint8_t xfer(uint8_t out)
{
	uint8_t in;
	spi_write_read_blocking(SD_SPI, &out, &in, 1);
	return in;
}

/* the card holds DO low while it is busy (programming a block) */
static bool wait_ready(uint32_t ms)
{
	uint32_t t0 = now_ms();
	do {
		if (xfer(0xFF) == 0xFF)
			return true;
	} while (now_ms() - t0 < ms && card_in());
	return false;
}

static void deselect(void)
{
	gpio_put(PIN_SD_NCS, 1);
	xfer(0xFF);                         /* the card releases DO on the next clock */
}

static bool select(void)
{
	gpio_put(PIN_SD_NCS, 0);
	xfer(0xFF);
	if (wait_ready(500))
		return true;
	deselect();
	return false;
}

static uint8_t crc7(const uint8_t *p, int n)
{
	uint8_t crc = 0;
	for (int i = 0; i < n; i++)
		for (int b = 7; b >= 0; b--) {
			uint8_t bit = (uint8_t)(((p[i] >> b) & 1) ^ (crc >> 6));
			crc = (uint8_t)((crc << 1) & 0x7F);
			if (bit)
				crc ^= 0x09;
		}
	return crc;
}

/* a command: its R1 response (bit 7 set: no response); the card stays selected */
static uint8_t send_cmd(uint8_t cmd, uint32_t arg)
{
	if (cmd & ACMD) {
		uint8_t r = send_cmd(55, 0);
		if (r > 1)
			return r;
		cmd &= (uint8_t)~ACMD;
	}
	deselect();
	if (!select())
		return 0xFF;
	uint8_t f[6] = { (uint8_t)(0x40 | cmd), (uint8_t)(arg >> 24), (uint8_t)(arg >> 16),
	                 (uint8_t)(arg >> 8), (uint8_t)arg, 0 };
	f[5] = (uint8_t)(crc7(f, 5) << 1 | 1);
	spi_write_blocking(SD_SPI, f, 6);
	uint8_t r;
	int n = 10;                         /* R1 within 8 bytes (NCR) */
	do
		r = xfer(0xFF);
	while ((r & 0x80) && --n);
	return r;
}

/* a data block after a read command: its start token, the data, the CRC */
static bool rx_block(uint8_t *buf, int n)
{
	uint32_t t0 = now_ms();
	uint8_t token;
	do
		token = xfer(0xFF);
	while (token == 0xFF && now_ms() - t0 < 200 && card_in());
	if (token != 0xFE)
		return false;
	for (int i = 0; i < n; i++)
		buf[i] = xfer(0xFF);
	xfer(0xFF);
	xfer(0xFF);
	return true;
}

static bool tx_block(const uint8_t *buf)
{
	if (!wait_ready(500))
		return false;
	xfer(0xFE);
	spi_write_blocking(SD_SPI, buf, 512);
	xfer(0xFF);                         /* CRC, not checked */
	xfer(0xFF);
	return (xfer(0xFF) & 0x1F) == 0x05; /* data response: accepted */
}

static int sd_init(void *ctx)
{
	(void)ctx;
	uint8_t ocr[4], csd[16];
	bool ok = false;

	spi_set_baudrate(SD_SPI, SLOW_HZ);
	gpio_put(PIN_SD_NCS, 1);
	for (int i = 0; i < 10; i++)        /* >= 74 clocks with CS high: native to SPI mode */
		xfer(0xFF);
	block_addr = false;
	if (send_cmd(0, 0) == 1) {          /* GO_IDLE_STATE */
		uint32_t t0 = now_ms();
		if (send_cmd(8, 0x1AA) == 1) {  /* SEND_IF_COND: a v2 card */
			for (int i = 0; i < 4; i++)
				ocr[i] = xfer(0xFF);
			if (ocr[2] == 0x01 && ocr[3] == 0xAA) {
				while (send_cmd(ACMD | 41, 1u << 30) && now_ms() - t0 < 1000)
					;           /* SD_SEND_OP_COND with HCS, until out of idle */
				if (now_ms() - t0 < 1000 && send_cmd(58, 0) == 0) {    /* READ_OCR */
					for (int i = 0; i < 4; i++)
						ocr[i] = xfer(0xFF);
					block_addr = ocr[0] & 0x40;             /* CCS */
					ok = true;
				}
			}
		} else {                        /* v1 */
			while (send_cmd(ACMD | 41, 0) && now_ms() - t0 < 1000)
				;
			ok = now_ms() - t0 < 1000 && send_cmd(16, 512) == 0;   /* SET_BLOCKLEN */
		}
	}
	/* SEND_CSD: the size, and the write-protect bits */
	if (ok && send_cmd(9, 0) == 0 && rx_block(csd, 16)) {
		if (csd[0] >> 6 == 1) {        /* CSD 2.0 */
			uint32_t c_size = (uint32_t)(csd[7] & 0x3F) << 16 | (uint32_t)csd[8] << 8 | csd[9];
			n_sectors = (c_size + 1) << 10;
		} else {                        /* CSD 1.0 */
			uint32_t c_size = (uint32_t)(csd[6] & 3) << 10 | (uint32_t)csd[7] << 2 | csd[8] >> 6;
			uint32_t mult = (uint32_t)(csd[9] & 3) << 1 | csd[10] >> 7;
			uint32_t bl_len = csd[5] & 15;
			n_sectors = (c_size + 1) << (mult + 2 + bl_len - 9);
		}
		protect = csd[14] & 0x30;       /* PERM_ or TMP_WRITE_PROTECT */
	} else {
		ok = false;
	}
	deselect();
	if (ok)
		spi_set_baudrate(SD_SPI, FAST_HZ);
	sd_spi_last_access = now_ms();
	return ok ? 0 : -1;
}

static bool sd_wp(void *ctx)
{
	(void)ctx;
	return protect;
}

static uint32_t sd_sectors(void *ctx)
{
	(void)ctx;
	return n_sectors;
}

static int sd_read(void *ctx, uint8_t *buf, uint32_t lba, uint32_t count)
{
	(void)ctx;
	bool ok = card_in();
	for (uint32_t i = 0; ok && i < count; i++) {
		uint32_t a = lba + i;
		ok = send_cmd(17, block_addr ? a : a * 512) == 0 && rx_block(buf + i * 512, 512);
	}
	deselect();
	sd_spi_last_access = now_ms();
	return ok ? 0 : -1;
}

static int sd_write(void *ctx, const uint8_t *buf, uint32_t lba, uint32_t count)
{
	(void)ctx;
	bool ok = card_in();
	for (uint32_t i = 0; ok && i < count; i++) {
		uint32_t a = lba + i;
		ok = send_cmd(24, block_addr ? a : a * 512) == 0 && tx_block(buf + i * 512);
	}
	deselect();
	sd_spi_last_access = now_ms();
	return ok ? 0 : -1;
}

/* the last write is finished when the card lets DO go high */
static int sd_sync(void *ctx)
{
	(void)ctx;
	bool ok = card_in() && select();
	deselect();
	return ok ? 0 : -1;
}

const st_disk_t sd_spi_ops = {
	.media = ST_MEDIA_SD,
	.init = sd_init, .write_protected = sd_wp, .sectors = sd_sectors,
	.read = sd_read, .write = sd_write, .sync = sd_sync,
};

void sd_spi_setup(void)
{
	spi_init(SD_SPI, SLOW_HZ);
	spi_set_format(SD_SPI, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
	gpio_set_function(PIN_SD_SCK, GPIO_FUNC_SPI);
	gpio_set_function(PIN_SD_MOSI, GPIO_FUNC_SPI);
	gpio_set_function(PIN_SD_MISO, GPIO_FUNC_SPI);
	gpio_pull_up(PIN_SD_MISO);          /* DO floats until the card drives it */
	gpio_init(PIN_SD_NCS);
	gpio_put(PIN_SD_NCS, 1);
	gpio_set_dir(PIN_SD_NCS, true);
	gpio_init(PIN_SD_NDETECT);
	gpio_pull_up(PIN_SD_NDETECT);       /* the socket's switch closes to GND with a card in */
	/* DAT1/DAT2: pulled up on the board, unused in SPI mode */
	gpio_init(PIN_SD_DAT1);
	gpio_init(PIN_SD_DAT2);
}
