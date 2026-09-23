/* The machine around the system card, in models: see sysmachine.c. */
#ifndef SYSMACHINE_H
#define SYSMACHINE_H

#include <stdbool.h>
#include <stdint.h>

#include "swdtarget.h"
#include "sysctl.h"
#include "sysmodels.h"

#define IMG_LEN 135100                    /* an HX4K bitstream */

struct sysmachine {
	uint64_t now;                         /* µs */
	int bus;
	sst39_t rom;
	w25q_t fl0, fl1;
	ice40_t chip, cpu;
	bridge_t br;
	tca_t u0, u1;
	int adc[3];
	bool sys_nrst;
	int reset_pulses;
	int contention;                       /* flash accessed while its FPGA owns it */
	uint8_t usb[8 + SYS_MAX_PAYLOAD];
	int usb_n;
	int prog_slot;                        /* the mux: -1 released (channel 7) */
	swdt_t *card[6];                      /* RP2040 cards on the programming port */
	uint32_t uart_baud;
	uint8_t uart[256];                    /* the UART's far end: a loopback */
	int uart_n;
	/* the programming-port UART's far end; unset: a loopback */
	struct {
		void (*open)(uint32_t baud);
		void (*write)(const uint8_t *d, int n);
		int (*read)(uint8_t *d, int max);
	} uart_far;
};

extern struct sysmachine M;
extern sysctl_t S;
extern swdt_t card2;                      /* the RP2040 card in slot 3 */
extern uint8_t img_chip[IMG_LEN], img_cpu[IMG_LEN];

/* power on the machine: the FPGAs boot from whatever their flash holds */
void power_on(bool chip_flashed, bool cpu_flashed);
void tick(void);

#endif
