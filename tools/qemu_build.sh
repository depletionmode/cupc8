#!/usr/bin/env bash
# Build the Wi-Fi card's QEMU for the native whole-machine emulator: Espressif's
# QEMU at the tag the SDK's binary comes from (tools/fetch_sdks.sh), with
# tools/patches/qemu-esp-lockstep.patch (the `-chardev cupc8` that keeps it in
# step with emu/machine; see emu/machine/README.md, "The Wi-Fi card"). The
# SDK's binary cannot be used: it has no such chardev.
#
# Built once per patch into $SDK/qemu-esp-lockstep/<hash>, then linked as
# build/qemu-esp (bin/qemu-system-riscv32).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SDK=${CUPC8_SDK:-$HOME/.local/share/cupc8-sdk}
REPO=https://github.com/espressif/qemu
TAG=esp-develop-9.2.2-20260417
COMMIT=40edccac415693c5130f91c01d84176ae6008566
PATCH=$ROOT/tools/patches/qemu-esp-lockstep.patch
KEY=$( (echo $COMMIT; cat "$PATCH") | sha256sum | cut -c1-12)
OUT=$SDK/qemu-esp-lockstep/$KEY
BIN=$OUT/bin/qemu-system-riscv32

if [ ! -x "$BIN" ]; then
	SRC=$SDK/qemu-esp-src
	if [ ! -d "$SRC/.git" ]; then
		git clone --quiet --depth 1 --branch $TAG $REPO "$SRC"
	fi
	[ "$(git -C "$SRC" rev-parse HEAD)" = $COMMIT ] || { echo "$SRC is not $TAG ($COMMIT)" >&2; exit 1; }
	rm -rf "$OUT"
	mkdir -p "$OUT"
	git -C "$SRC" worktree prune
	git -C "$SRC" worktree add --quiet --detach "$OUT/src" $COMMIT
	git -C "$OUT/src" apply "$PATCH"
	mkdir -p "$OUT/build"
	LOG=$OUT/build.log
	(cd "$OUT/build" && ../src/configure --prefix="$OUT" --bindir=bin --datadir=share/qemu --with-suffix="" \
		--target-list=riscv32-softmmu --without-default-features --enable-tcg --enable-slirp --enable-gcrypt \
		--enable-pixman --disable-docs --disable-werror && ninja install) > "$LOG" 2>&1 || { tail -30 "$LOG"; exit 1; }
fi
mkdir -p "$ROOT/build"
ln -sfn "$OUT" "$ROOT/build/qemu-esp"
echo "built $BIN"
