#!/usr/bin/env bash
# Set up a stock Ubuntu 24.04 machine (e.g. a cloud container) to run the test
# suite: apt packages, OSS CAD Suite in /opt/oss-cad-suite, Nim's sdl2
# wrapper, and the pinned SDKs (tools/fetch_sdks.sh). Idempotent; run as root.
#   tools/setup_ubuntu.sh            everything but KiCad (see doc/dev-environment.md)
# Needs: the Ubuntu archive, github.com (git and release downloads), pypi.org.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)

apt-get update -qq
apt-get install -y -qq nim gcc-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-newlib \
	libsdl2-dev ngspice cmake ninja-build python3-yaml poppler-utils libusb-1.0-0 libslirp0 >/dev/null

# OSS CAD Suite (GHDL, Yosys + ghdl plugin, Verilator, SBY, bitwuzla, nextpnr)
# at the path the scripts use. The distribution packages are too old: Yosys
# 0.33's smtbmc fails BUS-004's induction and speaks bitwuzla 0.1's options.
if [ ! -x /opt/oss-cad-suite/libexec/yosys ]; then
	tag=$(git ls-remote --tags https://github.com/YosysHQ/oss-cad-suite-build |
		awk -F/ '{print $3}' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort | tail -1)
	f=oss-cad-suite-linux-x64-${tag//-/}.tgz
	tmp=$(mktemp -d)
	curl -sSL -o "$tmp/$f" "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/$tag/$f"
	tar -xzf "$tmp/$f" -C /opt
	rm -rf "$tmp"
	echo "OSS CAD Suite $tag in /opt/oss-cad-suite"
fi

# Nim's sdl2 wrapper (tools/sim.nim); from git, as nimble's package index
# may be unreachable
if ! grep -qs nimpkgs/sdl2 ~/.config/nim/nim.cfg; then
	mkdir -p ~/.local/share/nimpkgs ~/.config/nim
	[ -d ~/.local/share/nimpkgs/sdl2 ] || git clone -q --depth 1 https://github.com/nim-lang/sdl2.git ~/.local/share/nimpkgs/sdl2
	grep -q nimpkgs/sdl2 ~/.config/nim/nim.cfg 2>/dev/null ||
		echo "--path:\"$HOME/.local/share/nimpkgs/sdl2/src\"" >>~/.config/nim/nim.cfg
fi

# ESP-IDF: its Python constraints come from dl.espressif.com; if that host is
# blocked, seed the stand-in (major versions for IDF 5.x) and skip Espressif's
# pip index. Both are used only when the real ones cannot be fetched.
SDK=${CUPC8_SDK:-$HOME/.local/share/cupc8-sdk}
mkdir -p "$SDK/espressif"
if ! curl -sSf -m 15 -o /dev/null https://dl.espressif.com/ 2>/dev/null; then
	cp -n "$ROOT/tools/devenv/espidf.constraints.v5.5.txt" "$SDK/espressif/" || true
	export IDF_PIP_WHEELS_URL=
fi
"$ROOT/tools/fetch_sdks.sh"
echo "done; KiCad 10 for the board tests: doc/dev-environment.md"
