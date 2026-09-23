#!/usr/bin/env bash
# Fetch the pinned SDKs the real firmware builds and emulated tests need.
#   tools/fetch_sdks.sh            (idempotent; re-run after a version bump)
# Everything goes under $CUPC8_SDK (default ~/.local/share/cupc8-sdk), outside
# the repository. Versions are pinned so a build is repeatable.
set -euo pipefail

SDK=${CUPC8_SDK:-$HOME/.local/share/cupc8-sdk}
mkdir -p "$SDK"

clone() {   # clone <dir> <url> <tag or commit> [submodules...]
	local name=$1 dir=$SDK/$1 url=$2 ref=$3
	shift 3
	if [ ! -d "$dir/.git" ]; then
		git clone --quiet "$url" "$dir"
	fi
	git -C "$dir" fetch --quiet --tags origin
	git -C "$dir" -c advice.detachedHead=false checkout --quiet "$ref"
	for sub in "$@"; do
		git -C "$dir" submodule update --quiet --init --depth 1 "$sub"
	done
	echo "$name @ $(git -C "$dir" rev-parse --short HEAD)"
}

clone pico-sdk   https://github.com/raspberrypi/pico-sdk.git  2.2.0 lib/tinyusb
clone PicoDVI    https://github.com/Wren6991/PicoDVI.git      dccd738bfa9af75badcb32acde3e41bd6a3fa30a
clone rp2040js   https://github.com/wokwi/rp2040js.git        v1.1.1

# rp2040js is single-core upstream (wokwi/rp2040js#109); our patch adds core 1,
# the inter-core FIFOs, per-core SIO divider/interpolators, SEV/WFE between
# cores and the PSM reset of core 1 (tools/patches/rp2040js-dualcore.patch)
PATCH=$(cd "$(dirname "$0")" && pwd)/patches/rp2040js-dualcore.patch
if git -C "$SDK/rp2040js" apply --check "$PATCH" 2>/dev/null; then
	git -C "$SDK/rp2040js" apply "$PATCH"
	rm -rf "$SDK/rp2040js/dist"
elif ! git -C "$SDK/rp2040js" apply --reverse --check "$PATCH" 2>/dev/null; then
	echo "rp2040js: the dual-core patch does not apply" >&2
	exit 1
fi
if [ ! -d "$SDK/rp2040js/node_modules" ]; then
	(cd "$SDK/rp2040js" && npm ci --silent)
fi
if [ ! -d "$SDK/rp2040js/dist" ]; then
	(cd "$SDK/rp2040js" && npm run --silent build)
fi
