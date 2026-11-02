/*
 * System card bring-up diagnostic (2026-11-02): why do both FPGA config
 * flashes read JEDEC ID ffffff through sysctl? Not the product firmware: it
 * prints a report over USB CDC (stdio) every 5 s and never runs the protocol.
 *
 * With both FPGAs held in reset (CRESET_n low: their SPI pins go high-Z), for
 * each flash bus it reports
 *   pulls  - each pin read with the RP2040's pull-up, then pull-down. A pin
 *            that does not follow its own pull is driven by something else.
 *   drive  - SCK, MOSI, CS_n driven high then low, read back at the pad.
 *   bitbang- JEDEC ID (0x9F) by plain GPIO at ~50 kHz, MISO pulled up then
 *            down: a real chip answers the same both times.
 *   spi    - JEDEC ID through the SPI1 block, as sysctl does it, at 1 and
 *            10 MHz, MISO pulled up then down.
 * Then it releases nothing: the FPGAs stay held until the card is reset.
 */
#include <stdio.h>
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "pins.h"

typedef struct {
	const char *name;
	uint sck, mosi, miso, cs, creset, cdone;
} flbus;

static const flbus buses[] = {
	{"FL0 chipset", PIN_FL0_SCK, PIN_FL0_MOSI, PIN_FL0_MISO, PIN_FL0_NCS, PIN_CHIPSET_NCRESET, PIN_CHIPSET_CDONE},
	{"FL1 cpucard", PIN_FL1_SCK, PIN_FL1_MOSI, PIN_FL1_MISO, PIN_FL1_NCS, PIN_CPUCARD_NCRESET, PIN_CPUCARD_CDONE},
};

static void as_input(uint pin)
{
	gpio_init(pin);                       /* SIO, input */
	gpio_disable_pulls(pin);
}

static void pull(uint pin, bool up)
{
	gpio_set_pulls(pin, up, !up);
	sleep_us(200);                        /* ~50k against the node's capacitance */
}

static void pulls_report(const flbus *b)
{
	const uint pins[4] = {b->sck, b->mosi, b->miso, b->cs};
	const char *names[4] = {"SCK", "MOSI", "MISO", "CS_n"};
	printf("  pulls (up/down):");
	for (int i = 0; i < 4; i++) {
		as_input(pins[i]);
		pull(pins[i], true);
		int u = gpio_get(pins[i]);
		pull(pins[i], false);
		int d = gpio_get(pins[i]);
		printf(" %s=%d/%d", names[i], u, d);
	}
	printf("   (1/0 = follows its pull: undriven)\n");
}

static void drive_report(const flbus *b)
{
	const uint pins[3] = {b->sck, b->mosi, b->cs};
	const char *names[3] = {"SCK", "MOSI", "CS_n"};
	printf("  drive (hi/lo read back):");
	for (int i = 0; i < 3; i++) {
		as_input(pins[i]);
		gpio_put(pins[i], 1);
		gpio_set_dir(pins[i], true);
		sleep_us(50);
		int h = gpio_get(pins[i]);
		gpio_put(pins[i], 0);
		sleep_us(50);
		int l = gpio_get(pins[i]);
		gpio_set_dir(pins[i], false);
		printf(" %s=%d/%d", names[i], h, l);
	}
	printf("   (1/0 = pad follows)\n");
}

/* mode 0: the flash samples DI on SCK rising and shifts DO out on falling */
static uint8_t bb_byte(const flbus *b, uint8_t out)
{
	uint8_t in = 0;
	for (int i = 7; i >= 0; i--) {
		gpio_put(b->mosi, (out >> i) & 1);
		sleep_us(10);
		gpio_put(b->sck, 1);
		sleep_us(5);
		in = (uint8_t)(in << 1 | gpio_get(b->miso));
		sleep_us(5);
		gpio_put(b->sck, 0);
	}
	return in;
}

/* one bit-banged frame: send tx, then read n bytes; MISO pulled up */
static void bb_frame(const flbus *b, const uint8_t *tx, int ntx, uint8_t *rx, int nrx)
{
	as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
	gpio_put(b->sck, 0); gpio_set_dir(b->sck, true);
	gpio_put(b->mosi, 0); gpio_set_dir(b->mosi, true);
	gpio_put(b->cs, 1); gpio_set_dir(b->cs, true);
	pull(b->miso, true);
	sleep_us(20);
	gpio_put(b->cs, 0);
	sleep_us(20);
	for (int i = 0; i < ntx; i++)
		bb_byte(b, tx[i]);
	for (int i = 0; i < nrx; i++)
		rx[i] = bb_byte(b, 0);
	gpio_put(b->cs, 1);
	sleep_us(100);                        /* > tRES1 3 us, tRST 30 us */
	as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
}

/* wake a W25Q that is in deep power-down (0xB9 state: only 0xAB is heard),
 * reset it, then ask again */
static void wake_report(const flbus *b)
{
	uint8_t r[4];
	const uint8_t ab[4] = {0xAB, 0, 0, 0}, en = 0x66, rst = 0x99, sr1 = 0x05, jedec = 0x9F;
	bb_frame(b, ab, 4, r, 1);
	printf("  wake 0xAB (release power-down) device ID: %02x  (W25Q32 = 15, W25Q16 = 14)\n", r[0]);
	bb_frame(b, &en, 1, 0, 0);
	bb_frame(b, &rst, 1, 0, 0);
	bb_frame(b, &sr1, 1, r, 1);
	printf("  after reset 0x66/0x99: status-1 %02x", r[0]);
	bb_frame(b, &jedec, 1, r, 3);
	printf("  JEDEC %02x%02x%02x\n", r[0], r[1], r[2]);
}

static void bitbang_id(const flbus *b, bool miso_up, uint8_t id[3])
{
	as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
	gpio_put(b->sck, 0); gpio_set_dir(b->sck, true);
	gpio_put(b->mosi, 0); gpio_set_dir(b->mosi, true);
	gpio_put(b->cs, 1); gpio_set_dir(b->cs, true);
	pull(b->miso, miso_up);
	sleep_us(20);
	gpio_put(b->cs, 0);
	sleep_us(20);
	bb_byte(b, 0x9F);
	for (int i = 0; i < 3; i++)
		id[i] = bb_byte(b, 0);
	gpio_put(b->cs, 1);
	sleep_us(20);
	as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
}

/* the same steps as sysctl's h_spi_select / h_spi_xfer / fl_id */
static void spi_id(const flbus *b, uint hz, bool miso_up, uint8_t id[3])
{
	spi_set_baudrate(spi1, hz);
	as_input(b->miso);
	pull(b->miso, miso_up);
	gpio_set_function(b->sck, GPIO_FUNC_SPI);
	gpio_set_function(b->mosi, GPIO_FUNC_SPI);
	gpio_set_function(b->miso, GPIO_FUNC_SPI);
	as_input(b->cs);
	gpio_put(b->cs, 0);
	gpio_set_dir(b->cs, true);
	uint8_t tx[4] = {0x9F, 0, 0, 0}, rx[4] = {0};
	spi_write_read_blocking(spi1, tx, rx, 4);
	gpio_put(b->cs, 1);
	sleep_us(5);
	as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
	id[0] = rx[1]; id[1] = rx[2]; id[2] = rx[3];
}

/* both FPGAs held in reset: open drain low, as sysctl's fpga_hold */
static void report_hold_only(void)
{
	for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
		gpio_init(buses[k].creset);
		gpio_put(buses[k].creset, 0);
		gpio_set_dir(buses[k].creset, true);
	}
}

static void report(void)
{
	printf("\n=== sysctl_diag (build %s %s) t=%lus ===\n", __DATE__, __TIME__,
	       (unsigned long)(to_ms_since_boot(get_absolute_time()) / 1000));
	for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
		const flbus *b = &buses[k];
		/* hold: open drain low, as sysctl's fpga_hold */
		gpio_init(b->creset);
		gpio_put(b->creset, 0);
		gpio_set_dir(b->creset, true);
		as_input(b->cdone);
		sleep_ms(1);
		printf("%s: CRESET_n pad=%d (want 0)  CDONE=%d\n", b->name, gpio_get(b->creset), gpio_get(b->cdone));
		pulls_report(b);
		drive_report(b);
		uint8_t id[3];
		for (int up = 1; up >= 0; up--) {
			bitbang_id(b, up, id);
			printf("  bitbang 50kHz MISO pull-%s: %02x%02x%02x\n", up ? "up  " : "down", id[0], id[1], id[2]);
		}
		wake_report(b);
		const uint rates[2] = {1000000, 10000000};
		for (int r = 0; r < 2; r++)
			for (int up = 1; up >= 0; up--) {
				spi_id(b, rates[r], up, id);
				printf("  spi1 %2uMHz  MISO pull-%s: %02x%02x%02x\n", rates[r] / 1000000, up ? "up  " : "down",
				       id[0], id[1], id[2]);
			}
	}
	printf("(W25Q32JV = ef4016, W25Q16JV = ef4015; ffffff/000000 that follows the pull = nothing drives MISO)\n");
}

/*
 * Static patterns for tracing the wiring with a DMM (no scope): one line of a
 * bus high, the rest low, held until the next key on the serial port. CS_n
 * stays high (flash deselected, its DO high-Z) whenever MISO is driven.
 *   '1'..'4' FL0 (chipset flash U8), '5'..'8' FL1 (CPU card flash):
 *   SCK high / MOSI high / MISO high / CS_n low.  'r' report, 'x' release.
 */
static void pattern(const flbus *b, int which)
{
	const uint pins[4] = {b->sck, b->mosi, b->miso, b->cs};
	for (int i = 0; i < 4; i++) {
		as_input(pins[i]);
		gpio_put(pins[i], 0);
		gpio_set_dir(pins[i], true);
	}
	gpio_put(b->cs, 1);                   /* deselected unless testing CS_n */
	if (which == 3) {
		gpio_set_dir(b->miso, false);     /* never drive DO with CS_n low */
		gpio_put(b->cs, 0);
	} else {
		gpio_put(pins[which], 1);
	}
	static const char *what[4] = {"SCK high", "MOSI high", "MISO high", "CS_n low"};
	printf("pattern %s: %s, the others low%s\n", b->name, what[which],
	       which == 3 ? " (MISO released)" : ", CS_n high");
}

static void release_all(void)
{
	for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
		as_input(buses[k].sck); as_input(buses[k].mosi); as_input(buses[k].miso); as_input(buses[k].cs);
	}
	printf("all flash-bus pins released (FPGAs still held)\n");
}

int main(void)
{
	stdio_init_all();
	spi_init(spi1, 1000000);
	bool reporting = true;
	absolute_time_t next = get_absolute_time();
	for (;;) {
		int c = getchar_timeout_us(100000);
		if (c >= '1' && c <= '8') {
			reporting = false;
			report_hold_only();
			pattern(&buses[(c - '1') / 4], (c - '1') % 4);
		} else if (c == 'f') {
			/* does the FPGA's own boot attempt put its flash to sleep? */
			reporting = false;
			for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
				const flbus *b = &buses[k];
				uint8_t r[3];
				const uint8_t jedec = 0x9F;
				bb_frame(b, &jedec, 1, r, 3);
				printf("%s: before, held: JEDEC %02x%02x%02x\n", b->name, r[0], r[1], r[2]);
				gpio_set_dir(b->creset, false);          /* release: the FPGA boots */
				sleep_ms(2000);
				printf("%s: after 2 s booting, CDONE=%d\n", b->name, gpio_get(b->cdone));
				gpio_put(b->creset, 0);
				gpio_set_dir(b->creset, true);           /* hold again */
				sleep_ms(1);
				bb_frame(b, &jedec, 1, r, 3);
				printf("%s: held again, no wake: JEDEC %02x%02x%02x\n", b->name, r[0], r[1], r[2]);
			}
		} else if (c == 'w') {
			/* why does a program not stick? status registers, WEL, one test
			 * page at $3FF000 (bit-banged, then SPI1 at 10 MHz at $3FF100) */
			reporting = false;
			report_hold_only();
			for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
				const flbus *b = &buses[k];
				uint8_t r[4];
				const uint8_t ab = 0xAB, sr1 = 0x05, sr2 = 0x35, sr3 = 0x15, wren = 0x06;
				bb_frame(b, &ab, 1, 0, 0);
				uint8_t s1, s2, s3;
				bb_frame(b, &sr1, 1, &s1, 1);
				bb_frame(b, &sr2, 1, &s2, 1);
				bb_frame(b, &sr3, 1, &s3, 1);
				printf("%s: SR1=%02x SR2=%02x SR3=%02x  (BP bits = SR1 bits 2-4, SEC/TB 5-6; CMP = SR2 bit 6)\n",
				       b->name, s1, s2, s3);
				bb_frame(b, &wren, 1, 0, 0);
				bb_frame(b, &sr1, 1, &s1, 1);
				printf("  after WREN: SR1=%02x (WEL bit 1 must be set)\n", s1);
				const uint8_t pp[8] = {0x02, 0x3F, 0xF0, 0x00, 0x12, 0x34, 0x56, 0x78};
				bb_frame(b, pp, 8, 0, 0);
				sleep_ms(5);
				const uint8_t rd[4] = {0x03, 0x3F, 0xF0, 0x00};
				bb_frame(b, rd, 4, r, 4);
				printf("  bit-banged page program 12345678 at $3FF000, read back %02x%02x%02x%02x\n",
				       r[0], r[1], r[2], r[3]);
				/* the same at 10 MHz through SPI1, as sysctl does */
				bb_frame(b, &wren, 1, 0, 0);
				spi_set_baudrate(spi1, 10000000);
				as_input(b->miso);
				gpio_set_function(b->sck, GPIO_FUNC_SPI);
				gpio_set_function(b->mosi, GPIO_FUNC_SPI);
				gpio_set_function(b->miso, GPIO_FUNC_SPI);
				as_input(b->cs);
				gpio_put(b->cs, 0);
				gpio_set_dir(b->cs, true);
				const uint8_t pp2[8] = {0x02, 0x3F, 0xF1, 0x00, 0x9A, 0xBC, 0xDE, 0xF0};
				spi_write_blocking(spi1, pp2, 8);
				gpio_put(b->cs, 1);
				sleep_ms(5);
				const uint8_t rd2[4] = {0x03, 0x3F, 0xF1, 0x00};
				bb_frame(b, rd2, 4, r, 4);
				printf("  SPI1 10 MHz page program 9abcdef0 at $3FF100, read back %02x%02x%02x%02x\n",
				       r[0], r[1], r[2], r[3]);
			}
		} else if (c == 's') {
			/* sysctl's own sequence, every byte through SPI1 (WREN as a one-byte
			 * frame), at three clocks, in the spare sector $3FE000 */
			reporting = false;
			report_hold_only();
			static const uint hz[3] = {10000000, 4000000, 1000000};
			for (unsigned k = 0; k < sizeof buses / sizeof buses[0]; k++) {
				const flbus *b = &buses[k];
				const uint8_t ab = 0xAB;
				bb_frame(b, &ab, 1, 0, 0);
				for (int h = 0; h < 3; h++) {
					spi_set_baudrate(spi1, hz[h]);
					as_input(b->miso);
					gpio_set_function(b->sck, GPIO_FUNC_SPI);
					gpio_set_function(b->mosi, GPIO_FUNC_SPI);
					gpio_set_function(b->miso, GPIO_FUNC_SPI);
					as_input(b->cs);
					gpio_put(b->cs, 1);
					gpio_set_dir(b->cs, true);
#define FRAME(tx, ntx, rx, nrx) do { \
	gpio_put(b->cs, 0); \
	spi_write_blocking(spi1, tx, ntx); \
	if (nrx) { spi_read_blocking(spi1, 0, rx, nrx); } \
	gpio_put(b->cs, 1); \
	sleep_us(2); \
} while (0)
					uint8_t s1 = 0, back[4] = {0};
					const uint8_t wren = 0x06, sr1 = 0x05;
					const uint8_t se[4] = {0x20, 0x3F, 0xE0, 0x00};
					const uint8_t pp[8] = {0x02, 0x3F, 0xE0, 0x00, 0xC0, 0xFF, 0xEE, (uint8_t)h};
					const uint8_t rd[4] = {0x03, 0x3F, 0xE0, 0x00};
					FRAME(&wren, 1, 0, 0);
					FRAME(&sr1, 1, &s1, 1);
					int wel = s1;
					FRAME(se, 4, 0, 0);
					for (int t = 0; t < 500; t++) { FRAME(&sr1, 1, &s1, 1); if (!(s1 & 1)) break; sleep_ms(1); }
					FRAME(&wren, 1, 0, 0);
					FRAME(pp, 8, 0, 0);
					sleep_ms(5);
					FRAME(rd, 4, back, 4);
#undef FRAME
					printf("%s @%2u MHz: SR1 after WREN %02x, erase+program c0ffee%02x, read %02x%02x%02x%02x %s\n",
					       b->name, hz[h] / 1000000, wel, h, back[0], back[1], back[2], back[3],
					       back[0] == 0xC0 && back[3] == h ? "OK" : "FAIL");
					as_input(b->sck); as_input(b->mosi); as_input(b->cs); as_input(b->miso);
				}
			}
		} else if (c == 'x') {
			reporting = false;
			release_all();
		} else if (c == 'r') {
			reporting = true;
			next = get_absolute_time();
		}
		if (reporting && time_reached(next)) {
			report();
			next = make_timeout_time_ms(5000);
		}
	}
}
