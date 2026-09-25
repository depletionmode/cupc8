#include "eink.h"

#include <string.h>

const eink_panel_t eink_panel_583 = {648, 480, "GDEY0583T81 5.83in 648x480"};
const eink_panel_t eink_panel_750 = {800, 480, "GDEY075T7 7.5in 800x480"};

/* ------------------------------------------------------------------ helpers */

static eink_t *of(gpu_t *g) { return (eink_t *)g; }       /* gpu is eink_t's first member */
static int W(const eink_t *e) { return e->panel->w; }
static int H(const eink_t *e) { return e->panel->h; }
static int stride1(const eink_t *e) { return W(e) / 8; }  /* the 1-bit picture's row */
static int stride2(const eink_t *e) { return W(e) / 4; }  /* mode 2's row */
static int s16(const uint8_t *p) { return (int16_t)(p[0] | (p[1] << 8)); }
static int u16(const uint8_t *p) { return p[0] | (p[1] << 8); }

uint8_t eink_lum(uint16_t c)
{
	uint32_t r = ((c >> 11) & 0x1F) * 255 / 31, g = ((c >> 5) & 0x3F) * 255 / 63, b = (c & 0x1F) * 255 / 31;
	return (uint8_t)((299 * r + 587 * g + 114 * b + 500) / 1000);
}

/* 4x4 ordered (Bayer) dither: a pixel is white when its brightness reaches
 * the threshold. Changing one pixel changes only its own dot, so a partial
 * refresh stays as small as the change. */
static const uint8_t bayer[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};
static bool dither_white(uint8_t lum, int x, int y)
{
	return lum >= bayer[y & 3][x & 3] * 16 + 8;
}

/* ------------------------------------------------------------------ mode 2 */

static uint8_t *m2(eink_t *e) { return e->gpu.gfx_bytes; }

static uint8_t get2(const eink_t *e, int x, int y)
{
	uint8_t b = e->gpu.gfx_bytes[y * stride2(e) + x / 4];
	return (uint8_t)((b >> (6 - 2 * (x & 3))) & 3);
}

static void px2(eink_t *e, int x, int y, uint8_t g)
{
	if (x < 0 || y < 0 || x >= W(e) || y >= H(e))
		return;
	uint8_t *p = &m2(e)[y * stride2(e) + x / 4];
	int sh = 6 - 2 * (x & 3);
	*p = (uint8_t)((*p & ~(3 << sh)) | (g << sh));
}

static void fill2(eink_t *e, int x, int y, int w, int h, uint8_t g)
{
	int x0 = x < 0 ? 0 : x, y0 = y < 0 ? 0 : y;
	int x1 = x + w > W(e) ? W(e) : x + w, y1 = y + h > H(e) ? H(e) : y + h;
	for (int yy = y0; yy < y1; yy++)
		for (int xx = x0; xx < x1; xx++)
			px2(e, xx, yy, g);
}

static void clear2(eink_t *e, uint8_t g)
{
	memset(m2(e), g * 0x55, (size_t)stride2(e) * (size_t)H(e));
}

static void line2(eink_t *e, int x0, int y0, int x1, int y1, uint8_t g)
{
	int dx = x1 > x0 ? x1 - x0 : x0 - x1, sx = x0 < x1 ? 1 : -1;
	int dy = y1 > y0 ? y0 - y1 : y1 - y0, sy = y0 < y1 ? 1 : -1;
	int err = dx + dy;
	for (;;) {
		px2(e, x0, y0, g);
		if (x0 == x1 && y0 == y1)
			break;
		int e2 = 2 * err;
		if (e2 >= dy) { err += dy; x0 += sx; }
		if (e2 <= dx) { err += dx; y0 += sy; }
	}
}

static void glyph2(eink_t *e, int x, int y, const uint8_t *rows, int n, uint8_t fg, uint8_t bg)
{
	for (int r = 0; r < n; r++)
		for (int b = 0; b < 8; b++) {
			if (rows[r] & (0x80 >> b))
				px2(e, x + b, y + r, fg);
			else if (bg != 0xFF)
				px2(e, x + b, y + r, bg);
		}
}

static void vscroll2(eink_t *e, int dy, uint8_t g)
{
	size_t row = (size_t)stride2(e);
	int h = H(e);
	if (dy > h) dy = h;
	if (dy < -h) dy = -h;
	if (dy > 0) {
		memmove(m2(e), m2(e) + row * (size_t)dy, row * (size_t)(h - dy));
		memset(m2(e) + row * (size_t)(h - dy), g * 0x55, row * (size_t)dy);
	} else if (dy < 0) {
		dy = -dy;
		memmove(m2(e) + row * (size_t)dy, m2(e), row * (size_t)(h - dy));
		memset(m2(e), g * 0x55, row * (size_t)dy);
	}
}

/* ------------------------------------------------------------------ commands */

/* a change to what is shown: the policy's clock starts */
static void changed(eink_t *e)
{
	e->change_seq++;
	e->last_change = e->now;
	if (!e->unshown) {
		e->unshown = true;
		e->unshown_since = e->now;
	}
}

/* the mode-2 commands' fixed argument bytes, and the variable part */
static long arg_len2(uint8_t op, const uint8_t *a, int avail)
{
	switch (op) {
	case 0x40: return 5;
	case 0x41: case 0x42: case 0x43: return 9;
	case 0x44: return avail >= 8 ? 10 + (long)((u16(a + 4) + 7) / 8) * u16(a + 6) : 10;
	case 0x45: return avail >= 8 ? 8 + (long)((u16(a + 4) + 3) / 4) * u16(a + 6) : 8;
	case 0x46: case 0x47: return avail >= 7 ? 7 + a[6] : 7;
	case 0x48: return 3;
	case 0x49: return 4;
	default: return -1;
	}
}

static bool grey_ok(uint8_t g) { return g <= 3; }
static bool bg_ok(uint8_t g) { return g <= 3 || g == 0xFF; }

static void mode2_command(eink_t *e, uint8_t op, const uint8_t *a, bool respond)
{
	gpu_t *g = &e->gpu;
	bool on = g->mode == EINK_MODE_NATIVE;
	uint8_t r;
	switch (op) {
	case 0x40:
		if (!grey_ok(a[4])) goto bad;
		if (on) px2(e, s16(a), s16(a + 2), a[4]);
		break;
	case 0x41:
		if (!grey_ok(a[8])) goto bad;
		if (on) fill2(e, s16(a), s16(a + 2), u16(a + 4), u16(a + 6), a[8]);
		break;
	case 0x42: {
		int x = s16(a), y = s16(a + 2), w = u16(a + 4), h = u16(a + 6);
		if (!grey_ok(a[8])) goto bad;
		if (on && w > 0 && h > 0) {
			fill2(e, x, y, w, 1, a[8]);
			fill2(e, x, y + h - 1, w, 1, a[8]);
			fill2(e, x, y, 1, h, a[8]);
			fill2(e, x + w - 1, y, 1, h, a[8]);
		}
		break;
	}
	case 0x43:
		if (!grey_ok(a[8])) goto bad;
		if (on) line2(e, s16(a), s16(a + 2), s16(a + 4), s16(a + 6), a[8]);
		break;
	case 0x44: {
		int x = s16(a), y = s16(a + 2), w = u16(a + 4), h = u16(a + 6), stride = (w + 7) / 8;
		uint8_t fg = a[8], bg = a[9];
		if (!grey_ok(fg) || !bg_ok(bg)) goto bad;
		if (!on) break;
		for (int j = 0; j < h; j++)
			for (int i = 0; i < w; i++) {
				if (a[10 + j * stride + i / 8] & (0x80 >> (i % 8)))
					px2(e, x + i, y + j, fg);
				else if (bg != 0xFF)
					px2(e, x + i, y + j, bg);
			}
		break;
	}
	case 0x45: {
		int x = s16(a), y = s16(a + 2), w = u16(a + 4), h = u16(a + 6), stride = (w + 3) / 4;
		if (!on) break;
		for (int j = 0; j < h; j++)
			for (int i = 0; i < w; i++)
				px2(e, x + i, y + j, (uint8_t)((a[8 + j * stride + i / 4] >> (6 - 2 * (i & 3))) & 3));
		break;
	}
	case 0x46: case 0x47: {
		uint8_t fg = a[4], bg = a[5];
		if (!grey_ok(fg) || !bg_ok(bg)) goto bad;
		if (!on) break;
		for (int i = 0; i < a[6]; i++) {
			uint8_t ch = a[7 + i];
			if (op == 0x46)
				glyph2(e, s16(a) + 8 * i, s16(a + 2), g->font16[ch], 16, fg, bg);
			else
				glyph2(e, s16(a) + 8 * i, s16(a + 2), g->font8[ch], 8, fg, bg);
		}
		break;
	}
	case 0x48:
		if (!grey_ok(a[2])) goto bad;
		if (on) vscroll2(e, s16(a), a[2]);
		break;
	case 0x49: {
		int x = s16(a), y = s16(a + 2);
		r = (on && x >= 0 && y >= 0 && x < W(e) && y < H(e)) ? get2(e, x, y) : 0;
		if (respond) card_respond(&g->card, &r, 1);
		return;
	}
	}
	if (on)
		changed(e);
	return;
bad:
	g->errors++;                                /* a grey level that is not one */
}

/* true: taken here; false: the graphics core runs it (fw/gpu/core) */
static bool ext_command(gpu_t *g, const uint8_t *f, int len, bool respond)
{
	eink_t *e = of(g);
	uint8_t op = f[0];
	const uint8_t *a = f + 1;
	int avail = len - 1;

	if (op >= 0x40 && op <= 0x49) {
		long need = arg_len2(op, a, avail);
		if (avail < need)
			g->errors++;                    /* short frame */
		else
			mode2_command(e, op, a, respond);
		return true;
	}
	switch (op) {
	case 0x01:                                  /* MODE */
		if (avail < 1)
			return false;
		if (a[0] == EINK_MODE_NATIVE) {
			g->mode = EINK_MODE_NATIVE;
			clear2(e, 3);
		} else if (a[0] > EINK_MODE_NATIVE) {
			return false;                   /* not a mode: the core ignores it */
		}
		e->full_next = true;
		changed(e);
		return a[0] == EINK_MODE_NATIVE;
	case 0x02:                                  /* CLS */
		if (avail < 1)
			return false;
		if (g->mode == EINK_MODE_NATIVE) {
			if (!grey_ok(a[0])) {
				g->errors++;
				return true;
			}
			clear2(e, a[0]);
		}
		e->full_next = true;
		changed(e);
		return g->mode == EINK_MODE_NATIVE;
	case 0x08: {                                /* INFO */
		uint8_t info[9] = {1, (uint8_t)(W(e) & 0xFF), (uint8_t)(W(e) >> 8), (uint8_t)(H(e) & 0xFF),
				   (uint8_t)(H(e) >> 8), 4, 0x03, GPU_TEXT_COLS, GPU_TEXT_ROWS};
		if (respond) card_respond(&g->card, info, sizeof info);
		return true;
	}
	case 0x09:                                  /* REFRESH */
		if (avail < 1 || a[0] > EINK_GREY) {
			g->errors++;
			return true;
		}
		e->explicit_req = a[0];
		g->hold = true;                     /* until the panel has it */
		return true;
	case 0x0A:                                  /* AUTO */
		if (avail < 3) {
			g->errors++;
			return true;
		}
		e->auto_on = a[0] != 0;
		e->idle10 = a[1];
		e->full_after = a[2];
		return true;
	case 0x0B: {                                /* EPD_STATUS */
		uint8_t st[3];
		eink_status(e, st);
		if (respond) card_respond(&g->card, st, 3);
		return true;
	}
	case 0x10: case 0x11: {                     /* PUTC, PUTS: a form feed clears the screen */
		int n = op == 0x10 ? 1 : (avail >= 1 ? a[0] : 0);
		const uint8_t *s = op == 0x10 ? a : a + 1;
		if (avail < (op == 0x10 ? 1 : 1 + n))
			return false;               /* the core counts the short frame */
		if (memchr(s, 0x0C, (size_t)n))
			e->full_next = true;
		changed(e);
		return false;
	}
	case 0x03: case 0x04: case 0x12: case 0x14: case 0x15: case 0x16: case 0x17: case 0x19: case 0x29:
		changed(e);                         /* TEXT and palette: shown in every mode */
		return false;
	}
	if (op >= 0x20 && op <= 0x28) {
		/* GFX mode 1's drawing: its buffer is mode 2's in mode 2 */
		if (g->mode == EINK_MODE_NATIVE) {
			if (op == 0x28 && respond) {
				uint8_t zero = 0;
				card_respond(&g->card, &zero, 1);
			}
			return true;
		}
		if (op != 0x28)
			changed(e);
	}
	return false;
}

static void ext_reset(gpu_t *g)
{
	eink_t *e = of(g);
	e->auto_on = true;
	e->idle10 = 15;
	e->full_after = 30;
	e->explicit_req = -1;
	e->full_next = true;
	changed(e);
}

static const gpu_ext_t eink_ext = {.command = ext_command, .reset = ext_reset};

/* ------------------------------------------------------------------ render */

/* one row's brightness, pixel by pixel (w bytes, 0 black ... 255 white) */
static void row_lum(const eink_t *e, int y, uint8_t *lum)
{
	const gpu_t *g = &e->gpu;
	int w = W(e), ox = (w - GPU_OUT_W) / 2;
	if (g->mode == EINK_MODE_NATIVE) {
		for (int x = 0; x < w; x++)
			lum[x] = (uint8_t)(get2(e, x, y) * 85);
		return;
	}
	memset(lum, 255, (size_t)w);                /* the margins are paper */
	if (g->mode == GPU_MODE_GFX) {
		/* each pixel's palette entry as a grey, not inverted: black is ink */
		uint8_t pl[256];
		const uint8_t *src = g->gfx[y / 2];
		for (int i = 0; i < 256; i++)
			pl[i] = eink_lum(g->palette[i]);
		for (int x = 0; x < GPU_OUT_W; x++)
			lum[ox + x] = pl[src[x / 2]];
		return;
	}
	/* TEXT: per cell, the brighter of the two colours is ink (black) and the
	 * darker is paper; equal colours are all paper. The cursor is drawn,
	 * not blinking: it inverts rows 14-15 (underline) or the cell (block). */
	int row = y / 16, line = y % 16;
	uint8_t pl[16];
	for (int i = 0; i < 16; i++)
		pl[i] = eink_lum(g->palette[i]);
	for (int col = 0; col < GPU_TEXT_COLS; col++) {
		gpu_cell_t cell = g->text[row][col];
		uint8_t lf = pl[cell.attr & 15], lb = pl[cell.attr >> 4];
		uint8_t bits = g->font16[cell.ch][line];
		/* ink where these bits are set */
		uint8_t ink = lf > lb ? bits : lb > lf ? (uint8_t)~bits : 0;
		if (g->cursor && row == g->cy && col == g->cx && (g->cursor == 2 || line >= 14))
			ink = (uint8_t)~ink;
		uint8_t *out = lum + ox + col * 8;
		for (int b = 0; b < 8; b++)
			out[b] = (ink & (0x80 >> b)) ? 0 : 255;
	}
}

void eink_render_row(eink_t *e, int y, uint8_t *out)
{
	uint8_t *lum = e->lum;
	row_lum(e, y, lum);
	memset(out, 0, (size_t)stride1(e));
	for (int x = 0; x < W(e); x++)
		if (dither_white(lum[x], x, y))
			out[x / 8] |= (uint8_t)(0x80 >> (x & 7));
}

/* one bit plane of the greyscale picture: grey 0-3 is {NEW, OLD} = its
 * high and low bit (with DDX = 01: 00 LUTKK black, 01 LUTWK dark grey,
 * 10 LUTKW light grey, 11 LUTWW white) */
static void render_plane(eink_t *e, int y, int bit, uint8_t *out)
{
	uint8_t *lum = e->lum;
	row_lum(e, y, lum);
	memset(out, 0, (size_t)stride1(e));
	for (int x = 0; x < W(e); x++) {
		int level = (lum[x] * 3 + 127) / 255;
		if ((level >> bit) & 1)
			out[x / 8] |= (uint8_t)(0x80 >> (x & 7));
	}
}

void eink_render(eink_t *e, uint8_t *grey, bool grey4)
{
	uint8_t *lum = e->lum;
	for (int y = 0; y < H(e); y++) {
		row_lum(e, y, lum);
		for (int x = 0; x < W(e); x++)
			grey[y * W(e) + x] = grey4 ? (uint8_t)((lum[x] * 3 + 127) / 255 * 85)
						   : (dither_white(lum[x], x, y) ? 255 : 0);
	}
}

/* ------------------------------------------------------------------ the panel loop */

enum { PANEL_OFF, PANEL_ASLEEP, PANEL_READY };
enum {
	S_IDLE, S_DIFF, S_PREP, S_PWR, S_RST_LOW, S_RST_HIGH, S_CONFIG, S_PON_WAIT,
	S_OLD, S_NEW, S_DRF_WAIT, S_POF_WAIT,
};

#define DIFF_ROWS 32                            /* rows compared per eink_poll() */
#define SEND_ROWS 8                             /* rows sent per eink_poll(): ~0.7 ms at 10 MHz */
#define PWR_SETTLE_US 10000                     /* the module's supply after PWR */
#define RST_LOW_US 1000                         /* >= 50 us (datasheet p.6) */
#define RST_WAIT_US 2000                        /* > 1 ms before commands (p.43) */
#define FLAG_WAIT_US 1000                       /* BUSY_N may take a moment to fall */

static void start(eink_t *e, int kind, bool explicit_req)
{
	e->kind = kind;
	e->explicit_run = explicit_req;
	e->refresh_seq = e->change_seq;
	e->unshown = false;                         /* later changes wait for the next one */
	if (kind == EINK_PARTIAL) {
		e->y0 = H(e);
		e->y1 = -1;
		e->row = 0;
		e->step = S_DIFF;
	} else {
		e->y0 = 0;
		e->y1 = H(e) - 1;
		e->step = S_PREP;
	}
}

static void finish(eink_t *e, bool ok)
{
	if (ok) {
		e->shown_seq = e->refresh_seq;
		if (e->y1 >= 0) {
			e->refreshes[e->kind]++;
			if (e->kind == EINK_PARTIAL) {
				if (e->partials < 255)
					e->partials++;
			} else {
				e->partials = 0;
				e->full_next = false;
				e->first_clean = false;
			}
		}
	} else {
		e->unshown = true;                  /* try again later */
		e->unshown_since = e->now;
	}
	if (e->explicit_run) {
		e->explicit_run = false;
		e->gpu.hold = false;
	}
	e->step = S_IDLE;
	e->last_panel = e->now;
}

static bool waited(const eink_t *e, uint32_t us) { return e->now - e->t0 >= us; }

/* after a command that raises BUSY: done once it has had time to fall and
 * has risen again; a panel that never answers is given up on */
static int flag_done(eink_t *e)
{
	if (!waited(e, FLAG_WAIT_US))
		return 0;
	if (!e->bus.busy(e->bus.ctx))
		return 1;
	if (waited(e, EINK_BUSY_TIMEOUT_US)) {
		e->panel_errors++;
		e->panel_state = PANEL_ASLEEP;       /* reset it before the next try */
		e->full_next = true;
		finish(e, false);
		return -1;
	}
	return 0;
}

static void send_row(eink_t *e, const uint8_t *row, int n)
{
	e->bus.data(e->bus.ctx, row, n);
}

static void idle(eink_t *e)
{
	bool dirty = e->change_seq != e->shown_seq;
	uint32_t quiet = e->now - e->last_change;
	if (e->explicit_req >= 0) {
		int m = e->explicit_req;
		e->explicit_req = -1;
		start(e, m, true);
		return;
	}
	if (e->auto_on) {
		if (dirty && (quiet >= e->idle10 * 10000u || e->now - e->unshown_since >= EINK_CAP_US)) {
			start(e, e->first_clean ? EINK_CLEAN : e->full_next ? EINK_FAST : EINK_PARTIAL, false);
			return;
		}
		if (e->full_after && e->partials >= e->full_after && quiet >= EINK_FULL_QUIET_US) {
			start(e, EINK_FAST, false);
			return;
		}
	}
	if (e->panel_state == PANEL_READY && e->now - e->last_panel >= EINK_SLEEP_US) {
		uc8179_deep_sleep(&e->bus);
		e->panel_state = PANEL_ASLEEP;
	}
}

static void panel_step(eink_t *e)
{
	const epd_bus_t *b = &e->bus;
	int n1 = stride1(e);
	switch (e->step) {
	case S_IDLE:
		idle(e);
		break;
	case S_DIFF:
		/* compare the new picture with the one on the panel, row by row */
		for (int i = 0; i < DIFF_ROWS && e->row < H(e); i++, e->row++) {
			eink_render_row(e, e->row, e->rowbuf);
			if (memcmp(e->rowbuf, &e->shown[e->row * n1], (size_t)n1)) {
				if (e->row < e->y0) e->y0 = e->row;
				e->y1 = e->row;
			}
		}
		if (e->row == H(e))
			e->y1 < 0 ? finish(e, true) : (void)(e->step = S_PREP);   /* nothing changed */
		break;
	case S_PREP:
		/* PWR and RST_N's waits count from the next poll: S_DIFF may have
		 * run in this one (~14 ms for 480 rows), so `now` is stale here
		 * (RST_N went high 7.5 us after it fell when waking from deep sleep) */
		e->t0_fresh = true;
		if (e->panel_state == PANEL_OFF) {
			b->pin(b->ctx, EPD_PIN_PWR, true);
			e->step = S_PWR;
		} else if (e->panel_state == PANEL_ASLEEP) {
			b->pin(b->ctx, EPD_PIN_RST_N, false);
			e->step = S_RST_LOW;
		} else {
			e->step = S_CONFIG;
		}
		break;
	case S_PWR:
		if (waited(e, PWR_SETTLE_US)) {
			b->pin(b->ctx, EPD_PIN_RST_N, false);
			e->t0 = e->now;
			e->step = S_RST_LOW;
		}
		break;
	case S_RST_LOW:
		if (waited(e, RST_LOW_US)) {
			b->pin(b->ctx, EPD_PIN_RST_N, true);
			e->t0 = e->now;
			e->resets++;
			e->step = S_RST_HIGH;
		}
		break;
	case S_RST_HIGH:
		if (waited(e, RST_WAIT_US)) {
			uc8179_setup(b, W(e), H(e));
			e->panel_state = PANEL_READY;
			e->step = S_CONFIG;
		}
		break;
	case S_CONFIG: {
		static const uc_waveform_t wf[] = {UC_WF_PARTIAL, UC_WF_FAST, UC_WF_CLEAN, UC_WF_GREY};
		uc8179_waveform(b, wf[e->kind]);
		uc8179_cmd(b, UC_PON);
		e->t0_fresh = true;
		e->step = S_PON_WAIT;
		break;
	}
	case S_PON_WAIT:
		if (flag_done(e) != 1)
			break;
		if (e->kind == EINK_PARTIAL)
			uc8179_window(b, 0, e->y0, W(e) - 1, e->y1);
		uc8179_cmd(b, UC_DTM1);             /* the old picture (or grey's low bits) */
		e->row = e->y0;
		e->step = S_OLD;
		break;
	case S_OLD:
		for (int i = 0; i < SEND_ROWS && e->row <= e->y1; i++, e->row++) {
			if (e->kind == EINK_GREY) {
				render_plane(e, e->row, 0, e->rowbuf);
				send_row(e, e->rowbuf, n1);
			} else {
				send_row(e, &e->shown[e->row * n1], n1);
			}
		}
		if (e->row > e->y1) {
			uc8179_cmd(b, UC_DTM2);     /* the new picture (or grey's high bits) */
			e->row = e->y0;
			e->step = S_NEW;
		}
		break;
	case S_NEW:
		for (int i = 0; i < SEND_ROWS && e->row <= e->y1; i++, e->row++) {
			uint8_t *shown = &e->shown[e->row * n1];
			if (e->kind == EINK_GREY) {
				render_plane(e, e->row, 1, e->rowbuf);
				send_row(e, e->rowbuf, n1);
				eink_render_row(e, e->row, shown);    /* what a partial refresh compares with */
			} else {
				eink_render_row(e, e->row, shown);
				send_row(e, shown, n1);
			}
		}
		if (e->row > e->y1) {
			uc8179_cmd(b, UC_DRF);
			e->t0_fresh = true;
			e->step = S_DRF_WAIT;
		}
		break;
	case S_DRF_WAIT:
		if (flag_done(e) != 1)
			break;
		if (e->kind == EINK_PARTIAL)
			uc8179_cmd(b, UC_PTOUT);
		uc8179_cmd(b, UC_POF);              /* no high voltage on the panel between refreshes */
		e->t0_fresh = true;
		e->step = S_POF_WAIT;
		break;
	case S_POF_WAIT:
		if (flag_done(e) == 1)
			finish(e, true);
		break;
	}
}

void eink_poll(eink_t *e, uint32_t now)
{
	/* VSYNC_COUNT keeps counting at 60 Hz, from this clock */
	e->vsync_acc += (now - e->now) * 60u;
	e->now = now;
	/* a wait for BUSY counts from here, not from this poll's start: sending
	 * rows takes time, so `now` was stale by the time the command went out
	 * (BUSY_N was read before it could fall, and the next command went to
	 * a busy controller) */
	if (e->t0_fresh) {
		e->t0 = now;
		e->t0_fresh = false;
	}
	while (e->vsync_acc >= 1000000u) {
		e->vsync_acc -= 1000000u;
		gpu_vsync(&e->gpu);
	}
	int before;
	do {                                        /* steps that do nothing slow run at once */
		before = e->step;
		panel_step(e);
	} while (e->step != before && (e->step == S_PREP || e->step == S_CONFIG));
}

bool eink_refreshing(const eink_t *e)
{
	return e->step == S_DRF_WAIT;
}

void eink_status(const eink_t *e, uint8_t out[3])
{
	out[0] = e->step != S_IDLE || e->explicit_req >= 0;
	out[1] = e->change_seq != e->shown_seq;
	out[2] = e->partials;
}

void eink_init(eink_t *e, const eink_panel_t *panel, const epd_bus_t *bus)
{
	memset(e, 0, sizeof *e);
	gpu_init(&e->gpu);
	e->gpu.ext = &eink_ext;
	e->panel = panel;
	e->bus = *bus;
	e->first_clean = true;
	e->panel_state = PANEL_OFF;
	e->step = S_IDLE;
	memset(e->shown, 0xFF, sizeof e->shown);   /* unknown: taken as white */
	ext_reset(&e->gpu);                         /* the policy's defaults; the screen is unshown */
}
