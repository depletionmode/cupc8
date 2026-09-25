/*
 * Models of the parts the sysctl core drives, for its host tests (SYS-001..005).
 * Time is a virtual microsecond clock owned by the test harness.
 *
 *   sst39   SST39VF040 ROM chip, mirroring soc/tb/models/sst39_model.vhd
 *   w25q    W25Q32 configuration flash
 *   ice40   an iCE40 booting itself from its W25Q (SPI master mode)
 *   bridge  the chipset's bus bridge, byte for byte as soc/bridge.vhd
 *   tca     TCA9555 I²C expander
 */
#ifndef SYSMODELS_H
#define SYSMODELS_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
	uint8_t mem[1 << 19];
	uint8_t device_id;                    /* $D7 VF040 */
	uint64_t t_bp, t_se, t_sce;           /* busy times, µs */
	int step;
	bool erase_armed, id_mode;
	uint64_t busy_until;
	int busy_kind;                        /* 1 program, 2 erase */
	uint8_t busy_d7, toggle;
	uint32_t stuck_addr;                  /* fault injection: these bits never clear */
	uint8_t stuck_mask;
	int writes;                           /* bus write cycles seen */
} sst39_t;

void sst39_init(sst39_t *m);
uint8_t sst39_read(sst39_t *m, uint32_t addr, uint64_t now);
void sst39_write(sst39_t *m, uint32_t addr, uint8_t d, uint64_t now);

typedef struct {
	uint8_t mem[4 << 20];
	bool wel;
	uint64_t busy_until;
	/* the frame in progress */
	uint8_t cmd;
	int n;                                /* bytes into the frame */
	uint32_t addr;
	uint8_t page[256];
	int page_n;
	uint32_t stuck_addr;
	uint8_t stuck_mask;
	int violations;
} w25q_t;

void w25q_init(w25q_t *m);
void w25q_select(w25q_t *m, bool sel, uint64_t now);
uint8_t w25q_byte(w25q_t *m, uint8_t mosi, uint64_t now);

typedef struct {
	w25q_t *flash;                        /* its own configuration flash */
	const uint8_t *expect;                /* the bitstream that configures it */
	int expect_len;
	bool creset, cdone, booting;
	uint64_t t_release;
	uint64_t boot_us;                     /* time to read the image */
	int loads;                            /* completed configurations */
} ice40_t;

/* expect: the one image that configures it; NULL: any image with the sync word */
void ice40_init(ice40_t *m, w25q_t *flash, const uint8_t *expect, int len);
void ice40_creset(ice40_t *m, bool level, uint64_t now);
void ice40_tick(ice40_t *m, uint64_t now);

typedef struct {
	uint8_t ram[1 << 19];                 /* the 512 KB SRAM (RAM_WR/RAM_RD reach its first 64 KB) */
	sst39_t *rom;
	bool configured;                      /* the chipset has CDONE */
	uint8_t gpo, ctl;
	uint32_t trace[512];
	int trace_head, trace_count;
	bool trace_lost;
	/* the frame in progress */
	int state, argn, len;
	uint8_t cmd, tx_cur, tx_next;
	uint32_t addr;
	int tcount, tbyte;
	bool thdr, lost_snap;
	int ctl_writes;
	uint8_t ctl_when_busw;                /* CPU_CTL at the last ROM bus write */
	/* optional: called at every SRAM cycle the bridge makes, before a read
	 * and after a write (the console tests log them and play the CPU there) */
	void (*on_ram)(uint32_t addr, bool write);
} bridge_t;

void bridge_init(bridge_t *m, sst39_t *rom);
void bridge_select(bridge_t *m, bool sel);
uint8_t bridge_byte(bridge_t *m, uint8_t mosi, uint64_t now);
void bridge_trace_push(bridge_t *m, uint16_t a, uint8_t d, uint8_t flags);

typedef struct {
	uint8_t reg[8];                       /* in0 in1 out0 out1 pol0 pol1 cfg0 cfg1 */
	uint8_t ext[2];                       /* what the board drives onto input pins */
	uint8_t pulled[2];                    /* level of an undriven pin */
} tca_t;

void tca_init(tca_t *m, uint8_t pulled0, uint8_t pulled1);
int tca_write(tca_t *m, const uint8_t *data, int n);
int tca_read(tca_t *m, uint8_t reg, uint8_t *data, int n);
uint8_t tca_pins(tca_t *m, int port);     /* the level on each pin */

#endif
