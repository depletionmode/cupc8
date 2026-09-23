/*
 * System card firmware (doc/hardware/sysctl.md, system-slot.md): the sysctl
 * core (fw/sysctl/core) on the RP2040, talking USB CDC to cupc8.py.
 *
 * At start-up it drives nothing on the machine: every machine-facing pin is
 * an input until a command needs it, and returns to one afterwards.
 */
#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "sysctl.h"
#include "tusb.h"

#define BRIDGE_HZ 1000000       /* the chipset oversamples SCK: <= 1 MHz (memory-map.md) */
#define FLASH_HZ  10000000      /* W25Q; FL1 runs through the CPU socket */

static sysctl_t sys;

/* the machine-facing SPI pins of each bus: SCK, MOSI, MISO, CS_n */
static const uint8_t bus_pins[3][4] = {
	[SPI_BRIDGE] = { PIN_BR_SCK, PIN_BR_MOSI, PIN_BR_MISO, PIN_BR_NCS },
	[SPI_FL0] = { PIN_FL0_SCK, PIN_FL0_MOSI, PIN_FL0_MISO, PIN_FL0_NCS },
	[SPI_FL1] = { PIN_FL1_SCK, PIN_FL1_MOSI, PIN_FL1_MISO, PIN_FL1_NCS },
};
static int selected = SPI_NONE;

static void release_bus(int bus)
{
	for (int i = 0; i < 4; i++) {
		gpio_set_function(bus_pins[bus][i], GPIO_FUNC_SIO);
		gpio_set_dir(bus_pins[bus][i], false);   /* Hi-Z: the FPGA owns its flash */
	}
}

static void h_spi_select(void *ctx, int bus)
{
	(void)ctx;
	if (selected != SPI_NONE)
		release_bus(selected);
	selected = bus;
	if (bus == SPI_NONE)
		return;
	spi_inst_t *spi = bus == SPI_BRIDGE ? spi0 : spi1;
	spi_set_baudrate(spi, bus == SPI_BRIDGE ? BRIDGE_HZ : FLASH_HZ);
	for (int i = 0; i < 3; i++)
		gpio_set_function(bus_pins[bus][i], GPIO_FUNC_SPI);
	gpio_put(bus_pins[bus][3], 0);                /* CS_n by hand: frames span calls */
	gpio_set_dir(bus_pins[bus][3], true);
}

static void h_spi_xfer(void *ctx, const uint8_t *tx, uint8_t *rx, int n)
{
	(void)ctx;
	if (selected == SPI_NONE)
		return;
	spi_inst_t *spi = selected == SPI_BRIDGE ? spi0 : spi1;
	static const uint8_t zero[64];
	while (n > 0) {
		int k = n > 64 ? 64 : n;
		const uint8_t *t = tx ? tx : zero;
		if (rx)
			spi_write_read_blocking(spi, t, rx, (size_t)k);
		else
			spi_write_blocking(spi, t, (size_t)k);
		if (tx)
			tx += k;
		if (rx)
			rx += k;
		n -= k;
	}
}

static const uint8_t hal_pins[] = {
	[HAL_CHIPSET_CRESET] = PIN_CHIPSET_NCRESET, [HAL_CHIPSET_CDONE] = PIN_CHIPSET_CDONE,
	[HAL_CPUCARD_CRESET] = PIN_CPUCARD_NCRESET, [HAL_CPUCARD_CDONE] = PIN_CPUCARD_CDONE,
	[HAL_SYS_NRST] = PIN_SYS_NRST,
};

/* open drain: low is driven, high is released to the board's pull-up */
static void h_pin_write(void *ctx, int pin, bool level)
{
	(void)ctx;
	gpio_set_dir(hal_pins[pin], !level);
}

static bool h_pin_read(void *ctx, int pin)
{
	(void)ctx;
	return gpio_get(hal_pins[pin]);
}

static int h_adc_mv(void *ctx, int ch)
{
	(void)ctx;
	adc_select_input((uint)(ch == ADC_CC1 ? 0 : ch == ADC_CC2 ? 1 : 2));
	return (int)(adc_read() * 3300u / 4096u);
}

static int h_i2c_write(void *ctx, uint8_t addr, const uint8_t *data, int n)
{
	(void)ctx;
	return i2c_write_timeout_us(i2c0, addr, data, (size_t)n, false, 10000) == n ? 0 : -1;
}

static int h_i2c_read(void *ctx, uint8_t addr, uint8_t reg, uint8_t *data, int n)
{
	(void)ctx;
	if (i2c_write_timeout_us(i2c0, addr, &reg, 1, true, 10000) != 1)
		return -1;
	return i2c_read_timeout_us(i2c0, addr, data, (size_t)n, false, 10000) == n ? 0 : -1;
}

static void h_delay_us(void *ctx, uint32_t us)
{
	(void)ctx;
	sleep_us(us);
}

static uint32_t h_now_ms(void *ctx)
{
	(void)ctx;
	return to_ms_since_boot(get_absolute_time());
}

static void h_usb_write(void *ctx, const uint8_t *data, int n)
{
	(void)ctx;
	while (n > 0 && tud_cdc_connected()) {
		uint32_t k = tud_cdc_write(data, (uint32_t)n);
		data += k;
		n -= (int)k;
		tud_cdc_write_flush();
		if (!k)
			tud_task();
	}
}

static const sysctl_hal hal = {
	.spi_select = h_spi_select, .spi_xfer = h_spi_xfer, .pin_write = h_pin_write, .pin_read = h_pin_read,
	.adc_mv = h_adc_mv, .i2c_write = h_i2c_write, .i2c_read = h_i2c_read, .delay_us = h_delay_us,
	.now_ms = h_now_ms, .usb_write = h_usb_write,
};

int main(void)
{
	/* every machine-facing pin an input: nothing is driven until asked */
	for (int b = 0; b < 3; b++) {
		for (int i = 0; i < 4; i++)
			gpio_init(bus_pins[b][i]);
		release_bus(b);
	}
	spi_init(spi0, BRIDGE_HZ);
	spi_init(spi1, FLASH_HZ);
	for (unsigned i = 0; i < sizeof hal_pins; i++) {
		gpio_init(hal_pins[i]);
		gpio_put(hal_pins[i], 0);       /* only ever driven low, when output */
		gpio_set_dir(hal_pins[i], false);
	}
	i2c_init(i2c0, 100000);
	gpio_set_function(PIN_I2C_SDA, GPIO_FUNC_I2C);
	gpio_set_function(PIN_I2C_SCL, GPIO_FUNC_I2C);
	adc_init();
	adc_gpio_init(PIN_CC1_SENSE);
	adc_gpio_init(PIN_CC2_SENSE);
	adc_gpio_init(PIN_V1V2_SENSE);
	gpio_init(PIN_LED_STATUS);
	gpio_set_dir(PIN_LED_STATUS, true);

	sysctl_init(&sys, &hal, NULL);
	tusb_init();
	for (;;) {
		tud_task();
		uint8_t buf[256];
		uint32_t n = tud_cdc_available() ? tud_cdc_read(buf, sizeof buf) : 0;
		if (n)
			sysctl_rx(&sys, buf, (int)n);
		sysctl_poll(&sys);
		gpio_put(PIN_LED_STATUS, tud_mounted());
	}
}
