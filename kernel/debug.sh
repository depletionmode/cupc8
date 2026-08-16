#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
./assemble.sh
exec ../tools/simtui "$@" kernel.o
