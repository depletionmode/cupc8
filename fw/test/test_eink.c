/* GPU-006..008: the e-ink card core (doc/hardware/eink-card.md) with its
 * panel, the UC8179 model (fw/test/epdmodel.c), on a fake clock.
 *
 *   GPU-006   every e-paper and mode-2 command, valid, boundary and malformed
 *   GPU-007   the ink rule, the dither, and the pictures the controller
 *             model shows after each refresh, against golden images
 *             (test/eink/golden, PBM and PGM) and against the core's raster
 *   GPU-008   the refresh policy's timing, the partial window, AUTO 0 and
 *             REFRESH, FENCE after REFRESH, deep sleep, a dead panel; and in
 *             all of them, the UC8179 command stream: the model counts every
 *             command the chip would ignore or mishandle; it must count none
 *
 * EINK_RECORD=1 rewrites the golden images (after a human has looked at
 * them: they are also written to build/fw as .pgm). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "check.h"
#include "eink.h"
#include "epdmodel.h"
#include "font8x8_cp437.h"

static eink_t eink;
static epd_model_t model;
static uint64_t now_us, spi_ns;         /* the card's clock; SPI time within a poll */
static bool stuck_busy;                 /* a panel that never releases BUSY */
static const char *golden_dir = "../test/eink/golden";
static uint8_t pic[EINK_MAX_W * EINK_H], ref[EINK_MAX_W * EINK_H];

/* ------------------------------------------------------------------ the bus */

/* the panel's time: SPI bytes take 0.8 us each (10 MHz), so a picture
 * sent in one poll ends later than the poll began, as on the card */
static uint64_t ns(void) { return now_us * 1000 + spi_ns; }
static void bus_command(void *ctx, uint8_t c) { (void)ctx; spi_ns += 800; epd_byte(&model, ns(), false, c); }
static void bus_data(void *ctx, const uint8_t *p, int n)
{
	(void)ctx;
	for (int i = 0; i < n; i++) {
		spi_ns += 800;
		epd_byte(&model, ns(), true, p[i]);
	}
}
static void bus_pin(void *ctx, int pin, bool v)
{
	(void)ctx;
	if (pin == EPD_PIN_RST_N)
		epd_rst(&model, ns(), v);
	else
		epd_pwr(&model, ns(), v);
}
static bool bus_busy(void *ctx) { (void)ctx; return stuck_busy || !epd_busy_n(&model, ns()); }
static const epd_bus_t bus = {0, bus_command, bus_data, bus_pin, bus_busy};

/* DRF times, from the model's log */
static uint64_t drf_at[64];
static int drfs;
static void on_log(void *ctx, const char *line)
{
	(void)ctx;
	if (!strncmp(line, "DRF:", 4) && drfs < 64)
		drf_at[drfs++] = now_us;
	if (getenv("EINK_LOG"))
		fprintf(stderr, "%8.3f ms %s\n", now_us / 1e3, line);
}

static void setup(const eink_panel_t *panel, double scale)
{
	epd_cfg_t cfg;
	if (model.glass)
		epd_free(&model);
	epd_cfg_default(&cfg, panel->w, panel->h);
	cfg.time_scale = scale;
	/* the firmware allows BUSY_N 1 ms to fall after a command that flags
	 * it; the panel here takes nearly all of that */
	cfg.busy_delay_us = 950;
	epd_init(&model, &cfg);
	model.log = on_log;
	now_us = 1000;
	drfs = 0;
	stuck_busy = false;
	eink_init(&eink, panel, &bus);
}

/* 100 us of card time: run commands, then the panel loop */
static void tick(void)
{
	now_us += 100 + spi_ns / 1000;
	spi_ns = 0;
	gpu_run(&eink.gpu, 1000);
	eink_poll(&eink, (uint32_t)now_us);
	epd_advance(&model, ns());                  /* the panel's time goes on too */
}
static void run_ms(double ms) { for (int i = 0; i < ms * 10; i++) tick(); }

static bool settled(void)
{
	uint8_t st[3];
	eink_status(&eink, st);
	return !st[0] && !st[1] && !model.busy_op;
}
/* until the picture is on the panel and nothing is pending (at most `ms`) */
static bool settle(double ms)
{
	for (int i = 0; i < ms * 10; i++) {
		if (settled())
			return true;
		tick();
	}
	return settled();
}

static void send(const uint8_t *bytes, int len)
{
	card_frame(&eink.gpu.card, bytes, 0, len);
	gpu_run(&eink.gpu, 1000);
}
#define SEND(...) do { uint8_t b_[] = {__VA_ARGS__}; send(b_, (int)sizeof b_); } while (0)

static int read_resp(uint8_t *out, int n)
{
	uint8_t mosi[2 + 16] = {CARD_OP_READ}, miso[2 + 16];
	card_frame(&eink.gpu.card, mosi, miso, 2 + n);
	memcpy(out, miso + 2, (size_t)n);
	return miso[1];
}

/* GETPIXEL2 */
static int GET2(int x, int y)
{
	uint8_t f[5] = {0x49, (uint8_t)x, (uint8_t)(x >> 8), (uint8_t)y, (uint8_t)(y >> 8)}, r;
	send(f, 5);
	return read_resp(&r, 1) == 1 ? r : -1;
}

static int W(void) { return eink.panel->w; }
static int H(void) { return eink.panel->h; }

/* ------------------------------------------------------------------ images */

static void write_pgm(const char *path, const uint8_t *g, int w, int h)
{
	FILE *f = fopen(path, "wb");
	if (!f)
		return;
	fprintf(f, "P5\n%d %d\n255\n", w, h);
	fwrite(g, 1, (size_t)w * (size_t)h, f);
	fclose(f);
}

/* 1-bit pictures as PBM (1 = black), greys as PGM */
static void write_golden(const char *path, const uint8_t *g, int w, int h, bool grey)
{
	FILE *f = fopen(path, "wb");
	if (!f) {
		perror(path);
		return;
	}
	if (grey) {
		fprintf(f, "P5\n%d %d\n255\n", w, h);
		fwrite(g, 1, (size_t)w * (size_t)h, f);
	} else {
		fprintf(f, "P4\n%d %d\n", w, h);
		for (int y = 0; y < h; y++)
			for (int x = 0; x < w; x += 8) {
				uint8_t b = 0;
				for (int i = 0; i < 8; i++)
					if (g[y * w + x + i] < 128)
						b |= (uint8_t)(0x80 >> i);
				fputc(b, f);
			}
	}
	fclose(f);
}

static bool read_golden(const char *path, uint8_t *g, int w, int h)
{
	FILE *f = fopen(path, "rb");
	if (!f)
		return false;
	char kind[3] = {0};
	int fw, fh, max = 1;
	bool ok = fscanf(f, "%2s %d %d", kind, &fw, &fh) == 3 && fw == w && fh == h;
	if (ok && !strcmp(kind, "P5"))
		ok = fscanf(f, "%d", &max) == 1;
	fgetc(f);
	if (ok && !strcmp(kind, "P5")) {
		ok = fread(g, 1, (size_t)w * (size_t)h, f) == (size_t)w * (size_t)h;
	} else if (ok && !strcmp(kind, "P4")) {
		for (int y = 0; y < h && ok; y++)
			for (int x = 0; x < w; x += 8) {
				int b = fgetc(f);
				if (b == EOF) {
					ok = false;
					break;
				}
				for (int i = 0; i < 8; i++)
					g[y * w + x + i] = (b & (0x80 >> i)) ? 0 : 255;
			}
	} else {
		ok = false;
	}
	fclose(f);
	return ok;
}

/* the glass equals the core's own raster, and a golden image */
static void check_picture(const char *name, bool grey)
{
	char path[512];
	int w = W(), h = H();
	eink_render(&eink, ref, grey);
	long diff = 0;
	for (int i = 0; i < w * h; i++)
		diff += model.glass[i] != ref[i];
	CHECK(diff == 0, "%s: the panel differs from the core's raster in %ld pixels", name, diff);
	snprintf(path, sizeof path, "%s/%s.pgm", getenv("OUT") ? getenv("OUT") : ".", name);
	write_pgm(path, model.glass, w, h);
	snprintf(path, sizeof path, "%s/%s.%s", golden_dir, name, grey ? "pgm" : "pbm");
	if (getenv("EINK_RECORD"))
		write_golden(path, model.glass, w, h, grey);
	if (!read_golden(path, pic, w, h)) {
		CHECK(0, "%s: no golden image %s (EINK_RECORD=1 once checked)", name, path);
		return;
	}
	diff = 0;
	for (int i = 0; i < w * h; i++)
		diff += model.glass[i] != pic[i];
	CHECK(diff == 0, "%s: the panel differs from %s in %ld pixels", name, path, diff);
}

static uint8_t glass(int x, int y) { return model.glass[y * W() + x]; }

/* ------------------------------------------------------------------ GPU-006 */

static void test_commands(void)
{
	uint8_t r[16];
	setup(&eink_panel_583, 0.01);

	/* INFO: e-paper, 648 x 480, 4 greys, partial refresh and mode 2, 80 x 30 */
	SEND(0x08);
	CHECK_EQ(read_resp(r, 9), 9);
	CHECK(r[0] == 1 && (r[1] | r[2] << 8) == 648 && (r[3] | r[4] << 8) == 480 && r[5] == 4 && r[6] == 3 &&
	      r[7] == 80 && r[8] == 30, "INFO 5.83");
	/* IDENT: the graphics type, as the HDMI card */
	SEND(CARD_OP_IDENT);
	CHECK_EQ(read_resp(r, 4), 4);
	CHECK(r[0] == CARD_TYPE_GPU && r[3] == CARD_IDENT_SIG, "IDENT type $01");

	/* AUTO and EPD_STATUS */
	SEND(0x0A, 0, 7, 3);
	CHECK(!eink.auto_on && eink.idle10 == 7 && eink.full_after == 3, "AUTO 0, 7, 3");
	SEND(0x0A, 1, 15, 30);
	CHECK(eink.auto_on && eink.idle10 == 15 && eink.full_after == 30, "AUTO 1, 15, 30");
	SEND(0x0B);
	CHECK_EQ(read_resp(r, 3), 3);
	CHECK(r[1] == 1 && r[2] == 0, "EPD_STATUS at power-on: dirty, no partials");
	CHECK(settle(5000), "the power-on refresh completes");
	SEND(0x0B);
	read_resp(r, 3);
	CHECK(r[0] == 0 && r[1] == 0, "EPD_STATUS settled: not busy, nothing unshown");

	/* malformed: short frames and bad arguments count errors and do nothing */
	uint32_t e = eink.gpu.errors;
	SEND(0x09);                                 /* REFRESH without m */
	SEND(0x09, 4);                              /* no such refresh */
	SEND(0x0A, 1, 2);                           /* AUTO short */
	CHECK_EQ(eink.gpu.errors, e + 3);
	CHECK(!eink.gpu.hold && eink.explicit_req < 0, "a bad REFRESH holds nothing");
	SEND(0x0B, 1, 2, 3);                        /* longer than its command: fine */
	CHECK_EQ(eink.gpu.errors, e + 3);

	/* AUTO_EXT and AUTO_GET: the defaults, a round trip, the limits */
	SEND(0x0D);
	CHECK_EQ(read_resp(r, 6), 6);
	CHECK(r[0] == 1 && r[1] == 15 && r[2] == 30 && r[3] == 100 && r[4] == 1 && r[5] == 10,
	      "AUTO_GET at power-on: 1, 15, 30, 100, 1, 10 (got %d %d %d %d %d %d)", r[0], r[1], r[2], r[3], r[4], r[5]);
	SEND(0x0A, 0, 7, 3);
	SEND(0x0C, 42, 3, 200);
	SEND(0x0D);
	CHECK_EQ(read_resp(r, 6), 6);
	CHECK(r[0] == 0 && r[1] == 7 && r[2] == 3 && r[3] == 42 && r[4] == 3 && r[5] == 200, "AUTO_GET round trip");
	SEND(0x0C, 0, 2, 0);                        /* no cap, clean, never sleep */
	SEND(0x0C, 255, 1, 255);                    /* the other ends */
	CHECK(eink.cap10 == 255 && eink.full_kind == EINK_FAST && eink.sleep_s == 255, "AUTO_EXT 255, 1, 255");
	SEND(0x0C, 0, 2, 0);
	CHECK(eink.cap10 == 0 && eink.full_kind == EINK_CLEAN && eink.sleep_s == 0, "AUTO_EXT 0, 2, 0");
	e = eink.gpu.errors;
	SEND(0x0C, 50, 0, 5);                       /* full_kind 0 is no full refresh */
	SEND(0x0C, 50, 4, 5);                       /* no such refresh */
	SEND(0x0C, 50, 255, 5);
	SEND(0x0C, 50, 1);                          /* short */
	SEND(0x0C);
	CHECK_EQ(eink.gpu.errors, e + 5);
	CHECK(eink.cap10 == 0 && eink.full_kind == EINK_CLEAN && eink.sleep_s == 0, "a bad AUTO_EXT changes nothing");
	SEND(0x0D, 9, 9);                           /* longer than its command: fine */
	CHECK_EQ(read_resp(r, 6), 6);
	CHECK_EQ(eink.gpu.errors, e + 5);
	SEND(0x0A, 1, 15, 30);
	SEND(0x0C, 100, 1, 10);

	/* MODE 2: native, cleared to white; MODE 3 is no mode */
	SEND(0x01, 2);
	CHECK_EQ(eink.gpu.mode, EINK_MODE_NATIVE);
	SEND(0x49, 0, 0, 0, 0);
	CHECK_EQ(read_resp(r, 1), 1);
	CHECK_EQ(r[0], 3);
	SEND(0x01, 3);
	CHECK_EQ(eink.gpu.mode, EINK_MODE_NATIVE);

	/* every mode-2 command at its corners */
	SEND(0x40, 0x87, 0x02, 0xDF, 0x01, 0);      /* PIXEL2 (647, 479) black */
	CHECK_EQ(GET2(647, 479), 0);
	SEND(0x40, 0x88, 0x02, 0, 0, 0);            /* x = 648: clipped */
	SEND(0x40, 0xFF, 0xFF, 0, 0, 0);            /* x = -1: clipped */
	CHECK_EQ(GET2(0, 0), 3);
	CHECK_EQ(GET2(648, 0), 0);                  /* off the panel reads 0 */
	SEND(0x41, 0xF6, 0xFF, 0xF6, 0xFF, 20, 0, 20, 0, 1);  /* FILL_RECT2 at (-10,-10) 20x20: clipped */
	CHECK(GET2(0, 0) == 1 && GET2(9, 9) == 1 && GET2(10, 10) == 3, "FILL_RECT2 clipped");
	SEND(0x42, 100, 0, 100, 0, 10, 0, 5, 0, 2); /* RECT2 */
	CHECK(GET2(100, 100) == 2 && GET2(109, 104) == 2 && GET2(105, 102) == 3, "RECT2 is an outline");
	SEND(0x43, 0, 0, 0x2C, 0x01, 0x87, 0x02, 0x2C, 0x01, 0);   /* LINE2 (0,300)-(647,300) */
	CHECK(GET2(0, 300) == 0 && GET2(647, 300) == 0 && GET2(300, 301) == 3, "LINE2 both ends");
	SEND(0x44, 200, 0, 200, 0, 10, 0, 2, 0, 0, 0xFF, 0x80, 0x40, 0x01, 0x80); /* BLIT1_2 transparent */
	CHECK(GET2(200, 200) == 0 && GET2(201, 200) == 3 && GET2(209, 200) == 0 && GET2(207, 201) == 0 &&
	      GET2(208, 201) == 0, "BLIT1_2 bits");
	SEND(0x45, 50, 0, 50, 0, 5, 0, 1, 0, 0x1B, 0x40); /* BLIT2 0,1,2,3,1 */
	CHECK(GET2(50, 50) == 0 && GET2(51, 50) == 1 && GET2(52, 50) == 2 && GET2(53, 50) == 3 && GET2(54, 50) == 1,
	      "BLIT2 levels");
	SEND(0x46, 0, 1, 0, 1, 0, 0xFF, 1, 'H');    /* TEXT16 at (256, 256) */
	bool ok = true;
	for (int y = 0; y < 16; y++)
		for (int x = 0; x < 8; x++) {
			bool on = font8x8_cp437['H'][y / 2] & (0x80 >> x);
			if (GET2(256 + x, 256 + y) != (on ? 0 : 3))
				ok = false;
		}
	CHECK(ok, "TEXT16 glyph");
	SEND(0x47, 0, 1, 0x40, 0, 1, 2, 1, 'H');    /* TEXT8_2 at (256, 64), bg dark grey */
	CHECK(GET2(256, 64) == 1 && GET2(256 + 1, 64) == 1 && GET2(256, 64 + 1) == 1, "TEXT8_2 background");
	SEND(0x40, 10, 0, 20, 0, 0);
	SEND(0x48, 5, 0, 2);                        /* VSCROLL2 up 5, fill light grey */
	CHECK(GET2(10, 15) == 0 && GET2(0, 479) == 2, "VSCROLL2 up");
	SEND(0x48, 0xFB, 0xFF, 1);                  /* down 5 */
	CHECK(GET2(10, 20) == 0 && GET2(0, 0) == 1, "VSCROLL2 down");
	SEND(0x48, 0x00, 0x10, 3);                  /* 4096 rows: all filled */
	CHECK(GET2(10, 20) == 3 && GET2(647, 479) == 3, "VSCROLL2 past the screen");
	SEND(0x02, 0);                              /* CLS g */
	CHECK(GET2(0, 0) == 0 && GET2(647, 479) == 0, "CLS 0 in mode 2");

	/* malformed mode-2 frames: short, a grey that is not one */
	e = eink.gpu.errors;
	SEND(0x40, 1, 0, 1, 0);                     /* short */
	SEND(0x40, 1, 0, 1, 0, 4);                  /* grey 4 */
	SEND(0x41, 0, 0, 0, 0, 1, 0, 1, 0, 0xFF);   /* transparent is no fill */
	SEND(0x44, 0, 0, 0, 0, 16, 0, 2, 0, 0, 1, 0xFF, 0xFF, 0xFF); /* BLIT1_2 one byte short */
	SEND(0x45, 0, 0, 0, 0, 8, 0, 1, 0, 0xFF);   /* BLIT2 one byte short */
	SEND(0x46, 0, 0, 0, 0, 0, 1, 3, 'a', 'b');  /* TEXT16 one short */
	SEND(0x46, 0, 0, 0, 0, 7, 1, 1, 'a');       /* fg 7 */
	SEND(0x02, 9);                              /* CLS 9 in mode 2 */
	SEND(0x48, 1);                              /* short */
	SEND(0x4A);                                 /* free, unknown */
	CHECK_EQ(eink.gpu.errors, e + 10);
	CHECK(GET2(1, 1) == 0, "malformed frames drew nothing");

	/* GFX mode 1's commands are ignored in mode 2 (their buffer is mode 2's),
	 * and mode 2's in modes 0 and 1 */
	e = eink.gpu.errors;
	SEND(0x21, 0, 0, 0, 16, 0, 16, 7);          /* FILL_RECT */
	CHECK(GET2(0, 0) == 0 && GET2(1, 0) == 0, "FILL_RECT is ignored in mode 2");
	SEND(0x28, 0, 0, 0);
	CHECK(read_resp(r, 1) == 1 && r[0] == 0, "GETPIXEL answers 0 in mode 2");
	SEND(0x01, 1);
	SEND(0x40, 0, 0, 0, 0, 3);
	SEND(0x49, 0, 0, 0, 0);
	CHECK(read_resp(r, 1) == 1 && r[0] == 0, "mode 2 is off in mode 1");
	CHECK_EQ(eink.gpu.gfx[0][0], 0);
	CHECK_EQ(eink.gpu.errors, e);

	/* SOFT_RESET: TEXT mode, the policy's defaults */
	SEND(0x0A, 0, 1, 1);
	SEND(0x0C, 7, 3, 0);
	SEND(CARD_OP_SOFT_RESET);
	CHECK(eink.gpu.mode == GPU_MODE_TEXT && eink.auto_on && eink.idle10 == 15 && eink.full_after == 30 &&
	      eink.full_next, "SOFT_RESET");
	SEND(0x0D);
	CHECK_EQ(read_resp(r, 6), 6);
	CHECK(r[0] == 1 && r[1] == 15 && r[2] == 30 && r[3] == 100 && r[4] == 1 && r[5] == 10,
	      "SOFT_RESET restores AUTO_EXT's defaults too (got %d %d %d %d %d %d)", r[0], r[1], r[2], r[3], r[4], r[5]);
	CHECK(settle(10000), "settles after SOFT_RESET");

	/* the 7.5" panel: INFO says so */
	setup(&eink_panel_750, 0.01);
	SEND(0x08);
	read_resp(r, 9);
	CHECK((r[1] | r[2] << 8) == 800 && (r[3] | r[4] << 8) == 480, "INFO 7.5");
	CHECK_EQ(model.errors, 0);
}

/* ------------------------------------------------------------------ GPU-007 */

static void test_pictures(void)
{
	/* the ink rule, cell by cell: all 256 attributes */
	setup(&eink_panel_583, 0.01);
	SEND(0x14, 0);
	for (int a = 0; a < 256; a++)
		SEND(0x17, (uint8_t)(a % 80), (uint8_t)(a / 80), (uint8_t)(a & 1 ? 'A' + a % 26 : 0xDB), (uint8_t)a);
	CHECK(settle(10000), "settles");
	bool ok = true;
	for (int a = 0; a < 256 && ok; a++) {
		int col = a % 80, row = a / 80;
		uint8_t ch = (uint8_t)(a & 1 ? 'A' + a % 26 : 0xDB);
		uint8_t lf = eink_lum(eink.gpu.palette[a & 15]), lb = eink_lum(eink.gpu.palette[a >> 4]);
		for (int y = 0; y < 16; y++)
			for (int x = 0; x < 8; x++) {
				bool bit = font8x8_cp437[ch][y / 2] & (0x80 >> x);
				bool ink = lf > lb ? bit : lb > lf ? !bit : false;
				if (glass(4 + col * 8 + x, row * 16 + y) != (ink ? 0 : 255)) {
					ok = false;
					fprintf(stderr, "attr $%02X at pixel %d,%d\n", a, x, y);
				}
			}
	}
	CHECK(ok, "the brighter colour of every cell is ink");
	CHECK(glass(0, 0) == 255 && glass(3, 100) == 255 && glass(644, 5) == 255 && glass(647, 479) == 255,
	      "4 white columns each side");
	CHECK(eink_lum(0xFFFF) == 255 && eink_lum(0) == 0, "luminance range");

	/* TEXT: the default $07 is black on white, $70 white on black, both
	 * cursors (static), control codes, a redefined glyph */
	SEND(0x02, 0x07);
	SEND(0x14, 1);
	uint8_t puts[] = {0x11, 20, 'C', 'U', 'P', 'C', '/', '8', ' ', 'e', '-', 'i', 'n', 'k', '\r', '\n', 'x', '\t',
			  'y', '\b', 'Y', '\n'};
	send(puts, sizeof puts);
	SEND(0x13, 0x70);
	SEND(0x11, 7, ' ', 'L', 'I', 'S', 'T', ' ', ' ');
	SEND(0x13, 0x07);
	uint8_t def[18] = {0x19, 1};
	for (int i = 0; i < 16; i++) def[2 + i] = (uint8_t)(i & 1 ? 0xAA : 0x55);
	send(def, sizeof def);
	SEND(0x17, 79, 29, 1, 0x1F);
	SEND(0x12, 10, 10);
	SEND(0x11, 5, '>', '>', ' ', '1', '0');
	CHECK(settle(10000), "settles");
	check_picture("text", false);
	CHECK(glass(4 + 8 * 15 + 3, 10 * 16 + 14) == 0 && glass(4 + 8 * 15 + 3, 10 * 16 + 13) == 255,
	      "the underline cursor is drawn, not blinking");
	SEND(0x14, 2);
	CHECK(settle(10000), "settles");
	CHECK(glass(4 + 8 * 15 + 3, 10 * 16 + 1) == 0, "the block cursor");

	/* GFX mode 1: the palette through luminance and the dither, every
	 * drawing command */
	SEND(0x01, 1);
	for (int c = 0; c < 256; c++)
		SEND(0x21, (uint8_t)((c % 32) * 10), 0, (uint8_t)((c / 32) * 16), 10, 0, 16, (uint8_t)c);
	SEND(0x22, 10, 0, 140, 100, 0, 50, 15);
	SEND(0x23, 0, 0, 200, 0x3F, 0x01, 239, 15);
	SEND(0x26, 200, 0, 150, 15, 0xFF, 5, 'H', 'e', 'l', 'l', 'o');
	uint8_t blit[6 + 64];
	blit[0] = 0x24; blit[1] = 20; blit[2] = 0; blit[3] = 200; blit[4] = 8; blit[5] = 8;
	for (int i = 0; i < 64; i++) blit[6 + i] = (uint8_t)(232 + i % 24);
	send(blit, sizeof blit);
	CHECK(settle(10000), "settles");
	check_picture("gfx", false);

	/* mode 2 at full resolution: every command, dithered on a 1-bit refresh */
	SEND(0x01, 2);
	for (int g = 0; g < 4; g++)
		SEND(0x41, (uint8_t)(g * 162), (uint8_t)((g * 162) >> 8), 0, 0, 162, 0, 60, 0, (uint8_t)g);
	SEND(0x42, 10, 0, 70, 0, 0x6C, 0x02, 100, 0, 0);
	SEND(0x43, 0, 0, 0x2C, 0x01, 0x87, 0x02, 0xDF, 0x01, 0);
	SEND(0x46, 20, 0, 80, 0, 0, 0xFF, 14, 'm', 'o', 'd', 'e', ' ', '2', ' ', '6', '4', '8', 'x', '4', '8', '0');
	SEND(0x47, 20, 0, 100, 0, 1, 2, 6, '4', 'g', 'r', 'e', 'y', 's');
	SEND(0x44, 0x80, 0x02, 0xD8, 0x01, 16, 0, 16, 0, 0, 0xFF,
	     0xFF, 0xFF, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01,
	     0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0x80, 0x01, 0xFF, 0xFF);
	uint8_t b2[9 + 60];
	b2[0] = 0x45; b2[1] = 0; b2[2] = 1; b2[3] = 200; b2[4] = 0; b2[5] = 240; b2[6] = 0; b2[7] = 1; b2[8] = 0;
	for (int i = 0; i < 60; i++) b2[9 + i] = (uint8_t)(i * 0x11);
	send(b2, sizeof b2);
	CHECK(settle(10000), "settles");
	check_picture("mode2", false);
	/* and in 4 greys: REFRESH 3 */
	SEND(0x09, EINK_GREY);
	CHECK(eink.gpu.hold, "REFRESH holds the interpreter");
	CHECK(settle(10000), "settles");
	CHECK(model.refreshes[EPD_WF_GREY] == 1, "a greyscale refresh");
	check_picture("mode2_grey", true);
	CHECK(glass(0, 0) == 0 && glass(162, 0) == 85 && glass(324, 0) == 170 && glass(486, 0) == 255,
	      "four greys");

	/* the 7.5" panel: 80 x 30 centred, 80 white columns each side */
	setup(&eink_panel_750, 0.01);
	SEND(0x14, 0);
	SEND(0x11, 10, 'C', 'U', 'P', 'C', '/', '8', ' ', '7', '.', '5');
	SEND(0x12, 69, 29);
	SEND(0x11, 10, '8', '0', 'x', '3', '0', ' ', 'e', 'n', 'd', '.');
	SEND(0x17, 79, 29, 0xDB, 0x07);             /* the last cell, without scrolling */
	CHECK(settle(10000), "settles");
	check_picture("text750", false);
	CHECK(glass(79, 470) == 255 && glass(80 + 79 * 8, 470) == 0 && glass(80 + 80 * 8, 470) == 255 && glass(80, 5) == 0,
	      "80 x 30 centred on 800 x 480");
	CHECK_EQ(model.errors, 0);
}

/* ------------------------------------------------------------------ GPU-008 */

static void test_policy(void)
{
	uint8_t r[4];
	/* realistic panel times here */
	setup(&eink_panel_583, 1.0);
	/* power-on: one clean full refresh once the stream has been quiet */
	run_ms(100);
	SEND(0x14, 0);                              /* no cursor: the windows below are the text's */
	SEND(0x11, 5, 'B', 'O', 'O', 'T', '\n');
	run_ms(100);
	CHECK_EQ(drfs, 0);
	run_ms(200);
	CHECK(drfs == 1 && model.busy_wf == EPD_WF_CLEAN, "the first refresh is a clean full one");
	/* 150 ms quiet, then the module's power, a reset, PON and the data
	 * (78 KB at 10 MHz) */
	CHECK(drf_at[0] > 101000 + 150000 + 60000 + 62000 && drf_at[0] < 101000 + 150000 + 160000,
	      "... 150 ms after the last change (DRF at %llu us)", (unsigned long long)drf_at[0]);
	CHECK(settle(5000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_CLEAN], 1);

	/* a key's echo: a partial refresh 150 ms after it, of its text row only */
	uint64_t t = now_us;
	drfs = 0;
	SEND(0x12, 3, 7);
	SEND(0x10, 'k');
	settle(2000);
	CHECK(drfs == 1 && model.refreshes[EPD_WF_PARTIAL] == 1, "one partial refresh");
	CHECK(drf_at[0] - t >= 150000 && drf_at[0] - t < 150000 + 60000, "150 ms quiet + PON (%llu us)",
	      (unsigned long long)(drf_at[0] - t));
	CHECK(model.busy_area[2] == 7 * 16 && model.busy_area[3] == 7 * 16 + 13 && model.busy_area[0] == 0 &&
	      model.busy_area[1] == 647, "the window is the rows that changed: the k's 14 (rows %d-%d)", model.busy_area[2],
	      model.busy_area[3]);
	CHECK(glass(4 + 3 * 8 + 1, 7 * 16 + 4) == 0, "the k is on the glass");

	/* continuous output: a refresh at least once a second */
	drfs = 0;
	t = now_us;
	for (int i = 0; i < 150; i++) {
		SEND(0x10, (uint8_t)('a' + i % 26));
		run_ms(20);
	}
	CHECK(drfs >= 2, "refreshes under continuous output: %d", drfs);
	CHECK(drfs && drf_at[0] - t <= 1000000 + 60000, "the first within 1 s (%llu us)",
	      (unsigned long long)(drf_at[0] - t));
	CHECK(settle(3000), "settles");
	CHECK_EQ(model.errors, 0);

	/* a change undone before the refresh costs nothing */
	uint32_t before = model.refreshes[EPD_WF_PARTIAL];
	SEND(0x17, 50, 20, 'Z', 0x07);
	SEND(0x17, 50, 20, ' ', 0x07);
	CHECK(settle(2000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_PARTIAL], before);

	/* CLS: the next refresh is a fast full one */
	SEND(0x02, 0x07);
	CHECK(settle(5000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_FAST], 1);
	SEND(0x10, 0x0C);                           /* form feed: the same */
	CHECK(settle(5000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_FAST], 2);

	/* after full_after partials, a fast full refresh at the next 2 s pause */
	SEND(0x0A, 1, 15, 3);
	for (int i = 0; i < 3; i++) {
		SEND(0x10, 'p');
		settle(2000);
	}
	CHECK_EQ(eink.partials, 3);
	SEND(0x10, 'q');
	run_ms(1000);
	CHECK_EQ(model.refreshes[EPD_WF_FAST], 2);  /* no pause yet: a 4th partial */
	CHECK_EQ(eink.partials, 4);
	run_ms(1500);
	CHECK(model.busy_op == 0x12 && model.busy_wf == EPD_WF_FAST, "then the ghosts are cleared");
	settle(3000);
	CHECK_EQ(model.refreshes[EPD_WF_FAST], 3);
	CHECK(eink.partials == 0 && model.partials_since_full == 0, "partials counted from 0 again");
	SEND(0x0A, 1, 15, 30);

	/* AUTO 0: nothing refreshes until REFRESH; FENCE after it fires when the
	 * picture is on the panel */
	SEND(0x0A, 0, 15, 30);
	SEND(0x11, 4, 'm', 'a', 'n', 'u');
	run_ms(3000);
	SEND(0x0B);
	read_resp(r, 3);
	CHECK(r[1] == 1, "AUTO 0: the change waits");
	before = model.refreshes[EPD_WF_PARTIAL];
	SEND(CARD_OP_IRQ_EN, 1);
	SEND(0x09, EINK_PARTIAL);
	SEND(0x05, 0x42);
	SEND(0x18);                                 /* GETXY waits behind REFRESH too */
	CHECK(!card_irq(&eink.gpu.card), "FENCE waits for the refresh");
	CHECK_EQ(read_resp(r, 2), 0);
	run_ms(100);
	CHECK(!card_irq(&eink.gpu.card), "... still refreshing");
	run_ms(600);
	CHECK(card_irq(&eink.gpu.card), "FENCE fires once the panel has the picture");
	CHECK_EQ(model.refreshes[EPD_WF_PARTIAL], before + 1);
	CHECK_EQ(read_resp(r, 2), 2);
	SEND(0x06);
	SEND(CARD_OP_IRQ_EN, 0);
	/* REFRESH 0 with nothing changed returns at once */
	SEND(0x09, EINK_PARTIAL);
	run_ms(3);                                  /* the comparison */
	CHECK(!eink.gpu.hold, "REFRESH with nothing to show");
	/* REFRESH 1 and 2 */
	SEND(0x09, EINK_FAST);
	CHECK(settle(3000), "REFRESH 1");
	SEND(0x09, EINK_CLEAN);
	CHECK(settle(5000), "REFRESH 2");
	CHECK(model.refreshes[EPD_WF_FAST] == 4 && model.refreshes[EPD_WF_CLEAN] == 2, "fast and clean refreshes");
	SEND(0x0A, 1, 15, 30);

	/* a change made during a refresh is shown by the next one */
	SEND(0x17, 0, 0, 'A', 0x07);
	run_ms(200);                                /* refreshing now */
	CHECK(model.busy_op == 0x12 || model.busy_op == 0x04, "refreshing");
	SEND(0x17, 0, 29, 'B', 0x07);
	CHECK(settle(3000), "settles");
	CHECK(glass(4 + 1, 29 * 16 + 3) == 0, "the change made during the refresh is on the glass");

	/* 10 s unused: deep sleep; the next change resets the controller */
	uint32_t resets = eink.resets;
	run_ms(11000);
	CHECK(model.asleep, "deep sleep after 10 s (state %d, step %d, panel %d, partials %d, dirty %d)", model.asleep,
	      eink.step, eink.panel_state, eink.partials, eink.change_seq != eink.shown_seq);
	SEND(0x10, 'w');
	CHECK(settle(3000), "wakes");
	CHECK(!model.asleep && eink.resets == resets + 1, "a reset wakes the controller");
	CHECK_EQ(model.errors, 0);
	if (model.errors)
		fprintf(stderr, "model: %s\n", model.error);

	/* VSYNC_COUNT counts at 60 Hz */
	SEND(0x07);
	read_resp(r, 1);
	uint8_t v0 = r[0];
	run_ms(1000);
	SEND(0x07);
	read_resp(r, 1);
	CHECK((uint8_t)(r[0] - v0) == 60, "60 vsyncs a second (%d)", (uint8_t)(r[0] - v0));

	/* a panel that never releases BUSY: given up after 10 s, REFRESH
	 * released, and the next refresh starts with a reset */
	stuck_busy = true;
	SEND(0x09, EINK_FAST);
	run_ms(9000);
	CHECK(eink.gpu.hold, "still waiting");
	run_ms(2000);
	CHECK(!eink.gpu.hold && eink.panel_errors == 1, "given up");
	stuck_busy = false;
	resets = eink.resets;
	SEND(0x10, 'z');
	CHECK(settle(8000), "recovers");
	CHECK_EQ(eink.resets, resets + 1);
}

/* AUTO_EXT's fields in use: cap10, full_kind, sleep_s */
static void idle_s(double s)                    /* long quiet stretches, in 10 ms steps */
{
	for (int i = 0; i < s * 100; i++) {
		now_us += 10000;
		gpu_run(&eink.gpu, 1000);
		eink_poll(&eink, (uint32_t)now_us);
		epd_advance(&model, ns());
	}
}

static void test_policy_ext(void)
{
	setup(&eink_panel_583, 1.0);
	/* full_kind 3 from the start: the first refresh after power-on stays clean */
	SEND(0x0C, 100, EINK_GREY, 10);
	SEND(0x14, 0);
	SEND(0x11, 4, 'B', 'O', 'O', 'T');
	CHECK(settle(5000), "settles");
	CHECK(model.refreshes[EPD_WF_CLEAN] == 1 && model.refreshes[EPD_WF_GREY] == 0,
	      "the power-on refresh is clean whatever full_kind says");

	/* cap10 0: continuous output (a change every 20 ms) waits for the quiet time */
	SEND(0x0C, 0, EINK_FAST, 10);
	drfs = 0;
	for (int i = 0; i < 150; i++) {
		SEND(0x10, (uint8_t)('a' + i % 26));
		run_ms(20);
	}
	CHECK(drfs == 0, "cap10 0: no refresh under 3 s of continuous output (%d)", drfs);
	CHECK(settle(2000), "then the quiet time shows it");
	CHECK_EQ(drfs, 1);

	/* cap10 50: continuous output reaches the glass every 0.5 s */
	SEND(0x0C, 50, EINK_FAST, 10);
	SEND(0x12, 0, 10);
	drfs = 0;
	uint64_t t = now_us;
	for (int i = 0; i < 150; i++) {
		SEND(0x10, (uint8_t)('a' + i % 26));
		run_ms(20);
	}
	CHECK(drfs >= 4, "cap10 50: refreshes in 3 s of continuous output: %d", drfs);
	CHECK(drfs && drf_at[0] - t >= 500000 && drf_at[0] - t <= 500000 + 60000, "the first after 0.5 s (%llu us)",
	      (unsigned long long)(drf_at[0] - t));
	CHECK(drfs >= 2 && drf_at[1] - drf_at[0] <= 600000, "the next 0.5 s later (%llu us)",
	      (unsigned long long)(drf_at[1] - drf_at[0]));
	CHECK(settle(3000), "settles");

	/* full_kind: CLS, a form feed and MODE make the next refresh one of it */
	uint32_t clean = model.refreshes[EPD_WF_CLEAN], grey = model.refreshes[EPD_WF_GREY];
	uint32_t fast = model.refreshes[EPD_WF_FAST];
	SEND(0x0C, 100, EINK_CLEAN, 10);
	SEND(0x02, 0x07);
	CHECK(settle(8000), "settles");
	CHECK(model.refreshes[EPD_WF_CLEAN] == clean + 1 && model.refreshes[EPD_WF_FAST] == fast,
	      "full_kind 2: CLS gives a clean full refresh");
	SEND(0x0C, 100, EINK_GREY, 10);
	SEND(0x02, 0x07);
	CHECK(settle(8000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_GREY], grey + 1);
	SEND(0x10, 0x0C);
	CHECK(settle(8000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_GREY], grey + 2);
	SEND(0x01, 0);
	CHECK(settle(8000), "settles");
	CHECK_EQ(model.refreshes[EPD_WF_GREY], grey + 3);
	CHECK(model.refreshes[EPD_WF_FAST] == fast && model.refreshes[EPD_WF_CLEAN] == clean + 1, "and no other");
	eink_render(&eink, ref, true);
	CHECK(!memcmp(model.glass, ref, (size_t)W() * (size_t)H()), "the glass is the core's 4-grey raster");

	/* ... and the automatic full refresh after full_after partials */
	SEND(0x0A, 1, 15, 2);
	for (int i = 0; i < 2; i++) {
		SEND(0x10, 'p');
		settle(2000);
	}
	CHECK_EQ(eink.partials, 2);
	run_ms(2500);
	CHECK(settle(5000), "settles");
	CHECK(model.refreshes[EPD_WF_GREY] == grey + 4 && eink.partials == 0,
	      "after full_after partials, a full refresh of full_kind 3");
	CHECK_EQ(model.refreshes[EPD_WF_FAST], fast);
	SEND(0x0A, 1, 15, 30);

	/* sleep_s 3: deep sleep 3 s after the last refresh, not before */
	SEND(0x0C, 100, EINK_FAST, 3);
	SEND(0x10, 's');
	CHECK(settle(2000), "settles");
	run_ms(2800);
	CHECK(!model.asleep, "sleep_s 3: awake at 2.8 s");
	run_ms(400);
	CHECK(model.asleep, "sleep_s 3: asleep at 3.2 s");
	uint32_t resets = eink.resets;
	SEND(0x10, 'w');
	CHECK(settle(3000), "wakes");
	CHECK(!model.asleep && eink.resets == resets + 1, "a reset wakes the controller");

	/* sleep_s 0: never */
	SEND(0x0C, 100, EINK_FAST, 0);
	idle_s(60);
	CHECK(!model.asleep, "sleep_s 0: awake after 60 s");

	/* sleep_s 255: the longest (255 000 000 us, within a uint32) */
	SEND(0x0C, 100, EINK_FAST, 255);
	SEND(0x10, 'x');
	CHECK(settle(2000), "settles");
	idle_s(254);
	CHECK(!model.asleep, "sleep_s 255: awake at 254 s");
	idle_s(2);
	CHECK(model.asleep, "sleep_s 255: asleep at 256 s");
	SEND(0x10, 'y');
	CHECK(settle(3000), "wakes");
	CHECK_EQ(model.errors, 0);
	if (model.errors)
		fprintf(stderr, "model: %s\n", model.error);
}

/* ------------------------------------------------------------------ main */

int main(void)
{
	if (getenv("EINK_GOLDEN"))
		golden_dir = getenv("EINK_GOLDEN");
	test_commands();
	test_pictures();
	test_policy();
	test_policy_ext();
	CHECK(model.errors == 0, "the UC8179 model saw nothing the chip would ignore (%u errors: %s)", model.errors,
	      model.error);
	return check_report("GPU-006..008 e-ink card core");
}
