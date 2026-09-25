#!/usr/bin/env bash
# The native whole-machine emulator (emu/machine), serially and threaded
# (twice): boot to BASIC and type a program; screen, emulated end times,
# board clocks, card core cycle counts, UART output and every slot SPI frame
# must be identical, and the program's output must be on the screen
# (test/emu/test_machine_native.mjs). The legacy JS emulator (machine.mjs) is
# not maintained and not compared.
#   test/emu/machine_diff.sh [--ns N] [--type TEXT] [--expect TEXT]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
tools/fw_rp2040.sh gpu io >/dev/null
tools/emu_machine_build.sh >/dev/null
exec node test/emu/test_machine_native.mjs "$@"
