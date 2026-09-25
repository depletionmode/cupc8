# CUPC/8: working in this repository

## Running tests

- Run anything that takes more than a few seconds (emulated firmware tests,
  QEMU, formal proofs, place and route, long test suites) **in the
  background**, then carry on with other work while it runs. Check the result
  when it finishes; don't sit waiting on it in the foreground.
- Run single tests by name rather than whole suites, unless the whole suite
  is what's needed.

## Emulator and simulator (David, 2026-09-25)

- **The emulator** (`emu/machine`, the native whole-machine emulator; the JS
  one in `test/emu/machine.mjs` is legacy) must be **cycle perfect for
  everything**: it runs the real RTL and the real card firmware, and it is
  what the end-to-end tests trust.
- **The simulator** (`tools/sim`, `tools/sim.nim` + `tools/simcards.nim`) is
  David's **interactive** way to run real CUPC/8 software locally and build
  programs. It must be **kept up to date**: any change to the kernel, the
  boot ROM, the memory map, the chipset registers or a card's commands lands
  in the simulator in the same piece of work, with a simulator test.

