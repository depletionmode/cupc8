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

# a host FAT reader for the storage card tests (IOC/E2E: images written by the
# card's FatFs checked on the host, and the reverse): pyfatfs in a venv, pinned
# (setuptools < 81: pyfilesystem2 still needs pkg_resources)
if [ ! -f "$SDK/pyfat/.cupc8-pyfatfs-1.1.0" ]; then
	python3 -m venv "$SDK/pyfat"
	"$SDK/pyfat/bin/pip" install --quiet pyfatfs==1.1.0 fs==2.4.16 appdirs==1.4.4 six==1.17.0 setuptools==80.9.0
	touch "$SDK/pyfat/.cupc8-pyfatfs-1.1.0"
fi
echo "pyfatfs @ 1.1.0 ($SDK/pyfat)"

# ESP-IDF for the Wi-Fi card (ESP32-C3), with its RISC-V toolchain and
# Espressif's QEMU; tools under $SDK/espressif, not ~/.espressif
if [ "${CUPC8_SKIP_IDF:-0}" != 1 ]; then
	IDF_VERSION=v5.5.5
	if [ ! -d "$SDK/esp-idf/.git" ]; then
		git clone --quiet --depth 1 --branch $IDF_VERSION https://github.com/espressif/esp-idf.git "$SDK/esp-idf"
	fi
	[ "$(git -C "$SDK/esp-idf" describe --tags)" = $IDF_VERSION ] || { echo "esp-idf is not $IDF_VERSION" >&2; exit 1; }
	echo "esp-idf @ $IDF_VERSION"
	if [ ! -f "$SDK/esp-idf/.cupc8-submodules" ]; then
		git -C "$SDK/esp-idf" submodule update --quiet --init --recursive --depth 1
		touch "$SDK/esp-idf/.cupc8-submodules"
	fi
	export IDF_TOOLS_PATH=$SDK/espressif
	if [ ! -f "$IDF_TOOLS_PATH/.cupc8-tools" ]; then
		(cd "$SDK/esp-idf" && ./install.sh esp32c3 >/dev/null)
		python3 "$SDK/esp-idf/tools/idf_tools.py" install qemu-riscv32 >/dev/null
		touch "$IDF_TOOLS_PATH/.cupc8-tools"
	fi
fi
