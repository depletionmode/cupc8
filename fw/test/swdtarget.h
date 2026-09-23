/*
 * An RP2040 as seen through SWD, bit by bit: a multi-drop SW-DP (dormant at
 * power-up, the ADIv5.2 wake-up, TARGETSEL), an AHB-AP, core debug (halt,
 * registers, reset) and the boot ROM's flash routines acting on a flash
 * array. For SYS-004: sysctl's SWD engine and cupc8.py's flash algorithm
 * must get every detail right to program it.
 */
#ifndef SWDTARGET_H
#define SWDTARGET_H

#include <stdbool.h>
#include <stdint.h>

#define SWDT_FLASH (2 * 1024 * 1024)
#define SWDT_RAM   (264 * 1024)

typedef struct {
	/* the wire */
	bool dormant;                     /* waiting for the selection alert */
	bool need_reset;                  /* woken: a line reset comes next */
	bool selected;                    /* TARGETSEL named us since the last line reset */
	int ones;                         /* consecutive 1s (line reset at 50) */
	int since_reset;                  /* bits since the last line reset (-1: none yet) */
	uint16_t to_dormant;              /* those bits, for the SWD-to-dormant code $E3BC */
	uint8_t window[16];               /* the last 128 bits, for the alert */
	int after_alert;                  /* bits seen after the alert (-1: none) */
	uint8_t act;                      /* the activation code as it arrives */
	int phase, nbits;                 /* 0 idle, 1 request, 2 write data, 3 TARGETSEL data */
	uint64_t shift;
	uint8_t req;
	uint8_t outq[40];                 /* bits the target drives next */
	int outq_n, outq_pos;

	/* the debug port */
	uint32_t ctrl, select, rdbuff, ap_last;
	bool sticky;
	uint32_t csw, tar;
	int wait_every, wait_count;       /* answer WAIT to every Nth AP access (0: never) */

	/* the chip */
	uint32_t regs[20];
	bool halted, debugen, xip, cmd_mode, connected;
	uint32_t dcrdr, demcr;
	int resets, calls;
	uint8_t ram[SWDT_RAM];
	uint8_t flash[SWDT_FLASH];
} swdt_t;

void swdt_init(swdt_t *t);
void swdt_out(swdt_t *t, int bit);        /* the host drove SWDIO for one clock */
int swdt_in(swdt_t *t);                   /* the host sampled SWDIO for one clock */

#endif
