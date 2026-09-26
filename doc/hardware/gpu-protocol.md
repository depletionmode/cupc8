# Graphics card protocol (card type $01)

The graphics card is an RP2040 running PicoDVI. It outputs **640×480 @ 60 Hz
DVI** on an HDMI type-A connector: no audio, no HDCP. It is an SPI slave
using the common framing in `slot.md`: one command per CS_n frame, and the
status byte comes back during the opcode.

**Hardware notes** (the board: `hw/boards/gpu.py`, `hw/boards/README.md`):
TMDS through 270 Ω series resistors (PicoDVI's DC-coupled output) and
TPD4E05U06 ESD; the pairs are on GPIO10–17 with the pads inverted
(`hw/pins.yaml`). The receptacle's +5V comes from a TPS61023 boost at 5.06 V
(the IO card's circuit, `power.md`), because the slot's +5V can be 4.1 V at
the card; its 100 mA PTC sits ahead of the boost. HPD through a 22k/33k
divider; DDC through 2N7002 level shifters.

The protocol is designed for an 8-bit CPU with two registers:
- every command is an opcode followed by **fixed-size** arguments;
- 16-bit values are little-endian, and only X coordinates need them;
- the common cases are short. Printing a character is **2 bytes** (`PUTC ch`).

## Modes

| Mode | Resolution | Pixels | Use |
|---|---|---|---|
| 0 TEXT (power-on default) | 80 × 30 cells, 8×16 font, 640×480 | 16-colour fg/bg per cell | terminal, boot ROM console |
| 1 GFX | 320 × 240, each pixel doubled to 640×480 | 8 bpp indexed, 256-entry palette | drawing, games, BASIC graphics |

Only one mode is displayed at a time. Switching modes clears the new mode's
buffer. Compositing both layers per scanline is deliberately out of scope for
M1, because of the TMDS encode time at 252 MHz.

**Fonts:**
- **TEXT:** a built-in CP437 8×16 font.
- **GFX:** a built-in 8×8 font for `TEXT8`.
- Both fonts can be redefined per glyph.

**Palette:**
- Entries 0–15 are the standard VGA 16 colours. TEXT mode uses these same 16,
  shown at RGB222 (2 bits per channel, the card's text encoder). That is exact
  for the VGA colours; a redefined entry shows its top 2 bits per channel.
- Entries 16–231 are a 6×6×6 RGB cube.
- Entries 232–255 are a 24-step grey ramp. This is the xterm-256 layout.
- `PALETTE` changes any entry. Colours are stored as RGB565.

## Status byte (returned during every opcode byte)

```
bit 7    0 (always, per slot.md)
bit 6:0  FREE — command FIFO free space in 64-byte units, capped at 127
```

- **FIFO size:** 8 KB, so an idle card reports `FREE = 127` (8128 bytes).
- **The acceptance guarantee:** if the status byte returned during an opcode
  says `FREE = n`, a frame of up to `n × 64` bytes (opcode included) **will be
  accepted**.
- **If FREE = 0:** the host ends the frame at once (`SPI_CS=0`). The card
  discards the incomplete frame, and the host retries later.
- **Long frames:** a host sending more than 64 bytes (`BLIT`, `PUTS`) checks
  FREE first. Short commands only need `FREE ≥ 1`.
- **Draining:** commands are executed in order from the FIFO. "All done"
  means FREE = 127 plus a `FENCE`.

## Commands

Notation: `x16` is a signed 16-bit LE X coordinate (0–319 on screen; TEXT uses `x8`),
`y8` is an 8-bit Y coordinate, and `c` is a palette index. → marks response
bytes, which the host collects with a READ frame (`$FE`, see `slot.md`).

### General

| Op | Name | Args | Description |
|---|---|---|---|
| $00 | NOP | — | Also safe to use as filler |
| $01 | MODE | m | 0 = TEXT, 1 = GFX. Clears that mode's buffer. Any other m is ignored (the e-ink card's mode 2, `eink-card.md`; the kernel's `API_GFX_MODE` does not send 2 to this card and returns an error). |
| $02 | CLS | c | TEXT: every cell becomes space with attr `c`, and the cursor goes to 0,0. GFX: fill with colour `c`. |
| $03 | PALETTE | idx, r, g, b | Set a palette entry (8-bit components, stored as RGB565) |
| $04 | PALETTE_RESET | — | Restore the default palette |
| $05 | FENCE | tag | When executed, latch `tag` and assert IRQ_n (if IRQ_EN) |
| $06 | FENCE_READ | → tag | Last executed fence tag. Also releases IRQ_n. |
| $07 | VSYNC_COUNT | → n | Frames since power-on, mod 256. Useful for timing and animation. |
| $08 | INFO | → kind, w16, h16, greys, flags, cols, rows | Which graphics card this is: here 0 (HDMI), 640, 480, 0 (colour), 0, 80, 30. The e-ink card answers 1 (e-paper) and its panel (`eink-card.md`). |
| $09-$0D | REFRESH, AUTO, EPD_STATUS, AUTO_EXT, AUTO_GET | m / on, idle10, full_after / — / cap10, full_kind, sleep_s / — | The e-ink card's (`eink-card.md`); NOPs here, so software may send them to either card |

### TEXT mode

Cursor and attribute state: `(cx, cy)` starts at 0,0 and `attr` starts at
`$07` (light grey on black). The high nibble of `attr` is bg, the low nibble
is fg.

| Op | Name | Args | Description |
|---|---|---|---|
| $10 | PUTC | ch | Terminal output at the cursor with `attr` (control codes below) |
| $11 | PUTS | len, ch × len | Same as PUTC for each byte. `len` is 1–255. |
| $12 | GOTOXY | x8, y8 | Move the cursor (clamped to 79, 29) |
| $13 | ATTR | a | Set the current attribute |
| $14 | CURSOR | mode | 0 off, 1 underline (power-on default), 2 block. Blinks at 2 Hz (on for 15 frames, off for 15). |
| $15 | SCROLL | n | Scroll up `n` lines. New lines take `attr`. |
| $16 | CLEOL | — | Clear from the cursor to end of line with `attr` |
| $17 | POKE | x8, y8, ch, a | Write a raw cell. No control-code handling, cursor unchanged. |
| $18 | GETXY | → x, y | Read the cursor |
| $19 | DEFCHAR16 | ch, 16 bytes | Redefine a TEXT glyph, top row first, MSB = left pixel |

PUTC control codes:

| Code | Action |
|---|---|
| `$08` BS | cursor left, stopping at column 0 |
| `$09` TAB | to the next multiple of 8 |
| `$0A` LF | next line, column 0 |
| `$0D` CR | column 0 |
| `$0C` FF | CLS with `attr` |
| everything else | printed as a glyph |

The cursor wraps at column 80, and writing past row 29 scrolls.

### GFX mode

All drawing is clipped to 320×240. Arguments outside the screen are legal.

| Op | Name | Args | Description |
|---|---|---|---|
| $20 | PIXEL | x16, y8, c | |
| $21 | FILL_RECT | x16, y8, w16, h8, c | |
| $22 | RECT | x16, y8, w16, h8, c | 1-pixel outline |
| $23 | LINE | x0_16, y0_8, x1_16, y1_8, c | Bresenham, both endpoints drawn |
| $24 | BLIT8 | x16, y8, w8, h8, then w×h bytes | 8 bpp, row-major. w and h must be ≥ 1, and the frame must be ≤ 8128 bytes. |
| $25 | BLIT1 | x16, y8, w8, h8, fg, bg, then ⌈w/8⌉×h bytes | 1 bpp, MSB = left pixel. `bg = $FF` means transparent. |
| $26 | TEXT8 | x16, y8, fg, bg, len, ch × len | 8×8 glyphs left to right, no wrapping. `bg = $FF` means transparent. |
| $27 | VSCROLL | dy (signed 8), c | Scroll the bitmap up by `dy` rows (down if negative) and fill the exposed rows with `c` |
| $28 | GETPIXEL | x16, y8 → c | Reads back after all earlier commands have executed. This can exceed the 5 ms response deadline, so keep polling READ while RESP_LEN is 0. |
| $29 | DEFCHAR8 | ch, 8 bytes | Redefine a TEXT8 glyph |

Using `$FF` as "transparent" means palette entry 255 can't be used as a BLIT1
or TEXT8 background. That's acceptable, because entry 255 is the brightest
grey.

### Errors

- **Unknown opcode:** the rest of the frame is ignored.
- **Frame shorter than its command:** discarded.
- **Frame longer than its command:** extra bytes ignored.
- **Counting:** each case increments an internal error counter. The counter
  is readable through the SWD debug interface only.

## Performance targets (verified in the co-simulation)

- **SPI rate:** at 3 MHz SCK, one byte takes ~2.7 µs on the wire. In practice
  the CPU's per-byte poll loop dominates, so one byte takes about 10–20 µs.
- **Throughput:** `PUTC` must keep up with any CPU rate, since a command costs
  far less on the card than on the wire.
- **A full-screen `CLS`** executes within one frame (16.7 ms).
- **`FILL_RECT`** of the full screen executes within one frame.

## Implementation notes (firmware, not protocol)

- **Core 0:** PicoDVI with the TMDS encode.
  - TEXT mode uses a per-scanline 1 bpp glyph expansion with per-cell colours.
  - GFX mode uses an 8 bpp → RGB565 line LUT, then PicoDVI's 16 bpp encoder.
- **Core 1:** SPI RX. A PIO SPI slave with a CS-edge marker, feeding a DMA
  ring into the FIFO. Core 1 also runs the command interpreter.
- **Memory:**
  - GFX buffer 76,800 B
  - TEXT buffer 4,800 B
  - fonts 6 KB
  - FIFO 8 KB
  - PicoDVI buffers ≈ 20 KB
  - That totals about 116 KB of the 264 KB SRAM.
- **Code split:** the interpreter and renderers are a hardware-independent
  core (`fw/gpu/core/`). The same code runs in host tests and in the
  co-simulation.
