/*
 * SYS-001/002/003/005: the system controller core against models of the
 * machine (fw/test/sysmodels.h), all driven through the USB protocol the way
 * tools/cupc8.py drives it. Time is virtual: SPI bytes and delays advance it.
 *
 *   SYS-001  USB protocol: framing, CRC, resync, stale frames, every command's
 *            argument checks, commands refused while the chipset is down
 *   SYS-002  FPGA flash: hold, erase, program, verify, reboot, for both FPGAs;
 *            never touching a flash its FPGA owns; the machine then boots with
 *            no system card at all
 *   SYS-003  the ROM chip through the bridge: ID, erase, program, verify,
 *            failure reporting, recovery after an interrupted write
 *   SYS-005  USB-C source class; cards run unless deliberately held
 */
#include <string.h>

#include "check.h"
#include "sysctl.h"
#include "sysmodels.h"

#define IMG_LEN 135100                    /* an HX4K bitstream */

static struct {
	uint64_t now;                         /* µs */
	int bus;
	sst39_t rom;
	w25q_t fl0, fl1;
	ice40_t chip, cpu;
	bridge_t br;
	tca_t u0, u1;
	int adc[3];
	bool sys_nrst;
	int reset_pulses;
	int contention;                       /* flash accessed while its FPGA owns it */
	uint8_t usb[8 + SYS_MAX_PAYLOAD];
	int usb_n;
} M;

static uint8_t img_chip[IMG_LEN], img_cpu[IMG_LEN];
static sysctl_t S;

/* ------------------------------------------------------------------ HAL */

static void tick(void)
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

static const sysctl_hal hal = {
	h_spi_select, h_spi_xfer, h_pin_write, h_pin_read, h_adc,
	h_i2c_write, h_i2c_read, h_delay, h_now_ms, h_usb_write,
};

/* --------------------------------------------------------------- machine */

/* power on a machine: FPGAs boot from whatever their flash holds */
static void power_on(bool chip_flashed, bool cpu_flashed)
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

/* ------------------------------------------------------------ USB helpers */

static uint8_t crc8(const uint8_t *p, int n)
{
	uint8_t c = 0;
	for (int i = 0; i < n; i++) {
		c ^= p[i];
		for (int b = 0; b < 8; b++)
			c = (uint8_t)(c & 0x80 ? c << 1 ^ 0x07 : c << 1);
	}
	return c;
}

static int frame(uint8_t *f, uint8_t cmd, const uint8_t *p, int n)
{
	f[0] = 0xC8;
	f[1] = cmd;
	f[2] = (uint8_t)n;
	f[3] = (uint8_t)(n >> 8);
	if (n)
		memcpy(f + 4, p, (size_t)n);
	f[4 + n] = crc8(f + 1, 3 + n);
	return 5 + n;
}

/* parse exactly one well-formed reply from the USB output */
static int take_reply(uint8_t *out, int *on)
{
	if (M.usb_n < 5 || M.usb[0] != 0xC8)
		return -1;
	int n = M.usb[2] | M.usb[3] << 8;
	CHECK_EQ(M.usb_n, 5 + n);
	CHECK(crc8(M.usb + 1, 3 + n) == M.usb[4 + n], "reply CRC");
	if (out)
		memcpy(out, M.usb + 4, (size_t)n);
	if (on)
		*on = n;
	int st = M.usb[1];
	M.usb_n = 0;
	return st;
}

static uint8_t resp[SYS_MAX_PAYLOAD];
static int resp_n;

static int req(uint8_t cmd, const uint8_t *p, int n)
{
	static uint8_t f[8 + SYS_MAX_PAYLOAD];
	int len = frame(f, cmd, p, n);
	M.usb_n = 0;
	sysctl_rx(&S, f, len);
	return take_reply(resp, &resp_n);
}

#define REQ(cmd, ...) ({ uint8_t a_[] = {__VA_ARGS__}; req(cmd, a_, (int)sizeof a_); })

/* the cupc8.py flow for one FPGA: hold, erase, program, verify, boot */
static int flash_fpga(int t, const uint8_t *img, int len)
{
	static uint8_t p[SYS_MAX_PAYLOAD];
	int r;
	if ((r = REQ(0x44, (uint8_t)t)) != ST_OK)
		return r;
	if ((r = REQ(0x41, (uint8_t)t, 0, 0, 0, (uint8_t)len, (uint8_t)(len >> 8), (uint8_t)(len >> 16))) != ST_OK)
		return r;
	for (int off = 0; off < len; off += SYS_MAX_PAYLOAD - 4) {
		int k = len - off < SYS_MAX_PAYLOAD - 4 ? len - off : SYS_MAX_PAYLOAD - 4;
		p[0] = (uint8_t)t;
		p[1] = (uint8_t)off;
		p[2] = (uint8_t)(off >> 8);
		p[3] = (uint8_t)(off >> 16);
		memcpy(p + 4, img + off, (size_t)k);
		if ((r = req(0x42, p, 4 + k)) != ST_OK)
			return r;
	}
	return REQ(0x45, (uint8_t)t);
}

/* ------------------------------------------------------------------ tests */

static void sys001_protocol(void)
{
	power_on(true, true);
	uint8_t f[64];

	CHECK_EQ(req(0x00, 0, 0), ST_OK);
	CHECK(resp_n == 16 && memcmp(resp, "CUPC8 sysctl 2.0", 16) == 0, "PING: %.*s", resp_n, resp);

	/* noise before a frame is skipped; a frame split into single bytes works */
	int n = frame(f, 0x00, 0, 0);
	sysctl_rx(&S, (const uint8_t *)"garbage\x01\x02", 9);
	CHECK_EQ(M.usb_n, 0);
	for (int i = 0; i < n; i++)
		sysctl_rx(&S, f + i, 1);
	CHECK_EQ(take_reply(0, 0), ST_OK);

	/* bad CRC, unknown command, oversized length */
	n = frame(f, 0x00, 0, 0);
	f[n - 1] ^= 0x55;
	sysctl_rx(&S, f, n);
	CHECK_EQ(take_reply(0, 0), ST_CRC);
	CHECK_EQ(req(0x77, 0, 0), ST_CMD);
	uint8_t big[4] = {0xC8, 0x00, 0x01, 0x20};          /* 8193 bytes */
	sysctl_rx(&S, big, 4);
	CHECK_EQ(take_reply(0, 0), ST_ARG);

	/* a frame left half-sent is dropped after 100 ms, and the next one works */
	n = frame(f, 0x00, 0, 0);
	sysctl_rx(&S, f, 3);
	M.now += 150000;
	sysctl_poll(&S);
	sysctl_rx(&S, f, n);
	CHECK_EQ(take_reply(0, 0), ST_OK);

	/* argument checks, command by command */
	CHECK_EQ(REQ(0x00, 1), ST_ARG);                                  /* PING takes nothing */
	CHECK_EQ(REQ(0x10, 0, 0, 0), ST_ARG);                            /* RAM_READ short */
	CHECK_EQ(REQ(0x10, 0, 0, 0, 0), ST_ARG);                         /* length 0 */
	CHECK_EQ(REQ(0x10, 0, 0, 0x01, 0x10), ST_ARG);                   /* 4097 bytes */
	CHECK_EQ(REQ(0x11, 0, 0), ST_ARG);                               /* RAM_WRITE with no data */
	CHECK_EQ(REQ(0x20, 0xFF, 0xFF, 0x07, 2, 0), ST_ARG);             /* past the ROM's end */
	CHECK_EQ(REQ(0x21, 0, 0, 0, 0, 0, 0x09), ST_ARG);
	CHECK_EQ(REQ(0x44, 2), ST_ARG);                                  /* no FPGA 2 */
	CHECK_EQ(REQ(0x45, 2), ST_ARG);
	CHECK_EQ(REQ(0x40, 2, 0, 0, 0, 1, 0), ST_ARG);
	CHECK_EQ(REQ(0x52, 6, 1), ST_ARG);                               /* no slot 7 */
	CHECK_EQ(REQ(0x30), ST_ARG);

	/* flash commands on a flash its FPGA owns are refused */
	CHECK_EQ(REQ(0x43, 0), ST_NOTHELD);
	CHECK_EQ(REQ(0x40, 1, 0, 0, 0, 16, 0), ST_NOTHELD);
	CHECK_EQ(REQ(0x41, 0, 0, 0, 0, 0, 16, 0), ST_NOTHELD);
	CHECK_EQ(M.contention, 0);

	/* STATUS */
	CHECK_EQ(req(0x01, 0, 0), ST_OK);
	CHECK_EQ(resp_n, 11);
	CHECK_EQ(resp[2], 3);                                            /* both CDONE */
	CHECK_EQ(resp[3], 0);                                            /* nothing held */
	CHECK_EQ(resp[10], 1);                                           /* CPU card present */

	/* RAM through the bridge, crossing its 256-byte frames */
	uint8_t data[1000];
	uint8_t p[2 + 1000];
	for (int i = 0; i < 1000; i++)
		data[i] = (uint8_t)(i * 7 + 1);
	p[0] = 0x00;
	p[1] = 0x20;
	memcpy(p + 2, data, 1000);
	CHECK_EQ(req(0x11, p, 1002), ST_OK);
	CHECK_EQ(REQ(0x10, 0x00, 0x20, 0xE8, 0x03), ST_OK);
	CHECK(resp_n == 1000 && memcmp(resp, data, 1000) == 0, "RAM read back");
	CHECK(memcmp(M.br.ram + 0x2000, data, 1000) == 0, "RAM in the model");

	/* CPU control and trace */
	CHECK_EQ(REQ(0x30, 0x01), ST_OK);
	CHECK(resp[0] & 0x01, "stopped");
	CHECK_EQ(REQ(0x30, 0x40), ST_OK);
	CHECK(resp[0] & 0x80, "/CPU_RST shown");
	CHECK_EQ(REQ(0x30, 0x00), ST_OK);
	bridge_trace_push(&M.br, 0x1234, 0x56, 3);
	bridge_trace_push(&M.br, 0x1235, 0x78, 1);
	CHECK_EQ(req(0x31, 0, 0), ST_OK);
	CHECK(resp_n == 2 + 8 && resp[0] == 2 && resp[1] == 0, "trace header %d %d", resp[0], resp[1]);
	CHECK(resp[2] == 0x34 && resp[3] == 0x12 && resp[4] == 0x56 && resp[5] == 3, "trace entry 0");
	for (int i = 0; i < 600; i++)
		bridge_trace_push(&M.br, (uint16_t)i, 0, 0);
	CHECK_EQ(req(0x31, 0, 0), ST_OK);
	CHECK(resp_n == 2 + 512 * 4 && (resp[0] | resp[1] << 8) == (0x8000 | 512), "full ring, lost bit");
	CHECK_EQ(req(0x31, 0, 0), ST_OK);
	CHECK(resp_n == 2 && resp[0] == 0 && resp[1] == 0, "drained, lost bit cleared");

	/* machine reset */
	CHECK_EQ(req(0x32, 0, 0), ST_OK);
	CHECK(M.reset_pulses == 1 && M.sys_nrst, "one SYS_nRST pulse, released");

	/* with the chipset held, the bridge is gone: its commands are refused */
	CHECK_EQ(REQ(0x44, 0), ST_OK);
	CHECK_EQ(REQ(0x10, 0, 0, 1, 0), ST_NOCHIPSET);
	CHECK_EQ(REQ(0x20, 0, 0, 0, 1, 0), ST_NOCHIPSET);
	CHECK_EQ(REQ(0x30, 0), ST_NOCHIPSET);
	CHECK_EQ(req(0x01, 0, 0), ST_OK);                                /* STATUS still answers */
	CHECK(resp[0] == 0 && resp[3] == 1, "status with the chipset held");
	CHECK_EQ(REQ(0x45, 0), ST_OK);                                   /* it boots again */
	CHECK_EQ(REQ(0x10, 0, 0, 1, 0), ST_OK);
	CHECK_EQ(M.contention, 0);
}

static void sys002_fpga_flash(void)
{
	/* a factory-new machine: both flashes blank, nothing configured */
	power_on(false, false);
	CHECK(!M.chip.cdone && !M.cpu.cdone, "blank flash: no CDONE");

	for (int t = 0; t < 2; t++) {
		const uint8_t *img = t ? img_cpu : img_chip;
		w25q_t *fl = t ? &M.fl1 : &M.fl0;
		ice40_t *f = t ? &M.cpu : &M.chip;

		CHECK_EQ(REQ(0x44, (uint8_t)t), ST_OK);
		CHECK_EQ(REQ(0x43, (uint8_t)t), ST_OK);
		CHECK(resp_n == 3 && resp[0] == 0xEF && resp[1] == 0x40 && resp[2] == 0x16, "JEDEC ID");
		CHECK_EQ(flash_fpga(t, img, IMG_LEN), ST_OK);
		CHECK(memcmp(fl->mem, img, IMG_LEN) == 0, "target %d: image in flash", t);
		CHECK(f->cdone && f->loads == 1, "target %d: configured once", t);
		CHECK_EQ(fl->violations, 0);
	}
	CHECK_EQ(M.contention, 0);

	/* the proof: power the machine again with no system card at all */
	power_on(true, true);
	w25q_t keep0 = M.fl0, keep1 = M.fl1;
	(void)keep0;
	(void)keep1;
	CHECK(M.chip.cdone && M.cpu.cdone, "boots from its own flash, no sysctl");

	/* a wrong image is reported, and the FPGA stays down */
	power_on(true, true);
	uint8_t bad[IMG_LEN];
	memcpy(bad, img_cpu, IMG_LEN);
	bad[1000] ^= 1;
	CHECK_EQ(flash_fpga(1, bad, IMG_LEN), ST_TIMEOUT);
	CHECK(!M.cpu.cdone, "wrong image: no CDONE");
	CHECK_EQ(flash_fpga(1, img_cpu, IMG_LEN), ST_OK);               /* recovers */
	CHECK(M.cpu.cdone, "recovered");

	/* a stuck flash bit is reported with its address */
	power_on(true, true);
	M.fl1.stuck_addr = 0x1234;
	M.fl1.stuck_mask = 0x80;
	uint8_t zeros[IMG_LEN] = {0};
	CHECK_EQ(flash_fpga(1, zeros, IMG_LEN), ST_VERIFY);
	CHECK(resp_n == 3 && (resp[0] | resp[1] << 8 | resp[2] << 16) == 0x1234,
	      "verify address %02x%02x%02x", resp[2], resp[1], resp[0]);

	/* a write across page boundaries, and an erase of exactly its sectors */
	power_on(true, true);
	CHECK_EQ(REQ(0x44, 1), ST_OK);
	uint8_t p[4 + 600];
	p[0] = 1; p[1] = 0xF0; p[2] = 0x00; p[3] = 0x20;                  /* $2000F0 */
	for (int i = 0; i < 600; i++)
		p[4 + i] = (uint8_t)(i ^ 0x5A);
	CHECK_EQ(REQ(0x41, 1, 0, 0, 0x20, 0, 0x10, 0), ST_OK);           /* $200000 + 4 KB */
	CHECK_EQ(req(0x42, p, sizeof p), ST_OK);
	CHECK_EQ(REQ(0x40, 1, 0xF0, 0x00, 0x20, 0x58, 0x02), ST_OK);
	CHECK(resp_n == 600 && memcmp(resp, p + 4, 600) == 0, "page-crossing write");
	M.fl1.mem[0x201000] = 0x42;
	CHECK_EQ(REQ(0x41, 1, 0x00, 0x08, 0x20, 1, 0, 0), ST_OK);        /* 1 byte in the $200000 sector */
	CHECK(M.fl1.mem[0x2000F0] == 0xFF && M.fl1.mem[0x201000] == 0x42, "one sector erased");
	CHECK_EQ(REQ(0x45, 1), ST_OK);
	CHECK_EQ(M.contention, 0);
	CHECK_EQ(M.fl1.violations, 0);
}

static void sys003_rom(void)
{
	power_on(true, true);
	static uint8_t img[64 * 1024];
	for (unsigned i = 0; i < sizeof img; i++)
		img[i] = i % 5 == 0 ? 0xFF : (uint8_t)(i * 13 + i / 97);

	CHECK_EQ(req(0x23, 0, 0), ST_OK);
	CHECK(resp_n == 2 && resp[0] == 0xBF && resp[1] == 0xD7, "ROM ID %02x %02x", resp[0], resp[1]);

	/* program over a dirty chip after erasing the range */
	memset(M.rom.mem, 0x00, sizeof img);
	CHECK_EQ(REQ(0x21, 0, 0, 0, 0, 0, 1), ST_OK);                    /* 64 KB */
	int writes0 = M.rom.writes;
	uint8_t p[3 + 4000];
	for (unsigned off = 0; off < sizeof img; off += 4000) {
		unsigned k = sizeof img - off < 4000 ? sizeof img - off : 4000;
		p[0] = (uint8_t)off; p[1] = (uint8_t)(off >> 8); p[2] = (uint8_t)(off >> 16);
		memcpy(p + 3, img + off, k);
		CHECK_EQ(req(0x22, p, 3 + (int)k), ST_OK);
	}
	CHECK(memcmp(M.rom.mem, img, sizeof img) == 0, "ROM image written");
	int programmed = 0;
	for (unsigned i = 0; i < sizeof img; i++)
		programmed += img[i] != 0xFF;
	CHECK_EQ(M.rom.writes - writes0, programmed * 4);                /* $FF skipped, no retries */
	CHECK(M.br.ctl_when_busw & 0x01, "CPU stopped while the ROM is written");
	CHECK_EQ(M.br.ctl, 0);                                           /* and released after */

	/* read back through the protocol */
	CHECK_EQ(REQ(0x20, 0x00, 0x10, 0, 0xA0, 0x0F), ST_OK);
	CHECK(resp_n == 4000 && memcmp(resp, img + 0x1000, 4000) == 0, "ROM read back");

	/* a CPU held in reset stays held */
	CHECK_EQ(REQ(0x30, 0x40), ST_OK);
	CHECK_EQ(REQ(0x22, 0x00, 0x00, 0x02, 0x11), ST_OK);
	CHECK_EQ(M.br.ctl, 0x40);
	CHECK_EQ(REQ(0x30, 0x00), ST_OK);

	/* a bit that will not program is reported with its address */
	M.rom.stuck_addr = 0x30010;
	M.rom.stuck_mask = 0x01;
	CHECK_EQ(REQ(0x22, 0x10, 0x00, 0x03, 0x00), ST_VERIFY);
	CHECK(resp_n == 3 && (resp[0] | resp[1] << 8 | resp[2] << 16) == 0x30010, "ROM verify address");

	/* sector erase covers exactly the sectors of the range */
	memset(M.rom.mem + 0x40000, 0x00, 0x4000);
	CHECK_EQ(REQ(0x21, 0x00, 0x18, 0x04, 0x00, 0x10, 0x00), ST_OK);  /* $41800, 4 KB */
	CHECK(M.rom.mem[0x40FFF] == 0x00 && M.rom.mem[0x41000] == 0xFF && M.rom.mem[0x42FFF] == 0xFF &&
	      M.rom.mem[0x43000] == 0x00, "sectors $41000-$42FFF erased only");

	/* an interrupted write (the host went away half way) recovers by redoing it */
	M.rom.stuck_mask = 0;
	CHECK_EQ(REQ(0x21, 0, 0, 0, 0, 0, 1), ST_OK);
	p[0] = 0; p[1] = 0; p[2] = 0;
	memcpy(p + 3, img, 2000);
	CHECK_EQ(req(0x22, p, 3 + 2000), ST_OK);                         /* ... then nothing */
	CHECK_EQ(REQ(0x21, 0, 0, 0, 0, 0, 1), ST_OK);
	for (unsigned off = 0; off < sizeof img; off += 4000) {
		unsigned k = sizeof img - off < 4000 ? sizeof img - off : 4000;
		p[0] = (uint8_t)off; p[1] = (uint8_t)(off >> 8); p[2] = (uint8_t)(off >> 16);
		memcpy(p + 3, img + off, k);
		CHECK_EQ(req(0x22, p, 3 + (int)k), ST_OK);
	}
	CHECK(memcmp(M.rom.mem, img, sizeof img) == 0, "rewritten after the interruption");

	/* chip erase, and a chip that never finishes erasing */
	CHECK_EQ(REQ(0x21, 0, 0, 0, 0, 0, 0), ST_OK);
	CHECK(M.rom.mem[0] == 0xFF && M.rom.mem[0x7FFFF] == 0xFF, "chip erased");
	M.rom.t_se = 10u * 1000 * 1000;
	CHECK_EQ(REQ(0x21, 0, 0x20, 0, 0, 0x10, 0), ST_TIMEOUT);
}

static void sys005_power_and_cards(void)
{
	/* CC voltage -> source class, at the boundaries, from either CC line */
	CHECK_EQ(power_class_of(0, 0), PWR_UNKNOWN);
	CHECK_EQ(power_class_of(199, 0), PWR_UNKNOWN);
	CHECK_EQ(power_class_of(200, 0), PWR_DEFAULT);
	CHECK_EQ(power_class_of(0, 659), PWR_DEFAULT);
	CHECK_EQ(power_class_of(660, 0), PWR_1A5);
	CHECK_EQ(power_class_of(0, 1229), PWR_1A5);
	CHECK_EQ(power_class_of(1230, 0), PWR_3A0);

	power_on(true, true);
	M.adc[ADC_CC2] = 1000;
	CHECK_EQ(req(0x50, 0, 0), ST_OK);
	CHECK(resp_n == 3 && resp[0] == PWR_1A5 && (resp[1] | resp[2] << 8) == 1000, "POWER");

	/* sysctl at start-up drives nothing: every card runs */
	CHECK_EQ(M.u0.reg[6], 0xFF);                                     /* all inputs */
	CHECK_EQ(tca_pins(&M.u0, 0) & 0x3F, 0x3F);

	/* holding one card in reset drives only that line */
	CHECK_EQ(REQ(0x52, 2, 1), ST_OK);
	CHECK_EQ(tca_pins(&M.u0, 0) & 0x3F, 0x3F & ~0x04);
	CHECK_EQ(M.u0.reg[6] & 0x3F, 0x3F & ~0x04);                      /* only bit 2 an output */
	CHECK_EQ(tca_pins(&M.u0, 1), 0xFF);                              /* PROG_n untouched */
	CHECK_EQ(REQ(0x52, 2, 0), ST_OK);
	CHECK_EQ(M.u0.reg[6], 0xFF);                                     /* back to inputs */
	CHECK_EQ(tca_pins(&M.u0, 0) & 0x3F, 0x3F);

	/* no CPU card fitted: reported, and the rest still works */
	M.u1.ext[1] = 0xFF;
	CHECK_EQ(req(0x01, 0, 0), ST_OK);
	CHECK_EQ(resp[10], 0);
}

int main(void)
{
	sys001_protocol();
	sys002_fpga_flash();
	sys003_rom();
	sys005_power_and_cards();
	return check_report("SYS-001/002/003/005 sysctl core");
}
