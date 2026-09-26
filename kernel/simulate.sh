#!/bin/bash
# Assemble the kernel and run it on the simulator. Works from any directory:
# the kernel is built in kernel/, and the simulator runs from where this was
# started, so relative paths in the options (--sd:card.img) mean what they say.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
(cd "$here" && ./assemble.sh)
exec "$here/../tools/sim" "$@" "$here/kernel.o"
