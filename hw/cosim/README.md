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
The generator separates `runtime_nets`, whose netlist values affect the
machine, from `structural_only_nets`, which have only a connectivity check.
All named nets without an executed model appear in `unmodeled_nets`, including
the structural-only subset. E2E-001 through E2E-004 use `--require-coverage`
and fail until each remaining net has a model or an explicit reviewed waiver.
This keeps local card and power circuits from being silently counted as covered.

The Type-C source input in E2E-004 passes through the extracted Rd/averaging/
reference network before it reaches the chipset's `PWR_HI` pin. The nominal
trip is 1.289 V on the active CC line; the test drives the 3 A minimum or
1.5 A maximum CC voltage, so a bad resistor network changes the class.
The main-board supervisor U6 reset output must connect to chipset U7's nPOR
input in the KiCad netlist **and** over measured routed copper. The manifest
passes `por_connected` to the native machine's reset input. On the routed
snapshot the shortest planar path is 88.152 mm; removing the supervisor
launch track makes `por_connected` false, and the native CPU stays at reset
PC `$E000` instead of reaching `$E2B9` in the 20 ms probe.
The IO card's USB host data pair must pass from the RP2040 pins through the
27 Ω series resistors to the receptacle. That netlist path controls keyboard
attachment in the native machine; an open path leaves it disconnected.
The storage card's seven SD signal contacts similarly control whether the
microSD socket is attached to its RP2040 model.
All four HDMI differential pairs, including the clock pair, must pass through
their 270 Ω series pack channels to the receptacle before the TMDS capture
endpoint attaches. Seven e-paper data/control lines through 33 Ω resistors
likewise control whether the panel attaches.
E2E-002 and E2E-003 capture the native HDMI frame after the BASIC program or
network page, replay the
observed GPU-slot SPI traffic through the independent host GPU core, and
compares all 640×480 decoded TMDS pixels at RGB222 precision. A fast mutation
test changes one SPI PUTC byte and requires the pixel comparison to fail.

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
and a missing MISO pull are rejected. With `--main-board` it also opens the
supervisor's routed nPOR launch. The third proves that ROM and CPU
address/data swaps, slot SCK/MOSI swaps, bridge SCK/MOSI swaps and an open
nPOR path change the running machine. The manifest currently covers the CPU,
main memory, slot data paths, system bridge, Type-C source class and
supervisor nPOR release. Other power and reset circuits still use native
machine wiring. On the current routed-board snapshot, all required top-level
routes are present, but 503 named nets remain without executed models or
reviewed waivers. E2E-001 through E2E-004 therefore remain pending behind
`--require-coverage` despite passing narrower runtime probes.
