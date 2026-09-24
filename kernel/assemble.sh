#!/bin/bash

rm -f merged.ss
for f in *.s; do
  echo "; @file $f" >> merged.ss
  cat "$f" >> merged.ss
  printf '\n' >> merged.ss
done
# code $1000-$3fff, data from $4000, bss from $6000 (as.py's defaults leave 8 KB for code)
python3 ../tools/as.py merged.ss kernel.o 0x1000,0x4000,0x6000 --map
#rm merged.ss
