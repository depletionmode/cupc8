# BASIC as a loadable program

Status: **decided 2026-09-26 by David** ("do 1, 4 and 5": the code area
to $67ff, BASIC as a program, and shrinking the kernel's code); **built
2026-09-26** (below, "As built"), with: "the
kernel should auto load its ROM BASIC after boot unless there is a BASIC on
the SD card (the SD card and the storage board are optional)". It follows the line-editing work (BASIC keeps lines sorted,
replaces and deletes them), which is in progress and touches the same code.

## Why

The kernel's code area is full: 20.2 KB of code, BASIC about 5 KB of it
(`ubasic.s` 3.9 KB, `ubasic_tokenizer.s` 0.9 KB, part of `term.s` and
`math.s`) plus its strings and variables. The code area grew to $67ff on
2026-09-26 (option 1, +2 KB), which buys time but not room to grow. Moving
BASIC out makes it an ordinary program on the kernel API, like the home
computers' BASICs loaded from ROM, and leaves the kernel to the terminal,
the drivers and the API.

## Proposed shape (defaults)

- **Where it runs:** BASIC is a program for **$7000**, like any `.PRG`
  (about 7 KB with its data and variables, $7000–$8bff or so). Its program
  text stays at **$c000–$dfff** (8 KB), its variables in its own bss.
- **Where it comes from (decided):** after boot the kernel loads
  **`BASIC.PRG` from the SD card** when a storage card is fitted, a card is
  in it and the file is there with a good header; **otherwise the ROM's
  BASIC**, which is always in the ROM image. The storage card and the SD
  card are optional: no card, no medium, no file, a read error or a bad
  header all fall back to the ROM's BASIC without delay or error (a note on
  the console says which BASIC started when it is the card's). After a
  native program ends the kernel reloads the same BASIC it started with.
- **Native programs:** `exec` / `cupc8.py run` load a native program over
  BASIC at $7000; when it returns, the kernel reloads the BASIC it started
  with, the card's or the ROM's (~7 KB, a few milliseconds from ROM) and BASIC finds the program text at $c000
  unchanged, **unless the native program used $c000 and up** (programs over
  20 KB), which `memory-map.md` already warns of. BASIC checks a signature
  and a length at $c000 and starts empty if they are not right.
- **What stays in the kernel:** the terminal and its commands (`help`,
  `dir`, `del`, `net`, `exec`, `refresh`), every driver, the API, the loader.
  Typing a BASIC line or a BASIC command (`run`, `list`, `new`, `save`,
  `load`, ...) hands over to BASIC.
- **How BASIC talks to the machine:** only through the kernel API (console,
  storage, graphics, e-ink, timers, banks). The API gains what BASIC needs
  and does not yet have, e.g. **read a line** (the terminal's line editor,
  with Backspace) and **the terminal's command hook** (so the kernel can
  pass BASIC the lines it does not handle itself).
- **Behaviour for the user: unchanged.** Same prompt, same banner, same
  statements, same messages, same SAVE/LOAD files.

## Build and test

- `tools/mkprg.py` builds BASIC like any program; the ROM builder
  (`tools/mkrom.py`, `romimage.mjs`, `simmachine.nim`) puts it in the ROM
  image; the boot ROM and the kernel know where.
- Every BASIC test (KRN-003, 006, 016–018, 020, 023 and the line-editing
  tests), the examples, E2E-002/007/008/015/016/020 and the simulator's CLI
  tests pass unchanged: the user sees the same machine.
- New: BASIC reloaded after a native program (the program text kept, or
  started empty when a big program used $c000+); `BASIC.PRG` on the card
  replacing the ROM's; the kernel with no BASIC at all (the terminal still
  works); the kernel's code size after the move.
- The simulator runs the same ROM image, so it needs no special support,
  only a test.

## Also: shrinking the kernel's code (option 5)

With BASIC out, look through what is left for duplication (as the three
expression parsers became one): repeated SPI framing in the drivers, string
compares, number printing, the per-command compare chain in `term.s`. Keep
behaviour identical (every test passes unchanged) and report the bytes
saved per change.

## Still open

- BASIC at $7000 and reloaded after native programs is the default; the
  alternative (a RAM bank run from the window) was not chosen.
- Networking (6.5 KB) could move out the same way later; not decided.

## As built (2026-09-26)

- **BASIC** is `basic/`: `basic.s` (main, the terminal's hook, the
  commands, the program editor, from `term.s`), `ubasic.s` and
  `ubasic_tokenizer.s` (from `kernel/`), `n16.s` (the 16-bit arithmetic the
  kernel does not need, and `str_atoi`); `basic/build.sh` assembles them
  with `kernel/math.s` (the kernel's `n16_shl1`, `n16_mul`, `n16_udiv`) as a
  program for $7000 (`tools/mkprg.py`, which now takes several sources and
  `--map`). About 6.3 KB of code, $7000 to about $9000 with its bss. It uses
  only the API; SAVE and LOAD through the storage group, their messages
  through the new `API_ST_PERROR`.
- **The program text** at $c000: `"BA"`, the end (two bytes), then the lines
  from $c004 (`memory-map.md`). The 4 bytes cost the longest program 4
  bytes: 8187 instead of 8191 (KRN-017, KRN-027 changed to match).
- **The ROM image** (`tools/mkrom.py --basic`; `romimage.mjs`,
  `simmachine.nim` pass it): BASIC's header at ROM $08000 (as the kernel's:
  load and entry $7000), its body from $08800, 0s to a page. The kernel body
  must end before $08000 (`mkrom.py` checks).
- **Boot** (`kernel/term.s term_do`, `sys.s sys_basic_boot`): the banner,
  then `BASIC.PRG` from the SD card through exec's loader (`sys_load`, to
  $bfff at most; too big is found before loading, by a byte past the room),
  with `BASIC from the SD card` under the banner; any failure: the ROM's,
  copied a page at a time with the ROM windows on and interrupts off, the
  header and body sums checked; neither: no BASIC (the terminal alone).
  Then BASIC's `main` at $7000: the program at $c000 kept if right, else
  empty; the hook set.
- **API** (only added): `API_TERM_HOOK` $1021, `API_READLINE` $1087,
  `API_ST_PERROR` $11a1 (`kernel-api.md`).
- **After a native program** (`sys_restart`: it returned or called
  `API_EXIT`) the kernel loads the BASIC it started with again (the ROM's if
  the card's no longer loads) and calls `main`; `API_RUN` is 2 meanwhile and
  while the hook runs, so `cupc8.py run` does not write over BASIC while it
  runs. `exec` of a file with no header goes to the hook (r0 = 1), and
  BASIC loads and runs it; a failed `exec` that had already loaded part of
  a program loads BASIC again.
- **Tests:** KRN-031 (reloaded after `cupc8.py run` and exec, the program
  kept or started empty), KRN-032 (BASIC.PRG on the card; the fallbacks with
  no delay; no BASIC in the ROM), KRN-033 (the new entries), KRN-010 (the
  layouts, the ROM header), SIM-010 (BASIC.PRG in the simulator). Test
  programs that leave results for the test now leave them at $bc00-$beff,
  above BASIC, which is loaded again over $7000 when they end.

