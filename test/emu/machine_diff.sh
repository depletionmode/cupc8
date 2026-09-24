#!/usr/bin/env bash
# The native whole-machine emulator (emu/machine) against machine.mjs: boot
# to BASIC and type a program on both, and the native one serially and
# threaded (twice); screen, emulated end times, board clocks, card core
# cycle counts, UART output and every slot SPI frame must be identical, and
# the program's output must be on the screen (test/emu/test_machine_native.mjs).
#   test/emu/machine_diff.sh [--ns N] [--type TEXT] [--expect TEXT] [--skip-js]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
tools/fw_rp2040.sh gpu io >/dev/null
tools/emu_machine_build.sh >/dev/null
exec node test/emu/test_machine_native.mjs "$@"
