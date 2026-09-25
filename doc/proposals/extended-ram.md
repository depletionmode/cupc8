# Extended RAM (option A in M1)

Status: **option A decided** (David, 2026-09-25: "implement the plan that
uses the current 512 KB chip") and **built** in M1, except the board wiring
(the main board's own work): see "As built" below. B and C stay plans.

## As built (option A)

- **Chipset** (`soc/chipset.vhd`): `RAM_BANK` at **$f205**, R/W, 5 bits
  (bits 7:5 read 0), **reset 2**. A CPU RAM cycle at $8000–$bfff goes to SRAM
  `RAM_BANK & A[13:0]`; every other RAM address to `000 & A` as before. The
  ROM windows, `ROM_OFF` RAM and I/O ignore it; no extra wait states.
  `memory-map.md` ("RAM banks") has the physical map and the rule that the
  kernel keeps nothing in the window.
- **Bridge** (`soc/bridge.vhd`): `$09 RAM_WR24` and `$0A RAM_RD24` take a
  19-bit physical address (bank × $4000 + offset), as the ROM commands do.
  `$01 RAM_WR`/`$02 RAM_RD` keep their meaning: SRAM $00000–$0ffff, wrapping
  there.
- **sysctl** (`fw/sysctl/core`): `$12 RAM_READ_FAR` (addr24, len16) and
  `$13 RAM_WRITE_FAR` (addr24, data), refused past $7ffff (`sysctl.md`).
  `cupc8.py ram read|write ADDR` takes a physical address up to $7ffff or
  `BANK:OFFSET`, and uses the far forms only past $0ffff.
- **Kernel** (`kernel/bank.s`): `api_bank_set` (r0 = bank; r0 = 1 if above
  31), `api_bank_get` (→ r0), `api_bank_count` (→ 32), `api_bank_far_copy`
  (source bank/offset, destination bank/offset and a 16-bit length in the API
  block at $6f00–$6f07; memmove semantics; ranges run on across banks; r0 = 1
  for a bad bank, an offset above $3fff or a range past $7ffff, with nothing
  copied). far_copy goes through a 256-byte buffer in kernel bss, in chunks
  that never cross a 256-byte page of either range, and puts the caller's
  `RAM_BANK` back. The jump table (`kernel/api.s`, `kernel-api.md`) gets them
  in group 0 as bank_set, bank_get, bank_count, far_copy.
- **Simulator** (`tools/sim.nim`): the same register and mapping in cards
  mode, with the 512 KB SRAM (`physRead`/`physWrite`).
- **Emulator**: the native emulator runs the chipset RTL; its SRAM model now
  uses all 19 address lines (`soc/emu/board.h`), as do the testbenches.
- **Tests**: MMU-005 (window decode for every bank and address line, reset
  value and a second reset, readback, aliasing of banks 0/1/3, nothing
  outside the window moves, ROM windows/ROM_OFF/I/O unaffected), MMU-004
  (formal: `mmu_ram_window`, `mmu_ram_flat`, `mmu_rom_fixed`,
  `mmu_rom_banked`, `mmu_io_not_memory`, `mmu_ram_bank_reset`), BRG-004
  (RAM_WR24/RAM_RD24), MUT-001 (mutants: the window ignoring RAM_BANK, reset
  value 0, the far commands cut to 16 bits), SYS-007 (sysctl far commands),
  HOST-002 (cupc8.py far addresses), SIM-005 (the simulator's mapping),
  KRN-008 (a pattern in all 32 banks through the kernel, far_copy's edge
  cases against memmove), E2E-009 (the whole machine: far writes from the
  PC, BASIC through the window, far reads back).

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
- **Later, RTL and kernel only:** a `RAM_BANK` register (e.g. $f205; built
  with reset 2) maps a **16 KB window at $8000–$bfff** to any of the 32 banks of 16 KB:
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
