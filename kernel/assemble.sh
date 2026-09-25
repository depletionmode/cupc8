#!/bin/bash

rm -f merged.ss
for f in *.s; do
  echo "; @file $f" >> merged.ss
  cat "$f" >> merged.ss
  printf '\n' >> merged.ss
done
# code $1000-$4fff (the API jump table first), data $5000-$5fff, bss
# $6000-$6eff; $6f00 is the API block, $7000 the user program
# (doc/hardware/memory-map.md). testKernelLayout checks the limits.
python3 ../tools/as.py merged.ss kernel.o 0x1000,0x5000,0x6000 --map
#rm merged.ss
