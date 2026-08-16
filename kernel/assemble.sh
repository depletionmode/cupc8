#!/bin/bash

rm -f merged.ss
for f in *.s; do
  echo "; @file $f" >> merged.ss
  cat "$f" >> merged.ss
  printf '\n' >> merged.ss
done
python3 ../tools/as.py merged.ss kernel.o --map
#rm merged.ss
