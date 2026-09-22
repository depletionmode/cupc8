#!/bin/bash
# Analyse, elaborate and run one GHDL testbench.
#   soc/tb/run_ghdl.sh <top> <file.vhd>... [-- <run options, e.g. -gNAME=value>]
# Work files go to build/ghdl/<top>. The build is locked and skipped when up
# to date, so several tests can share a testbench and run in parallel.
# Exit status is the simulation's.
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
(
	flock 9
	newest=$(ls -t "${files[@]}" | head -1)
	if [ ! -x "$top" ] || [ "$newest" -nt "$top" ]; then
		"$GHDL" -a --std=08 -fsynopsys "${files[@]}"
		"$GHDL" -e --std=08 -fsynopsys "$top"
	fi
) 9>"$work/.lock"
exec ./"$top" --ieee-asserts=disable "$@"
