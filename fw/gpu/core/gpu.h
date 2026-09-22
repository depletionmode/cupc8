/*
 * CUPC/8 graphics card core (doc/hardware/gpu-protocol.md).
 *
 * Hardware-independent: the RP2040 build, the host tests and the simulator
 * all use this. The SPI side streams frames into the command FIFO through
 * the common card engine (fw/common/cardproto.h); gpu_run() executes them.
 * gpu_render() produces a 640x480 RGB frame (tests and simulator); the
 * RP2040 build renders scanlines itself from the same state.
 */
#ifndef GPU_H
#define GPU_H

#include <stdbool.h>
#include <stdint.h>

#include "cardproto.h"

#define GPU_TEXT_COLS 80
#define GPU_TEXT_ROWS 30
#define GPU_GFX_W     320
#define GPU_GFX_H     240
#define GPU_OUT_W     640
#define GPU_OUT_H     480
#define GPU_FIFO_SIZE 8192

enum { GPU_MODE_TEXT = 0, GPU_MODE_GFX = 1 };

typedef struct {
	uint8_t ch, attr;
} gpu_cell_t;

typedef struct gpu {
	card_t card;

	uint8_t mode;
	gpu_cell_t text[GPU_TEXT_ROWS][GPU_TEXT_COLS];
	uint8_t cx, cy, attr, cursor;
	uint8_t gfx[GPU_GFX_H][GPU_GFX_W];
	uint16_t palette[256];                 /* RGB565 */
	uint8_t font16[256][16];               /* TEXT glyphs */
	uint8_t font8[256][8];                 /* TEXT8 glyphs */

	/* command FIFO: frames stored as [len lo][len hi][bytes...] */
	uint8_t fifo[GPU_FIFO_SIZE];
	uint32_t head, tail;                   /* free-running byte counters */
	uint32_t cur_start, cur_len;           /* frame being received */
	bool cur_bad;
	uint32_t frame_seq, exec_seq;          /* commands received / executed */

	uint8_t fence_tag;
	bool fence_irq;
	uint8_t vsync_count;
	uint32_t errors;
} gpu_t;

void gpu_init(gpu_t *g);
void gpu_reset(gpu_t *g);              /* power-on state (SOFT_RESET) */
int gpu_run(gpu_t *g, int max_frames); /* execute queued commands; returns how many */
void gpu_vsync(gpu_t *g);              /* one video frame elapsed */
uint32_t gpu_fifo_free(const gpu_t *g);
void gpu_render(const gpu_t *g, uint32_t *rgb);   /* 640x480, 0x00RRGGBB */

#endif
