#!/usr/bin/env bash
# EMU-005: the native RP2040 emulator's modules against rp2040js, each on its
# differential harness (randomised, seeded; every state change compared):
# the Cortex-M0+ core and PPB, PIO, the peripherals (DMA, UART, SPI, I2C,
# timers, PWM, ADC, RTC, watchdog) and USB (device, host, the keyboard model).
# js checks utils/js.h's fast number conversions against their plain definitions;
# decode checks the core's decode table against the if/else chain (exhaustive);
# steps checks RP2040::runSteps against Emu::step() on the card images
# (build/rp2040, tools/fw_rp2040.sh).
#   emu/rp2040/test/diffs.sh [js|decode|steps|core|pio|periph|usb ...]    (default: all)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
B=build/emu-native
cmake -G Ninja -S emu/rp2040 -B "$B" >/dev/null
ninja -C "$B" test_core_diff test_pio_diff test_periph_diff test_usb_diff test_js_numbers test_decode test_runsteps >/dev/null
T=emu/rp2040/test
want=" ${*:-js decode steps core pio periph usb} "
bad=0
run() {
	local name=$1
	shift
	[[ $want == *" $name "* ]] || return 0
	if "$@" >"$B/diff-$name.log" 2>&1; then
		echo "pass $name: $(tail -1 "$B/diff-$name.log")"
	else
		bad=$((bad + 1))
		echo "FAIL $name: $(tail -3 "$B/diff-$name.log" | tr '\n' ' ') (log $B/diff-$name.log)"
	fi
}
run js "$B/test_js_numbers"
run decode "$B/test_decode"
run steps "$B/test_runsteps" build/rp2040 --ns 50e6
run core node $T/core/core-diff.mjs --driver $B/test_core_diff --seeds 1-10 --steps 50000
run pio node $T/pio/pio_diff.mjs --cxx $B/test_pio_diff
run periph node $T/periph/periph_diff.mjs --cxx $B/test_periph_diff --seeds 40 --ops 20000
run usb node $T/usb/usb_diff.mjs $B/test_usb_diff --scenarios 200 --steps 4000
echo "EMU-005: $bad failure(s)"
exit $((bad > 0))
