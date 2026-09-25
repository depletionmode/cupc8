/*
 * The machine around the system card, in models (fw/test/sysmodels.h,
 * swdtarget.h), wired to the sysctl core through its HAL: the host tests
 * (test_sysctl.c) and sysctl_sim (cupc8.py's stand-in for the hardware) both
 * run on it. Time is virtual: SPI bytes, SWD bits and delays advance it.
 */
#include "sysmachine.h"

#include <string.h>


struct sysmachine M;

swdt_t card2;                      /* an RP2040 card in slot 3 */

uint8_t img_chip[IMG_LEN], img_cpu[IMG_LEN];
sysctl_t S;

/* ------------------------------------------------------------------ HAL */

void tick(void)
{
	ice40_tick(&M.chip, M.now);
	ice40_tick(&M.cpu, M.now);
	M.br.configured = M.chip.cdone;
}

static void bus_select(int bus, bool sel)
{
	if (bus == SPI_BRIDGE)
		bridge_select(&M.br, sel);
	else if (bus == SPI_FL0)
		w25q_select(&M.fl0, sel, M.now);
	else if (bus == SPI_FL1)
		w25q_select(&M.fl1, sel, M.now);
}

static void h_spi_select(void *ctx, int bus)
{
	(void)ctx;
	if (M.bus != SPI_NONE)
		bus_select(M.bus, false);
	M.bus = bus;
	if (bus == SPI_BRIDGE)
		M.bridge_frames++;
	if (bus != SPI_NONE)
		bus_select(bus, true);
}

static void h_spi_xfer(void *ctx, const uint8_t *tx, uint8_t *rx, int n)
{
	(void)ctx;
	for (int i = 0; i < n; i++) {
		uint8_t mosi = tx ? tx[i] : 0, miso = 0xFF;
		tick();
		switch (M.bus) {
		case SPI_BRIDGE:
			M.now += 8;                    /* ≤ 1 MHz */
			miso = bridge_byte(&M.br, mosi, M.now);
			break;
		case SPI_FL0:
		case SPI_FL1: {
			ice40_t *f = M.bus == SPI_FL0 ? &M.chip : &M.cpu;
			if (f->creset)
				M.contention++;           /* the FPGA owns this bus */
			M.now += 1;
			miso = w25q_byte(M.bus == SPI_FL0 ? &M.fl0 : &M.fl1, mosi, M.now);
			break;
		}
		default:
			M.now += 1;
		}
		if (rx)
			rx[i] = miso;
	}
}

static void h_pin_write(void *ctx, int pin, bool level)
{
	(void)ctx;
	tick();
	if (pin == HAL_CHIPSET_CRESET)
		ice40_creset(&M.chip, level, M.now);
	else if (pin == HAL_CPUCARD_CRESET)
		ice40_creset(&M.cpu, level, M.now);
	else if (pin == HAL_SYS_NRST) {
		if (!level && M.sys_nrst)
			M.reset_pulses++;
		M.sys_nrst = level;
	}
}

static bool h_pin_read(void *ctx, int pin)
{
	(void)ctx;
	tick();
	return pin == HAL_CHIPSET_CDONE ? M.chip.cdone : pin == HAL_CPUCARD_CDONE ? M.cpu.cdone : true;
}

static int h_adc(void *ctx, int ch) { (void)ctx; return M.adc[ch]; }

static int h_i2c_write(void *ctx, uint8_t addr, const uint8_t *d, int n)
{
	(void)ctx;
	return addr == 0x20 ? tca_write(&M.u0, d, n) : addr == 0x21 ? tca_write(&M.u1, d, n) : -1;
}

static int h_i2c_read(void *ctx, uint8_t addr, uint8_t reg, uint8_t *d, int n)
{
	(void)ctx;
	return addr == 0x20 ? tca_read(&M.u0, reg, d, n) : addr == 0x21 ? tca_read(&M.u1, reg, d, n) : -1;
}

static void h_delay(void *ctx, uint32_t us) { (void)ctx; M.now += us; tick(); }
static uint32_t h_now_ms(void *ctx) { (void)ctx; return (uint32_t)(M.now / 1000); }

static void h_usb_write(void *ctx, const uint8_t *d, int n)
{
	(void)ctx;
	memcpy(M.usb + M.usb_n, d, (size_t)n);
	M.usb_n += n;
}

static void h_prog_select(void *ctx, int slot) { (void)ctx; M.prog_slot = slot; }

static void h_swd_io(void *ctx, bool out, uint32_t *bits, int n)
{
	(void)ctx;
	swdt_t *t = M.prog_slot >= 0 ? M.card[M.prog_slot] : 0;
	if (!out)
		*bits = 0;
	for (int i = 0; i < n; i++) {
		if (out) {
			if (t)
				swdt_out(t, (int)(*bits >> i & 1));
		} else {
			*bits |= (uint32_t)(t ? swdt_in(t) : 1) << i;   /* nothing there: the pull-up */
		}
	}
	M.now += (uint64_t)n;                 /* ~1 MHz */
}

static void h_uart_open(void *ctx, uint32_t baud)
{
	(void)ctx;
	M.uart_baud = baud;
	M.uart_n = 0;
	if (M.uart_far.open)
		M.uart_far.open(baud);
}

static void h_uart_write(void *ctx, const uint8_t *d, int n)
{
	(void)ctx;
	if (M.uart_far.write) {
		if (M.uart_baud)
			M.uart_far.write(d, n);
		return;
	}
	for (int i = 0; i < n && M.uart_baud && M.uart_n < (int)sizeof M.uart; i++)
		M.uart[M.uart_n++] = d[i];          /* no far end: a loopback */
}

static int h_uart_read(void *ctx, uint8_t *d, int max)
{
	(void)ctx;
	if (M.uart_far.read)
		return M.uart_baud ? M.uart_far.read(d, max) : 0;
	int n = M.uart_n < max ? M.uart_n : max;
	memcpy(d, M.uart, (size_t)n);
	memmove(M.uart, M.uart + n, (size_t)(M.uart_n - n));
	M.uart_n -= n;
	return n;
}

static bool h_con_open(void *ctx) { (void)ctx; return M.con.open; }
static int h_con_room(void *ctx) { (void)ctx; return M.con.room; }

static void h_con_write(void *ctx, const uint8_t *d, int n)
{
	(void)ctx;
	if (n > M.con.room)
		M.con.room = -1;                  /* more than it said it would take: the tests look */
	else
		M.con.room -= n;
	for (int i = 0; i < n && M.con.to_pc_n < (int)sizeof M.con.to_pc; i++)
		M.con.to_pc[M.con.to_pc_n++] = d[i];
}

static int h_con_read(void *ctx, uint8_t *d, int max)
{
	(void)ctx;
	int n = M.con.from_pc_n < max ? M.con.from_pc_n : max;
	memcpy(d, M.con.from_pc, (size_t)n);
	memmove(M.con.from_pc, M.con.from_pc + n, (size_t)(M.con.from_pc_n - n));
	M.con.from_pc_n -= n;
	return n;
}

static const sysctl_hal hal = {
	h_spi_select, h_spi_xfer, h_pin_write, h_pin_read, h_adc,
	h_i2c_write, h_i2c_read, h_delay, h_now_ms, h_usb_write,
	h_prog_select, h_swd_io, h_uart_open, h_uart_write, h_uart_read,
	h_con_open, h_con_room, h_con_write, h_con_read,
};

/* --------------------------------------------------------------- machine */

/* power on a machine: FPGAs boot from whatever their flash holds */
void power_on(bool chip_flashed, bool cpu_flashed)
{
	static bool once;
	if (!once) {
		for (int i = 0; i < IMG_LEN; i++) {
			img_chip[i] = (uint8_t)(i * 31 + i / 256);
			img_cpu[i] = (uint8_t)(i * 17 + 3);
		}
		memcpy(img_chip, "\xff\x00\x00\xff\x7e\xaa\x99\x7e", 8);   /* iCE40 preamble */
		memcpy(img_cpu, "\xff\x00\x00\xff\x7e\xaa\x99\x7e", 8);
		once = true;
	}
	memset(&M, 0, sizeof M);
	M.bus = SPI_NONE;
	M.sys_nrst = true;
	M.prog_slot = -1;
	M.con.room = 4096;                    /* CFG_TUD_CDC_TX_BUFSIZE */
	swdt_init(&card2);
	M.card[2] = &card2;
	sst39_init(&M.rom);
	M.rom.t_se = 2000;                    /* shortened: the algorithm, not the wait, is under test */
	M.rom.t_sce = 5000;
	w25q_init(&M.fl0);
	w25q_init(&M.fl1);
	if (chip_flashed)
		memcpy(M.fl0.mem, img_chip, IMG_LEN);
	if (cpu_flashed)
		memcpy(M.fl1.mem, img_cpu, IMG_LEN);
	ice40_init(&M.chip, &M.fl0, img_chip, IMG_LEN);
	ice40_init(&M.cpu, &M.fl1, img_cpu, IMG_LEN);
	bridge_init(&M.br, &M.rom);
	tca_init(&M.u0, 0xFF, 0xFF);          /* CARD_RST_n and PROG_n pulled up */
	tca_init(&M.u1, 0xFF, 0xF8);          /* CPU card present (PRSNT2_n low), ID 00 */
	M.adc[ADC_V1V2] = 1200;
	M.now += 300000;                      /* both FPGAs have booted by now */
	tick();
	sysctl_init(&S, &hal, 0);
}

