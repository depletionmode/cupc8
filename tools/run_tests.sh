#!/bin/bash
# Build and run in-repo tests that drive tools/as.py + the shipped sim.nim CPU.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="${HOME}/.local/bin:${PATH}"
nim c --hints:off simtest.nim
exec ./simtest "$@"
