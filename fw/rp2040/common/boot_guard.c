/*
 * Boot guard: a watchdog around the SDK's clock set-up, in every card's
 * firmware (bring-up 2026-11-02, doc/hardware/bringup.md, fix 3).
 *
 * From a cold start the cards' 12 MHz crystal (X322512MSB4SI, CL 20 pF,
 * 33 pF + 1k) is sometimes not stable in time; the PLL then never locks and
 * the SDK waits for ever in runtime_init_clocks. The 64 ms start-up wait
 * (PICO_XOSC_STARTUP_DELAY_MULTIPLIER, CMakeLists.txt) made it rare, not
 * impossible: on the USB-C charger it still hung now and then.
 *
 * Before the clock set-up this arms the watchdog on the ring oscillator,
 * which needs no crystal. A hang there resets the chip, but not the crystal
 * oscillator (PSM WDSEL leaves XOSC and ROSC out, as the SDK's own
 * watchdog_enable does): on the second pass the crystal is already running,
 * the case that always worked (BOOTSEL, picotool reboot). After the clocks
 * it is disarmed, so the firmware runs exactly as before.
 */
#include "hardware/structs/psm.h"
#include "hardware/structs/watchdog.h"
#include "hardware/sync.h"
#include "pico/runtime_init.h"

/* The watchdog counts ticks of clk_ref / TICK_CYCLES. Before the clocks are
 * set up clk_ref is the ring oscillator: 1.8-12 MHz over process, voltage
 * and temperature (6.5 nominal). 500 000 ticks of 12 cycles is 0.5 s at
 * 12 MHz and 3.3 s at 1.8 MHz: always far longer than the 64 ms crystal wait
 * and the PLL lock. RP2040-E1: the counter drops 2 a tick, so load twice. */
#define TICK_CYCLES 12u
#define GUARD_TICKS 500000u

static void boot_guard_arm(void)
{
	watchdog_hw->scratch[4] = 0;          /* a plain reset: no reboot-to-address magic */
	/* the reset takes the crystal oscillator too: kept running, a stuck one
	 * hung every retry (bench, 1 cold start in 7); each retry is a fresh
	 * start. Not the ring oscillator: it clocks the watchdog's tick. */
	psm_hw->wdsel = PSM_WDSEL_BITS & ~PSM_WDSEL_ROSC_BITS;
	watchdog_hw->tick = WATCHDOG_TICK_ENABLE_BITS | TICK_CYCLES;
	watchdog_hw->load = GUARD_TICKS * 2;
	watchdog_hw->ctrl = WATCHDOG_CTRL_ENABLE_BITS | WATCHDOG_CTRL_PAUSE_DBG0_BITS |
	                    WATCHDOG_CTRL_PAUSE_DBG1_BITS | WATCHDOG_CTRL_PAUSE_JTAG_BITS;
}
/* after the early resets ("00100"), before the clocks ("00500") */
PICO_RUNTIME_INIT_FUNC_HW(boot_guard_arm, "00150");

static void boot_guard_disarm(void)
{
	hw_clear_bits(&watchdog_hw->ctrl, WATCHDOG_CTRL_ENABLE_BITS);
}
/* after the clocks and the post-clock resets ("00600") */
PICO_RUNTIME_INIT_FUNC_HW(boot_guard_disarm, "00650");
