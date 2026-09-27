# Schematic-derived wiring prerequisite

`gen_top.py` exports fresh KiCad netlists for the seven cards and reads the
main-board netlist. It joins contacts by physical pad number, including the
system socket's x4 pad translation. It checks the shared slot buses, their
chipset series resistors, the weak MISO pull, CPU socket and resistor packs,
and SRAM/ROM attachment. Its JSON manifest lists contact joins and the
verified model attachment paths. A broken connection exits nonzero.

The native RTL machine consumes the manifest when `CUPC8_COSIM_TOP` points to
it. CPU address/data wires and SRAM/ROM address/data pins use physical bit
maps read from KiCad pads. Slot SPI/IRQ and system bridge lines use their
connector maps. The shared MISO idle level comes from the verified 47 kΩ
pull-up. Cards receive edges after the 33 Ω source RC delay (1.089 ns for a
15 pF input). SRAM and ROM reads wait their 45 ns and 70 ns maximum access
times plus routed copper delay (7 ps/mm). A memory bus with no routed copper
gets provisional access times and `routed_timing: false`. The manifest lists
unrouted CPU, memory, slot, bridge, clock, reset and power-policy signal nets
under `missing_routes`; `--require-route` rejects them.
The generator also lists every named net that is not attached to an executed
model path under `unmodeled_nets`. E2E-001 uses `--require-coverage` and fails
until each remaining net has a model or an explicit reviewed waiver. This
keeps local card and power circuits from being silently counted as covered.

The Type-C source input in E2E-004 passes through the extracted Rd/averaging/
reference network before it reaches the chipset's `PWR_HI` pin. The nominal
trip is 1.289 V on the active CC line; the test drives the 3 A minimum or
1.5 A maximum CC voltage, so a bad resistor network changes the class.

From the repo root, after building the main board:

```
python3 hw/cosim/gen_top.py --output build/hw/cosim/top.json
python3 test/hw/test_cosim_wiring.py
python3 test/hw/test_cosim_runtime.py --top build/hw/cosim/top.json
# after the main route is complete:
python3 hw/cosim/gen_top.py --require-route --output build/hw/cosim/top.json
CUPC8_COSIM_TOP=build/hw/cosim/top.json CUPC8_EMU=native node test/emu/test_e2e.mjs E2E-002
# The catalogue can use this strict entry point for each row:
python3 hw/cosim/run.py E2E-001
python3 hw/cosim/run.py E2E-002
python3 hw/cosim/run.py E2E-003
python3 hw/cosim/run.py E2E-004
```

The second command proves swapped SCK/MOSI contacts, a missing chip select,
and a missing MISO pull are rejected. The third proves that ROM and CPU
address/data swaps, slot SCK/MOSI swaps and bridge SCK/MOSI swaps change the
running machine's result. The manifest currently
covers the CPU, main memory, slot data paths and system bridge. Power and
reset circuits still use native machine wiring except the Type-C class input,
and the current main-board
route lacks memory copper. E2E-001 through E2E-004 remain pending until those
paths and the full programs are exercised with a final routed board.
