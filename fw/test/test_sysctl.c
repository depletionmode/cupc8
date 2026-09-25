/*
 * SYS-001/002/003/005/007/008: the system controller core against models of the
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
 *   SYS-007  the whole 512 KB SRAM through RAM_READ_FAR/RAM_WRITE_FAR
 *   SYS-008  the USB console: the two rings in the API block against the
 *            bridge's SRAM (wrap, full, the USB side full, CR LF out, CR and
 *            LF in, HOST on open and close and after the kernel reboots),
 *            no bridge traffic while the port is closed or the chipset held
 *   SYS-004  the card programming port: the slot mux, SWD against a bit-level
 *            RP2040 target (wake-up, multi-drop, power-up, posted reads,
 *            WAIT, FAULT), and the UART tunnel
 */
#include <string.h>

#include "check.h"
#include "sysctl.h"
#include "sysmachine.h"

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
	CHECK(resp_n == 16 && memcmp(resp, "CUPC8 sysctl 2.1", 16) == 0, "PING: %.*s", resp_n, resp);
	/* a nonce comes back after the id (cupc8.py resyncs on it) */
	CHECK_EQ(REQ(0x00, 0xA5, 0x5A, 0x01, 0x02), ST_OK);
	CHECK(resp_n == 20 && memcmp(resp + 16, "\xA5\x5A\x01\x02", 4) == 0, "PING nonce: %d bytes", resp_n);

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
	CHECK_EQ(REQ(0x00, 1, 2, 3, 4, 5, 6, 7, 8, 9), ST_ARG);          /* PING takes a nonce of 8 bytes at most */
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

/* ------------------------------------------------------------ SYS-004 */

static uint8_t swd_req(bool ap, bool read, int a)
{
	int p = ap ^ read ^ (a >> 2 & 1) ^ (a >> 3 & 1);
	return (uint8_t)(1 | ap << 1 | read << 2 | (a >> 2 & 1) << 3 | (a >> 3 & 1) << 4 | p << 5 | 1 << 7);
}

/* one transfer through SWD_XFER: returns the ack, *v in/out */
static int xfer(bool ap, bool read, int a, uint32_t *v)
{
	uint8_t p[5] = { swd_req(ap, read, a) };
	int n = 1;
	if (!read) {
		for (int i = 0; i < 4; i++)
			p[1 + i] = (uint8_t)(*v >> (8 * i));
		n = 5;
	}
	if (req(0x55, p, n) != 0 || resp_n < 1)
		return -1;
	if (read && resp[0] == 1 && resp_n == 5)
		*v = resp[1] | (uint32_t)resp[2] << 8 | (uint32_t)resp[3] << 16 | (uint32_t)resp[4] << 24;
	return resp[0];
}

static void seq(const uint8_t *bits, int nbits)
{
	uint8_t p[2 + 64] = { (uint8_t)nbits, (uint8_t)(nbits >> 8) };
	memcpy(p + 2, bits, (size_t)(nbits + 7) / 8);
	CHECK_EQ(req(0x54, p, 2 + (nbits + 7) / 8), 0);
}

static const uint8_t line_reset[8] = { 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00 };   /* 56 ones, 8 idle */
static const uint8_t wake[] = { 0xff, 0x92, 0xf3, 0x09, 0x62, 0x95, 0x2d, 0x85, 0x86,
                                0xe9, 0xaf, 0xdd, 0xe3, 0xa2, 0x0e, 0xbc, 0x19, 0xa0, 0x01 };

static int targetsel(uint32_t id)
{
	uint8_t p[5] = { 0x99, (uint8_t)id, (uint8_t)(id >> 8), (uint8_t)(id >> 16), (uint8_t)(id >> 24) };
	return req(0x55, p, 5) == 0 ? resp[0] : -1;
}

static void sys004_progport(void)
{
	power_on(true, true);
	uint32_t v = 0;

	/* the mux: nothing selected until asked; an empty slot answers nothing */
	CHECK_EQ(M.prog_slot, -1);
	uint8_t s3 = 3;
	CHECK_EQ(req(0x53, &s3, 1), 0);
	CHECK_EQ(M.prog_slot, 3);
	CHECK_EQ(xfer(false, true, 0, &v), 7);
	uint8_t bad = 6;
	CHECK_EQ(req(0x53, &bad, 1), ST_ARG);

	/* slot 3's RP2040 starts dormant: a line reset alone gets no answer */
	uint8_t s2 = 2;
	CHECK_EQ(req(0x53, &s2, 1), 0);
	seq(line_reset, 64);
	CHECK_EQ(xfer(false, true, 0, &v), 7);

	/* the dormant-to-SWD wake-up, a line reset, TARGETSEL core 0: DPIDR */
	seq(wake, 148);
	seq(line_reset, 64);
	CHECK_EQ(targetsel(0x01002927), 1);
	v = 0;
	CHECK_EQ(xfer(false, true, 0, &v), 1);
	CHECK(v == 0x0BC12477, "DPIDR %08x", v);

	/* a TARGETSEL for another core deselects it */
	seq(line_reset, 64);
	CHECK_EQ(targetsel(0x11002927), 1);
	CHECK_EQ(xfer(false, true, 0, &v), 7);
	seq(line_reset, 64);
	CHECK_EQ(targetsel(0x01002927), 1);

	/* an AP access before power-up faults; ABORT clears it; power up */
	CHECK_EQ(xfer(true, true, 0xC, &v), 4);
	v = 0x1E;
	CHECK_EQ(xfer(false, false, 0, &v), 1);
	v = 0x50000000;
	CHECK_EQ(xfer(false, false, 4, &v), 1);
	CHECK_EQ(xfer(false, true, 4, &v), 1);
	CHECK(v & 0xA0000000, "CTRL/STAT acks power-up: %08x", v);

	/* memory through the AHB-AP: CSW word + increment, TAR, DRW; reads are posted */
	v = 0;
	CHECK_EQ(xfer(false, false, 8, &v), 1);          /* SELECT AP 0 bank 0 */
	v = 0x23000012;
	CHECK_EQ(xfer(true, false, 0, &v), 1);
	v = 0x20001000;
	CHECK_EQ(xfer(true, false, 4, &v), 1);
	for (uint32_t i = 0; i < 4; i++) {
		v = 0xC0DE0000 + i;
		CHECK_EQ(xfer(true, false, 0xC, &v), 1);
	}
	CHECK(card2.ram[0x1000] == 0x00 && card2.ram[0x1002] == 0xDE && card2.ram[0x100C] == 0x03, "RAM written");
	v = 0x20001000;
	xfer(true, false, 4, &v);
	CHECK_EQ(xfer(true, true, 0xC, &v), 1);          /* posted: the value comes next */
	CHECK_EQ(xfer(true, true, 0xC, &v), 1);
	CHECK(v == 0xC0DE0000, "first read, delivered by the second: %08x", v);
	CHECK_EQ(xfer(false, true, 0xC, &v), 1);         /* RDBUFF */
	CHECK(v == 0xC0DE0001, "RDBUFF %08x", v);

	/* WAIT: the engine retries until the access goes through */
	card2.wait_every = 2;
	v = 0x20001000;
	CHECK_EQ(xfer(true, false, 4, &v), 1);
	v = 0x12345678;
	CHECK_EQ(xfer(true, false, 0xC, &v), 1);
	CHECK(card2.ram[0x1000] == 0x78, "written through WAITs");
	card2.wait_every = 0;

	/* several transfers in one frame; it stops at the first failure */
	uint8_t many[] = { swd_req(false, true, 0), swd_req(false, true, 4), swd_req(true, true, 0xC) };
	CHECK_EQ(req(0x55, many, 3), 0);
	CHECK(resp_n == 15 && resp[0] == 1 && resp[5] == 1 && resp[10] == 1, "three reads in one frame (%d bytes)", resp_n);

	/* the UART tunnel */
	uint8_t baud[4] = { 0x00, 0xC2, 0x01, 0x00 };    /* 115200 */
	CHECK_EQ(req(0x56, baud, 4), 0);
	CHECK_EQ(M.uart_baud, 115200);
	CHECK_EQ(req(0x57, (const uint8_t *)"ÀsyncÀ", 6), 0);
	CHECK(resp_n == 6 && !memcmp(resp, "ÀsyncÀ", 6), "UART_XFER round trip (%d)", resp_n);

	/* PROG_n: only that slot's line, and only while asked */
	uint8_t pg[2] = { 4, 1 };
	CHECK_EQ(req(0x58, pg, 2), 0);
	CHECK(tca_pins(&M.u0, 1) == (uint8_t)~0x10, "PROG_n slot 5 low, the rest pulled up: %02x", tca_pins(&M.u0, 1));
	CHECK(tca_pins(&M.u0, 0) == 0xFF, "no card held in reset");
	pg[1] = 0;
	CHECK_EQ(req(0x58, pg, 2), 0);
	CHECK(tca_pins(&M.u0, 1) == 0xFF, "PROG_n released");
	pg[0] = 6;
	CHECK_EQ(req(0x58, pg, 2), ST_ARG);

	uint8_t none = 0xFF;
	CHECK_EQ(req(0x53, &none, 1), 0);
	CHECK_EQ(M.prog_slot, -1);
}

/* SYS-007: RAM_READ_FAR/RAM_WRITE_FAR, the whole 512 KB SRAM through the
 * bridge's RAM_RD24/RAM_WR24 (extended-ram.md), next to the 16-bit forms */
static void sys007_far_ram(void)
{
	power_on(true, true);
	static uint8_t p[3 + 3000], data[3000];

	/* across bank boundaries, across $0ffff (the 16-bit forms wrap there),
	 * and up to the last byte, each crossing the bridge's 256-byte frames */
	static const uint32_t at[] = {0x00100, 0x0BF80, 0x0FC00, 0x13F00, 0x42ABC, 0x7F448};
	for (int t = 0; t < (int)(sizeof at / sizeof at[0]); t++) {
		uint32_t a = at[t];
		int len = a == 0x7F448 ? 0x80000 - 0x7F448 : 3000;
		for (int i = 0; i < len; i++)
			data[i] = (uint8_t)(i * 5 + t * 29 + (i >> 8));
		p[0] = (uint8_t)a;
		p[1] = (uint8_t)(a >> 8);
		p[2] = (uint8_t)(a >> 16);
		memcpy(p + 3, data, (size_t)len);
		CHECK_EQ(req(0x13, p, 3 + len), ST_OK);
		CHECK(memcmp(M.br.ram + a, data, (size_t)len) == 0, "RAM_WRITE_FAR at $%05x in the model", a);
		CHECK_EQ(REQ(0x12, (uint8_t)a, (uint8_t)(a >> 8), (uint8_t)(a >> 16), (uint8_t)len, (uint8_t)(len >> 8)), ST_OK);
		CHECK(resp_n == len && memcmp(resp, data, (size_t)len) == 0, "RAM_READ_FAR at $%05x", a);
	}
	/* the 16-bit forms keep their meaning: SRAM $00000-$0ffff, wrapping */
	CHECK_EQ(REQ(0x11, 0xFE, 0xFF, 0xA1, 0xA2, 0xA3, 0xA4), ST_OK);
	CHECK(M.br.ram[0xFFFE] == 0xA1 && M.br.ram[0xFFFF] == 0xA2 && M.br.ram[0x0000] == 0xA3 &&
	      M.br.ram[0x0001] == 0xA4 && M.br.ram[0x10000] != 0xA3, "RAM_WRITE wraps past $ffff");
	CHECK_EQ(REQ(0x12, 0xFE, 0xFF, 0x00, 4, 0), ST_OK);
	CHECK(resp[0] == 0xA1 && resp[1] == 0xA2 && resp[2] == M.br.ram[0x10000], "RAM_READ_FAR does not wrap");

	/* argument checks */
	CHECK_EQ(REQ(0x12, 0, 0, 0, 0), ST_ARG);                         /* short */
	CHECK_EQ(REQ(0x12, 0, 0, 0, 0, 0), ST_ARG);                      /* length 0 */
	CHECK_EQ(REQ(0x12, 0, 0, 0, 0x01, 0x10), ST_ARG);                /* 4097 bytes */
	CHECK_EQ(REQ(0x12, 0xFF, 0xFF, 0x07, 2, 0), ST_ARG);             /* past $7ffff */
	CHECK_EQ(REQ(0x12, 0x00, 0x00, 0x08, 1, 0), ST_ARG);             /* $80000 */
	CHECK_EQ(REQ(0x12, 0xFF, 0xFF, 0x07, 1, 0), ST_OK);              /* the last byte */
	CHECK_EQ(REQ(0x13, 0, 0, 0), ST_ARG);                            /* no data */
	CHECK_EQ(REQ(0x13, 0xFF, 0xFF, 0x07, 1, 2), ST_ARG);             /* past $7ffff */
	CHECK_EQ(REQ(0x13, 0xFF, 0xFF, 0x07, 0x5A), ST_OK);
	CHECK_EQ(M.br.ram[0x7FFFF], 0x5A);

	/* with the chipset held they are refused like the other bridge commands */
	CHECK_EQ(REQ(0x44, 0), ST_OK);
	CHECK_EQ(REQ(0x12, 0, 0, 1, 1, 0), ST_NOCHIPSET);
	CHECK_EQ(REQ(0x13, 0, 0, 1, 0), ST_NOCHIPSET);
	CHECK_EQ(REQ(0x45, 0), ST_OK);
	CHECK_EQ(M.contention, 0);
}

/* ---------------------------------------------------------------- console */

#define RAM(a) M.br.ram[(a)]

/* virtual time passes a millisecond at a time, the main loop polling */
static void con_run(int ms)
{
	for (int i = 0; i < ms; i++) {
		M.now += 1000;
		tick();
		sysctl_poll(&S);
	}
}

/* the kernel's side: put bytes in CON_OUT (the caller keeps it from filling) */
static void kput(const char *s, int n)
{
	int head = RAM(CON_OUT_HEAD);
	for (int i = 0; i < n; i++) {
		RAM(CON_OUT + head) = (uint8_t)s[i];
		head = (head + 1) & (CON_OUT_SIZE - 1);
	}
	RAM(CON_OUT_HEAD) = (uint8_t)head;
}

/* the kernel's side: take everything in CON_IN */
static int kget(char *d)
{
	int n = 0, tail = RAM(CON_IN_TAIL);
	while (tail != RAM(CON_IN_HEAD)) {
		d[n++] = (char)RAM(CON_IN + tail);
		tail = (tail + 1) & (CON_IN_SIZE - 1);
	}
	RAM(CON_IN_TAIL) = (uint8_t)tail;
	d[n] = 0;
	return n;
}

static void pc_type(const char *s)
{
	int n = (int)strlen(s);
	memcpy(M.con.from_pc + M.con.from_pc_n, s, (size_t)n);
	M.con.from_pc_n += n;
}

static bool pc_got(const char *s)
{
	int n = (int)strlen(s);
	bool ok = M.con.to_pc_n == n && memcmp(M.con.to_pc, s, (size_t)n) == 0;
	if (!ok) {
		fprintf(stderr, "  the PC got %d bytes: '", M.con.to_pc_n);
		for (int i = 0; i < M.con.to_pc_n; i++)
			fputc(M.con.to_pc[i] >= 32 && M.con.to_pc[i] < 127 ? M.con.to_pc[i] : '.', stderr);
		fprintf(stderr, "', expected '%s'\n", s);
	}
	M.con.to_pc_n = 0;
	return ok;
}

/* the bridge's SRAM cycles, in order: address, and W or R */
static struct { uint32_t a; bool w; } ramlog[4096];
static int ramlog_n;
static void (*cpu_at_read)(uint32_t a);    /* the CPU acting between the card's cycles */

static void log_ram(uint32_t a, bool w)
{
	if (ramlog_n < (int)(sizeof ramlog / sizeof ramlog[0]))
		ramlog[ramlog_n].a = a, ramlog[ramlog_n++].w = w;
	if (!w && cpu_at_read)
		cpu_at_read(a);
}

static int last_write_to(uint32_t lo, uint32_t hi)
{
	int at = -1;
	for (int i = 0; i < ramlog_n; i++)
		if (ramlog[i].w && ramlog[i].a >= lo && ramlog[i].a <= hi)
			at = i;
	return at;
}

static int first_write_to(uint32_t a)
{
	for (int i = 0; i < ramlog_n; i++)
		if (ramlog[i].w && ramlog[i].a == a)
			return i;
	return -1;
}

/* the kernel prints while the card is between reading CON_OUT_HEAD and its data */
static void kernel_prints_now(uint32_t a)
{
	if (a == CON_OUT_HEAD + 4) {              /* the last byte of the index read */
		cpu_at_read = NULL;
		kput("LATE", 4);
	}
}

static void sys008_console(void)
{
	char in[256];
	power_on(true, true);
	M.br.on_ram = log_ram;
	/* RAM is junk at power-on. A PC with the port open before the kernel has
	 * booted: CON_FLAGS $A5 is not the kernel's, so the card drops both rings
	 * (moving only its own indices) instead of sending the PC a ring of junk */
	memset(M.br.ram + 0x6f00, 0xA5, 0x100);
	RAM(CON_OUT_HEAD) = 0x31;
	RAM(CON_IN_TAIL) = 0x17;
	M.con.open = true;
	con_run(CON_POLL_MS * 3);
	CHECK(pc_got(""), "power-up junk in the rings: nothing sent");
	CHECK(RAM(CON_OUT_TAIL) == 0x31 && RAM(CON_IN_HEAD) == 0x17 && RAM(CON_OUT_HEAD) == 0x31 &&
	      RAM(CON_IN_TAIL) == 0x17, "junk: the card's indices moved to the kernel's, the kernel's left alone");
	CHECK_EQ(RAM(CON_FLAGS), CON_HOST);
	M.con.open = false;
	con_run(1);
	M.bridge_frames = 0;
	/* the kernel zeroes the rings at boot */
	memset(M.br.ram + 0x6f00, 0xA5, 0x100);
	memset(M.br.ram + CON_OUT_HEAD, 0, 5);

	/* closed: no bridge traffic at all, nothing written, however long */
	uint8_t before[0x100];
	kput("hello\n", 6);
	memcpy(before, M.br.ram + 0x6f00, sizeof before);
	pc_type("typed while closed");
	con_run(500);
	CHECK_EQ(M.bridge_frames, 0);
	CHECK(memcmp(before, M.br.ram + 0x6f00, sizeof before) == 0, "closed: the API block untouched");
	CHECK_EQ(M.con.to_pc_n, 0);
	CHECK_EQ(M.con.from_pc_n, 18);
	M.con.from_pc_n = 0;

	/* open: HOST set on the first poll, the waiting output sent, \n as CR LF */
	M.con.open = true;
	con_run(1);
	CHECK_EQ(RAM(CON_FLAGS), CON_HOST);
	CHECK(pc_got("hello\r\n"), "output with CR LF");
	CHECK_EQ(RAM(CON_OUT_TAIL), 6);
	/* the card never writes into the output ring, only its tail */
	CHECK_EQ(last_write_to(CON_OUT, CON_OUT + CON_OUT_SIZE - 1), -1);

	/* polls come every CON_POLL_MS, not more often */
	int frames = M.bridge_frames;
	sysctl_poll(&S);
	CHECK_EQ(M.bridge_frames, frames);
	con_run(CON_POLL_MS);
	CHECK(M.bridge_frames > frames, "polled again after %d ms", CON_POLL_MS);

	/* the ring wraps: 20 bytes from index 120 */
	RAM(CON_OUT_HEAD) = RAM(CON_OUT_TAIL) = 120;
	kput("0123456789abcdefghij", 20);
	CHECK_EQ(RAM(CON_OUT_HEAD), 12);
	con_run(CON_POLL_MS);
	CHECK(pc_got("0123456789abcdefghij"), "output across the wrap");
	CHECK_EQ(RAM(CON_OUT_TAIL), 12);

	/* a full ring (127 bytes, one slot free) comes out whole */
	char full[CON_OUT_SIZE];
	for (int i = 0; i < CON_OUT_SIZE - 1; i++)
		full[i] = (char)('A' + i % 26);
	full[CON_OUT_SIZE - 1] = 0;
	kput(full, CON_OUT_SIZE - 1);
	CHECK_EQ(RAM(CON_OUT_HEAD), (12 + 127) & 127);
	CHECK_EQ((RAM(CON_OUT_HEAD) + 1) & 127, RAM(CON_OUT_TAIL));      /* full as the kernel sees it */
	con_run(CON_POLL_MS);
	CHECK(pc_got(full), "a full ring");
	CHECK_EQ(RAM(CON_OUT_TAIL), RAM(CON_OUT_HEAD));

	/* the USB side full: nothing taken; then only what fits, never half a CR LF */
	M.con.room = 0;
	kput("ab\ncd\n", 6);
	int tail = RAM(CON_OUT_TAIL);
	con_run(10);
	CHECK_EQ(RAM(CON_OUT_TAIL), tail);
	CHECK_EQ(M.con.to_pc_n, 0);
	M.con.room = 3;
	con_run(CON_POLL_MS);
	CHECK(pc_got("ab"), "3 bytes of room: the \\n's CR LF does not fit");
	CHECK_EQ(RAM(CON_OUT_TAIL), (tail + 2) & 127);
	M.con.room = 4;
	con_run(CON_POLL_MS);
	CHECK(pc_got("\r\ncd"), "the rest, as room allows");
	M.con.room = 4096;
	con_run(CON_POLL_MS);
	CHECK(pc_got("\r\n"), "and the last");
	CHECK(M.con.room >= 0, "con_write never got more than con_room");

	/* the kernel writing while the card polls: the card sends only up to the
	 * head it read, and the rest on its next poll */
	cpu_at_read = kernel_prints_now;
	kput("early ", 6);
	con_run(CON_POLL_MS);
	CHECK(pc_got("early "), "only what was there when the head was read");
	con_run(CON_POLL_MS);
	CHECK(pc_got("LATE"), "the late bytes on the next poll");

	/* input: CR is Enter, the LF of CR LF dropped, a lone LF is Enter */
	ramlog_n = 0;
	pc_type("10 print 1\r\n20 goto 10\n");
	con_run(CON_POLL_MS);
	CHECK_EQ(kget(in), 22);
	CHECK(strcmp(in, "10 print 1\r20 goto 10\r") == 0, "input: '%s'", in);
	CHECK(first_write_to(CON_IN_HEAD) > last_write_to(CON_IN, CON_IN + CON_IN_SIZE - 1),
	      "CON_IN_HEAD written after the data");
	/* a CR LF split across polls is still one Enter */
	pc_type("x\r");
	con_run(CON_POLL_MS);
	pc_type("\ny");
	con_run(CON_POLL_MS);
	CHECK_EQ(kget(in), 3);
	CHECK(strcmp(in, "x\ry") == 0, "split CR LF: '%s'", in);

	/* the input ring wraps, and fills: 63 bytes at most, the rest waits on the PC */
	RAM(CON_IN_HEAD) = RAM(CON_IN_TAIL) = 60;
	char many[101];
	for (int i = 0; i < 100; i++)
		many[i] = (char)('a' + i % 26);
	many[100] = 0;
	pc_type(many);
	con_run(CON_POLL_MS);
	CHECK_EQ(RAM(CON_IN_HEAD), (60 + 63) & 63);
	CHECK_EQ(M.con.from_pc_n, 100 - 63);
	CHECK(RAM(CON_IN + 63) == 'd' && RAM(CON_IN + 0) == 'e', "CON_IN wraps");
	con_run(10);
	CHECK_EQ(M.con.from_pc_n, 100 - 63);                             /* full: nothing more */
	CHECK_EQ(kget(in), 63);
	CHECK(memcmp(in, many, 63) == 0, "the first 63");
	con_run(CON_POLL_MS);
	CHECK_EQ(M.con.from_pc_n, 0);
	CHECK_EQ(kget(in), 37);
	CHECK(memcmp(in, many + 63, 37) == 0, "then the rest");

	/* the kernel boots again: it zeroes the indices and CON_FLAGS; the next poll sets HOST */
	memset(M.br.ram + CON_OUT_HEAD, 0, 5);
	con_run(CON_POLL_MS);
	CHECK_EQ(RAM(CON_FLAGS), CON_HOST);
	kput("again\n", 6);
	con_run(CON_POLL_MS);
	CHECK(pc_got("again\r\n"), "after the kernel's reboot");

	/* junk in the indices' high bits is ignored (they count modulo the ring) */
	RAM(CON_OUT_HEAD) = 0x80 | 3;
	RAM(CON_OUT_TAIL) = 0x80 | 1;
	RAM(CON_OUT + 1) = 'j';
	RAM(CON_OUT + 2) = 'k';
	con_run(CON_POLL_MS);
	CHECK(pc_got("jk"), "indices modulo the ring");
	CHECK_EQ(RAM(CON_OUT_TAIL), 3);

	/* the chipset held: no bridge traffic; booted again: HOST set again */
	CHECK_EQ(REQ(0x44, 0), ST_OK);
	RAM(CON_FLAGS) = 0;
	frames = M.bridge_frames;
	con_run(20);
	CHECK_EQ(M.bridge_frames, frames);
	CHECK_EQ(REQ(0x45, 0), ST_OK);
	con_run(CON_POLL_MS);
	CHECK_EQ(RAM(CON_FLAGS), CON_HOST);

	/* closed: HOST cleared once, then no traffic; the kernel then drops */
	M.con.open = false;
	con_run(1);
	CHECK_EQ(RAM(CON_FLAGS), 0);
	frames = M.bridge_frames;
	kput("dropped", 7);
	pc_type("zz");
	con_run(200);
	CHECK_EQ(M.bridge_frames, frames);
	CHECK_EQ(M.con.to_pc_n, 0);
	CHECK_EQ(M.con.from_pc_n, 2);

	/* the protocol port works the same with the console open and polling */
	M.con.open = true;
	con_run(CON_POLL_MS);
	CHECK_EQ(REQ(0x10, 0x26, 0x6f, 1, 0), ST_OK);
	CHECK(resp_n == 1 && resp[0] == CON_HOST, "RAM_READ of CON_FLAGS");
	M.br.on_ram = NULL;
	cpu_at_read = NULL;
}

int main(void)
{
	sys004_progport();
	sys001_protocol();
	sys007_far_ram();
	sys002_fpga_flash();
	sys003_rom();
	sys005_power_and_cards();
	sys008_console();
	return check_report("SYS-001..008 sysctl core");
}
