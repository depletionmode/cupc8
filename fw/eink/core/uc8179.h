/*
 * UltraChip UC8179 e-paper controller: the command sequences the e-ink card
 * sends (doc/hardware/eink-card.md, "Panel controller"), over a small bus
 * interface that the RP2040 port (SPI1 + DC/RST/BUSY/PWR), the host tests
 * and the simulator each provide.
 *
 * Written from the UC8179c datasheet (UltraChip, rev 0.6, 2019: "Command
 * table" p.8-11, "Command description" p.12-39, "BUSY_N signal" p.46) and
 * the panel vendors' notes on which OTP waveform a forced temperature picks
 * (Waveshare's EPD_7in5_V2.c, MIT licence, is the reference for those three
 * values; nothing is copied from GPL code). Nothing here waits: the caller's
 * state machine (eink.c) waits for BUSY and for the reset timings.
 */
#ifndef UC8179_H
#define UC8179_H

#include <stdbool.h>
#include <stdint.h>

/* the controller's commands (datasheet p.8-11) */
enum {
	UC_PSR = 0x00, UC_PWR = 0x01, UC_POF = 0x02, UC_PON = 0x04, UC_BTST = 0x06,
	UC_DSLP = 0x07, UC_DTM1 = 0x10, UC_DRF = 0x12, UC_DTM2 = 0x13, UC_DUSPI = 0x15,
	UC_CDI = 0x50, UC_TCON = 0x60, UC_TRES = 0x61, UC_PTL = 0x90, UC_PTIN = 0x91,
	UC_PTOUT = 0x92, UC_CCSET = 0xE0, UC_TSSET = 0xE5,
};

/* the OTP waveforms of the GDEY0583T81 / GDEY075T7, chosen by forcing the
 * temperature (CCSET TSFIX + TSSET); the clean full refresh uses the real
 * temperature */
typedef enum { UC_WF_CLEAN, UC_WF_FAST, UC_WF_GREY, UC_WF_PARTIAL } uc_waveform_t;
#define UC_TS_FAST    0x5A
#define UC_TS_GREY    0x5F
#define UC_TS_PARTIAL 0x6E

enum { EPD_PIN_RST_N, EPD_PIN_PWR };

typedef struct epd_bus {
	void *ctx;
	void (*command)(void *ctx, uint8_t cmd);                 /* DC low: one command byte */
	void (*data)(void *ctx, const uint8_t *p, int n);        /* DC high: its parameters / pixels */
	void (*pin)(void *ctx, int pin, bool level);             /* RST_n, PWR */
	bool (*busy)(void *ctx);                                  /* the controller is busy */
} epd_bus_t;

/* registers after a hardware reset: power, booster, KW mode with the OTP
 * LUTs, the resolution, single SPI, TCON */
void uc8179_setup(const epd_bus_t *b, int w, int h);
/* the waveform for the next refresh, and the data polarity (1 = white) */
void uc8179_waveform(const epd_bus_t *b, uc_waveform_t wf);
/* a partial window (x0 and x1 + 1 multiples of 8; inclusive), entered */
void uc8179_window(const epd_bus_t *b, int x0, int y0, int x1, int y1);
void uc8179_cmd(const epd_bus_t *b, uint8_t cmd);            /* PON, POF, DRF, PTOUT, DTM1/2 */
void uc8179_deep_sleep(const epd_bus_t *b);

#endif
