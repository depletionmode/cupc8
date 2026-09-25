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
/* the GFX buffer's size: a card built on this core may make it bigger for a
 * mode of its own that shares it (the e-ink card's native mode 2, 96,000
 * bytes: fw/eink/core/eink.h). Every file of one build must agree. */
#ifndef GPU_GFX_BYTES
#define GPU_GFX_BYTES (GPU_GFX_W * GPU_GFX_H)
#endif

enum { GPU_MODE_TEXT = 0, GPU_MODE_GFX = 1 };

typedef struct {
	uint8_t ch, attr;
} gpu_cell_t;

struct gpu;

/* An extension: a card that runs this core with commands of its own (the
 * e-ink card, fw/eink/core). It sees every command before the core does. */
typedef struct gpu_ext {
	/* true: the extension executed the command (or rejected it), and the
	 * core does nothing more with it */
	bool (*command)(struct gpu *g, const uint8_t *f, int len, bool respond);
	/* after the core's own power-on state (SOFT_RESET) */
	void (*reset)(struct gpu *g);
} gpu_ext_t;

typedef struct gpu {
	card_t card;
	const gpu_ext_t *ext;                  /* optional */
	/* the extension holds execution (the e-ink card's REFRESH waits for the
	 * panel); commands keep queuing in the FIFO meanwhile */
	volatile bool hold;

	uint8_t mode;
	gpu_cell_t text[GPU_TEXT_ROWS][GPU_TEXT_COLS];
	uint8_t cx, cy, attr, cursor;
	union {
		uint8_t gfx[GPU_GFX_H][GPU_GFX_W] __attribute__((aligned(4)));   /* word reads on the card */
		uint8_t gfx_bytes[GPU_GFX_BYTES];      /* an extension's own mode (mode 2) */
	};
	uint16_t palette[256];                 /* RGB565 */
	uint8_t font16[256][16];               /* TEXT glyphs */
	uint8_t font8[256][8];                 /* TEXT8 glyphs */

	/* command FIFO: frames stored as [len lo][len hi][bytes...] */
	uint8_t fifo[GPU_FIFO_SIZE];
	uint32_t head, tail;                   /* free-running byte counters */
	uint32_t cur_start, cur_len;           /* frame being received */
	bool cur_bad;
	uint32_t frame_seq, exec_seq;          /* commands received / executed */
	uint8_t cmd[CARD_FRAME_MAX];           /* the command gpu_run() is executing (not on
	                                          the stack: the RP2040's is 2 KB) */

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
