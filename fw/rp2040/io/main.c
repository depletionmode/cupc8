/*
 * IO card firmware (doc/hardware/io-card.md): a USB keyboard on the RP2040's
 * native port, in TinyUSB host mode, becomes bytes for the CPU through the
 * common IO core (fw/io/core/iocard.c) and the slot SPI slave.
 */
#include "hardware/gpio.h"
#include "iocard.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "slotspi.h"
#include "tusb.h"

static iocard_t io;
static uint8_t kbd_addr, kbd_instance;
static bool have_kbd;
static uint8_t led_report;            /* must outlive the control transfer */
static bool changed;                  /* status or response may differ: re-arm the preload */
static uint32_t key_led_until;        /* LED_KEY (activity) stays lit until then, in ms */

#define KEY_LED_MS 30                 /* activity LED on-time after each HID report */

static uint32_t now_ms(void)
{
	return to_ms_since_boot(get_absolute_time());
}

/* the core decided the lock LEDs (bit 0 Num, 1 Caps): HID output report bit 0 Num, 1 Caps */
static void set_leds(iocard_t *c, uint8_t leds)
{
	(void)c;
	led_report = leds;
	if (have_kbd)
		tuh_hid_set_report(kbd_addr, kbd_instance, 0, HID_REPORT_TYPE_OUTPUT, &led_report, 1);
}

void tuh_hid_mount_cb(uint8_t dev_addr, uint8_t instance, uint8_t const *desc, uint16_t len)
{
	(void)desc;
	(void)len;
	if (have_kbd || tuh_hid_interface_protocol(dev_addr, instance) != HID_ITF_PROTOCOL_KEYBOARD)
		return;         /* one keyboard; mice and the rest are ignored */
	have_kbd = true;
	kbd_addr = dev_addr;
	kbd_instance = instance;
	io_connected(&io, true);
	set_leds(&io, (uint8_t)((io.num ? 1 : 0) | (io.caps ? 2 : 0)));
	tuh_hid_receive_report(dev_addr, instance);
	changed = true;
}

void tuh_hid_umount_cb(uint8_t dev_addr, uint8_t instance)
{
	if (have_kbd && dev_addr == kbd_addr && instance == kbd_instance) {
		have_kbd = false;
		io_connected(&io, false);
		changed = true;
	}
}

void tuh_hid_report_received_cb(uint8_t dev_addr, uint8_t instance, uint8_t const *report, uint16_t len)
{
	if (have_kbd && dev_addr == kbd_addr && instance == kbd_instance && len >= 8) {
		io_report(&io, report, now_ms());
		key_led_until = now_ms() + KEY_LED_MS;
		changed = true;
	}
	tuh_hid_receive_report(dev_addr, instance);
}

/* TinyUSB's host waits in here while it enumerates (450 ms debouncing a new
 * keyboard, 50 ms resets): keep answering the slot meanwhile, or a frame
 * waits past slot.md's 5 ms deadline (the boot ROM's IDENT probe got RESP_LEN
 * 0 and recorded the slot as empty). Overrides TinyUSB's weak busy-wait. */
void tusb_time_delay_ms_api(uint32_t ms)
{
	uint32_t start = now_ms();
	while (now_ms() - start < ms) {
		if (slotspi_poll()) {
			slotspi_refresh();
			slotspi_update_irq();
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
	stdio_init_all();
	io_init(&io);
	io.set_leds = set_leds;

	/* the VBUS switch: on, and its fault flag (open drain, active low) */
	gpio_init(PIN_VBUS_EN);
	gpio_set_dir(PIN_VBUS_EN, true);
	gpio_put(PIN_VBUS_EN, 1);
	gpio_init(PIN_VBUS_NFAULT);
	gpio_pull_up(PIN_VBUS_NFAULT);
	gpio_init(PIN_LED_KBD);
	gpio_set_dir(PIN_LED_KBD, true);
	gpio_init(PIN_LED_KEY);
	gpio_set_dir(PIN_LED_KEY, true);

	slotspi_init(&io.card, status);
	tuh_init(0);                    /* the native port */

	bool fault = false;
	for (;;) {
		tuh_task();
		if (slotspi_poll())
			changed = true;
		uint8_t before = io.count;
		io_poll(&io, now_ms());
		if (io.count != before)
			changed = true;
		bool f = !gpio_get(PIN_VBUS_NFAULT);
		if (f != fault) {
			fault = f;
			io_vbus_fault(&io, f);
			changed = true;
		}
		gpio_put(PIN_LED_KBD, have_kbd);
		gpio_put(PIN_LED_KEY, (int32_t)(key_led_until - now_ms()) > 0);
		if (changed) {
			changed = false;
			slotspi_refresh();
			slotspi_update_irq();
		}
	}
}
