/*
 * E-ink graphics card firmware (doc/hardware/eink-card.md): the graphics
 * card's protocol on an e-paper panel with a UC8179 controller, on its
 * driver module at the card's 9-pin header (SPI1 + DC, RST, BUSY, PWR).
 *
 * One core, one loop: the slot SPI slave (fw/rp2040/common/slotspi.c),
 * command execution (fw/gpu/core + fw/eink/core, the same code the host
 * tests and the simulator run) and the panel loop (eink_poll(), which never
 * waits: a BUSY panel is polled, and a picture goes out a few rows a turn),
 * so IDENT is answered at once, whatever the panel is doing.
 *
 * Built for the 5.83" GDEY0583T81 (eink.elf) or, with EINK_PANEL_750, the
 * 7.5" GDEY075T7 (eink750.elf): the card cannot ask the panel which it is.
 */
#include "eink.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "slotspi.h"

#ifdef EINK_PANEL_750
#define PANEL eink_panel_750
#else
#define PANEL eink_panel_583
#endif

#define EPD_SPI      spi1
#define EPD_SPI_HZ   10000000               /* the UC8179 takes up to 20 MHz (datasheet p.3) */

static eink_t eink;

/* CS is a GPIO around each command and each run of data, as the vendors'
 * drivers do; spi_write_blocking() returns once the last bit is out, so DC
 * and CS never change under a byte */
static void epd_command(void *ctx, uint8_t c)
{
	(void)ctx;
	gpio_put(PIN_EPD_DC, 0);
	gpio_put(PIN_EPD_NCS, 0);
	spi_write_blocking(EPD_SPI, &c, 1);
	gpio_put(PIN_EPD_NCS, 1);
}

static void epd_data(void *ctx, const uint8_t *p, int n)
{
	(void)ctx;
	gpio_put(PIN_EPD_DC, 1);
	gpio_put(PIN_EPD_NCS, 0);
	spi_write_blocking(EPD_SPI, p, (size_t)n);
	gpio_put(PIN_EPD_NCS, 1);
}

static void epd_pin(void *ctx, int pin, bool level)
{
	(void)ctx;
	gpio_put(pin == EPD_PIN_RST_N ? PIN_EPD_NRST : PIN_EPD_PWR, level);
}

static bool epd_busy(void *ctx)
{
	(void)ctx;
	return !gpio_get(PIN_EPD_BUSY);             /* UC8179: BUSY_N low while busy */
}

static const epd_bus_t bus = {0, epd_command, epd_data, epd_pin, epd_busy};

static uint8_t status(card_t *c, uint32_t queued_bytes, uint32_t queued_frames)
{
	(void)c;
	/* as the graphics card: what is still in the SPI ring counts as used */
	uint32_t free = gpu_fifo_free(&eink.gpu), used = queued_bytes + 2 * queued_frames;
	uint32_t units = free > used ? (free - used) / 64 : 0;
	return (uint8_t)(units > 127 ? 127 : units);
}

static void out_pin(uint pin, bool level)
{
	gpio_init(pin);
	gpio_put(pin, level);
	gpio_set_dir(pin, true);
}

int main(void)
{
	/* the panel's lines: the module stays unpowered until the first refresh */
	out_pin(PIN_EPD_NCS, 1);
	out_pin(PIN_EPD_DC, 1);
	out_pin(PIN_EPD_NRST, 1);
	out_pin(PIN_EPD_PWR, 0);
	out_pin(PIN_LED_REFRESH, 0);
	gpio_init(PIN_EPD_BUSY);
	gpio_pull_up(PIN_EPD_BUSY);                 /* no module: never busy */
	spi_init(EPD_SPI, EPD_SPI_HZ);              /* mode 0, MSB first, 8 bits */
	gpio_set_function(PIN_EPD_CLK, GPIO_FUNC_SPI);
	gpio_set_function(PIN_EPD_DIN, GPIO_FUNC_SPI);

	eink_init(&eink, &PANEL, &bus);
	slotspi_init(&eink.gpu.card, status);

	for (;;) {
		slotspi_poll();
		slotspi_busy(true);                     /* commands may set a response */
		int ran = gpu_run(&eink.gpu, 8);
		slotspi_busy(false);
		if (ran)
			slotspi_refresh();              /* more FIFO space, maybe a response */
		eink_poll(&eink, time_us_32());
		gpio_put(PIN_LED_REFRESH, eink_refreshing(&eink));
		slotspi_update_irq();
	}
}
