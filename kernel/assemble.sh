#!/bin/bash

rm -f merged.ss
for f in *.s; do
  echo "; @file $f" >> merged.ss
  cat "$f" >> merged.ss
  printf '\n' >> merged.ss
done
# code $1000-$4fff, data $5000-$5fff, bss $6000-$6eff (doc/proposals/kernel-api.md)
python3 ../tools/as.py merged.ss kernel.o 0x1000,0x5000,0x6000 --map
#rm merged.ss
