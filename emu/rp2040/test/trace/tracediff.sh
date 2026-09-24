#!/usr/bin/env bash
# EMU-004: the native RP2040 emulator (emu/rp2040) is cycle-identical to
# rp2040js on real firmware images. Each case runs in both, tracing
# "<ns> <pc0> <pc1>" every 97 steps, and the traces and UART output must match
# byte for byte.
#   emu/rp2040/test/trace/tracediff.sh [case...]    (default: all)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$ROOT"
cmake -G Ninja -S emu/rp2040 -B build/emu-native >/dev/null
ninja -C build/emu-native rp2040run >/dev/null
OUT=build/emu-native/tracediff
mkdir -p "$OUT"

# name ; elf ; until ; max ns ; extra options
CASES=(
	'selftest;emu_selftest.elf;EMU (PASS|FAIL)[^\n]*\n;200e6;'
	'nested;emu_nested.elf;NEST (PASS|FAIL)[^\n]*\n;500e6;--toggle-gpio 2:997'
	'gpu;gpu.elf;^NEVER$;100e6;--mhz 252'
	'io;io.elf;^NEVER$;100e6;'
	'sysctl;sysctl.elf;^NEVER$;100e6;'
)
want=("$@")
bad=0
for c in "${CASES[@]}"; do
	IFS=';' read -r name elf until ns extra <<<"$c"
	if [ ${#want[@]} -gt 0 ] && [[ ! " ${want[*]} " == *" $name "* ]]; then continue; fi
	# shellcheck disable=SC2086
	build/emu-native/rp2040run "build/rp2040/$elf" --until "$until" --max-ns "$ns" $extra --trace-every 97 \
		2>"$OUT/$name.native.trace" >"$OUT/$name.native.out" || true
	# shellcheck disable=SC2086
	node emu/rp2040/test/trace/trace.mjs "build/rp2040/$elf" --until "$until" --max-ns "$ns" $extra --trace-every 97 \
		2>"$OUT/$name.js.trace" >"$OUT/$name.js.out" || true
	n=$(wc -l <"$OUT/$name.js.trace")
	if cmp -s "$OUT/$name.native.trace" "$OUT/$name.js.trace" && cmp -s "$OUT/$name.native.out" "$OUT/$name.js.out" && [ "$n" -gt 0 ]; then
		echo "pass $name: $n trace points identical, UART identical"
	else
		bad=$((bad + 1))
		echo "FAIL $name: traces or UART differ (first difference below; files in $OUT)"
		diff "$OUT/$name.native.trace" "$OUT/$name.js.trace" | head -4 || true
	fi
done
echo "EMU-004: $bad failure(s)"
exit $((bad > 0))
