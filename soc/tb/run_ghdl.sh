#!/bin/bash
# Analyse, elaborate and run one GHDL testbench.
#   soc/tb/run_ghdl.sh <top> <file.vhd>... [-- <run options>]
# Work files go to build/ghdl/<top>. Exit status is the simulation's.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GHDL=/opt/oss-cad-suite/bin/ghdl
top="$1"; shift
files=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do files+=("$(realpath "$1")"); shift; done
[ "${1:-}" = "--" ] && shift
work="$ROOT/build/ghdl/$top"
mkdir -p "$work"
cd "$work"
"$GHDL" -a --std=08 -fsynopsys "${files[@]}"
"$GHDL" -e --std=08 -fsynopsys "$top"
exec "$GHDL" -r --std=08 -fsynopsys "$top" --ieee-asserts=disable "$@"
