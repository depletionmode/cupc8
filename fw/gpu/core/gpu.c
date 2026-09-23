#include "gpu.h"

#include <string.h>

#include "font8x8_cp437.h"

#define GPU_FW_MAJOR 1
#define GPU_FW_MINOR 0

/* ------------------------------------------------------------------ palette */

static uint16_t rgb565(int r, int g, int b)
{
	return (uint16_t)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

static void palette_default(gpu_t *g)
{
	static const uint8_t vga[16][3] = {
		{0, 0, 0}, {0, 0, 170}, {0, 170, 0}, {0, 170, 170},
		{170, 0, 0}, {170, 0, 170}, {170, 85, 0}, {170, 170, 170},
		{85, 85, 85}, {85, 85, 255}, {85, 255, 85}, {85, 255, 255},
		{255, 85, 85}, {255, 85, 255}, {255, 255, 85}, {255, 255, 255},
	};
	static const uint8_t level[6] = {0, 95, 135, 175, 215, 255};
	for (int i = 0; i < 16; i++)
		g->palette[i] = rgb565(vga[i][0], vga[i][1], vga[i][2]);
	for (int i = 0; i < 216; i++)
		g->palette[16 + i] = rgb565(level[i / 36], level[(i / 6) % 6], level[i % 6]);
	for (int i = 0; i < 24; i++)
		g->palette[232 + i] = rgb565(8 + 10 * i, 8 + 10 * i, 8 + 10 * i);
}

static uint32_t rgb888(uint16_t c)
{
	uint32_t r = (c >> 11) & 0x1F, gr = (c >> 5) & 0x3F, b = c & 0x1F;
	return ((r * 255 / 31) << 16) | ((gr * 255 / 63) << 8) | (b * 255 / 31);
}

/* TEXT shows its 16 colours at RGB222, as the card's 2bpp font encoder does
 * (exact for the VGA defaults) */
static uint32_t rgb222(uint16_t c)
{
	uint32_t r = (c >> 14) & 3, gr = (c >> 9) & 3, b = (c >> 3) & 3;
	return ((r * 0x55) << 16) | ((gr * 0x55) << 8) | (b * 0x55);
}

/* ------------------------------------------------------------------ text */

static void text_clear_rows(gpu_t *g, int from, int to, uint8_t attr)
{
	for (int y = from; y < to; y++)
		for (int x = 0; x < GPU_TEXT_COLS; x++)
			g->text[y][x] = (gpu_cell_t){' ', attr};
}

static void text_scroll(gpu_t *g, int n)
{
	if (n <= 0)
		return;
	if (n > GPU_TEXT_ROWS)
		n = GPU_TEXT_ROWS;
	memmove(&g->text[0], &g->text[n], sizeof(gpu_cell_t) * GPU_TEXT_COLS * (GPU_TEXT_ROWS - n));
	text_clear_rows(g, GPU_TEXT_ROWS - n, GPU_TEXT_ROWS, g->attr);
}

static void text_newline(gpu_t *g)
{
	g->cx = 0;
	if (g->cy + 1 >= GPU_TEXT_ROWS)
		text_scroll(g, 1);
	else
		g->cy++;
}

static void text_putc(gpu_t *g, uint8_t ch)
{
	switch (ch) {
	case 0x08:
		if (g->cx > 0)
			g->cx--;
		break;
	case 0x09:
		g->cx = (uint8_t)((g->cx + 8) & ~7);
		if (g->cx >= GPU_TEXT_COLS)
			text_newline(g);
		break;
	case 0x0A:
		text_newline(g);
		break;
	case 0x0D:
		g->cx = 0;
		break;
	case 0x0C:
		text_clear_rows(g, 0, GPU_TEXT_ROWS, g->attr);
		g->cx = g->cy = 0;
		break;
	default:
		g->text[g->cy][g->cx] = (gpu_cell_t){ch, g->attr};
		if (++g->cx >= GPU_TEXT_COLS)
			text_newline(g);
		break;
	}
}

/* ------------------------------------------------------------------ graphics */

static void px(gpu_t *g, int x, int y, uint8_t c)
{
	if (x >= 0 && y >= 0 && x < GPU_GFX_W && y < GPU_GFX_H)
		g->gfx[y][x] = c;
}

static void fill_rect(gpu_t *g, int x, int y, int w, int h, uint8_t c)
{
	int x0 = x < 0 ? 0 : x, y0 = y < 0 ? 0 : y;
	int x1 = x + w > GPU_GFX_W ? GPU_GFX_W : x + w;
	int y1 = y + h > GPU_GFX_H ? GPU_GFX_H : y + h;
	for (int yy = y0; yy < y1; yy++)
		for (int xx = x0; xx < x1; xx++)
			g->gfx[yy][xx] = c;
}

static void line(gpu_t *g, int x0, int y0, int x1, int y1, uint8_t c)
{
	int dx = x1 > x0 ? x1 - x0 : x0 - x1, sx = x0 < x1 ? 1 : -1;
	int dy = y1 > y0 ? y0 - y1 : y1 - y0, sy = y0 < y1 ? 1 : -1;
	int err = dx + dy;
	for (;;) {
		px(g, x0, y0, c);
		if (x0 == x1 && y0 == y1)
			break;
		int e2 = 2 * err;
		if (e2 >= dy) { err += dy; x0 += sx; }
		if (e2 <= dx) { err += dx; y0 += sy; }
	}
}

static void glyph8(gpu_t *g, int x, int y, uint8_t ch, uint8_t fg, uint8_t bg)
{
	for (int r = 0; r < 8; r++)
		for (int b = 0; b < 8; b++) {
			if (g->font8[ch][r] & (0x80 >> b))
				px(g, x + b, y + r, fg);
			else if (bg != 0xFF)
				px(g, x + b, y + r, bg);
		}
}

/* ------------------------------------------------------------------ FIFO */

static uint32_t fifo_used(const gpu_t *g) { return g->head - g->tail; }

uint32_t gpu_fifo_free(const gpu_t *g)
{
	uint32_t used = fifo_used(g) + (g->card.selected ? g->cur_len + 2 : 0);
	return used >= GPU_FIFO_SIZE ? 0 : GPU_FIFO_SIZE - used;
}

static uint8_t fifo_at(const gpu_t *g, uint32_t i) { return g->fifo[i % GPU_FIFO_SIZE]; }

static void frame_begin(card_t *c)
{
	gpu_t *g = c->priv;
	g->cur_start = g->head + 2;             /* room for the length header */
	g->cur_len = 0;
	g->cur_bad = false;
}

static void frame_byte(card_t *c, uint8_t b)
{
	gpu_t *g = c->priv;
	if (fifo_used(g) + 2 + g->cur_len + 1 > GPU_FIFO_SIZE) {
		g->cur_bad = true;                  /* no room: the frame will be discarded */
		return;
	}
	g->fifo[(g->cur_start + g->cur_len) % GPU_FIFO_SIZE] = b;
	g->cur_len++;
}

static void frame_end(card_t *c)
{
	gpu_t *g = c->priv;
	if (g->cur_bad || g->cur_len == 0) {
		if (g->cur_bad)
			g->errors++;
		return;
	}
	g->fifo[g->head % GPU_FIFO_SIZE] = (uint8_t)g->cur_len;
	g->fifo[(g->head + 1) % GPU_FIFO_SIZE] = (uint8_t)(g->cur_len >> 8);
	g->head += 2 + g->cur_len;
	g->frame_seq++;
}

/* ------------------------------------------------------------------ commands */

static int arg_len(uint8_t op, const uint8_t *a, int avail)
{
	switch (op) {
	case 0x00: case 0x04: case 0x06: case 0x07: case 0x16: case 0x18: return 0;
	case 0x01: case 0x02: case 0x05: case 0x10: case 0x13: case 0x14: case 0x15: return 1;
	case 0x12: case 0x27: return 2;
	case 0x28: return 3;
	case 0x03: case 0x17: case 0x20: return 4;
	case 0x21: case 0x22: case 0x23: return 7;
	case 0x29: return 9;
	case 0x19: return 17;
	case 0x11: return avail >= 1 ? 1 + a[0] : 1;
	case 0x24: return avail >= 5 ? 5 + a[3] * a[4] : 5;
	case 0x25: return avail >= 7 ? 7 + ((a[3] + 7) / 8) * a[4] : 7;
	case 0x26: return avail >= 6 ? 6 + a[5] : 6;
	default: return -1;
	}
}

static int s16(const uint8_t *p) { return (int16_t)(p[0] | (p[1] << 8)); }
static int u16(const uint8_t *p) { return p[0] | (p[1] << 8); }

static void execute(gpu_t *g, const uint8_t *f, int len, bool respond)
{
	uint8_t op = f[0];
	const uint8_t *a = f + 1;
	int avail = len - 1;
	int need = arg_len(op, a, avail);
	uint8_t r[2];

	if (need < 0 || avail < need) {
		g->errors++;                        /* unknown opcode or short frame */
		return;
	}
	switch (op) {
	case 0x00: break;
	case 0x01:
		g->mode = a[0] ? GPU_MODE_GFX : GPU_MODE_TEXT;
		if (g->mode == GPU_MODE_TEXT) {
			text_clear_rows(g, 0, GPU_TEXT_ROWS, g->attr);
			g->cx = g->cy = 0;
		} else {
			memset(g->gfx, 0, sizeof g->gfx);
		}
		break;
	case 0x02:
		if (g->mode == GPU_MODE_TEXT) {
			text_clear_rows(g, 0, GPU_TEXT_ROWS, a[0]);
			g->cx = g->cy = 0;
		} else {
			memset(g->gfx, a[0], sizeof g->gfx);
		}
		break;
	case 0x03: g->palette[a[0]] = rgb565(a[1], a[2], a[3]); break;
	case 0x04: palette_default(g); break;
	case 0x05: g->fence_tag = a[0]; g->fence_irq = true; break;
	case 0x06:
		g->fence_irq = false;
		if (respond) card_respond(&g->card, &g->fence_tag, 1);
		break;
	case 0x07: if (respond) card_respond(&g->card, &g->vsync_count, 1); break;

	case 0x10: text_putc(g, a[0]); break;
	case 0x11: for (int i = 0; i < a[0]; i++) text_putc(g, a[1 + i]); break;
	case 0x12:
		g->cx = a[0] < GPU_TEXT_COLS ? a[0] : GPU_TEXT_COLS - 1;
		g->cy = a[1] < GPU_TEXT_ROWS ? a[1] : GPU_TEXT_ROWS - 1;
		break;
	case 0x13: g->attr = a[0]; break;
	case 0x14: g->cursor = a[0] <= 2 ? a[0] : 0; break;
	case 0x15: text_scroll(g, a[0]); break;
	case 0x16:
		for (int x = g->cx; x < GPU_TEXT_COLS; x++)
			g->text[g->cy][x] = (gpu_cell_t){' ', g->attr};
		break;
	case 0x17:
		if (a[0] < GPU_TEXT_COLS && a[1] < GPU_TEXT_ROWS)
			g->text[a[1]][a[0]] = (gpu_cell_t){a[2], a[3]};
		break;
	case 0x18:
		r[0] = g->cx; r[1] = g->cy;
		if (respond) card_respond(&g->card, r, 2);
		break;
	case 0x19: memcpy(g->font16[a[0]], a + 1, 16); break;

	case 0x20: px(g, s16(a), a[2], a[3]); break;
	case 0x21: fill_rect(g, s16(a), a[2], u16(a + 3), a[5], a[6]); break;
	case 0x22: {
		int x = s16(a), y = a[2], w = u16(a + 3), h = a[5];
		if (w > 0 && h > 0) {
			fill_rect(g, x, y, w, 1, a[6]);
			fill_rect(g, x, y + h - 1, w, 1, a[6]);
			fill_rect(g, x, y, 1, h, a[6]);
			fill_rect(g, x + w - 1, y, 1, h, a[6]);
		}
		break;
	}
	case 0x23: line(g, s16(a), a[2], s16(a + 3), a[5], a[6]); break;
	case 0x24: {
		int x = s16(a), y = a[2], w = a[3], h = a[4];
		for (int j = 0; j < h; j++)
			for (int i = 0; i < w; i++)
				px(g, x + i, y + j, a[5 + j * w + i]);
		break;
	}
	case 0x25: {
		/* x16, y8, w8, h8, fg, bg, then ceil(w/8) bytes per row, MSB = left */
		int x = s16(a), y = a[2], w = a[3], h = a[4], stride = (w + 7) / 8;
		uint8_t fg = a[5], bg = a[6];
		for (int j = 0; j < h; j++)
			for (int i = 0; i < w; i++) {
				if (a[7 + j * stride + i / 8] & (0x80 >> (i % 8)))
					px(g, x + i, y + j, fg);
				else if (bg != 0xFF)
					px(g, x + i, y + j, bg);
			}
		break;
	}
	case 0x26:
		for (int i = 0; i < a[5]; i++)
			glyph8(g, s16(a) + 8 * i, a[2], a[6 + i], a[3], a[4]);
		break;
	case 0x27: {
		int dy = (int8_t)a[0];
		uint8_t c = a[1];
		if (dy > 0) {
			if (dy > GPU_GFX_H) dy = GPU_GFX_H;
			memmove(&g->gfx[0], &g->gfx[dy], (size_t)GPU_GFX_W * (GPU_GFX_H - dy));
			memset(&g->gfx[GPU_GFX_H - dy], c, (size_t)GPU_GFX_W * dy);
		} else if (dy < 0) {
			dy = -dy;
			if (dy > GPU_GFX_H) dy = GPU_GFX_H;
			memmove(&g->gfx[dy], &g->gfx[0], (size_t)GPU_GFX_W * (GPU_GFX_H - dy));
			memset(&g->gfx[0], c, (size_t)GPU_GFX_W * dy);
		}
		break;
	}
	case 0x28: {
		int x = s16(a), y = a[2];
		r[0] = (x >= 0 && x < GPU_GFX_W && y < GPU_GFX_H) ? g->gfx[y][x] : 0;
		if (respond) card_respond(&g->card, r, 1);
		break;
	}
	case 0x29: memcpy(g->font8[a[0]], a + 1, 8); break;
	}
}

int gpu_run(gpu_t *g, int max_frames)
{
	int n = 0;
	while (n < max_frames && fifo_used(g) >= 2) {
		uint32_t len = fifo_at(g, g->tail) | (fifo_at(g, g->tail + 1) << 8);
		for (uint32_t i = 0; i < len; i++)
			g->cmd[i] = fifo_at(g, g->tail + 2 + i);
		g->tail += 2 + len;
		g->exec_seq++;
		/* only the most recent command's response is kept (slot.md) */
		execute(g, g->cmd, (int)len, g->exec_seq == g->frame_seq);
		n++;
	}
	return n;
}

/* ------------------------------------------------------------------ card glue */

static uint8_t status(card_t *c)
{
	gpu_t *g = c->priv;
	uint32_t units = gpu_fifo_free(g) / 64;
	return (uint8_t)(units > 127 ? 127 : units);
}

static bool irq(card_t *c)
{
	return ((gpu_t *)c->priv)->fence_irq;
}

static void soft_reset(card_t *c)
{
	gpu_reset(c->priv);
}

static const card_ops_t gpu_ops = {
	.type = CARD_TYPE_GPU, .fw_major = GPU_FW_MAJOR, .fw_minor = GPU_FW_MINOR,
	.status = status,
	.frame_begin = frame_begin, .frame_byte = frame_byte, .frame_end = frame_end,
	.soft_reset = soft_reset,
	.irq = irq,
};

void gpu_reset(gpu_t *g)
{
	g->mode = GPU_MODE_TEXT;
	g->attr = 0x07;
	g->cursor = 1;
	g->cx = g->cy = 0;
	text_clear_rows(g, 0, GPU_TEXT_ROWS, g->attr);
	memset(g->gfx, 0, sizeof g->gfx);
	palette_default(g);
	for (int ch = 0; ch < 256; ch++) {
		memcpy(g->font8[ch], font8x8_cp437[ch], 8);
		for (int r = 0; r < 16; r++)
			g->font16[ch][r] = font8x8_cp437[ch][r / 2];   /* each row doubled */
	}
	g->head = g->tail = 0;
	g->frame_seq = g->exec_seq = 0;
	g->fence_tag = 0;
	g->fence_irq = false;
	g->errors = 0;
}

void gpu_init(gpu_t *g)
{
	memset(g, 0, sizeof *g);
	card_init(&g->card, &gpu_ops, g);
	gpu_reset(g);
}

void gpu_vsync(gpu_t *g)
{
	g->vsync_count++;
}

/* ------------------------------------------------------------------ render */

void gpu_render(const gpu_t *g, uint32_t *rgb)
{
	if (g->mode == GPU_MODE_GFX) {
		for (int y = 0; y < GPU_OUT_H; y++)
			for (int x = 0; x < GPU_OUT_W; x++)
				rgb[y * GPU_OUT_W + x] = rgb888(g->palette[g->gfx[y / 2][x / 2]]);
		return;
	}
	bool cursor_on = g->cursor != 0 && (g->vsync_count / 15) % 2 == 0;
	for (int row = 0; row < GPU_TEXT_ROWS; row++)
		for (int col = 0; col < GPU_TEXT_COLS; col++) {
			gpu_cell_t cell = g->text[row][col];
			uint32_t fg = rgb222(g->palette[cell.attr & 0x0F]);
			uint32_t bg = rgb222(g->palette[cell.attr >> 4]);
			bool here = cursor_on && row == g->cy && col == g->cx;
			for (int r = 0; r < 16; r++) {
				uint8_t bits = g->font16[cell.ch][r];
				if (here && (g->cursor == 2 || r >= 14))
					bits = (uint8_t)~bits;
				uint32_t *out = rgb + (row * 16 + r) * GPU_OUT_W + col * 8;
				for (int b = 0; b < 8; b++)
					out[b] = (bits & (0x80 >> b)) ? fg : bg;
			}
		}
}
