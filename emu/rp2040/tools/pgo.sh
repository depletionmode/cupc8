#!/usr/bin/env bash
# Profile-guided build of the native RP2040 emulator (README.md, "Build"):
# builds an instrumented copy in <build>-pgogen, trains it on the card images
# (rp2040run on gpu, gpu with the slot's pins moving, io, sysctl, and the
# self-tests), then configures <build> with RP2040EMU_PGO=use on that profile
# and builds it. Other cmake options (-DRP2040EMU_NATIVE=ON, ...) are passed to
# both builds. Needs the firmware (tools/fw_rp2040.sh).
#   emu/rp2040/tools/pgo.sh [build dir (default build/emu-native)] [-Dopt=value ...]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
B=build/emu-native
if [ $# -gt 0 ] && [[ $1 != -* ]]; then
	B=$1
	shift
fi
B=$(mkdir -p "$B" && cd "$B" && pwd)
G=$B-pgogen
PROFILE=$B/pgo-profile
for elf in gpu io sysctl emu_selftest emu_nested; do
	[ -f "build/rp2040/$elf.elf" ] || { echo "pgo.sh: build/rp2040/$elf.elf missing (tools/fw_rp2040.sh)" >&2; exit 1; }
done
cmake -G Ninja -S emu/rp2040 -B "$G" -DRP2040EMU_PGO=generate "-DRP2040EMU_PGO_DIR=$PROFILE" "$@" >/dev/null
ninja -C "$G" rp2040run >/dev/null
rm -rf "$PROFILE"
run() { "$G/rp2040run" "$@" >/dev/null || true; }
run build/rp2040/gpu.elf --mhz 252 --until '^NEVER$' --max-ns 60e6
run build/rp2040/gpu.elf --mhz 252 --until '^NEVER$' --max-ns 30e6 --toggle-gpio 5:60000 --toggle-gpio 2:41 --toggle-gpio 3:97
run build/rp2040/io.elf --until '^NEVER$' --max-ns 100e6
run build/rp2040/sysctl.elf --until '^NEVER$' --max-ns 100e6
run build/rp2040/emu_selftest.elf --until 'EMU (PASS|FAIL)[^\n]*\n' --max-ns 200e6
run build/rp2040/emu_nested.elf --until 'NEST (PASS|FAIL)[^\n]*\n' --max-ns 100e6 --toggle-gpio 2:997
cmake -G Ninja -S emu/rp2040 -B "$B" -DRP2040EMU_PGO=use "-DRP2040EMU_PGO_DIR=$PROFILE" "$@" >/dev/null
ninja -C "$B" >/dev/null
echo "pgo.sh: $B built with the profile in $PROFILE"
