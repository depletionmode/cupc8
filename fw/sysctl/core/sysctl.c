/*
 * The USB command protocol and the power-up sequence
 * (doc/hardware/sysctl.md, "USB protocol" and "Power-up sequence").
 */
#include "sysctl.h"

#include <string.h>

#define MAGIC        0xC8
#define FRAME_MS     100                  /* a frame older than this is dropped */
#define ROM_SIZE     0x80000u
#define FLASH_SIZE   0x400000u
#define SLOT_TABLE   0x0002

enum {
	C_PING = 0x00, C_STATUS = 0x01,
	C_RAM_READ = 0x10, C_RAM_WRITE = 0x11,
	C_ROM_READ = 0x20, C_ROM_ERASE = 0x21, C_ROM_PROGRAM = 0x22, C_ROM_ID = 0x23,
	C_CPU_CTL = 0x30, C_TRACE = 0x31,
	C_FLASH_READ = 0x40, C_FLASH_ERASE = 0x41, C_FLASH_PROGRAM = 0x42,
	C_FPGA_BOOT = 0x43, C_FPGA_LOAD = 0x44,
	C_POWER = 0x50, C_POWER_FORCE = 0x51, C_CARD_RESET = 0x52,
};

static uint8_t reply_buf[4 + SYS_MAX_PAYLOAD + 1];

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

static uint32_t le16(const uint8_t *p) { return p[0] | (uint32_t)p[1] << 8; }
static uint32_t le24(const uint8_t *p) { return le16(p) | (uint32_t)p[2] << 16; }

/* the payload goes in reply_buf + 4 before this is called */
static void reply(sysctl_t *s, uint8_t status, int n)
{
	reply_buf[0] = MAGIC;
	reply_buf[1] = status;
	reply_buf[2] = (uint8_t)n;
	reply_buf[3] = (uint8_t)(n >> 8);
	reply_buf[4 + n] = crc8(reply_buf + 1, 3 + n);
	s->hal->usb_write(s->ctx, reply_buf, 5 + n);
}

static int power_payload(sysctl_t *s, uint8_t *out)
{
	int cc1 = s->hal->adc_mv(s->ctx, ADC_CC1), cc2 = s->hal->adc_mv(s->ctx, ADC_CC2);
	int cc = cc1 > cc2 ? cc1 : cc2;
	out[0] = s->power_class;
	out[1] = (uint8_t)cc;
	out[2] = (uint8_t)(cc >> 8);
	out[3] = s->held_slots;
	out[4] = s->power_forced;
	return 5;
}

/* one request; returns the status, with the reply payload length in *rn */
static int command(sysctl_t *s, uint8_t cmd, const uint8_t *p, int n, uint8_t *out, int *rn)
{
	uint32_t bad = 0;
	int r;
	*rn = 0;

	switch (cmd) {
	case C_PING: {
		static const char id[] = "CUPC8 sysctl " SYSCTL_VERSION;
		if (n != 0)
			return ST_ARG;
		memcpy(out, id, sizeof id - 1);
		*rn = sizeof id - 1;
		return ST_OK;
	}
	case C_STATUS: {
		if (n != 0)
			return ST_ARG;
		int v12 = s->hal->adc_mv(s->ctx, ADC_V1V2);
		uint8_t pw[5];
		power_payload(s, pw);
		out[0] = br_status(s);
		out[1] = br_gpo(s);
		out[2] = s->cdone;
		out[3] = pw[0];
		out[4] = pw[1];
		out[5] = pw[2];
		out[6] = (uint8_t)v12;
		out[7] = (uint8_t)(v12 >> 8);
		out[8] = s->held_slots;
		out[9] = s->boot_status;
		*rn = 10;
		return ST_OK;
	}
	case C_RAM_READ: {
		if (n != 4)
			return ST_ARG;
		uint32_t len = le16(p + 2);
		if (len == 0 || len > SYS_MAX_PAYLOAD)
			return ST_ARG;
		br_ram_read(s, (uint16_t)le16(p), out, (int)len);
		*rn = (int)len;
		return ST_OK;
	}
	case C_RAM_WRITE:
		if (n < 3)
			return ST_ARG;
		br_ram_write(s, (uint16_t)le16(p), p + 2, n - 2);
		return ST_OK;
	case C_ROM_READ: {
		if (n != 5)
			return ST_ARG;
		uint32_t addr = le24(p), len = le16(p + 3);
		if (len == 0 || len > SYS_MAX_PAYLOAD || addr + len > ROM_SIZE)
			return ST_ARG;
		br_rom_read(s, addr, out, (int)len);
		*rn = (int)len;
		return ST_OK;
	}
	case C_ROM_ERASE: {
		if (n != 6)
			return ST_ARG;
		uint32_t addr = le24(p), len = le24(p + 3);
		if (addr + len > ROM_SIZE)
			return ST_ARG;
		return rom_erase(s, addr, len);
	}
	case C_ROM_PROGRAM: {
		if (n < 4 || le24(p) + (uint32_t)(n - 3) > ROM_SIZE)
			return ST_ARG;
		r = rom_program(s, le24(p), p + 3, n - 3, &bad);
		break;
	}
	case C_ROM_ID:
		if (n != 0)
			return ST_ARG;
		*rn = 2;
		return rom_id(s, &out[0], &out[1]);
	case C_CPU_CTL:
		if (n != 1)
			return ST_ARG;
		br_cpu_ctl(s, p[0]);
		out[0] = br_status(s);
		*rn = 1;
		return ST_OK;
	case C_TRACE:
		if (n != 0)
			return ST_ARG;
		*rn = br_trace(s, out);
		return ST_OK;
	case C_FLASH_READ: {
		if (n != 5)
			return ST_ARG;
		uint32_t addr = le24(p), len = le16(p + 3);
		if (len == 0 || len > SYS_MAX_PAYLOAD || addr + len > FLASH_SIZE)
			return ST_ARG;
		fl_read(s, addr, out, (int)len);
		*rn = (int)len;
		return ST_OK;
	}
	case C_FLASH_ERASE: {
		if (n != 6)
			return ST_ARG;
		uint32_t addr = le24(p), len = le24(p + 3);
		if (len == 0 || addr + len > FLASH_SIZE)
			return ST_ARG;
		return fl_erase(s, addr, len);
	}
	case C_FLASH_PROGRAM:
		if (n < 4 || le24(p) + (uint32_t)(n - 3) > FLASH_SIZE)
			return ST_ARG;
		r = fl_program(s, le24(p), p + 3, n - 3, &bad);
		break;
	case C_FPGA_BOOT:
		if (n != 1 || p[0] > 1)
			return ST_ARG;
		return fpga_boot(s, p[0]);
	case C_FPGA_LOAD:
		if (n < 2 || p[0] > 1)
			return ST_ARG;
		if (p[1] == 0 && n == 2) {
			s->load_target = p[0];
			fpga_load_begin(s, p[0]);
			return ST_OK;
		}
		if (s->load_target != p[0])
			return ST_ARG;                    /* data or end without a begin */
		if (p[1] == 1)
			return fpga_load_data(s, p[0], p + 2, n - 2);
		if (p[1] == 2 && n == 2) {
			s->load_target = -1;
			return fpga_load_end(s, p[0]);
		}
		return ST_ARG;
	case C_POWER:
		if (n != 0)
			return ST_ARG;
		*rn = power_payload(s, out);
		return ST_OK;
	case C_POWER_FORCE:
		if (n != 1)
			return ST_ARG;
		power_force(s, p[0] != 0);
		*rn = power_payload(s, out);
		return ST_OK;
	case C_CARD_RESET:
		if (n != 2)
			return ST_ARG;
		return card_reset(s, p[0], p[1] != 0);
	default:
		return ST_CMD;
	}

	/* ROM_PROGRAM and FLASH_PROGRAM report where a verify failed */
	if (r == ST_VERIFY) {
		out[0] = (uint8_t)bad;
		out[1] = (uint8_t)(bad >> 8);
		out[2] = (uint8_t)(bad >> 16);
		*rn = 3;
	}
	return r;
}

static void frame_done(sysctl_t *s)
{
	int n = (int)le16(s->rx + 2);
	int rn;
	if (crc8(s->rx + 1, 3 + n) != s->rx[4 + n]) {
		reply(s, ST_CRC, 0);
		return;
	}
	int st = command(s, s->rx[1], s->rx + 4, n, reply_buf + 4, &rn);
	reply(s, (uint8_t)st, rn);
}

void sysctl_rx(sysctl_t *s, const uint8_t *data, int n)
{
	for (int i = 0; i < n; i++) {
		uint8_t b = data[i];
		if (s->rx_len == 0 && b != MAGIC)
			continue;                         /* noise between frames */
		s->rx[s->rx_len++] = b;
		s->rx_last_ms = s->hal->now_ms(s->ctx);
		if (s->rx_len == 4 && le16(s->rx + 2) > SYS_MAX_PAYLOAD) {
			reply(s, ST_ARG, 0);
			s->rx_len = 0;
		} else if (s->rx_len >= 5 && s->rx_len == 5 + (int)le16(s->rx + 2)) {
			frame_done(s);
			s->rx_len = 0;
		}
	}
}

void sysctl_poll(sysctl_t *s)
{
	if (s->rx_len && s->hal->now_ms(s->ctx) - s->rx_last_ms > FRAME_MS)
		s->rx_len = 0;
}

void sysctl_init(sysctl_t *s, const sysctl_hal *hal, void *ctx)
{
	memset(s, 0, sizeof *s);
	s->hal = hal;
	s->ctx = ctx;
	s->load_target = -1;
}

int sysctl_boot(sysctl_t *s)
{
	const sysctl_hal *h = s->hal;
	int r;

	/* every card in reset until the FPGAs are up */
	s->reset_slots = 0x3F;
	expander_apply(s);

	uint32_t start = h->now_ms(s->ctx);
	for (;;) {
		int mv = h->adc_mv(s->ctx, ADC_V1V2);
		if (mv >= 1140 && mv <= 1260)
			break;
		if (h->now_ms(s->ctx) - start > 100)
			return s->boot_status = ST_TIMEOUT;
		h->delay_us(s->ctx, 1000);
	}

	if ((r = fpga_boot(s, 0)) != ST_OK)
		return s->boot_status = (uint8_t)r;
	br_cpu_ctl(s, 0x40);                      /* /CPU_RST */
	bool cpu = cpu_card_present(s);
	if (cpu && (r = fpga_boot(s, 1)) != ST_OK)
		return s->boot_status = (uint8_t)r;

	s->reset_slots = 0;
	expander_apply(s);
	br_cpu_ctl(s, 0x00);
	if (!cpu) {
		/* no CPU card: no boot ROM run and no slot table, but sysctl, the
		 * chipset and ROM/RAM programming all work */
		power_update(s);
		return s->boot_status = ST_OK;
	}

	/* the boot ROM's slot probe is done once POST passes $04 */
	start = h->now_ms(s->ctx);
	for (;;) {
		uint8_t gpo = br_gpo(s);
		if (gpo >= 0x08 && gpo <= 0x80)
			break;
		if (h->now_ms(s->ctx) - start > 2000) {
			power_update(s);                  /* no slot table: no card is held */
			return s->boot_status = ST_TIMEOUT;
		}
		h->delay_us(s->ctx, 1000);
	}
	br_ram_read(s, SLOT_TABLE, s->slot_types, 6);
	power_update(s);
	return s->boot_status = ST_OK;
}
