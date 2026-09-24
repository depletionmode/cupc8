#include "epdmodel.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define US 1000ull

void epd_cfg_default(epd_cfg_t *c, int w, int h)
{
	memset(c, 0, sizeof *c);
	c->w = w;
	c->h = h;
	c->pwr_pin = true;
	c->time_scale = 1.0;
	c->pon_us = 50000;
	c->pof_us = 30000;
	c->dslp_us = 1000;
	c->clean_us = 3000000;
	c->fast_us = 1500000;
	c->grey_us = 2000000;
	c->partial_us = 300000;
	c->busy_delay_us = 100;
}

static void logf_(epd_model_t *m, const char *fmt, ...)
{
	if (!m->log)
		return;
	char line[256];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(line, sizeof line, fmt, ap);
	va_end(ap);
	m->log(m->log_ctx, line);
}

static void error(epd_model_t *m, const char *fmt, ...)
{
	char line[256];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(line, sizeof line, fmt, ap);
	va_end(ap);
	if (!m->errors)
		snprintf(m->error, sizeof m->error, "%.3f ms: %.200s", m->now / 1e6, line);
	m->errors++;
	logf_(m, "ERROR %s", line);
}

/* registers after RST_N or power-up (the "Default" column, p.8-11) */
static void defaults(epd_model_t *m)
{
	m->psr = 0x0F;
	m->cdi[0] = 0x31;
	m->cdi[1] = 0x07;
	m->ccset = 0;
	m->tsset = 0;
	m->hres = 800;
	m->vres = 600;
	m->ptl[0] = 0; m->ptl[1] = 0x3FF; m->ptl[2] = 0; m->ptl[3] = 0x257;
	m->ptl_mode = false;
	m->pon = false;
	m->asleep = false;
	m->cmd = -1;
	m->nparam = 0;
	m->busy_op = 0;
	m->dtm1_count = m->dtm2_count = -1;
}

/* SRAM content that nobody wrote: a pattern, so a picture sent in part shows */
static void garbage(epd_model_t *m)
{
	size_t n = (size_t)m->cfg.w * (size_t)m->cfg.h;
	for (size_t i = 0; i < n; i++) {
		m->old_ram[i] = (uint8_t)((i / 3) & 1);
		m->new_ram[i] = (uint8_t)((i / 5) & 1);
	}
}

void epd_init(epd_model_t *m, const epd_cfg_t *cfg)
{
	memset(m, 0, sizeof *m);
	m->cfg = *cfg;
	size_t n = (size_t)cfg->w * (size_t)cfg->h;
	m->old_ram = malloc(n);
	m->new_ram = malloc(n);
	m->glass = malloc(n);
	/* the glass keeps the picture from before power-off: diagonal stripes */
	for (int y = 0; y < cfg->h; y++)
		for (int x = 0; x < cfg->w; x++)
			m->glass[y * cfg->w + x] = ((x + y) / 24) % 2 ? 0 : 255;
	defaults(m);
	garbage(m);
	m->powered = !cfg->pwr_pin;
	m->rst_n = true;
}

void epd_free(epd_model_t *m)
{
	free(m->old_ram);
	free(m->new_ram);
	free(m->glass);
}

static uint64_t scaled(const epd_model_t *m, uint32_t us)
{
	return (uint64_t)((double)us * m->cfg.time_scale * 1000.0);
}

/* ------------------------------------------------------------------ refresh */

enum { LUT_WW, LUT_KW, LUT_WK, LUT_KK };

/* the LUT a pixel's {NEW, OLD} selects in KW mode (CDI's DDX table, p.28) */
static int lut_of(int ddx, int nw, int od)
{
	switch (ddx) {
	case 0: return nw ? (od ? LUT_KK : LUT_WK) : (od ? LUT_KW : LUT_WW);
	case 1: return nw ? (od ? LUT_WW : LUT_KW) : (od ? LUT_WK : LUT_KK);
	case 2: return nw ? LUT_WK : LUT_KW;                       /* KW mode without NEW/OLD */
	default: return nw ? LUT_KW : LUT_WK;
	}
}

static int waveform(const epd_model_t *m)
{
	int t = (m->ccset & 2) ? m->tsset : 25;                    /* TSFIX: TS_SET, else the sensor */
	switch (t) {
	case 0x5A: return EPD_WF_FAST;
	case 0x5F: return EPD_WF_GREY;
	case 0x6E: return EPD_WF_PARTIAL;
	default: return EPD_WF_CLEAN;
	}
}

static void area(const epd_model_t *m, int a[4])
{
	if (m->ptl_mode) {
		memcpy(a, m->ptl, sizeof m->ptl);
	} else {
		a[0] = 0; a[1] = m->hres - 1; a[2] = 0; a[3] = m->vres - 1;
	}
}

static long area_pixels(const int a[4]) { return (long)(a[1] - a[0] + 1) * (a[3] - a[2] + 1); }

static void apply_refresh(epd_model_t *m)
{
	static const uint8_t full[4] = {255, 255, 0, 0}, grey[4] = {255, 170, 85, 0};
	const int *a = m->busy_area;
	int ddx = m->cdi[0] & 3, wf = m->busy_wf;
	bool shl = m->psr & 0x04, ud = m->psr & 0x08;
	for (int y = a[2]; y <= a[3]; y++)
		for (int x = a[0]; x <= a[1]; x++) {
			int i = y * m->cfg.w + x;
			int lut = lut_of(ddx, m->new_ram[i], m->old_ram[i]);
			int gx = shl ? x : m->hres - 1 - x, gy = ud ? y : m->vres - 1 - y;
			uint8_t *g = &m->glass[gy * m->cfg.w + gx];
			switch (wf) {
			case EPD_WF_GREY: *g = grey[lut]; break;
			case EPD_WF_PARTIAL:
				/* the partial waveform only moves pixels whose NEW differs */
				if (lut == LUT_KW) *g = 255;
				else if (lut == LUT_WK) *g = 0;
				break;
			default: *g = full[lut]; break;
			}
			if (m->cdi[0] & 0x08)                          /* N2OCP */
				m->old_ram[i] = m->new_ram[i];
		}
	m->refreshes[wf]++;
	if (wf == EPD_WF_PARTIAL) {
		m->partials_since_full++;
		if (m->partials_since_full > m->max_partials_between_fulls)
			m->max_partials_between_fulls = m->partials_since_full;
	} else {
		m->partials_since_full = 0;
	}
	m->seq++;
	logf_(m, "refresh done: waveform %d, rows %d-%d", wf, a[2], a[3]);
}

static void complete(epd_model_t *m)
{
	switch (m->busy_op) {
	case 0x04: m->pon = true; break;
	case 0x02: m->pon = false; break;
	case 0x07: m->asleep = true; m->pon = false; break;
	case 0x12: apply_refresh(m); break;
	}
	m->busy_op = 0;
}

void epd_advance(epd_model_t *m, uint64_t ns)
{
	if (ns > m->now)
		m->now = ns;
	if (m->busy_op && m->now >= m->busy_end)
		complete(m);
}

static void busy(epd_model_t *m, int op, uint64_t duration)
{
	m->busy_op = op;
	m->busy_start = m->now;
	m->busy_pin = m->now + m->cfg.busy_delay_us * US;
	m->busy_end = m->now + duration;
	if (m->busy_end < m->busy_pin)
		m->busy_end = m->busy_pin;
}

static void refresh(epd_model_t *m)
{
	int a[4];
	area(m, a);
	if (!(m->psr & 0x10)) {
		error(m, "DRF in KWR mode (PSR KW/R = 0): only KW mode is modelled");
		return;
	}
	if (m->psr & 0x20) {
		error(m, "DRF with LUTs from registers (PSR REG = 1): the card uses the OTP's");
		return;
	}
	if (!m->pon) {
		error(m, "DRF with the booster off (no PON)");
		return;
	}
	if (m->hres > m->cfg.w || m->vres > m->cfg.h) {
		error(m, "TRES %dx%d is larger than the panel (%dx%d)", m->hres, m->vres, m->cfg.w, m->cfg.h);
		return;
	}
	if (a[1] >= m->hres || a[3] >= m->vres || a[0] > a[1] || a[2] > a[3]) {
		error(m, "partial window %d-%d x %d-%d outside TRES %dx%d", a[0], a[1], a[2], a[3], m->hres, m->vres);
		return;
	}
	long want = area_pixels(a);
	if (m->dtm2_count != want)
		error(m, "DRF after %ld pixels of NEW data (DTM2) for a %ld-pixel area", m->dtm2_count, want);
	if (m->dtm1_count >= 0 && m->dtm1_count != want)
		error(m, "DRF after %ld pixels of OLD data (DTM1) for a %ld-pixel area", m->dtm1_count, want);
	m->dtm1_count = m->dtm2_count = -1;
	int wf = waveform(m);
	static const char *names[] = {"clean full", "fast full", "4-grey", "partial"};
	uint32_t us[] = {m->cfg.clean_us, m->cfg.fast_us, m->cfg.grey_us, m->cfg.partial_us};
	busy(m, 0x12, scaled(m, us[wf]));
	m->busy_wf = wf;
	memcpy(m->busy_area, a, sizeof m->busy_area);
	logf_(m, "DRF: %s refresh of %d-%d x %d-%d", names[wf], a[0], a[1], a[2], a[3]);
}

/* ------------------------------------------------------------------ commands */

/* parameter bytes each command takes (p.8-11); -1: pixel data, -2: a read
 * (not wired: the card's SPI1 has no MISO), -3: not a command */
static int nparams(int c)
{
	switch (c) {
	case 0x00: return 1;
	case 0x01: return 5;            /* the fifth (VDHR) is optional */
	case 0x02: case 0x04: case 0x05: case 0x12: case 0x91: case 0x92: return 0;
	case 0x03: return 1;
	case 0x06: return 4;
	case 0x07: return 1;
	case 0x10: case 0x13: return -1;
	case 0x15: case 0x17: case 0x30: case 0x41: case 0x52: case 0x60: case 0x80: case 0x82:
	case 0xE0: case 0xE3: case 0xE4: case 0xE5: case 0xE7: return 1;
	case 0x20: case 0x22: case 0x23: case 0x24: return 60;
	case 0x21: case 0x25: return 42;
	case 0x2A: case 0x50: return 2;
	case 0x2B: return 3;
	case 0x42: return 3;
	case 0x61: case 0x65: return 4;
	case 0x90: return 9;
	case 0x11: case 0x40: case 0x43: case 0x44: case 0x51: case 0x70: case 0x71: case 0x81: case 0xA2:
		return -2;
	default: return -3;
	}
}

static void param_done(epd_model_t *m)
{
	const uint8_t *p = m->param;
	switch (m->cmd) {
	case 0x00:
		m->psr = p[0];
		if (!(p[0] & 1)) {                  /* RST_N = 0: soft reset */
			defaults(m);
			logf_(m, "PSR soft reset");
		}
		break;
	case 0x07:
		if (p[0] == 0xA5)
			busy(m, 0x07, scaled(m, m->cfg.dslp_us));
		else
			error(m, "DSLP check code $%02X (not $A5): ignored", p[0]);
		break;
	case 0x50: m->cdi[0] = p[0]; m->cdi[1] = p[1]; break;
	case 0x61:
		m->hres = ((p[0] & 3) << 8 | p[1]) & ~7;
		m->vres = (p[2] & 3) << 8 | p[3];
		break;
	case 0x90:
		m->ptl[0] = ((p[0] & 3) << 8 | p[1]) & ~7;
		m->ptl[1] = ((p[2] & 3) << 8 | p[3]) | 7;
		m->ptl[2] = (p[4] & 3) << 8 | p[5];
		m->ptl[3] = (p[6] & 3) << 8 | p[7];
		if ((p[3] & 7) != 7 || (p[1] & 7))
			error(m, "PTL: HRST[2:0] must be 000 and HRED[2:0] 111");
		break;
	case 0xE0: m->ccset = p[0]; break;
	case 0xE5: m->tsset = p[0]; break;
	case 0x17:
		error(m, "AUTO sequence: not used by the card, not modelled");
		break;
	}
}

static void command(epd_model_t *m, uint8_t c)
{
	int n = nparams(c);
	m->cmd = c;
	m->nparam = 0;
	m->wp = 0;
	m->commands++;
	logf_(m, "command $%02X", c);
	if (n == -3) {
		error(m, "command $%02X: reserved (datasheet p.11: must not be used)", c);
		m->cmd = -1;
		return;
	}
	if (n == -2) {
		error(m, "command $%02X reads the controller, but the card has no MISO", c);
		m->cmd = -1;
		return;
	}
	switch (c) {
	case 0x04:
		busy(m, 0x04, scaled(m, m->cfg.pon_us));
		break;
	case 0x02:
		busy(m, 0x02, scaled(m, m->cfg.pof_us));
		break;
	case 0x05:
		busy(m, 0x05, scaled(m, 1000));
		break;
	case 0x12:
		refresh(m);
		break;
	case 0x91: m->ptl_mode = true; break;
	case 0x92: m->ptl_mode = false; break;
	case 0x10: m->dtm1_count = 0; break;
	case 0x13: m->dtm2_count = 0; break;
	}
}

static void pixel_data(epd_model_t *m, uint8_t b)
{
	int a[4];
	area(m, a);
	int aw = a[1] - a[0] + 1;
	long total = area_pixels(a);
	uint8_t *ram = m->cmd == 0x10 ? m->old_ram : m->new_ram;
	long *count = m->cmd == 0x10 ? &m->dtm1_count : &m->dtm2_count;
	if (m->wp >= total) {
		if (m->wp == total)
			error(m, "DTM%d: more pixel data than the %ld-pixel area", m->cmd == 0x10 ? 1 : 2, total);
		m->wp += 8;
		return;
	}
	for (int i = 0; i < 8 && m->wp < total; i++, m->wp++) {
		int x = a[0] + (int)(m->wp % aw), y = a[2] + (int)(m->wp / aw);
		if (x < m->cfg.w && y < m->cfg.h)
			ram[y * m->cfg.w + x] = (b >> (7 - i)) & 1;
	}
	*count = m->wp;
}

void epd_byte(epd_model_t *m, uint64_t ns, bool dc, uint8_t b)
{
	epd_advance(m, ns);
	if (!m->powered) {
		error(m, "SPI byte $%02X while the module is unpowered (PWR low)", b);
		return;
	}
	if (!m->rst_n) {
		error(m, "SPI byte $%02X while RST_N is low", b);
		return;
	}
	if (m->now < m->ready_at) {
		error(m, "SPI byte $%02X within 1 ms of reset: ignored by the chip", b);
		return;
	}
	if (m->asleep) {
		error(m, "SPI byte $%02X in deep sleep (only RST_N wakes it)", b);
		return;
	}
	if (m->busy_op) {
		error(m, "%s $%02X while BUSY (command $%02X running): ignored by the chip", dc ? "data" : "command", b,
		      m->busy_op);
		return;
	}
	if (!dc) {
		command(m, b);
		return;
	}
	if (m->cmd < 0) {
		error(m, "data $%02X with no command", b);
		return;
	}
	int n = nparams(m->cmd);
	if (n == -1) {
		pixel_data(m, b);
		return;
	}
	if (m->nparam >= n) {
		error(m, "command $%02X: parameter %d is one too many", m->cmd, m->nparam + 1);
		return;
	}
	m->param[m->nparam++] = b;
	if (m->nparam == n || (m->cmd == 0x01 && m->nparam == 4))
		param_done(m);
}

void epd_rst(epd_model_t *m, uint64_t ns, bool rst_n)
{
	epd_advance(m, ns);
	if (rst_n == m->rst_n)
		return;
	m->rst_n = rst_n;
	if (!rst_n) {
		m->rst_fell = m->now;
		defaults(m);                        /* and out of deep sleep */
		logf_(m, "RST_N low");
		return;
	}
	if (m->now - m->rst_fell < 50 * US)
		error(m, "RST_N low for %.1f us (the minimum is 50)", (m->now - m->rst_fell) / 1e3);
	m->ready_at = m->now + 1000 * US;
	logf_(m, "RST_N high");
}

void epd_pwr(epd_model_t *m, uint64_t ns, bool on)
{
	epd_advance(m, ns);
	if (!m->cfg.pwr_pin || on == m->powered)
		return;
	m->powered = on;
	defaults(m);
	if (on) {
		garbage(m);                         /* SRAM does not survive power off */
		m->ready_at = m->now + 1000 * US;
	}
	logf_(m, "module power %s", on ? "on" : "off");
}

bool epd_busy_n(epd_model_t *m, uint64_t ns)
{
	epd_advance(m, ns);
	if (!m->powered)
		return true;
	return !(m->busy_op && m->now >= m->busy_pin && m->now < m->busy_end);
}

uint64_t epd_next_event(const epd_model_t *m)
{
	if (!m->busy_op)
		return UINT64_MAX;
	return m->now < m->busy_pin ? m->busy_pin : m->busy_end;
}
