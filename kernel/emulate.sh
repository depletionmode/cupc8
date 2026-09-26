#!/bin/bash
# Assemble the kernel, bring the card firmware and the native emulator up to
# date (incremental: a few seconds when nothing changed), and watch the
# machine in a browser (tools/machine_view.mjs --native). Works from any
# directory: the viewer runs from where this was started, so relative paths
# in the options (--sd card.img) mean what they say. The viewer builds its
# ROM image from kernel/ itself; assembling here first stops on a kernel
# error before anything starts.
#
#   kernel/emulate.sh --slots hdmi,io,storage,wifi --sd card.img
#   kernel/emulate.sh --slots eink,io,storage --sd card.img --console
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/.."
log="$root/build/emulate.log"
mkdir -p "$root/build"
step() {   # run a build step quietly; on failure show its output and stop
  if ! "$@" >"$log" 2>&1; then cat "$log" >&2; echo "emulate.sh: $* failed" >&2; exit 1; fi
}
step bash -c "cd '$here' && ./assemble.sh"
step "$root/tools/fw_rp2040.sh"
step "$root/tools/emu_machine_build.sh"
exec node "$root/tools/machine_view.mjs" --native "$@"
