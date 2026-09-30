# MISO digital integration — 2026-09-30

Native `Machine::inputs` resolves enabled external buffers before applying passive bias. One active driver overrides either idle level. Multiple enabled buffers fail explicitly, with opposing levels distinguished from duplicate enabled drivers. RP2040 input/reset pad pulls determine buffer input while the external CS-controlled buffer remains selected.

Co-simulation recognizes the existing 74LVC1G125GW direct output and the exact SN74AHC1G125DCKR output through R60=270 ohms, with R61=10k from the connector MISO bus to GND. Unknown buffer families, wrong OE/power/input/output wiring, series bypasses/values and absent/incorrect ground bias are rejected. Each physical output and bias leg is checked against copper. Runtime idle remains high for old networks. A fitted new card with connected MISO and routed ground bias makes passive idle low, including a fitted card whose firmware cannot boot.

## Verification

- Native rebuild: `ninja -C build/emu-machine`, passed.
- Resolver regression: `c++ -std=c++17 -Wall -Wextra -Werror -Iemu/machine test/emu/test_miso_bus.cpp -o /tmp/cupc8-test-miso-bus`, then execute; active bits/bytes, both idle levels, disabled buffers and contention passed.
- `node test/emu/test_slotwiring.mjs`: fitted/absent, old/new network and disconnected bias cases passed.
- `python3 test/hw/test_cosim_miso.py`: two tests covering both supported card types and seven wiring fault mutations passed.
- `node test/emu/test_machine_native.mjs --ns 20e6 --type '' --expect ''`: serial and two threaded runs identical, passed.
- `node test/emu/test_machine_miso.mjs --top TOP`: actual ROM POST and IDENT/retry routines retained; test instrumented the code immediately after probing to verify all six slot-table entries. No cards: empty at320ms; fitted working GPU and passive00: only GPU detected at900ms, active C8 signature present; fitted unbooted GPU and passive00: all empty at1020ms.

Boot regression used the compatible historical Claude `scratchpad/cosim-w/top2.json` runtime as a development fixture with explicit proposed pull-down metadata. It is software evidence, not fresh manufacturing or analog evidence. The newly generated real AHC runtime must be retested after physical adoption and canonical board builds. Native digital resolution does not simulate OE propagation time, voltage thresholds or thermal behavior.
