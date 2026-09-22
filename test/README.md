# Tests

Every test in the project is listed in **`catalogue.toml`**: the CPU, ALU,
chipset blocks (MMU, SPI, IRQ, ROM windows, bridge, debug), the CPU bus, boot
ROM, kernel, each card's firmware, sysctl, host tools, the whole system, and
**each board** (main board, CPU card, GPU card, IO card, Wi-Fi card).

| Command | What it does |
|---|---|
| `make test` | run every implemented test |
| `make verify` | the fab gate: also fails while any non-hardware test is still pending |
| `make test-list` | list all tests and whether they're implemented |
| `test/run.py CPU MB-0` | run only tests whose id starts with a prefix |
| `test/run.py --kind hw MB-1` | hardware bring-up tests, run on the real boards |

Logs are written to `build/test/<id>.log`, and a summary to
`build/test/results.json`.

## Adding a test

1. Add or edit its entry in `catalogue.toml`, keeping the id prefix of its
   block or board.
2. Implement it, and give the entry a `cmd` that exits 0 on pass. The entry
   stays "pending" until it has a `cmd`.

## Kinds

| Kind | Meaning |
|---|---|
| sim | simulation or unit test |
| static | checks on design files (ERC, DRC, BOM, pins, fab package) |
| formal | SymbiYosys proofs |
| hw | bring-up on real boards after delivery (not part of the pre-fab gate) |

The contract these tests implement is `doc/hardware/verification.md`.

## Where the pieces live

- `test/*.s`: the original 2016 CPU test programs, used by CPU-001.
- `tools/testdata/*.s`: the simulator's test programs, used by SIM-001 and
  CPU-001.
- `soc/tb/`: VHDL testbenches.
- `test/board-test/`: the 2016 memory-board scripts (historical).
