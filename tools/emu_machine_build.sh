#!/usr/bin/env bash
# Build the native whole-machine emulator (emu/machine): the Verilated main
# board (tools/emu_build.sh, also build/emu/core.node for machine.mjs), then
# build/emu-machine/machine.node (test/emu/machinenative.mjs) and
# build/emu-machine/machinerun.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
"$ROOT/tools/emu_build.sh" >/dev/null
cmake -G Ninja -S "$ROOT/emu/machine" -B "$ROOT/build/emu-machine" >/dev/null
ninja -C "$ROOT/build/emu-machine" >"$ROOT/build/emu-machine/ninja.log" 2>&1 || { cat "$ROOT/build/emu-machine/ninja.log"; exit 1; }
echo "built $ROOT/build/emu-machine/machine.node"
