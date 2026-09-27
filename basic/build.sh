#!/bin/bash
# basic/build.sh [OUTDIR]: BASIC as a program for $7000 (tools/mkprg.py, with
# kernel/api.inc in front) into OUTDIR/BASIC.PRG, its map OUTDIR/basic.map.
# OUTDIR defaults to build/basic. The ROM image carries it (tools/mkrom.py
# --basic); a copy named BASIC.PRG on the SD card replaces the ROM's at boot
# (doc/proposals/basic-program.md, doc/hardware/memory-map.md). Like any
# program it needs nothing of the kernel's but kernel/api.inc.
set -e
BDIR=$(cd "$(dirname "$0")" && pwd)
ROOT="$BDIR/.."
OUT=$(mkdir -p "${1:-$ROOT/build/basic}" && cd "${1:-$ROOT/build/basic}" && pwd)
python3 "$ROOT/tools/mkprg.py" "$BDIR/n16.s" "$BDIR/basic.s" "$BDIR/ubasic.s" "$BDIR/ubasic_tokenizer.s" \
  -o "$OUT/BASIC.PRG" --map "$OUT/basic.map"
