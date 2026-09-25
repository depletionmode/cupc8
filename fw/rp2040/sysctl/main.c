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
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "sysctl.h"
#include "tusb.h"
#include "uart.pio.h"

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

/* USB activity LEDs (milestone-1.md, Indicator LEDs): each is lit until
 * its deadline, ~30 ms after the last data in its direction */
#define ACTIVITY_MS 30
static uint32_t led_tx_until, led_rx_until;

static void activity(uint32_t *until)
{
	*until = to_ms_since_boot(get_absolute_time()) + ACTIVITY_MS;
}

static void h_usb_write(void *ctx, const uint8_t *data, int n)
{
	(void)ctx;
	if (n > 0)
		activity(&led_tx_until);
	while (n > 0 && tud_cdc_connected()) {
		uint32_t k = tud_cdc_write(data, (uint32_t)n);
		data += k;
		n -= (int)k;
		tud_cdc_write_flush();
		if (!k)
			tud_task();
	}
}

/* ---------------------------------------------------- the programming port */

static const uint8_t mux_pins[3] = { PIN_MUX_SEL0, PIN_MUX_SEL1, PIN_MUX_SEL2 };

/* a slot: MUX_SEL driven; -1: released, and the board's pull-ups pick the
 * unconnected channel 7 */
static void h_prog_select(void *ctx, int slot)
{
	(void)ctx;
	for (int i = 0; i < 3; i++) {
		gpio_put(mux_pins[i], slot >= 0 && (slot >> i & 1));
		gpio_set_dir(mux_pins[i], slot >= 0);
	}
}

#define SWD_HALF_US 1           /* ~500 kHz: slow enough for the mux and 33 ohm */
static bool swdio_out;

static void swd_clock(void)
{
	sleep_us(SWD_HALF_US);
	gpio_put(PIN_PROG_CLK, 1);
	sleep_us(SWD_HALF_US);
	gpio_put(PIN_PROG_CLK, 0);
}

/* SWDIO changes while SWCLK is low; the target samples on the rising edge
 * and drives its bits after it, so the host samples just before the next one */
static void h_swd_io(void *ctx, bool out, uint32_t *bits, int n)
{
	(void)ctx;
	gpio_set_dir(PIN_PROG_CLK, true);
	if (out != swdio_out) {
		/* turnaround: one clock with nobody driving SWDIO */
		gpio_set_dir(PIN_PROG_IO, false);
		swd_clock();
		gpio_set_dir(PIN_PROG_IO, out);
		swdio_out = out;
	}
	if (!out)
		*bits = 0;
	for (int i = 0; i < n; i++) {
		if (out) {
			gpio_put(PIN_PROG_IO, *bits >> i & 1);
			swd_clock();
		} else {
			sleep_us(SWD_HALF_US);
			*bits |= (uint32_t)gpio_get(PIN_PROG_IO) << i;
			gpio_put(PIN_PROG_CLK, 1);
			sleep_us(SWD_HALF_US);
			gpio_put(PIN_PROG_CLK, 0);
		}
	}
}

static PIO uart_pio = pio0;
static uint uart_tx_sm, uart_rx_sm, uart_tx_prog, uart_rx_prog;
static bool uart_on;

/* received bytes stream into a ring by DMA: the PIO FIFO holds 8, and the
 * host polls about once a millisecond, when 11 can arrive at 115200 */
#define RX_RING_BITS 12
static uint8_t rx_ring[1u << RX_RING_BITS] __attribute__((aligned(1u << RX_RING_BITS)));
static int rx_dma = -1;
static uint32_t rx_tail;                       /* free-running */

static uint32_t rx_head(void)
{
	return 0xffffffffu - dma_channel_hw_addr((uint)rx_dma)->transfer_count;
}

static void port_release(void)
{
	gpio_set_function(PIN_PROG_CLK, GPIO_FUNC_SIO);
	gpio_set_function(PIN_PROG_IO, GPIO_FUNC_SIO);
	gpio_set_dir(PIN_PROG_CLK, false);
	gpio_set_dir(PIN_PROG_IO, false);
	gpio_put(PIN_PROG_CLK, 0);
	swdio_out = false;
}

static void h_uart_open(void *ctx, uint32_t baud)
{
	(void)ctx;
	if (uart_on) {
		pio_sm_set_enabled(uart_pio, uart_tx_sm, false);
		pio_sm_set_enabled(uart_pio, uart_rx_sm, false);
		dma_channel_abort((uint)rx_dma);
		uart_on = false;
	}
	port_release();
	if (!baud)
		return;
	float div = (float)clock_get_hz(clk_sys) / (8.0f * (float)baud);
	/* TX on PROG_CLK */
	pio_sm_config c = port_uart_tx_program_get_default_config(uart_tx_prog);
	sm_config_set_out_shift(&c, true, false, 32);
	sm_config_set_out_pins(&c, PIN_PROG_CLK, 1);
	sm_config_set_sideset_pins(&c, PIN_PROG_CLK);
	sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
	sm_config_set_clkdiv(&c, div);
	pio_sm_set_pins_with_mask(uart_pio, uart_tx_sm, 1u << PIN_PROG_CLK, 1u << PIN_PROG_CLK);
	pio_sm_set_pindirs_with_mask(uart_pio, uart_tx_sm, 1u << PIN_PROG_CLK, 1u << PIN_PROG_CLK);
	pio_gpio_init(uart_pio, PIN_PROG_CLK);
	pio_sm_init(uart_pio, uart_tx_sm, uart_tx_prog, &c);
	/* RX on PROG_IO */
	c = port_uart_rx_program_get_default_config(uart_rx_prog);
	sm_config_set_in_pins(&c, PIN_PROG_IO);
	sm_config_set_jmp_pin(&c, PIN_PROG_IO);
	sm_config_set_in_shift(&c, true, false, 32);
	sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);
	sm_config_set_clkdiv(&c, div);
	gpio_pull_up(PIN_PROG_IO);
	pio_sm_init(uart_pio, uart_rx_sm, uart_rx_prog, &c);
	/* the byte is in bits 31:24 of the RX FIFO word: DMA its top byte */
	dma_channel_config d = dma_channel_get_default_config((uint)rx_dma);
	channel_config_set_transfer_data_size(&d, DMA_SIZE_8);
	channel_config_set_read_increment(&d, false);
	channel_config_set_write_increment(&d, true);
	channel_config_set_ring(&d, true, RX_RING_BITS);
	channel_config_set_dreq(&d, pio_get_dreq(uart_pio, uart_rx_sm, false));
	dma_channel_configure((uint)rx_dma, &d, rx_ring, (const uint8_t *)&uart_pio->rxf[uart_rx_sm] + 3, 0xffffffffu, true);
	rx_tail = 0;
	pio_sm_set_enabled(uart_pio, uart_tx_sm, true);
	pio_sm_set_enabled(uart_pio, uart_rx_sm, true);
	uart_on = true;
}

static void h_uart_write(void *ctx, const uint8_t *d, int n)
{
	(void)ctx;
	for (int i = 0; i < n && uart_on; i++)
		pio_sm_put_blocking(uart_pio, uart_tx_sm, d[i]);
}

static int h_uart_read(void *ctx, uint8_t *d, int max)
{
	(void)ctx;
	int n = 0;
	if (!uart_on)
		return 0;
	uint32_t head = rx_head();
	if (head - rx_tail > sizeof rx_ring)
		rx_tail = head - sizeof rx_ring;      /* overrun: keep the newest */
	while (n < max && rx_tail != head)
		d[n++] = rx_ring[rx_tail++ % sizeof rx_ring];
	return n;
}

static const sysctl_hal hal = {
	.spi_select = h_spi_select, .spi_xfer = h_spi_xfer, .pin_write = h_pin_write, .pin_read = h_pin_read,
	.adc_mv = h_adc_mv, .i2c_write = h_i2c_write, .i2c_read = h_i2c_read, .delay_us = h_delay_us,
	.now_ms = h_now_ms, .usb_write = h_usb_write,
	.prog_select = h_prog_select, .swd_io = h_swd_io,
	.uart_open = h_uart_open, .uart_write = h_uart_write, .uart_read = h_uart_read,
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
	for (int i = 0; i < 3; i++)
		gpio_init(mux_pins[i]);             /* inputs: the mux parks on channel 7 */
	gpio_init(PIN_PROG_CLK);
	gpio_init(PIN_PROG_IO);
	port_release();
	uart_tx_prog = pio_add_program(uart_pio, &port_uart_tx_program);
	uart_rx_prog = pio_add_program(uart_pio, &port_uart_rx_program);
	uart_tx_sm = (uint)pio_claim_unused_sm(uart_pio, true);
	uart_rx_sm = (uint)pio_claim_unused_sm(uart_pio, true);
	rx_dma = dma_claim_unused_channel(true);
	gpio_init(PIN_LED_STATUS);
	gpio_set_dir(PIN_LED_STATUS, true);
	gpio_init(PIN_LED_USB_TX);
	gpio_set_dir(PIN_LED_USB_TX, true);
	gpio_init(PIN_LED_USB_RX);
	gpio_set_dir(PIN_LED_USB_RX, true);

	sysctl_init(&sys, &hal, NULL);
	tusb_init();
	for (;;) {
		tud_task();
		uint8_t buf[256];
		uint32_t n = tud_cdc_available() ? tud_cdc_read(buf, sizeof buf) : 0;
		if (n) {
			activity(&led_rx_until);
			sysctl_rx(&sys, buf, (int)n);
		}
		sysctl_poll(&sys);
		gpio_put(PIN_LED_STATUS, tud_mounted());
		uint32_t now = to_ms_since_boot(get_absolute_time());
		gpio_put(PIN_LED_USB_TX, (int32_t)(led_tx_until - now) > 0);
		gpio_put(PIN_LED_USB_RX, (int32_t)(led_rx_until - now) > 0);
	}
}
