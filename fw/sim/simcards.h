/*
 * Opaque wrapper around the card cores for the Nim simulator (and any other
 * host that wants a slot card): the simulator's slot cards are the real
 * firmware cores.
 */
#ifndef SIMCARDS_H
#define SIMCARDS_H

#include <stdint.h>

typedef struct simcard simcard_t;

/* the e-ink graphics card (card type $01 on the slot) with its 5.83" or 7.5" panel */
#define SIMCARD_EINK    0x101
#define SIMCARD_EINK750 0x102

simcard_t *simcard_new(int type);          /* CARD_TYPE_GPU / _IO / _WIFI / _STORAGE, SIMCARD_EINK[750] */
void simcard_free(simcard_t *c);
int simcard_type(const simcard_t *c);

/* SPI slave side */
void simcard_select(simcard_t *c, int selected);
uint8_t simcard_miso(simcard_t *c);
void simcard_mosi(simcard_t *c, uint8_t b);
int simcard_irq(simcard_t *c);             /* IRQ_n asserted */

/* background work: execute queued GPU commands, vsync, key repeat */
void simcard_tick(simcard_t *c, uint32_t now_ms);

/* GPU: render the current picture (640x480, 0x00RRGGBB) */
void simcard_render(simcard_t *c, uint32_t *rgb);

/* GPU state, for tests: the character/attribute of a text cell, and a pixel */
int simcard_gpu_cell(simcard_t *c, int x, int y);
int simcard_gpu_pixel(simcard_t *c, int x, int y);
int simcard_gpu_mode(simcard_t *c);
/* the e-ink card's panel: refreshes by waveform (0 clean, 1 fast, 2 grey,
 * 3 partial) and the UC8179 model's error count; -1 on other cards */
int simcard_eink_refreshes(simcard_t *c, int waveform);
int simcard_eink_errors(simcard_t *c);

/* IO: type an ASCII character (press + release of the matching US key) */
void simcard_type_ascii(simcard_t *c, uint8_t ch, uint32_t now_ms);
/* IO: raw HID boot report */
void simcard_hid(simcard_t *c, const uint8_t report[8], uint32_t now_ms);

/* Storage: insert the disk image at path (read and written through, and
 * write-protected if wp), or pull the medium (path 0); -1 if it cannot be
 * opened. Delay every command by ms of guest time (the medium's busy time,
 * so the host's not-ready retries run). */
int simcard_storage_image(simcard_t *c, const char *path, int wp);
void simcard_storage_latency(simcard_t *c, uint32_t ms);
int simcard_storage_status(simcard_t *c);  /* the status byte */

#endif
