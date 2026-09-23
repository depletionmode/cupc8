/*
 * EMU-002: nested interrupts. A low-priority alarm IRQ runs a checksum that
 * needs every register; a high-priority GPIO IRQ (the harness toggles GPIO 2)
 * keeps preempting it and clobbers the caller-saved registers. On silicon the
 * hardware stacks the preempted state, so every checksum must come out right.
 * Prints "NEST PASS <preemptions>" or "NEST FAIL".
 */
#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#include "hardware/timer.h"
#include "pico/stdlib.h"

static volatile uint32_t preemptions, runs, bad, sink;

static void gpio_isr(uint gpio, uint32_t events)
{
	(void)gpio;
	(void)events;
	/* dirty r0-r3, r12 and the flags */
	uint32_t a = 0xdeadbeef, b = 0x12345678;
	for (int i = 0; i < 7; i++)
		a = a * 1664525u + b + (uint32_t)i;
	sink = a;
	preemptions++;
}

static uint32_t checksum(uint32_t seed)
{
	uint32_t x = seed, y = seed ^ 0x55aa55aa, z = seed * 3u;
	for (int i = 0; i < 200; i++) {
		x = x * 1103515245u + 12345u;
		y ^= x >> 7;
		z += y + (x ^ (uint32_t)i);
	}
	return x ^ y ^ z;
}

static void alarm_isr(void)
{
	hw_clear_bits(&timer_hw->intr, 1u << 0);
	uint32_t want = 0;
	for (int k = 0; k < 20; k++) {
		/* the same checksum twice: a preemption that corrupts state shows */
		uint32_t a = checksum((uint32_t)k + runs), b = checksum((uint32_t)k + runs);
		if (a != b)
			bad++;
		want ^= a;
	}
	sink = want;
	runs++;
	timer_hw->alarm[0] = timer_hw->timerawl + 200;
}

int main(void)
{
	stdio_init_all();
	gpio_init(2);
	gpio_set_irq_enabled_with_callback(2, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, gpio_isr);
	irq_set_priority(IO_IRQ_BANK0, 0);
	irq_set_exclusive_handler(TIMER_IRQ_0, alarm_isr);
	irq_set_priority(TIMER_IRQ_0, 0x80);
	hw_set_bits(&timer_hw->inte, 1u << 0);
	irq_set_enabled(TIMER_IRQ_0, true);
	timer_hw->alarm[0] = timer_hw->timerawl + 200;
	while (runs < 200)
		__wfi();
	irq_set_enabled(TIMER_IRQ_0, false);
	printf(bad ? "NEST FAIL %lu of %lu\n" : "NEST PASS %lu %lu\n", (unsigned long)(bad ? bad : preemptions),
	       (unsigned long)runs);
	for (;;)
		tight_loop_contents();
}
