#!/bin/bash

rm -f merged.ss
for f in *.s; do
  echo "; @file $f" >> merged.ss
  cat "$f" >> merged.ss
  printf '\n' >> merged.ss
done
# code $1000-$5dff (the API jump table first), data $5e00-$63ff, bss
# $6400-$6eff; $6f00 is the API block, $7000 the user program
# (doc/hardware/memory-map.md). testKernelLayout checks the limits.
python3 ../tools/as.py merged.ss kernel.o 0x1000,0x5e00,0x6400 --map
#rm merged.ss
