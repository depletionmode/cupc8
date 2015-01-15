#!/bin/bash

cat *.s > merged.ss
python3 ../tools/as.py merged.ss kernel.o
rm merged.ss
