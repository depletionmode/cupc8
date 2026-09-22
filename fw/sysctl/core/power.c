/*
 * Power policy and the TCA9555 expanders (doc/hardware/sysctl.md, "Power
 * policy" and "Expanders").
 */
#include "sysctl.h"

#define U0 0x20                           /* CARD_RST_n, PROG_n */
#define U1 0x21                           /* PRSNT2_n, CPU card presence and ID */
#define SLOT_WIFI 0x03

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
	uint8_t hold = (s->held_slots | s->reset_slots) & 0x3F;
	/* output registers first, so the pins never glitch when they turn into outputs */
	uint8_t out[3] = {0x02, (uint8_t)~hold, 0xFF};      /* CARD_RST_n, PROG_n high */
	uint8_t cfg[3] = {0x06, 0xC0, 0xC0};                /* bits 0-5 outputs */
	s->hal->i2c_write(s->ctx, U0, out, 3);
	s->hal->i2c_write(s->ctx, U0, cfg, 3);
}

void power_update(sysctl_t *s)
{
	s->power_class = power_class_of(s->hal->adc_mv(s->ctx, ADC_CC1),
	                                s->hal->adc_mv(s->ctx, ADC_CC2));
	s->held_slots = 0;
	if (s->power_class <= PWR_DEFAULT && !s->power_forced)
		for (int i = 0; i < 6; i++)
			if (s->slot_types[i] == SLOT_WIFI)
				s->held_slots |= (uint8_t)(1u << i);
	expander_apply(s);
}

void power_force(sysctl_t *s, bool on)
{
	s->power_forced = on;
	power_update(s);
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
