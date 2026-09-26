#!/bin/bash
# Build and run in-repo tests that drive tools/as.py + the shipped sim.nim CPU.
# Runs side by side are safe: the build is one at a time (a lock), and each
# run executes its own copy of the binary, so a later build cannot replace
# it under a run; the tests write only to their own directory (simtest.nim
# workDir).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="${HOME}/.local/bin:${PATH}"
mkdir -p ../build
exec 9>../build/.simtest.lock
flock 9
nim c --hints:off simtest.nim
run=$(mktemp -d ../build/simtest-XXXXXX)
cp simtest "$run/simtest"
flock -u 9
exec 9>&-
status=0
"$run/simtest" "$@" || status=$?
rm -rf "$run"
exit $status
