#!/usr/bin/env bash
# Build the whole-machine emulator's main board (build/emu/core.node): the
# CPU + chipset RTL synthesised by GHDL, compiled by Verilator, and wrapped
# with the memory models as a Node addon (soc/emu/core.cpp).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OSS=/opt/oss-cad-suite/bin
OUT=$ROOT/build/emu
NODE_INC=$(dirname "$(dirname "$(command -v node)")")/include/node
mkdir -p "$OUT"
cd "$OUT"
"$OSS/ghdl" synth --std=08 --out=verilog \
	"$ROOT"/soc/alu.vhd "$ROOT"/soc/cpu.vhd "$ROOT"/soc/spi_master.vhd "$ROOT"/soc/bridge.vhd \
	"$ROOT"/soc/chipset.vhd "$ROOT"/soc/emu/machine_core.vhd -e machine_core > machine_core.v
"$OSS/verilator" --cc -O3 -Wno-fatal -Wno-lint -Wno-style --top-module machine_core \
	-CFLAGS "-fPIC -O2" machine_core.v > verilator.log 2>&1
make -s -C obj_dir -f Vmachine_core.mk Vmachine_core__ALL.a verilated.o verilated_threads.o > make.log 2>&1
VINC=$("$OSS/verilator" --getenv VERILATOR_ROOT)/include
gcc -c -fPIC -O2 -o sysmodels.o "$ROOT"/fw/test/sysmodels.c
g++ -shared -fPIC -O2 -std=c++17 -o core.node "$ROOT"/soc/emu/core.cpp sysmodels.o \
	-I obj_dir -I "$VINC" -I "$VINC/vltstd" -I "$NODE_INC" -I "$ROOT"/fw/test \
	obj_dir/Vmachine_core__ALL.a obj_dir/verilated.o obj_dir/verilated_threads.o -lpthread
echo "built $OUT/core.node"
