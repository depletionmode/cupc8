#include "simcards.h"

#include <stdlib.h>
#include <string.h>

#include "cardproto.h"
#include "gpu.h"
#include "iocard.h"

struct simcard {
	int type;
	card_t *card;
	gpu_t *gpu;
	iocard_t *io;
	uint32_t last_vsync_ms;
};

simcard_t *simcard_new(int type)
{
	simcard_t *c = calloc(1, sizeof *c);
	if (!c)
		return 0;
	c->type = type;
	if (type == CARD_TYPE_GPU) {
		c->gpu = malloc(sizeof *c->gpu);
		gpu_init(c->gpu);
		c->card = &c->gpu->card;
	} else if (type == CARD_TYPE_IO) {
		c->io = malloc(sizeof *c->io);
		io_init(c->io);
		io_connected(c->io, 1);
		c->card = &c->io->card;
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
	free(c->gpu);
	free(c->io);
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
	if (c->gpu) {
		gpu_run(c->gpu, 1 << 20);
		while (now_ms - c->last_vsync_ms >= 17) {       /* ~60 Hz */
			gpu_vsync(c->gpu);
			c->last_vsync_ms += 17;
		}
	}
	if (c->io)
		io_poll(c->io, now_ms);
}

void simcard_render(simcard_t *c, uint32_t *rgb)
{
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
