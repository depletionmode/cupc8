#include "uc8179.h"

static void send(const epd_bus_t *b, uint8_t cmd, const uint8_t *p, int n)
{
	b->command(b->ctx, cmd);
	if (n)
		b->data(b->ctx, p, n);
}
#define SEND(b, cmd, ...) do { const uint8_t p_[] = {__VA_ARGS__}; send(b, cmd, p_, (int)sizeof p_); } while (0)

void uc8179_setup(const epd_bus_t *b, int w, int h)
{
	/* PWR: internal DC/DC for VGH/VGL and VDH/VDL (p.13), VGH/VGL = +-20 V,
	 * VDH/VDL = +-15 V: the panel vendors' values */
	SEND(b, UC_PWR, 0x07, 0x07, 0x3F, 0x3F);
	/* BTST: soft start phases A, B 10 ms at strength 3, C1 strength 6 (p.16) */
	SEND(b, UC_BTST, 0x17, 0x17, 0x28, 0x17);
	/* PSR: LUT from OTP, KW mode, scan up, shift right, booster on, no
	 * soft reset (p.12) */
	SEND(b, UC_PSR, 0x1F);
	/* TRES: HRES in 8-pixel banks, VRES (p.31) */
	SEND(b, UC_TRES, (uint8_t)(w >> 8), (uint8_t)(w & 0xF8), (uint8_t)(h >> 8), (uint8_t)h);
	SEND(b, UC_DUSPI, 0x00);                     /* single SPI (p.18) */
	SEND(b, UC_TCON, 0x22);                      /* S2G = G2S = 12 x 667 ns (p.30) */
}

void uc8179_waveform(const epd_bus_t *b, uc_waveform_t wf)
{
	static const uint8_t ts[] = {0, UC_TS_FAST, UC_TS_GREY, UC_TS_PARTIAL};
	/* CDI (p.27-28): DDX = 01, so data 1 is white and {NEW, OLD} = 11
	 * selects LUTWW; no NEW-to-OLD copy (both pictures are always sent);
	 * the border to white (BDV 10 = LUTKW), or Hi-Z during a partial
	 * refresh so that it is not driven every time */
	SEND(b, UC_CDI, wf == UC_WF_PARTIAL ? 0xA1 : 0x21, 0x07);
	if (wf == UC_WF_CLEAN) {
		SEND(b, UC_CCSET, 0x00);             /* the temperature sensor's value (p.38) */
		return;
	}
	SEND(b, UC_CCSET, 0x02);                     /* TSFIX: the temperature is TS_SET */
	SEND(b, UC_TSSET, ts[wf]);
}

void uc8179_window(const epd_bus_t *b, int x0, int y0, int x1, int y1)
{
	/* PTL (p.33): HRST[9:3], HRED[9:3] | 7, VRST, VRED, PT_SCAN = 1 (gates
	 * scan the whole panel, the vendors' choice); then PTIN */
	SEND(b, UC_PTL, (uint8_t)(x0 >> 8), (uint8_t)(x0 & 0xF8), (uint8_t)(x1 >> 8), (uint8_t)(x1 | 7),
	     (uint8_t)(y0 >> 8), (uint8_t)y0, (uint8_t)(y1 >> 8), (uint8_t)y1, 0x01);
	uc8179_cmd(b, UC_PTIN);
}

void uc8179_cmd(const epd_bus_t *b, uint8_t cmd)
{
	b->command(b->ctx, cmd);
}

void uc8179_deep_sleep(const epd_bus_t *b)
{
	SEND(b, UC_DSLP, 0xA5);                      /* the check code (p.17) */
}
