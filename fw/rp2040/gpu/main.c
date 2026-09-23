/*
 * Graphics card firmware (doc/hardware/gpu-protocol.md): 640x480 DVI from
 * PicoDVI on an RP2040 at 252 MHz, the TMDS bit clock.
 *
 * Core 0: the slot SPI slave (fw/rp2040/common/slotspi.c), command execution
 * (fw/gpu/core/gpu.c, the same core the host tests and simulator use), the
 * frame count, and PicoDVI's DMA interrupt.
 * Core 1: renders every scanline from the GPU state straight to TMDS:
 *   TEXT: tmds_encode_font_2bpp, 80x30 cells, fg/bg in RGB222
 *   GFX:  the 320-pixel line through the palette to RGB565, pixel-doubled
 */
#include <string.h>

#include "dvi.h"
#include "dvi_serialiser.h"
#include "gpu.h"
#include "hardware/clocks.h"
#include "hardware/irq.h"
#include "hardware/structs/bus_ctrl.h"
#include "hardware/vreg.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pins.h"
#include "slotspi.h"
#include "tmds_encode.h"
#include "tmds_encode_font_2bpp.h"

#define DVI_TIMING dvi_timing_640x480p_60hz
#define WORDS_PER_LANE (GPU_OUT_W / DVI_SYMBOLS_PER_WORD)
#define COLOUR_WORDS (GPU_TEXT_COLS * 4 / 32)          /* one plane of one text row */

/* our TMDS pins (hw/pins.yaml): lanes blue, green, red; GPIO n is P */
static const struct dvi_serialiser_cfg gpu_dvi_cfg = {
	.pio = pio0,
	.sm_tmds = { 0, 1, 2 },
	.pins_tmds = { PIN_TMDS_D00, PIN_TMDS_D10, PIN_TMDS_D20 },
	.pins_clk = PIN_TMDS_CLK0,
	.invert_diffpairs = false,
};

static gpu_t gpu;
static struct dvi_inst dvi0;
static volatile uint32_t frames;               /* frames finished by core 1 */

/* core 1's scanline state */
static uint8_t font_lines[16][256];            /* font16 by scanline: [line][char] */
static uint16_t attr_nibbles[256];             /* attr -> fg|bg<<2 for each plane, 4 bits each */
/* the text screen as core 1 shows it, snapshotted in each vertical blank */
static uint8_t frame_chars[GPU_TEXT_ROWS][GPU_TEXT_COLS];
static uint32_t frame_colour[GPU_TEXT_ROWS][3 * COLOUR_WORDS];
static uint32_t cursor_colour[3 * COLOUR_WORDS];       /* the cursor's row, its cell swapped */
static uint16_t line565[GPU_GFX_W];

/* TEXT colours are the palette's first 16 entries in RGB222: blue in bits
 * 1:0 (lane 0), green 3:2, red 5:4. The VGA defaults are exact. */
static uint32_t rgb222(uint16_t c)
{
	return (uint32_t)(((c & 0x1f) >> 3) | (((c >> 5) & 0x3f) >> 4) << 2 | ((c >> 11) >> 3) << 4);
}

static uint8_t rev8(uint8_t b)
{
	b = (uint8_t)((b & 0xf0) >> 4 | (b & 0x0f) << 4);
	b = (uint8_t)((b & 0xcc) >> 2 | (b & 0x33) << 2);
	return (uint8_t)((b & 0xaa) >> 1 | (b & 0x55) << 1);
}

static bool cursor_on(void)
{
	return gpu.cursor != 0 && (gpu.vsync_count / 15) % 2 == 0;     /* as gpu_render() */
}

/* once a frame: what each attribute byte looks like in the three planes */
static void make_attr_nibbles(void)
{
	uint32_t c[16];
	for (int i = 0; i < 16; i++)
		c[i] = rgb222(gpu.palette[i]);
	for (int a = 0; a < 256; a++) {
		uint32_t fg = c[a & 15], bg = c[a >> 4], n = 0;
		for (int plane = 0; plane < 3; plane++)
			n |= (((fg >> (2 * plane)) & 3) | ((bg >> (2 * plane)) & 3) << 2) << (4 * plane);
		attr_nibbles[a] = (uint16_t)n;
	}
}

/* Build text row `row` for this frame. All 30 are built in the vertical
 * blank, so a scanline only pays for its three TMDS encodes. */
static void __not_in_flash_func(build_row)(int row)
{
	uint32_t *colour = frame_colour[row];
	memset(colour, 0, 3 * COLOUR_WORDS * sizeof(uint32_t));
	for (int col = 0; col < GPU_TEXT_COLS; col++) {
		gpu_cell_t cell = gpu.text[row][col];
		frame_chars[row][col] = cell.ch;
		uint32_t nib = attr_nibbles[cell.attr];
		int w = col / 8, sh = (col % 8) * 4;
		colour[w] |= (nib & 0xf) << sh;
		colour[COLOUR_WORDS + w] |= ((nib >> 4) & 0xf) << sh;
		colour[2 * COLOUR_WORDS + w] |= ((nib >> 8) & 0xf) << sh;
	}
}

/* the cursor inverts its cell: the same row with that cell's fg and bg swapped */
static void make_cursor_row(int row, int col)
{
	memcpy(cursor_colour, frame_colour[row], sizeof cursor_colour);
	int w = col / 8, sh = (col % 8) * 4;
	for (int plane = 0; plane < 3; plane++) {
		uint32_t *p = &cursor_colour[plane * COLOUR_WORDS + w];
		uint32_t v = (*p >> sh) & 0xf;
		*p = (*p & ~(0xfu << sh)) | ((v >> 2) | (v & 3) << 2) << sh;
	}
}

/* 320 palette lookups, two pixels per store */
static void __not_in_flash_func(gfx_line)(const uint8_t *src)
{
	const uint16_t *pal = gpu.palette;
	const uint32_t *in = __builtin_assume_aligned(src, 4);  /* gfx rows are word-aligned */
	uint32_t *out = (uint32_t *)line565;
	for (int i = 0; i < GPU_GFX_W / 4; i++) {
		uint32_t four = in[i];
		out[2 * i] = pal[four & 0xff] | (uint32_t)pal[(four >> 8) & 0xff] << 16;
		out[2 * i + 1] = pal[(four >> 16) & 0xff] | (uint32_t)pal[four >> 24] << 16;
	}
}

static void __not_in_flash_func(core1_main)(void)
{
	uint32_t *prev = NULL;
	for (;;) {
		/* vertical blank: pick up font and palette changes, build row 0 */
		/* PicoDVI's font encoder takes the leftmost pixel from bit 0; our
		 * glyphs have it in bit 7 */
		for (int line = 0; line < 16; line++)
			for (int ch = 0; ch < 256; ch++)
				font_lines[line][ch] = rev8(gpu.font16[ch][line]);
		make_attr_nibbles();
		bool gfx = gpu.mode == GPU_MODE_GFX;
		bool cursor = cursor_on();
		int cursor_row = gpu.cy, cursor_col = gpu.cx;
		if (!gfx) {
			for (int row = 0; row < GPU_TEXT_ROWS; row++)
				build_row(row);
			if (cursor)
				make_cursor_row(cursor_row, cursor_col);
		}
		for (int y = 0; y < GPU_OUT_H; y++) {
			uint32_t *tmds;
			queue_remove_blocking_u32(&dvi0.q_tmds_free, &tmds);
			if (gfx) {
				if (y & 1) {
					/* the second copy of a 320x240 line: the same symbols */
					memcpy(tmds, prev, 3 * WORDS_PER_LANE * sizeof(uint32_t));
				} else {
					gfx_line(gpu.gfx[y / 2]);
					const uint32_t *pix = (const uint32_t *)line565;
					tmds_encode_data_channel_16bpp(pix, tmds + 0 * WORDS_PER_LANE, GPU_GFX_W, DVI_16BPP_BLUE_MSB, DVI_16BPP_BLUE_LSB);
					tmds_encode_data_channel_16bpp(pix, tmds + 1 * WORDS_PER_LANE, GPU_GFX_W, DVI_16BPP_GREEN_MSB, DVI_16BPP_GREEN_LSB);
					tmds_encode_data_channel_16bpp(pix, tmds + 2 * WORDS_PER_LANE, GPU_GFX_W, DVI_16BPP_RED_MSB, DVI_16BPP_RED_LSB);
				}
				prev = tmds;
			} else {
				int row = y / 16, line = y % 16;
				bool inv = cursor && row == cursor_row && (gpu.cursor == 2 || line >= 14);
				const uint32_t *colour = inv ? cursor_colour : frame_colour[row];
				for (int plane = 0; plane < 3; plane++)
					tmds_encode_font_2bpp(frame_chars[row], &colour[plane * COLOUR_WORDS],
							      tmds + plane * WORDS_PER_LANE, GPU_OUT_W, font_lines[line]);
			}
			queue_add_blocking_u32(&dvi0.q_tmds_valid, &tmds);
		}
		frames++;
	}
}

static uint8_t status(card_t *c, uint32_t queued_bytes, uint32_t queued_frames)
{
	(void)c;
	/* FREE counts what is still in the SPI ring as used: every queued byte
	 * plus the FIFO's 2-byte header per frame */
	uint32_t free = gpu_fifo_free(&gpu), used = queued_bytes + 2 * queued_frames;
	uint32_t units = free > used ? (free - used) / 64 : 0;
	return (uint8_t)(units > 127 ? 127 : units);
}

int main(void)
{
	vreg_set_voltage(VREG_VOLTAGE_1_20);
	sleep_ms(10);
	set_sys_clock_khz(DVI_TIMING.bit_clk_khz, true);

	gpu_init(&gpu);
	dvi0.timing = &DVI_TIMING;
	dvi0.ser_cfg = gpu_dvi_cfg;
	dvi_init(&dvi0, next_striped_spin_lock_num(), next_striped_spin_lock_num());
	hw_set_bits(&bus_ctrl_hw->priority, BUSCTRL_BUS_PRIORITY_PROC1_BITS);
	multicore_launch_core1(core1_main);
	/* the DVI DMA interrupt runs here, so core 1 only encodes: it has ~25 us
	 * per scanline to run, and costs ~400 cycles a line */
	dvi_register_irqs_this_core(&dvi0, DMA_IRQ_0);
	/* the top priority: it must set up the next scanline's DMA within a
	 * porch (~2 us), or the lanes' control blocks get mixed up */
	irq_set_priority(DMA_IRQ_0, 0);
	dvi_start(&dvi0);

	gpio_init(PIN_LED_ACT);
	gpio_set_dir(PIN_LED_ACT, true);
	slotspi_init(&gpu.card, status);

	uint32_t seen = 0;
	for (;;) {
		slotspi_poll();
		slotspi_busy(true);                     /* commands may set a response */
		int ran = gpu_run(&gpu, 8);
		slotspi_busy(false);
		if (ran)
			slotspi_refresh();              /* more FIFO space, maybe a response */
		gpio_put(PIN_LED_ACT, ran != 0);
		while (seen != frames) {
			seen++;
			gpu_vsync(&gpu);
		}
		slotspi_update_irq();
	}
}
