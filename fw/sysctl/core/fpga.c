/*
 * FPGA reset and reboot. Each FPGA boots itself from its own flash (SPI
 * master mode); sysctl only holds it in reset while it reprograms that
 * flash, then lets it reboot (doc/hardware/system-slot.md, "Buses").
 */
#include "sysctl.h"

#define CDONE_MS 1000                     /* an HX4K reads its ~135 KB image in ~0.2 s */

static const int creset[2] = {HAL_CHIPSET_CRESET, HAL_CPUCARD_CRESET};
static const int cdone[2] = {HAL_CHIPSET_CDONE, HAL_CPUCARD_CDONE};

void fpga_hold(sysctl_t *s, int target)
{
	s->hal->pin_write(s->ctx, creset[target], false);
	s->hal->delay_us(s->ctx, 10);          /* CRESET_B low ≥ 200 ns; its SPI pins go high-Z */
	s->held |= (uint8_t)(1u << target);
}

bool fpga_done(sysctl_t *s, int target)
{
	return s->hal->pin_read(s->ctx, cdone[target]);
}

int fpga_boot(sysctl_t *s, int target)
{
	/* a pulse even if it was not held: FPGA_BOOT is also "reconfigure now" */
	if (!(s->held & (1u << target)))
		fpga_hold(s, target);
	s->hal->pin_write(s->ctx, creset[target], true);
	s->held &= (uint8_t)~(1u << target);
	uint32_t start = s->hal->now_ms(s->ctx);
	while (!fpga_done(s, target)) {
		if (s->hal->now_ms(s->ctx) - start > CDONE_MS)
			return ST_TIMEOUT;
		s->hal->delay_us(s->ctx, 1000);
	}
	return ST_OK;
}
