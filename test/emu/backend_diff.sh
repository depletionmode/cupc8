#!/usr/bin/env bash
# EMU-006: the card tests give the same result on the native emulator as on
# rp2040js. Each test runs on both backends (test/emu/emu_backend.mjs) with
# CUPC8_EMU_TRACE=1 (every runUntil result with its emulated time, every host
# frame, a digest of every TMDS capture) and DEBUG=1; stdout and the trace
# must be byte-identical, and both must pass.
#   test/emu/backend_diff.sh [gpu|io|sysctl ...]    (default: all)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
tools/fw_rp2040.sh gpu io sysctl >/dev/null
cmake -G Ninja -S emu/rp2040 -B build/emu-native >/dev/null
ninja -C build/emu-native rp2040emu_node >/dev/null
OUT=build/emu-native/backend-diff
mkdir -p "$OUT"
want=" ${*:-gpu io sysctl} "
bad=0
for t in gpu io sysctl; do
	[[ $want == *" $t "* ]] || continue
	for b in js native; do
		CUPC8_EMU=$b CUPC8_EMU_TRACE=1 DEBUG=1 node "test/emu/test_$t.mjs" >"$OUT/$t.$b.out" 2>"$OUT/$t.$b.trace" &&
			echo 0 >"$OUT/$t.$b.rc" || echo $? >"$OUT/$t.$b.rc"
	done
	if cmp -s "$OUT/$t.js.out" "$OUT/$t.native.out" && cmp -s "$OUT/$t.js.trace" "$OUT/$t.native.trace" &&
		[ "$(cat "$OUT/$t.js.rc")" = 0 ] && [ "$(cat "$OUT/$t.native.rc")" = 0 ]; then
		echo "pass $t: $(tail -1 "$OUT/$t.native.out"); $(wc -l <"$OUT/$t.native.trace") trace lines identical"
	else
		bad=$((bad + 1))
		echo "FAIL $t: rc js $(cat "$OUT/$t.js.rc") native $(cat "$OUT/$t.native.rc"); first difference:"
		diff "$OUT/$t.js.out" "$OUT/$t.native.out" | head -3 || true
		diff "$OUT/$t.js.trace" "$OUT/$t.native.trace" | head -3 || true
	fi
done
echo "EMU-006: $bad failure(s)"
exit $((bad > 0))
