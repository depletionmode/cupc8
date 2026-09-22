/*
 * CUPC/8 system controller core (doc/hardware/sysctl.md), the firmware of
 * the removable system card (doc/hardware/system-slot.md).
 *
 * Hardware-independent: everything it touches goes through sysctl_hal, which
 * is the RP2040 on the card and a set of models in the host tests. The
 * machine runs without it; it only programs, resets and debugs.
 */
#ifndef SYSCTL_H
#define SYSCTL_H

#include <stdbool.h>
#include <stdint.h>

#define SYSCTL_VERSION  "2.0"
#define SYS_MAX_PAYLOAD 4096          /* a full trace drain is 2 + 512 * 4 */

/* SPI buses: one selected at a time (the two flash buses share SPI1) */
enum { SPI_NONE = -1, SPI_BRIDGE = 0, SPI_FL0, SPI_FL1 };

/* FPGA targets: the chipset (flash FL0) and the CPU card (flash FL1) */
enum { FPGA_CHIPSET = 0, FPGA_CPUCARD = 1 };

/* pins */
enum { HAL_CHIPSET_CRESET, HAL_CHIPSET_CDONE, HAL_CPUCARD_CRESET, HAL_CPUCARD_CDONE, HAL_SYS_NRST };

/* ADC channels */
enum { ADC_CC1, ADC_CC2, ADC_V1V2 };

/* reply status codes */
enum {
	ST_OK = 0, ST_CRC, ST_CMD, ST_ARG, ST_TIMEOUT, ST_VERIFY, ST_NOTHELD, ST_NOCHIPSET,
};

/* USB-C source classes */
enum { PWR_UNKNOWN = 0, PWR_DEFAULT, PWR_1A5, PWR_3A0 };

typedef struct {
	/* select one bus (or SPI_NONE), then clock bytes; tx may be 0 (sends $00) */
	void (*spi_select)(void *ctx, int bus);
	void (*spi_xfer)(void *ctx, const uint8_t *tx, uint8_t *rx, int n);
	/* outputs are open drain: false drives low, true releases (the board pulls up) */
	void (*pin_write)(void *ctx, int pin, bool level);
	bool (*pin_read)(void *ctx, int pin);
	int (*adc_mv)(void *ctx, int ch);
	/* I2C: 0 on ACK */
	int (*i2c_write)(void *ctx, uint8_t addr, const uint8_t *data, int n);
	int (*i2c_read)(void *ctx, uint8_t addr, uint8_t reg, uint8_t *data, int n);
	void (*delay_us)(void *ctx, uint32_t us);
	uint32_t (*now_ms)(void *ctx);
	void (*usb_write)(void *ctx, const uint8_t *data, int n);
} sysctl_hal;

typedef struct {
	const sysctl_hal *hal;
	void *ctx;

	/* USB frame parser */
	uint8_t rx[4 + SYS_MAX_PAYLOAD + 1];
	int rx_len;
	uint32_t rx_last_ms;

	uint8_t held;                     /* FPGAs held in reset: bit per target */
	uint8_t reset_slots;              /* cards held in reset by CARD_RESET */
} sysctl_t;

void sysctl_init(sysctl_t *s, const sysctl_hal *hal, void *ctx);
void sysctl_rx(sysctl_t *s, const uint8_t *data, int n);   /* bytes from USB */
void sysctl_poll(sysctl_t *s);                            /* drop stale frames */

/* bridge (bridge.c) */
uint8_t br_status(sysctl_t *s);
uint8_t br_gpo(sysctl_t *s);
void br_cpu_ctl(sysctl_t *s, uint8_t ctl);
void br_ram_write(sysctl_t *s, uint16_t addr, const uint8_t *data, int n);
void br_ram_read(sysctl_t *s, uint16_t addr, uint8_t *data, int n);
void br_rom_read(sysctl_t *s, uint32_t addr, uint8_t *data, int n);
void br_rom_busw(sysctl_t *s, uint32_t addr, uint8_t data);
int br_trace(sysctl_t *s, uint8_t *out);                  /* ≤ 2 + 512 * 4 bytes */

/* ROM chip (romflash.c): ST_* codes; *bad gets the failing address */
int rom_id(sysctl_t *s, uint8_t *mfr, uint8_t *dev);
int rom_erase(sysctl_t *s, uint32_t addr, uint32_t len);
int rom_program(sysctl_t *s, uint32_t addr, const uint8_t *data, int n, uint32_t *bad);

/* an FPGA's configuration flash (spiflash.c); the FPGA must be held */
void fl_read(sysctl_t *s, int target, uint32_t addr, uint8_t *data, int n);
int fl_erase(sysctl_t *s, int target, uint32_t addr, uint32_t len);
int fl_program(sysctl_t *s, int target, uint32_t addr, const uint8_t *data, int n, uint32_t *bad);
void fl_id(sysctl_t *s, int target, uint8_t id[3]);

/* FPGA reset and reboot (fpga.c) */
void fpga_hold(sysctl_t *s, int target);                  /* CRESET_n low: it lets go of its flash */
int fpga_boot(sysctl_t *s, int target);                   /* release, wait for CDONE */
bool fpga_done(sysctl_t *s, int target);

/* USB-C source and the expanders (power.c) */
uint8_t power_class_of(int cc1_mv, int cc2_mv);
int card_reset(sysctl_t *s, int slot, bool hold);
void expander_apply(sysctl_t *s);
bool cpu_card_present(sysctl_t *s);

#endif
