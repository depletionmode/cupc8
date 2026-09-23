/*
 * EMU-001: checks that the RP2040 emulator (rp2040js + our dual-core patch)
 * runs what the card firmware relies on: core 1 launch, the inter-core
 * FIFOs and their IRQ, CPUID, and each core's own hardware divider. Prints
 * "EMU PASS" or "EMU FAIL <what>" on UART0.
 */
#include <stdio.h>

#include "hardware/irq.h"
#include "hardware/structs/sio.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"

static volatile uint32_t core1_divs, core1_bad;
static volatile uint32_t core0_irq_words;

static void core1_main(void)
{
	multicore_fifo_push_blocking(get_core_num());          /* expect 1 */
	/* echo every word back, plus one */
	for (;;) {
		uint32_t v = multicore_fifo_pop_blocking();
		if (v == 0xdead)
			break;
		multicore_fifo_push_blocking(v + 1);
	}
	/* divide while core 0 divides too: interleaved, a shared divider breaks */
	for (uint32_t i = 1; i < 2000; i++) {
		volatile uint32_t a = 1000003u * i, b = i + 7;
		if (a / b != (uint32_t)((uint64_t)1000003u * i / (i + 7)) || a % b != 1000003u * i % (i + 7))
			core1_bad++;
		core1_divs++;
	}
	multicore_fifo_push_blocking(0xd1d);
	for (;;)
		__wfe();
}

static void sio_irq(void)
{
	while (multicore_fifo_rvalid()) {
		(void)multicore_fifo_pop_blocking();
		core0_irq_words++;
	}
	multicore_fifo_clear_irq();
}

static void __attribute__((noreturn)) fail(const char *what)
{
	printf("EMU FAIL %s\n", what);
	for (;;)
		tight_loop_contents();
}

int main(void)
{
	stdio_init_all();
	if (get_core_num() != 0)
		fail("core 0 CPUID");
	multicore_launch_core1(core1_main);
	if (multicore_fifo_pop_blocking() != 1)
		fail("core 1 CPUID");
	for (uint32_t v = 10; v < 30; v++) {
		multicore_fifo_push_blocking(v);
		if (multicore_fifo_pop_blocking() != v + 1)
			fail("fifo echo");
	}
	/* core 1 has drained everything we sent, so there is room */
	if (!(sio_hw->fifo_st & SIO_FIFO_ST_RDY_BITS))
		fail("fifo RDY");
	multicore_fifo_push_blocking(0xdead);

	uint32_t bad = 0;
	for (uint32_t i = 1; i < 2000; i++) {
		volatile uint32_t a = 7919u * i + 13, b = (i & 63) + 3;
		if (a / b != (7919u * i + 13) / ((i & 63) + 3))
			bad++;
	}
	if (bad)
		fail("core 0 divider");

	/* the rest of core 1's words arrive through the SIO IRQ */
	irq_set_exclusive_handler(SIO_IRQ_PROC0, sio_irq);
	irq_set_enabled(SIO_IRQ_PROC0, true);
	absolute_time_t until = make_timeout_time_ms(50);
	while (!core0_irq_words && !time_reached(until))
		__wfi();
	if (core0_irq_words != 1)
		fail("fifo IRQ");
	if (core1_divs != 1999 || core1_bad)
		fail("core 1 divider");
	/* reading an empty FIFO sets the sticky ROE flag (with the IRQ off, or
	 * its handler would clear it first) */
	irq_set_enabled(SIO_IRQ_PROC0, false);
	(void)sio_hw->fifo_rd;
	if (!(sio_hw->fifo_st & SIO_FIFO_ST_ROE_BITS))
		fail("fifo ROE");
	multicore_fifo_clear_irq();
	printf("EMU PASS\n");
	for (;;)
		tight_loop_contents();
}
