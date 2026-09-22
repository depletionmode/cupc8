/*
 * CUPC/8 system controller core (doc/hardware/sysctl.md).
 *
 * Hardware-independent: everything it touches goes through sysctl_hal, which
 * is the RP2040 on the board and a set of models in the host tests.
 */
#ifndef SYSCTL_H
#define SYSCTL_H

#include <stdbool.h>
#include <stdint.h>

#define SYSCTL_VERSION  "1.0"
#define SYS_MAX_PAYLOAD 4096          /* a full trace drain is 2 + 512 * 4 */

/* SPI devices on the shared sysctl bus */
enum { SPI_NONE = -1, SPI_FLASH = 0, SPI_CHIPSET_CFG, SPI_CPUCARD_CFG, SPI_BRIDGE };

/* pins */
enum { PIN_CHIPSET_CRESET, PIN_CHIPSET_CDONE, PIN_CPUCARD_CRESET, PIN_CPUCARD_CDONE };

/* ADC channels */
enum { ADC_CC1, ADC_CC2, ADC_V1V2 };

/* reply status codes */
enum {
	ST_OK = 0, ST_CRC, ST_CMD, ST_ARG, ST_TIMEOUT, ST_VERIFY, ST_NOIMAGE, ST_POWER,
};

/* power classes */
enum { PWR_UNKNOWN = 0, PWR_DEFAULT, PWR_1A5, PWR_3A0 };

typedef struct {
	/* select one device (or SPI_NONE), then clock bytes; tx may be 0 (sends $00) */
	void (*spi_select)(void *ctx, int dev);
	void (*spi_xfer)(void *ctx, const uint8_t *tx, uint8_t *rx, int n);
	void (*pin_write)(void *ctx, int pin, bool level);
	bool (*pin_read)(void *ctx, int pin);
	int (*adc_mv)(void *ctx, int ch);
	/* I²C: 0 on ACK */
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

	/* direct CRAM load in progress (FPGA_LOAD), or -1 */
	int load_target;

	/* power policy */
	uint8_t power_class;
	bool power_forced;
	uint8_t held_slots;               /* CARD_RST_n held by the policy */
	uint8_t reset_slots;              /* CARD_RST_n held by CARD_RESET */
	uint8_t slot_types[6];

	uint8_t cdone;                    /* bit0 chipset, bit1 CPU card */
	uint8_t boot_status;              /* ST_* from sysctl_boot */
} sysctl_t;

void sysctl_init(sysctl_t *s, const sysctl_hal *hal, void *ctx);
void sysctl_rx(sysctl_t *s, const uint8_t *data, int n);   /* bytes from USB */
void sysctl_poll(sysctl_t *s);                            /* drop stale frames */
int sysctl_boot(sysctl_t *s);                             /* the power-up sequence */

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

/* configuration flash (spiflash.c) */
void fl_read(sysctl_t *s, uint32_t addr, uint8_t *data, int n);
int fl_erase(sysctl_t *s, uint32_t addr, uint32_t len);
int fl_program(sysctl_t *s, uint32_t addr, const uint8_t *data, int n, uint32_t *bad);

/* FPGA configuration (fpgacfg.c) */
#define FL_SLOT_SIZE  0x100000u
#define FL_IMAGE_OFS  0x100u
#define FPGA_MAX_IMAGE (160u * 1024)   /* staged in RAM; an HX4K bitstream is 135100 */
int fpga_boot(sysctl_t *s, int target);                   /* from the flash slot */
void fpga_load_begin(sysctl_t *s, int target);
int fpga_load_data(sysctl_t *s, int target, const uint8_t *data, int n);
int fpga_load_end(sysctl_t *s, int target);
uint32_t crc32_ieee(uint32_t crc, const uint8_t *data, int n);

/* power policy and expanders (power.c) */
uint8_t power_class_of(int cc1_mv, int cc2_mv);
void power_update(sysctl_t *s);       /* read CC, slot types; apply the policy */
void power_force(sysctl_t *s, bool on);
int card_reset(sysctl_t *s, int slot, bool hold);
void expander_apply(sysctl_t *s);
bool cpu_card_present(sysctl_t *s);

#endif
