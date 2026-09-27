# CUPC/8: working in this repository

## Running tests

- Run anything that takes more than a few seconds (emulated firmware tests,
  QEMU, formal proofs, place and route, long test suites) **in the
  background**, then carry on with other work while it runs. Check the result
  when it finishes; don't sit waiting on it in the foreground.
- Run single tests by name rather than whole suites, unless the whole suite
  is what's needed.
- **Software changes: the simulator first** (David, 2026-09-27). Test kernel,
  BASIC, ROM and program changes on the simulator (`tools/run_tests.sh`,
  `test/sim/*.py`) until they pass there; it is much faster. Only then run
  the emulator (native E2E) tests, as the final check.

## Emulator and simulator (David, 2026-09-25)

- **The emulator** (`emu/machine`, the native whole-machine emulator; the JS
  one in `test/emu/machine.mjs` is legacy) must be **cycle perfect for
  everything**: it runs the real RTL and the real card firmware, and it is
  what the end-to-end tests trust. The Wi-Fi card is no longer an
  exception (2026-09-26): its QEMU runs in step with the board
  (`emu/machine/README.md`, "The Wi-Fi card"; EMU-009). What cannot be in
  step is outside the machine: the host network behind QEMU's slirp, and
  cupc8.py's bytes on the system card's port.
- **The simulator** (`tools/sim`, `tools/sim.nim` + `tools/simcards.nim`) is
  David's **interactive** way to run real CUPC/8 software locally and build
  programs. It must be **kept up to date**: any change to the kernel, the
  boot ROM, the memory map, the chipset registers or a card's commands lands
  in the simulator in the same piece of work, with a simulator test.

