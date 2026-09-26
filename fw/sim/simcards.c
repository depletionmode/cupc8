#include "simcards.h"

#include <stdlib.h>
#include <string.h>

#include "cardproto.h"
#include "eink.h"
#include "epdmodel.h"
#include "gpu.h"
#include "imgdisk.h"
#include "iocard.h"
#include "netposix.h"
#include "storage.h"
#include "wifi.h"

struct simcard {
	int type;
	card_t *card;
	gpu_t *gpu;
	iocard_t *io;
	wifi_t *wifi;
	storage_t *st;
	imgdisk_t *disk;                   /* the storage card's medium, 0 = none */
	uint32_t st_latency_ms, st_busy_since;
	int st_was_busy;
	uint32_t last_vsync_ms;
	/* the e-ink card: its core and its panel (the UC8179 model) */
	eink_t *eink;
	epd_model_t *panel;
	uint64_t panel_ns;                 /* the panel's time: now, plus SPI bytes sent since */
};

/* the e-ink card's panel header, on the host: bytes take 0.8 us (10 MHz) */
static void sim_epd_command(void *ctx, uint8_t b)
{
	simcard_t *c = ctx;
	c->panel_ns += 800;
	epd_byte(c->panel, c->panel_ns, false, b);
}
static void sim_epd_data(void *ctx, const uint8_t *p, int n)
{
	simcard_t *c = ctx;
	for (int i = 0; i < n; i++) {
		c->panel_ns += 800;
		epd_byte(c->panel, c->panel_ns, true, p[i]);
	}
}
static void sim_epd_pin(void *ctx, int pin, bool v)
{
	simcard_t *c = ctx;
	if (pin == EPD_PIN_RST_N)
		epd_rst(c->panel, c->panel_ns, v);
	else
		epd_pwr(c->panel, c->panel_ns, v);
}
static bool sim_epd_busy(void *ctx)
{
	simcard_t *c = ctx;
	return !epd_busy_n(c->panel, c->panel_ns);
}

simcard_t *simcard_new(int type)
{
	simcard_t *c = calloc(1, sizeof *c);
	if (!c)
		return 0;
	c->type = type;
	if (type == SIMCARD_EINK || type == SIMCARD_EINK750) {
		/* the e-ink graphics card: type $01 on the slot, its panel's busy
		 * times x 0.1 (the simulator's guest time is slow to come by) */
		int w = type == SIMCARD_EINK ? 648 : 800;
		epd_cfg_t cfg;
		epd_cfg_default(&cfg, w, 480);
		cfg.time_scale = 0.1;
		c->panel = malloc(sizeof *c->panel);
		epd_init(c->panel, &cfg);
		c->eink = malloc(sizeof *c->eink);
		epd_bus_t bus = {c, sim_epd_command, sim_epd_data, sim_epd_pin, sim_epd_busy};
		eink_init(c->eink, type == SIMCARD_EINK ? &eink_panel_583 : &eink_panel_750, &bus);
		c->gpu = &c->eink->gpu;         /* the text and GFX state, for tests */
		c->card = &c->gpu->card;
		c->type = CARD_TYPE_GPU;
	} else if (type == CARD_TYPE_GPU) {
		c->gpu = malloc(sizeof *c->gpu);
		gpu_init(c->gpu);
		c->card = &c->gpu->card;
	} else if (type == CARD_TYPE_IO) {
		c->io = malloc(sizeof *c->io);
		io_init(c->io);
		io_connected(c->io, 1);
		c->card = &c->io->card;
	} else if (type == CARD_TYPE_STORAGE) {
		/* no medium until simcard_storage_image(); FatFs has one volume, so
		 * one storage card per process */
		c->st = malloc(sizeof *c->st);
		st_init(c->st, &imgdisk_ops, 0, false);
		c->card = &c->st->card;
	} else if (type == CARD_TYPE_WIFI) {
		c->wifi = malloc(sizeof *c->wifi);
		wifi_init(c->wifi, &netposix_ops, netposix_new());
		c->card = &c->wifi->card;
	} else {
		free(c);
		return 0;
	}
	return c;
}

void simcard_free(simcard_t *c)
{
	if (!c)
		return;
	if (c->eink) {
		free(c->eink);
		epd_free(c->panel);
		free(c->panel);
	} else {
		free(c->gpu);
	}
	free(c->io);
	free(c->wifi);
	if (c->st) {
		st_detect(c->st, false);        /* FatFs lets go of the volume before it is freed */
		st_poll(c->st);
	}
	free(c->st);
	imgdisk_free(c->disk);
	free(c);
}

int simcard_type(const simcard_t *c) { return c->type; }
void simcard_select(simcard_t *c, int s) { card_select(c->card, s != 0); }
uint8_t simcard_miso(simcard_t *c) { return card_next_miso(c->card); }

void simcard_mosi(simcard_t *c, uint8_t b)
{
	card_mosi(c->card, b);
}

int simcard_irq(simcard_t *c) { return card_irq(c->card); }

void simcard_tick(simcard_t *c, uint32_t now_ms)
{
	if (c->eink) {
		uint64_t ns = (uint64_t)now_ms * 1000000u;
		if (ns > c->panel_ns)
			c->panel_ns = ns;
		epd_advance(c->panel, c->panel_ns);
		gpu_run(c->gpu, 1 << 20);
		eink_poll(c->eink, (uint32_t)(c->panel_ns / 1000));   /* VSYNC_COUNT too */
		return;
	}
	if (c->gpu) {
		gpu_run(c->gpu, 1 << 20);
		while (now_ms - c->last_vsync_ms >= 17) {       /* ~60 Hz */
			gpu_vsync(c->gpu);
			c->last_vsync_ms += 17;
		}
	}
	if (c->io)
		io_poll(c->io, now_ms);
	if (c->wifi)
		wifi_poll(c->wifi);
	if (c->st) {
		/* the medium's time: commands wait st_latency_ms before they run
		 * (READ says not ready meanwhile), as an SD card's writes do */
		int busy = st_busy(c->st);
		if (busy && !c->st_was_busy)
			c->st_busy_since = now_ms;
		c->st_was_busy = busy;
		if (!busy || now_ms - c->st_busy_since >= c->st_latency_ms) {
			st_poll(c->st);
			c->st_was_busy = 0;
		}
	}
}

int simcard_storage_image(simcard_t *c, const char *path, int wp)
{
	if (!c->st)
		return -1;
	st_detect(c->st, false);
	st_poll(c->st);
	imgdisk_free(c->disk);
	c->disk = 0;
	c->st->ctx = 0;
	if (!path)
		return 0;
	c->disk = imgdisk_open(path);
	if (!c->disk)
		return -1;
	c->disk->wp = wp != 0;
	c->st->ctx = c->disk;
	st_detect(c->st, true);
	st_poll(c->st);
	return 0;
}

void simcard_storage_latency(simcard_t *c, uint32_t ms)
{
	c->st_latency_ms = ms;
}

int simcard_storage_status(simcard_t *c)
{
	return c->st ? st_status(c->st) : -1;
}

void simcard_render(simcard_t *c, uint32_t *rgb)
{
	if (c->eink) {
		/* the panel's glass, as of its last refresh: the 640x480 middle */
		int w = c->panel->cfg.w, ox = (w - GPU_OUT_W) / 2;
		for (int y = 0; y < GPU_OUT_H; y++)
			for (int x = 0; x < GPU_OUT_W; x++)
				rgb[y * GPU_OUT_W + x] = c->panel->glass[y * w + ox + x] * 0x010101u;
		return;
	}
	if (c->gpu)
		gpu_render(c->gpu, rgb);
}

int simcard_gpu_cell(simcard_t *c, int x, int y)
{
	if (!c->gpu || x < 0 || y < 0 || x >= GPU_TEXT_COLS || y >= GPU_TEXT_ROWS)
		return -1;
	return c->gpu->text[y][x].ch | (c->gpu->text[y][x].attr << 8);
}

int simcard_gpu_pixel(simcard_t *c, int x, int y)
{
	if (!c->gpu || x < 0 || y < 0 || x >= GPU_GFX_W || y >= GPU_GFX_H)
		return -1;
	return c->gpu->gfx[y][x];
}

int simcard_gpu_mode(simcard_t *c) { return c->gpu ? c->gpu->mode : -1; }

int simcard_eink_refreshes(simcard_t *c, int waveform)
{
	return c->eink && waveform >= 0 && waveform < 4 ? (int)c->panel->refreshes[waveform] : -1;
}

int simcard_eink_errors(simcard_t *c) { return c->eink ? (int)c->panel->errors : -1; }

int simcard_eink_pixel2(simcard_t *c, int x, int y)
{
	/* mode 2's picture (eink-card.md): 2 bits a pixel, the leftmost in bits 7-6 */
	if (!c->eink || x < 0 || y < 0 || x >= c->eink->panel->w || y >= c->eink->panel->h)
		return -1;
	uint8_t b = c->eink->gpu.gfx_bytes[y * (c->eink->panel->w / 4) + x / 4];
	return (b >> (6 - 2 * (x & 3))) & 3;
}

int simcard_gpu_errors(simcard_t *c) { return c->gpu ? (int)c->gpu->errors : -1; }

void simcard_hid(simcard_t *c, const uint8_t report[8], uint32_t now_ms)
{
	if (c->io)
		io_report(c->io, report, now_ms);
}

/* ASCII → (modifiers, HID usage) for the US layout */
static int ascii_to_hid(uint8_t ch, uint8_t *mods, uint8_t *usage)
{
	static const char plain[] = "abcdefghijklmnopqrstuvwxyz1234567890\r\x1b\b\t -=[]\\#;'`,./";
	static const char shift[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()\r\x1b\b\t _+{}|~:\"~<>?";
	*mods = 0;
	if (ch == '\n')
		ch = '\r';
	if (ch == 0x7F) { *usage = 0x4C; return 1; }                  /* Delete */
	if (ch >= 1 && ch <= 26 && ch != '\r' && ch != '\b' && ch != '\t') {
		*mods = 0x01;                                                /* Ctrl+letter */
		*usage = (uint8_t)(0x04 + ch - 1);
		return 1;
	}
	const char *p = memchr(plain, ch, sizeof plain - 1);
	if (p) { *usage = (uint8_t)(0x04 + (p - plain)); return 1; }
	p = memchr(shift, ch, sizeof shift - 1);
	if (p) { *mods = 0x02; *usage = (uint8_t)(0x04 + (p - shift)); return 1; }
	return 0;
}

void simcard_type_ascii(simcard_t *c, uint8_t ch, uint32_t now_ms)
{
	uint8_t mods, usage;
	if (!c->io || !ascii_to_hid(ch, &mods, &usage))
		return;
	uint8_t down[8] = {mods, 0, usage}, up[8] = {0};
	io_report(c->io, down, now_ms);
	io_report(c->io, up, now_ms);
}
