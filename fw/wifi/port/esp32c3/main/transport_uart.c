/* The QEMU build's stand-in for the slot SPI: frames over UART1. The host
 * sends $A5, len16 LE, then the MOSI bytes; the card answers $5A, len16, then
 * the same number of MISO bytes, which are exactly what the SPI slave would
 * have shifted out: the preload taken when the previous frame ended, then $00. */
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "frames.h"
#include "transport.h"

#define PORT UART_NUM_1

static uint8_t preload[FRAMES_MAX_LEN];
static int npreload;

static bool read_all(uint8_t *p, int n)
{
	while (n > 0) {
		int r = uart_read_bytes(PORT, p, (uint32_t)n, portMAX_DELAY);
		if (r <= 0)
			return false;
		p += r;
		n -= r;
	}
	return true;
}

static void uart_task(void *arg)
{
	static uint8_t mosi[FRAMES_MAX_LEN], miso[FRAMES_MAX_LEN];
	npreload = frames_preload(preload, sizeof preload);
	for (;;) {
		uint8_t h[3];
		if (!read_all(h, 1) || h[0] != 0xA5 || !read_all(h + 1, 2))
			continue;
		int len = h[1] | h[2] << 8;
		if (len > FRAMES_MAX_LEN)
			continue;
		if (!read_all(mosi, len))
			continue;
		for (int i = 0; i < len; i++)
			miso[i] = i < npreload ? preload[i] : 0;
		uint8_t r[3] = { 0x5A, h[1], h[2] };
		uart_write_bytes(PORT, r, 3);
		uart_write_bytes(PORT, miso, (size_t)len);
		frames_received(mosi, len);
		npreload = frames_preload(preload, sizeof preload);   /* as the SPI ISR does */
	}
}

void transport_uart_start(void)
{
	uart_config_t cfg = {
		.baud_rate = 115200, .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
		.stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
	};
	ESP_ERROR_CHECK(uart_driver_install(PORT, 4096, 4096, 0, NULL, 0));
	ESP_ERROR_CHECK(uart_param_config(PORT, &cfg));
	xTaskCreate(uart_task, "frames", 4096, NULL, 10, NULL);
}
