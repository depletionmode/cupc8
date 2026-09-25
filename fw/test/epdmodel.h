/*
 * A model of the UltraChip UC8179 e-paper controller and its panel, driven
 * at its pins: SPI bytes with DC, RST_N, the module's PWR, and BUSY_N out.
 * One model for the host tests (fw/test/test_eink.c) and the native
 * emulator (emu/machine/einkpanel.cpp, on the e-ink card's SPI1).
 *
 * From the UC8179c datasheet (UltraChip, rev 0.6, 2019):
 * - commands and their parameter counts: "Command table", p.8-11;
 * - KW mode, the OLD (DTM1) and NEW (DTM2) pictures, the LUT each pixel's
 *   {NEW, OLD} pair selects under DDX: CDI, p.27-28;
 * - the resolution and the partial window: TRES p.31, PTL/PTIN/PTOUT p.33;
 * - BUSY_N low while a command that flags it runs, and every other write
 *   command ignored meanwhile: "BUSY_N signal", p.46;
 * - RST_N low >= 50 us (p.6), and commands ignored for 1 ms after it
 *   rises (p.43); deep sleep left only by RST_N (p.17, p.52).
 * The panel's OTP waveforms (what each LUT does to a pixel, and how long it
 * takes) are the panel vendors' (eink-card.md, "Panel controller"): the
 * full ones drive every pixel to its NEW colour, the 4-grey one gives the
 * four LUTs four greys, and the partial one moves only the pixels whose NEW
 * differs from their OLD, so a wrong OLD leaves a pixel wrong on the glass.
 *
 * The model is strict where the chip is silent: anything the chip would
 * ignore or get wrong (a command while BUSY, a refresh with the booster
 * off, too much or too little pixel data, a command in deep sleep or during
 * reset) is counted in `errors`, with the first one described in `error`.
 * The glass changes only when a refresh completes, as on the real panel.
 */
#ifndef EPDMODEL_H
#define EPDMODEL_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
	int w, h;                   /* the glass: 648 x 480 (5.83") or 800 x 480 (7.5") */
	bool pwr_pin;               /* the module's power follows PWR (Waveshare HAT); false: always on */
	double time_scale;          /* every busy time x this (1 = the vendors' figures) */
	/* busy times, us (GDEY0583T81: full 3 s, fast 1.5 s, partial 0.3 s, 4-grey 2 s) */
	uint32_t pon_us, pof_us, dslp_us, clean_us, fast_us, grey_us, partial_us;
	uint32_t busy_delay_us;     /* from the command to BUSY_N falling */
} epd_cfg_t;

enum { EPD_WF_CLEAN, EPD_WF_FAST, EPD_WF_GREY, EPD_WF_PARTIAL };

typedef struct epd_model {
	epd_cfg_t cfg;
	uint64_t now;               /* ns, the last input or advance */
	bool powered, rst_n, asleep, pon;
	uint64_t rst_fell, ready_at;

	/* the command being received */
	int cmd;                    /* -1: none */
	int nparam;
	uint8_t param[64];

	/* registers */
	uint8_t psr, cdi[2], ccset, tsset;
	int hres, vres;
	int ptl[4];                 /* x0, x1, y0, y1 (inclusive) */
	bool ptl_mode;

	/* SRAM, one byte a pixel (0/1), in data order */
	uint8_t *old_ram, *new_ram;
	long wp;                    /* pixels written by the current DTM */
	long dtm1_count, dtm2_count;/* pixels sent since the last refresh (-1: none) */

	/* the operation that holds BUSY */
	int busy_op;                /* 0: none, else the command */
	uint64_t busy_start, busy_pin, busy_end;
	int busy_wf;
	int busy_area[4];

	/* the glass: one byte a pixel, 0 black ... 255 white */
	uint8_t *glass;

	uint32_t refreshes[4];      /* by waveform */
	uint32_t partials_since_full;
	uint32_t max_partials_between_fulls;
	uint32_t seq;               /* the glass changed */
	uint32_t errors;
	char error[256];            /* the first */
	uint32_t commands;          /* command bytes accepted */
	void (*log)(void *ctx, const char *line);
	void *log_ctx;
} epd_model_t;

void epd_cfg_default(epd_cfg_t *c, int w, int h);
void epd_init(epd_model_t *m, const epd_cfg_t *cfg);
void epd_free(epd_model_t *m);

/* inputs, at `ns` (never decreasing) */
void epd_pwr(epd_model_t *m, uint64_t ns, bool on);
void epd_rst(epd_model_t *m, uint64_t ns, bool rst_n);
void epd_byte(epd_model_t *m, uint64_t ns, bool dc, uint8_t b);   /* one SPI byte with CS low */
/* run to `ns`: operations that end by then complete */
void epd_advance(epd_model_t *m, uint64_t ns);
/* the BUSY_N pin at `ns` (low = busy); an unpowered module's line floats up */
bool epd_busy_n(epd_model_t *m, uint64_t ns);
/* when the BUSY_N pin or the glass next changes (UINT64_MAX: nothing pending) */
uint64_t epd_next_event(const epd_model_t *m);

#endif
