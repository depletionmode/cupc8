/*
 * Storage card firmware (doc/hardware/storage-card.md): files on a microSD
 * card for the CPU, through the storage core (fw/storage/core) and the slot
 * SPI slave.
 *
 * Core 0: the slot SPI slave and the card engine: it queues each command,
 * hands one at a time to core 1, and posts the answer when it comes back.
 * So the slot always answers (status byte with BUSY, IDENT, a not-ready
 * READ) while the SD card takes its time. Also card detect and the LEDs.
 * Core 1: FatFs and the SD card (fw/rp2040/storage/sd_spi.c): st_exec() on
 * each request, st_service() between them.
 */
#include "hardware/gpio.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "sd_spi.h"
#include "slotspi.h"
#include "storage.h"

#define DETECT_MS 20                   /* card detect debounce */
#define ACT_MS    30                   /* the ACT LED stays lit this long after an access */

static storage_t st;

/* one request at a time between the cores; the FIFO words only signal */
static st_req_t req;
static uint8_t resp[CARD_RESP_MAX];
static volatile int resp_len;

static uint32_t now_ms(void)
{
	return to_ms_since_boot(get_absolute_time());
}

static void core1_main(void)
{
	for (;;) {
		if (multicore_fifo_rvalid()) {
			(void)multicore_fifo_pop_blocking();
			resp_len = st_exec(&st, req.data, req.len, resp);
			multicore_fifo_push_blocking(1);
		} else {
			st_service(&st);    /* card detect: unmount, or mount a new card */
			sleep_us(100);
		}
	}
}

static uint8_t status(card_t *c, uint32_t queued_bytes, uint32_t queued_frames)
{
	(void)queued_bytes;
	(void)queued_frames;
	return c->ops->status(c);
}

int main(void)
{
	stdout_uart_init();                 /* TX only: GPIO17 is card detect */
	gpio_init(PIN_LED_ACT);
	gpio_set_dir(PIN_LED_ACT, true);
	gpio_init(PIN_LED_CARD);
	gpio_set_dir(PIN_LED_CARD, true);
	sd_spi_setup();
	sleep_us(100);                      /* the detect pull-up settles */

	bool present = !gpio_get(PIN_SD_NDETECT);
	st_init(&st, &sd_spi_ops, 0, present);
	slotspi_init(&st.card, status);
	multicore_launch_core1(core1_main); /* it mounts the card, if one is in */

	bool raw = present;
	uint32_t raw_since = now_ms();
	uint8_t shown = st_status(&st);
	for (;;) {
		slotspi_poll();
		uint32_t now = now_ms();

		/* card detect, debounced; st_detect unmounts at once */
		bool in = !gpio_get(PIN_SD_NDETECT);
		if (in != raw) {
			raw = in;
			raw_since = now;
		} else if (in != present && now - raw_since >= DETECT_MS) {
			present = in;
			st_detect(&st, present);
		}

		/* the answer from core 1 */
		if (st.running && multicore_fifo_rvalid()) {
			(void)multicore_fifo_pop_blocking();
			slotspi_busy(true);         /* the preload must not offer a half-set answer */
			st_done(&st, req.seq, resp, resp_len);
			slotspi_busy(false);
			slotspi_refresh();
		}
		/* the next request to core 1 */
		if (st_take(&st, &req))
			multicore_fifo_push_blocking(1);

		uint8_t s = st_status(&st);
		if (s != shown) {               /* a new status byte for the next frame */
			shown = s;
			slotspi_refresh();
		}
		gpio_put(PIN_LED_ACT, now - sd_spi_last_access < ACT_MS);
		gpio_put(PIN_LED_CARD, (s & (ST_S_MEDIA | ST_S_MOUNTED)) == (ST_S_MEDIA | ST_S_MOUNTED));
	}
}
