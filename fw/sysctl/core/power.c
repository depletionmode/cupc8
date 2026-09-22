/*
 * USB-C source class and the TCA9555 expanders (doc/hardware/sysctl.md).
 * The power policy itself is on the main board (PWR_HI, read by the kernel),
 * so the machine keeps it without the system card; sysctl only reports it.
 */
#include "sysctl.h"

#define U0 0x20                           /* CARD_RST_n, PROG_n */
#define U1 0x21                           /* PRSNT2_n, CPU card presence and ID */

uint8_t power_class_of(int cc1_mv, int cc2_mv)
{
	int mv = cc1_mv > cc2_mv ? cc1_mv : cc2_mv;
	if (mv < 200)
		return PWR_UNKNOWN;
	if (mv < 660)
		return PWR_DEFAULT;
	if (mv < 1230)
		return PWR_1A5;
	return PWR_3A0;
}

void expander_apply(sysctl_t *s)
{
	/* a pin is an output (driving low) only while its card is held in reset;
	 * otherwise it is an input and the board's pull-up runs the card */
	uint8_t hold = s->reset_slots & 0x3F;
	uint8_t out[3] = {0x02, (uint8_t)~hold, 0xFF};
	uint8_t cfg[3] = {0x06, (uint8_t)~hold, 0xFF};
	s->hal->i2c_write(s->ctx, U0, out, 3);      /* output register first: no glitch */
	s->hal->i2c_write(s->ctx, U0, cfg, 3);
}

int card_reset(sysctl_t *s, int slot, bool hold)
{
	if (slot < 0 || slot > 5)
		return ST_ARG;
	if (hold)
		s->reset_slots |= (uint8_t)(1u << slot);
	else
		s->reset_slots &= (uint8_t)~(1u << slot);
	expander_apply(s);
	return ST_OK;
}

bool cpu_card_present(sysctl_t *s)
{
	uint8_t in = 0xFF;
	if (s->hal->i2c_read(s->ctx, U1, 0x01, &in, 1) != 0)
		return false;
	return !(in & 0x01);                  /* PRSNT2_n */
}
