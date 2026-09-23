#!/usr/bin/env bash
# Build the RP2040 card firmware (the real flash images) into build/rp2040.
#   tools/fw_rp2040.sh [target...]      (default: all)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
"$ROOT/tools/fetch_sdks.sh" >/dev/null
cmake -S "$ROOT/fw/rp2040" -B "$ROOT/build/rp2040" -G Ninja >/dev/null
ninja -C "$ROOT/build/rp2040" "$@" | tail -1
