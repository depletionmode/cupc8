# Extended RAM (plan, not in M1)

Status: **plan only** (David, 2026-09-25: "plan support, not added yet").
Nothing here is built; the one M1 question is whether to wire the SRAM's
top address pins now (below).

## What the machine has

- The CPU has a 16-bit address space: RAM $0000–$dfff (56 KB), the ROM
  windows over $e000–$efff until the kernel turns them off, I/O at $f000.
- The main board's SRAM is an **IS62WV5128 (512 KB)**, of which 64 KB is
  used: its A16–A18 are **tied to GND** on the board (`parts.md`).
- The chipset already drives a **19-bit memory address** (MEM_A[18:0], for
  the 512 KB ROM behind `ROM_BANK`) and puts **0 on A16–A18 for every RAM
  cycle** (`soc/chipset.vhd`: `phys := "000" & a`).
- The CPU socket carries the CPU bus to the chipset; a card never drives the
  memory bus (`cpu-bus.md`). The x1 slots are SPI only.

## Options

### A. Bank the main board's SRAM (recommended)

**+448 KB, no new parts.**

- **M1 board change (the only one):** connect the SRAM's A16–A18 to
  MEM_A16–A18 instead of GND. Three traces. M1 behaves exactly the same,
  because the chipset drives 0 there on RAM cycles.
- **Later, RTL and kernel only:** a `RAM_BANK` register (e.g. $f205, reset
  0) maps a **16 KB window at $8000–$bfff** to any of the 32 banks of 16 KB:
  physical = `RAM_BANK << 14 | A[13:0]` inside the window, and the normal
  64 KB outside it. Banks 0–3 are the normal memory, so `RAM_BANK = 2`
  (the window's own) is the power-on identity map. The window sits inside
  the user area, so a program keeps its code at $7000–$7fff and
  $c000–$dfff and pages data (or overlays) through $8000–$bfff.
- **Kernel API** (system group, `kernel-api.md`): `bank_set`, `bank_get`,
  `bank_count`, and a `far_copy` between any two (bank, offset) pairs. The
  kernel never keeps anything in the window, so interrupts need not save
  the bank.
- **System card:** `RAM_READ`/`RAM_WRITE` gain a 24-bit form (as ROM has),
  so `cupc8.py` can load and inspect any bank.
- **Emulator:** the native emulator runs the chipset RTL, so it follows
  automatically; `tools/sim.nim` gets the same mapping.
- **Tests:** bus conformance and formal (the window decode, the identity
  map at reset, no aliasing with the ROM windows or I/O), a kernel test
  writing a pattern to all 32 banks and reading it back, `far_copy` edge
  cases, the bridge's 24-bit access.

### B. More than 512 KB (1–2 MB)

The same design with a bigger chip and more address lines: a 1 M×8 or
2 M×8 3.3 V SRAM (JLC stock and price to check; 8-bit parts this size are
rarer, and 45–55 ns is needed for the 4-clock cycle), plus MEM_A19–A20 on
spare chipset I/O (the HX4K has 12 free). `RAM_BANK` grows to 6–7 bits;
nothing else changes. A later main board revision, not a card.

### C. A "memory card" in an x1 slot

An RP2040 + 8 MB PSRAM (APS6404L) as a slot card: **not memory-mapped**
(the slot is SPI), so the CPU copies blocks in and out with slot commands
at ~100–200 KB/s, like a RAM disk. Useful for large data and swapping
overlays, with no board change. Card type $05, the common slot protocol.
Slower and less convenient than A for programs, and it cannot hold code
the CPU runs directly.

## Recommendation

**Do A's board change now** (three traces on the main board, free), and
leave the register, the kernel API and the tests for when programs need the
memory. B is a later board revision; C only if a big data store is wanted.
