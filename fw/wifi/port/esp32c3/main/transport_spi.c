/* The slot SPI slave on GPSPI2 (mode 0). Two transaction descriptors take
 * turns: when one ends, its MOSI bytes are queued for the task and the other
 * is queued from the ISR with a fresh preload to meet the 20 us the host
 * leaves between frames. Actual re-arm latency still needs measurement. */
#include "driver/spi_slave.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_intr_alloc.h"
#include "esp_private/spi_slave_internal.h"
#include "frames.h"
#include "pins.h"
#include "transport.h"
#include <string.h>

#define HOST SPI2_HOST

static WORD_ALIGNED_ATTR DMA_ATTR uint8_t rx[2][FRAMES_MAX_LEN];
static WORD_ALIGNED_ATTR DMA_ATTR uint8_t tx[2][FRAMES_MAX_LEN];
static spi_slave_transaction_t trans[2];

static void IRAM_ATTR arm(int i)
{
	int n = frames_preload(tx[i], FRAMES_MAX_LEN);
	/* Cache-safe memset avoids hundreds of scalar stores inside the frame ISR. */
	memset(tx[i] + n, 0, FRAMES_MAX_LEN - n);
	trans[i].length = FRAMES_MAX_LEN * 8;
	trans[i].tx_buffer = tx[i];
	trans[i].rx_buffer = rx[i];
	trans[i].user = (void *)(intptr_t)i;
}

static void IRAM_ATTR done(spi_slave_transaction_t *t)
{
	int i = (int)(intptr_t)t->user;
	frames_received(rx[i], (int)(t->trans_len / 8));
	arm(i ^ 1);
	spi_slave_queue_trans_isr(HOST, &trans[i ^ 1]);
}

void transport_spi_start(void)
{
	spi_bus_config_t bus = {
		.mosi_io_num = PIN_SLOT_MOSI, .miso_io_num = PIN_SLOT_MISO, .sclk_io_num = PIN_SLOT_SCK,
		.quadwp_io_num = -1, .quadhd_io_num = -1,
		/* Keep serving frames during NVS flash writes (cache disabled). */
		.intr_flags = ESP_INTR_FLAG_IRAM,
	};
	spi_slave_interface_config_t slave = {
		.spics_io_num = PIN_SLOT_NCS, .mode = 0, .queue_size = 2, .post_trans_cb = done,
		/* Results are consumed in done(), never through the return queue. */
		.flags = SPI_SLAVE_NO_RETURN_RESULT,
	};
	ESP_ERROR_CHECK(spi_slave_initialize(HOST, &bus, &slave, SPI_DMA_CH_AUTO));
	/* IDF's SPI pinmux setup preserves pulls. Keep the host-driven inputs
	 * free of internal pull loads, including behind a local level buffer. */
	ESP_ERROR_CHECK(gpio_set_pull_mode(PIN_SLOT_SCK, GPIO_FLOATING));
	ESP_ERROR_CHECK(gpio_set_pull_mode(PIN_SLOT_MOSI, GPIO_FLOATING));
	ESP_ERROR_CHECK(gpio_set_pull_mode(PIN_SLOT_NCS, GPIO_FLOATING));
	arm(0);
	ESP_ERROR_CHECK(spi_slave_queue_trans(HOST, &trans[0], portMAX_DELAY));
}
