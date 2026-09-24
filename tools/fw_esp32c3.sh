#!/usr/bin/env bash
# Build the Wi-Fi card firmware (ESP32-C3) with the pinned ESP-IDF.
#   tools/fw_esp32c3.sh [card|qemu]     card: the real image (default)
#                                       qemu: the emulated build (UART frames, OpenCores Ethernet)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SDK=${CUPC8_SDK:-$HOME/.local/share/cupc8-sdk}
"$ROOT/tools/fetch_sdks.sh" >/dev/null
export IDF_TOOLS_PATH=$SDK/espressif
# shellcheck disable=SC1091
. "$SDK/esp-idf/export.sh" >/dev/null 2>&1
VARIANT=${1:-card}
SRC=$ROOT/fw/wifi/port/esp32c3
OUT=$ROOT/build/esp32c3-$VARIANT
DEFAULTS="$SRC/sdkconfig.defaults"
[ "$VARIANT" = qemu ] && DEFAULTS="$DEFAULTS;$SRC/sdkconfig.qemu"
LOG=$OUT.log
mkdir -p "$ROOT/build"
# the defaults only apply to a fresh sdkconfig: a stale one in $OUT would
# silently keep old settings (it kept CONFIG_LWIP_SO_RCVBUF off after the
# defaults turned it on), so the image is always built from the defaults
rm -f "$OUT/sdkconfig"
if ! idf.py -C "$SRC" -B "$OUT" -D SDKCONFIG="$OUT/sdkconfig" -D SDKCONFIG_DEFAULTS="$DEFAULTS" build > "$LOG" 2>&1; then
	grep -E "error|Error|FAILED" "$LOG" | head -30
	exit 1
fi
if [ "$VARIANT" = qemu ]; then
	# one flash image for QEMU: bootloader, partition table, app
	(cd "$OUT" && esptool.py --chip esp32c3 merge_bin --fill-flash-size 4MB -o flash.bin @flash_args) >> "$LOG" 2>&1
fi
echo "built $OUT"
