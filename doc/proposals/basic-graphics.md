# 16-bit BASIC, BASIC graphics, and the e-ink native mode in the API

Status: **decided 2026-09-26 by David** ("add 1 and 2"; 16-bit BASIC; an
8 KB program buffer), **built 2026-09-26** (see "As built" at the end).

## Why

The graphics cards already draw in colour and in greys (`gpu-protocol.md`,
`eink-card.md`), but BASIC could not reach them, and the kernel API had no
entries for the e-ink card's native 4-grey mode. BASIC's numbers were 8-bit
(0–255, wrapping at 256): too small for screen coordinates (320 wide in the
HDMI card's GFX mode, 648 or 800 on the e-ink panel). Its program buffer was
256 bytes, about seven short lines.

## 1. Kernel API: the e-ink native mode

- `API_GFX_MODE` accepts **2** (the e-ink card's native mode, 648 x 480 or
  800 x 480 at 2 bits a pixel: grey 0 black ... 3 white). The HDMI card
  ignores MODE 2 (`gpu-protocol.md`), so the entry returns an error there
  (r0 != 0, `API_ERR`), found through INFO.
- New graphics-group entries (the next free slots of group 2, $10c3 +
  3n), one per card command, 16-bit coordinates in `API_ARGS`, low byte
  first: `GFX2_PIXEL`, `GFX2_FILL_RECT`, `GFX2_RECT`, `GFX2_LINE`,
  `GFX2_BLIT1`, `GFX2_BLIT2`, `GFX2_TEXT16`, `GFX2_TEXT8`, `GFX2_VSCROLL`,
  `GFX2_GETPIXEL`. On HDMI they do nothing and return an error. Each
  routine's comment is its contract; `api.inc` names them.

## 2. BASIC

### 16-bit numbers

- Variables `a`–`z` and all arithmetic are **16-bit signed**
  (-32768..32767, wrapping); `print` prints signed decimal; `/` and `%`
  truncate toward zero; dividing by 0 still gives 0.
- **Line numbers 1–32767.**
- `poke addr, value` and `peek addr, var` take a plain 16-bit address. The
  old forms `poke hi, lo, value` / `peek hi, lo, var` (three arguments) keep
  working, so saved programs still run.
- Existing programs keep their meaning except where they relied on
  wrapping at 256; the BASIC tests are re-checked by hand for 16-bit and
  every changed expectation says why.

### 8 KB program buffer

- The program lives at **$c000–$dfff** (8 KB), the top of the user area,
  not in the kernel's bss. The line index grows to match (about 300 lines).
- A native program that uses that part of the user area overwrites the
  BASIC program in memory (as on the home computers this is modelled on);
  `exec` of a native program says nothing about it, and `memory-map.md`
  documents it. Programs up to $bfff (20 KB) leave it alone.
- `PROGRAM FULL` still refuses a line that does not fit.

### Graphics statements

All go through the kernel API, so the same program runs on either card,
and the simulator and emulator run them unchanged.

| Statement | Does |
|---|---|
| `mode n` | 0 TEXT, 1 GFX (320 x 240, 256 colours; on e-ink shown in grey), 2 the e-ink card's native 4-grey mode |
| `cls [c]` | clear: TEXT with attribute c, GFX with colour c, mode 2 with grey c |
| `color fg [, bg]` | the TEXT attribute (16 colours each) |
| `plot x, y, c` | a pixel (colour 0–255 in GFX, grey 0–3 in mode 2) |
| `line x0, y0, x1, y1, c` | a line |
| `box x, y, w, h, c [, 1]` | a rectangle outline, or filled with a last argument of 1 |
| `palette i, r, g, b` / `palette` | set a palette entry / restore the default palette (HDMI) |
| `refresh [m]` | the e-ink panel now (m as REFRESH: 0 partial, 1 fast, 2 clean, 3 greyscale; default 3 in mode 2, 0 otherwise); nothing on HDMI |

`refresh` draws what is there; the refresh policy's settings stay out of
BASIC (David, 2026-09-25). Out-of-range arguments are clipped or ignored as
the card does; a wrong number of arguments is a syntax error.

## Tests

- Kernel on the simulator: the new API entries on the e-ink and HDMI cards
  (return codes, what the card received), 16-bit arithmetic and printing
  (negative numbers, wrap at 32768, / and % signs), line numbers above 255,
  poke/peek in both forms, a program near 8 KB and `PROGRAM FULL` past it,
  SAVE/LOAD of a long program, every graphics statement.
- Whole machine (native emulator): a BASIC program drawing in GFX mode
  checked on the HDMI card's decoded picture (pixel colours at known
  places); the same in mode 2 checked on the e-ink panel's glass after a
  greyscale refresh (the four greys at known places).
- The existing BASIC tests pass (with the changed expectations explained),
  and the counterexamples that use BASIC still fail as they should.
- Every bug found: a test and a counterexample.

## As built (2026-09-26)

- **API** (`kernel/sys.s`, `kernel/api.inc`): `API_GFX_MODE` returns r0 = 0,
  or $ff for mode 2 when INFO did not say e-paper (nothing sent). The ten
  entries are group 2's entries 11-20: `API_GFX2_PIXEL` $10e4,
  `API_GFX2_FILL_RECT` $10e7, `API_GFX2_RECT` $10ea, `API_GFX2_LINE` $10ed,
  `API_GFX2_BLIT1` $10f0, `API_GFX2_BLIT2` $10f3, `API_GFX2_TEXT16` $10f6,
  `API_GFX2_TEXT8` $10f9, `API_GFX2_VSCROLL` $10fc, `API_GFX2_GETPIXEL`
  $10ff (their `API_ARGS` in `kernel-api.md`). The texts take a pointer as
  `API_GFX_TEXT8` does; the BLITs a pointer to the picture, w at most 1020
  and one frame of at most 8128 bytes (else r0 = $fe, nothing sent). Frames
  over 64 bytes wait for the card's FREE first (`gpu_wait_free`).
- **Numbers** (`kernel/math.s`): 16-bit routines on `n_a`, `n_b` (add, sub,
  and, or, neg, shift-and-add multiply, shift-and-subtract division, signed
  compare, signed print). `%` by 0 gives the number itself, as the 8-bit
  BASIC did. A leading `-` (unary minus) was added, so negative numbers can
  be written; literals are at most 5 digits, and 32768-99999 wrap (so
  `poke 61440, n` reaches $f000). `str_atoi` is 16-bit.
- **The interpreter** (`kernel/ubasic.s`): one precedence routine for
  relations, `+ - & |` and `* / %` (it replaced three copies); the
  tokenizer's keywords are a table (`ub_keywords`) instead of a compare per
  keyword, which paid for the new code: the kernel's code ends at about
  $5d85 of $5fff, so the layout did not change. The line index is 300
  entries of 4 bytes in bss; past it (and for a line not run yet) GOTO,
  GOSUB, RETURN and NEXT find the line from the start of the program.
  `peek a, b` is the 2-argument form when `b` is a variable that ends the
  statement, else the tokenizer goes back and reads the old 3-argument form.
- **Program buffer** (`kernel/term.s`): $c000-$dfff, its length 16-bit;
  NEW writes a 0 at $c000; LOAD stops at the first line that does not fit.
- **Graphics statements**: as the table above. `mode 2` on HDMI and a mode
  above 2 are ignored (the card ignores them). In GFX mode y and h are
  clamped to 0-255 (the card's y8, h8). `box`'s sixth argument fills when it
  is not 0. A program that ends in mode 1 or 2 keeps its picture until a
  key, then MODE 0 (the text is cleared) and `DONE.`; a fatal error's
  message is printed again then. `help` lists the statements. The banner is
  `CUPC/8 BASIC 2026.09` (David).
- **Tests**: KRN-016 (16-bit numbers), KRN-017 (the 8 KB buffer, PROGRAM
  FULL at its last byte, a near-8 KB program past the line index; SAVE and
  LOAD of long programs in KRN-006), KRN-018 (every statement on the
  simulator's HDMI and e-ink cards), KRN-019 (the API entries), E2E-015 (the
  HDMI picture), E2E-016 (the e-ink glass), SIM-010 (the simulator CLI). The
  KRN-003 programs were re-checked by hand for 16 bits: only `200+100`
  changed (44 in 8 bits, 300 now).
