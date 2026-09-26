# 16-bit BASIC, BASIC graphics, and the e-ink native mode in the API

Status: **decided 2026-09-26 by David** ("add 1 and 2"; 16-bit BASIC; an
8 KB program buffer), being implemented.

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
