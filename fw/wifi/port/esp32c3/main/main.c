/*
 * Wi-Fi card firmware (doc/hardware/wifi-card.md): the network stack on the
 * ESP32-C3, four sockets for the CPU through the common card protocol.
 */
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "frames.h"
#include "netesp.h"
#include "nvs_flash.h"
#include "pins.h"
#include "sdkconfig.h"
#include "transport.h"
#include "wifi.h"

static wifi_t card;

#define ACTIVITY_MS 30                  /* an LED stays lit this long after data moves, so bursts show */

/* light `pin` for ACTIVITY_MS after `count` changes */
static void activity(gpio_num_t pin, uint32_t count, uint32_t *seen, TickType_t *until)
{
	TickType_t now = xTaskGetTickCount();
	if (count != *seen) {
		*seen = count;
		*until = now + pdMS_TO_TICKS(ACTIVITY_MS);
	}
	gpio_set_level(pin, (int32_t)(*until - now) > 0);
}

void app_main(void)
{
	esp_err_t e = nvs_flash_init();
	if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_ERROR_CHECK(nvs_flash_erase());
		e = nvs_flash_init();
	}
	ESP_ERROR_CHECK(e);

	/* IRQ_n is open drain: driven low, or released */
	gpio_reset_pin(PIN_SLOT_NIRQ);
	gpio_set_level(PIN_SLOT_NIRQ, 0);
	gpio_set_direction(PIN_SLOT_NIRQ, GPIO_MODE_INPUT);
	gpio_reset_pin(PIN_LED_LINK);
	gpio_set_direction(PIN_LED_LINK, GPIO_MODE_OUTPUT);
	gpio_reset_pin(PIN_LED_TX);
	gpio_set_direction(PIN_LED_TX, GPIO_MODE_OUTPUT);
	gpio_reset_pin(PIN_LED_RX);
	gpio_set_direction(PIN_LED_RX, GPIO_MODE_OUTPUT);
	uint32_t tx_seen = 0, rx_seen = 0;
	TickType_t tx_until = 0, rx_until = 0;

	wifi_init(&card, &netesp_ops, netesp_init());
	frames_init(&card.card);
#if CONFIG_CUPC8_QEMU
	transport_uart_start();
#else
	transport_spi_start();
#endif

	for (;;) {
		frames_poll();
		frames_busy(true);          /* polling may complete a deferred response */
		wifi_poll(&card);
		frames_busy(false);
		gpio_set_direction(PIN_SLOT_NIRQ, card_irq(&card.card) ? GPIO_MODE_OUTPUT : GPIO_MODE_INPUT);
		gpio_set_level(PIN_LED_LINK, card.link == WIFI_LINK_UP);
		activity(PIN_LED_TX, card.tx_bytes, &tx_seen, &tx_until);
		activity(PIN_LED_RX, card.rx_bytes, &rx_seen, &rx_until);
		vTaskDelay(1);
	}
}
