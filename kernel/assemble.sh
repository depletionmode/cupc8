#!/bin/bash

cat *.s > in.ss
python3 ../tools/as.py in.ss kernel.o
rm in.ss
