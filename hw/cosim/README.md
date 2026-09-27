# Schematic-derived wiring prerequisite

`gen_top.py` exports fresh KiCad netlists for the seven cards and reads the
main-board netlist. It joins contacts by physical pad number, including the
system socket's x4 pad translation. It checks the shared slot buses, their
chipset series resistors, the weak MISO pull, CPU socket and resistor packs,
and SRAM/ROM attachment. Its JSON manifest lists contact joins and the
verified model attachment paths. A broken connection exits nonzero.

From the repo root, after building the main board:

```
python3 hw/cosim/gen_top.py --output build/hw/cosim/top.json
python3 test/hw/test_cosim_wiring.py
```

The second command proves swapped SCK/MOSI contacts, a missing chip select,
and a missing MISO pull are rejected. The generated manifest is a wiring
prerequisite. The native emulator still uses its hardcoded board interconnect;
it does not yet consume the manifest or model trace delay and weak pulls.
Consequently E2E-001 through E2E-004 remain pending as full co-simulation
rows. The native emulator's E2E-002A, E2E-003A and E2E-004A cover the
functional scenarios separately.
