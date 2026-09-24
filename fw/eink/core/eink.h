/*
 * CUPC/8 e-ink graphics card core (doc/hardware/eink-card.md).
 *
 * Hardware-independent, like fw/gpu/core: the RP2040 build, the host tests
 * and the simulator all use it. It is the graphics card's interpreter
 * (fw/gpu/core/gpu.c, unchanged for TEXT and GFX) with an extension for the
 * e-paper commands (INFO, REFRESH, AUTO, EPD_STATUS) and the native 4-grey
 * mode 2, plus the panel loop: the refresh policy, the rasteriser to the
 * panel (the ink rule, an ordered dither) and the UC8179's command
 * sequences (uc8179.h), as a state machine that never waits: eink_poll()
 * does a little and returns, so the slot SPI is never kept waiting.
 *
 * Build with -DGPU_GFX_BYTES=96000 (mode 2's buffer shares the GFX buffer).
 */
#ifndef EINK_CORE_H
#define EINK_CORE_H

#include <stdbool.h>
#include <stdint.h>

#include "gpu.h"
#include "uc8179.h"

#define EINK_MAX_W      800
#define EINK_H          480
#define EINK_MODE2_BYTES (EINK_MAX_W / 4 * EINK_H)
_Static_assert(GPU_GFX_BYTES >= EINK_MODE2_BYTES, "build the e-ink card with -DGPU_GFX_BYTES=96000");

enum { EINK_MODE_NATIVE = 2 };

/* REFRESH m */
enum { EINK_PARTIAL = 0, EINK_FAST = 1, EINK_CLEAN = 2, EINK_GREY = 3 };

/* the panel: the controller is the UC8179 on both */
typedef struct {
	uint16_t w, h;
	const char *name;
} eink_panel_t;

extern const eink_panel_t eink_panel_583;       /* Good Display GDEY0583T81, 648 x 480 */
extern const eink_panel_t eink_panel_750;       /* Good Display GDEY075T7, 800 x 480 */

/* the policy's fixed times (eink-card.md, "Refresh policy") */
#define EINK_CAP_US        1000000u     /* changes wait at most this long under continuous output */
#define EINK_FULL_QUIET_US 2000000u     /* the ghost-clearing full refresh waits for this much quiet */
#define EINK_SLEEP_US      10000000u    /* the controller goes to deep sleep after this long unused */
#define EINK_BUSY_TIMEOUT_US 10000000u  /* a BUSY this long means the panel is not answering */

typedef struct eink {
	gpu_t gpu;                              /* first: TEXT and GFX are the graphics card's */
	const eink_panel_t *panel;
	epd_bus_t bus;
	uint32_t now;                           /* us, as of the last eink_poll() */
	uint32_t vsync_acc;

	/* the refresh policy */
	bool auto_on;
	uint8_t idle10, full_after;
	uint32_t change_seq, shown_seq, refresh_seq;
	uint32_t last_change, unshown_since;
	bool unshown;                           /* a change since the running refresh took its picture */
	bool full_next;                         /* CLS, FF, MODE, SOFT_RESET: the next one is a full refresh */
	bool first_clean;                       /* power-on: the first is a clean full refresh */
	uint8_t partials;                       /* partial refreshes since the last full one */
	int explicit_req;                       /* a REFRESH m waiting to run (-1: none) */
	bool explicit_run;                      /* the running refresh is one; it releases the hold */

	/* the panel loop */
	int step;
	int panel_state;                        /* off, asleep (needs a reset), ready */
	int kind;                               /* the running refresh */
	int y0, y1, row;
	uint32_t t0, last_panel;

	/* counters, for tests and SWD */
	uint32_t refreshes[4];                  /* by kind */
	uint32_t panel_errors;                  /* BUSY timeouts */
	uint32_t resets;                        /* hardware resets of the controller */

	uint8_t rowbuf[EINK_MAX_W / 8];
	uint8_t lum[EINK_MAX_W];                /* a row's brightness (not on the RP2040's small stack) */
	uint8_t shown[EINK_MAX_W / 8 * EINK_H]; /* the picture on the panel, 1 bit, 1 = white */
} eink_t;

void eink_init(eink_t *e, const eink_panel_t *panel, const epd_bus_t *bus);
/* the panel loop and the 60 Hz VSYNC_COUNT; call it often (every loop) */
void eink_poll(eink_t *e, uint32_t now_us);
/* the panel is refreshing (the REFRESH LED) */
bool eink_refreshing(const eink_t *e);
/* EPD_STATUS */
void eink_status(const eink_t *e, uint8_t out[3]);

/* The picture as the panel would show it now, w x h, one byte a pixel
 * (0 black ... 255 white): a 1-bit refresh (dithered) or a greyscale one
 * (4 levels) */
void eink_render(eink_t *e, uint8_t *grey, bool grey4);
/* one row of the 1-bit picture, as sent to the panel (MSB left, 1 = white) */
void eink_render_row(eink_t *e, int y, uint8_t *out);

/* the ink rule's brightness: 0.299 R + 0.587 G + 0.114 B of an RGB565 colour */
uint8_t eink_lum(uint16_t rgb565);

#endif
