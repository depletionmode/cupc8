#!/bin/bash

res=`python3 as.py $1`
outf=`echo $res | cut -d' ' -f3`
echo $res
shift
if [ ! -f sim ]; then
	nim c -d:release sim.nim
fi
./sim $outf $@

