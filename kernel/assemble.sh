#!/bin/bash
# kernel/assemble.sh [OUTDIR]: merge kernel/*.s and assemble them into
# OUTDIR/kernel.o and OUTDIR/kernel.map (with OUTDIR/merged.ss). OUTDIR
# defaults to kernel/ itself (simulate.sh, debug.sh); tests build in a private
# directory of their own (tools/simmachine.nim buildKernel, test/emu/
# romimage.mjs), so builds running side by side cannot clobber each other.
set -e
KDIR=$(cd "$(dirname "$0")" && pwd)
OUT=$(mkdir -p "${1:-$KDIR}" && cd "${1:-$KDIR}" && pwd)
cd "$KDIR"
rm -f "$OUT/merged.ss"
for f in *.s; do
  echo "; @file $f" >> "$OUT/merged.ss"
  cat "$f" >> "$OUT/merged.ss"
  printf '\n' >> "$OUT/merged.ss"
done
# code $1000-$67ff (the API jump table first), data $6800-$6eff, bss
# $e000-$efff (RAM once the ROM is off); $6f00 is the API block, $7000 the
# user program
# (doc/hardware/memory-map.md). testKernelLayout checks the limits.
cd "$OUT"
python3 "$KDIR"/../tools/as.py merged.ss kernel.o 0x1000,0x6800,0xe000 --map
