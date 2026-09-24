# Proposal: GPU features for games (target: Milestone 3)

**Status: proposal only. Not for Milestone 1 or 2.**

**Software only:** GPU card firmware, the GPU protocol, the kernel and BASIC.
No hardware changes: the boards, the slot and its SPI stay exactly as in M1,
and the M1 commands keep working. It can go in at any time after the boards
are made, since the GPU card's RP2040 is reprogrammed in-system from the
system card's USB port. Raised 2026-09-24 by David ("could I drive a 30 fps
game?").

## Why

GFX mode is 320 × 240 at 8 bpp: a whole screen is 76,800 bytes, and every
byte crosses the slot SPI from the 12 MHz CPU.

| Limit | Rate (estimate from the specs) |
|---|---|
| Slot SPI: SCK ≤ 6 MHz, ≥ 1 µs between bytes (`slot.md`) | ≈ 2.3 µs a byte, ≈ 400 KB/s |
| The CPU feeding it (load, store to SPI, wait, loop) | ≈ 3–4 µs a byte, ≈ 200–300 KB/s |
| Full screen from the CPU | 0.25–0.4 s: **3–5 frames/s** at best |
| 30 fps full screen would need | 2.3 MB/s: more than the SPI carries even with no gaps (750 KB/s) |

So full-screen redraws from the CPU are out, and always will be on this
slot. A 30 fps game is still possible today the 8-bit way, drawing only
what changes: at 30 fps a frame is 33 ms, and with half of it for game logic
there is room for roughly 4–8 KB of GPU commands. That is about 10 16×16
`BLIT8` sprites with their erases, a `VSCROLL` and a score line. It works,
but sprites are sent pixel by pixel every frame and there is no way to avoid
tearing.

The GPU card is an RP2040 at 252 MHz, far faster than the CPU. The idea:
**keep the graphics on the GPU and send it small commands**, so a frame is a
few hundred bytes and the CPU spends its time on the game.

## What

New commands in the free range **$30–$3F**. All are fixed-size, and the
X coordinates are 16-bit, as elsewhere. Only GFX mode is affected; TEXT mode
is unchanged.

| Op | Name | Arguments | Effect |
|---|---|---|---|
| $30 | SPRITE_DEF | id, w8, h8, then w×h bytes | Store an 8 bpp sprite of up to 32×32 in GPU RAM as `id` (0–63). Colour `$FF` is transparent. |
| $31 | SPRITE_DRAW | id, x16, y8 | Draw sprite `id` into the back buffer: **5 bytes**, instead of ~262 for a 16×16 `BLIT8`. |
| $32 | SPRITE_DRAWF | id, x16, y8, flags | As above, with flags: bit 0 flip H, bit 1 flip V. |
| $33 | TILE_DEF | n, then 64 bytes | Define 8×8 tile `n` (0–255), 8 bpp. |
| $34 | TILEMAP_MODE | on | Background from a 40 × 30 tile map instead of the bitmap. |
| $35 | TILE_SET | col, row, n | Set one map cell: **4 bytes**. |
| $36 | TILE_ROW | row, then 40 tile numbers | A whole row: 42 bytes. |
| $37 | SCROLL_XY | x16, y8 | Background scroll offset in pixels, with wrap: smooth scrolling for **4 bytes**. |
| $38 | DOUBLE | on | Two GFX buffers: draw into the back one, show the front one. |
| $39 | FLIP | — | Swap the buffers at the next vsync. With `FENCE`, the host knows when it happened. |
| $3A | COPY_FRONT | — | Copy the front buffer to the back one (for games that draw only changes). |

A 30 fps frame then looks like: `FLIP`, `SCROLL_XY`, a dozen `SPRITE_DRAW`s,
a few `TILE_SET`s and the score: **about 100–200 bytes**, not 4–8 KB. The
limit moves from the SPI to how much the GPU can draw per frame, which is
the RP2040's job.

**Compatibility:** the new commands are unknown opcodes to M1 firmware,
which ignores them (`gpu-protocol.md`, error handling). Software checks the
firmware version from `IDENT` (`fw_major` ≥ 2) before using them. Old
programs see no difference.

## Can the GPU card do it?

**Memory** (RP2040, 264 KB SRAM; M1 uses about 116 KB):

| Item | Size |
|---|---|
| M1 today (GFX 75 KB, TEXT, fonts, 8 KB FIFO, PicoDVI ≈ 20 KB) | ≈ 116 KB |
| Second GFX buffer (DOUBLE) | + 75 KB |
| 64 sprites, 32×32 at 8 bpp worst case | + 64 KB |
| 256 tiles, 8×8 | + 16 KB |
| Tile map, 40 × 30 | + 1.2 KB |
| **Total** | **≈ 272 KB: over.** |

So something has to give. Options: sprites limited to 16×16 or to 32 slots
(64 KB → 16 KB), the tile map as the background *instead of* a second bitmap
(tile mode rendered per scanline needs no framebuffer), or a 4 bpp sprite
format. The likely fit is double-buffered bitmaps with 16×16 sprites (≈ 207
KB), or a tile background plus a sprite layer composited per scanline (well
under 200 KB).

**CPU time:** core 0 encodes TMDS; core 1 receives SPI and runs the
interpreter. Sprite and tile drawing runs on core 1 between commands, or
per scanline for a tile/sprite layer. How many sprites a frame it can draw
is the thing to measure first.

## How we'd find out (before writing the firmware)

The whole-machine emulator is cycle-exact to the real firmware, so all of
this can be measured without hardware:

1. Measure today's numbers: SPI bytes/s from a kernel-style loop, the time
   for a full-screen `BLIT8`, `VSCROLL`, and N `BLIT8` sprites per frame.
   (The figures in the table above are estimates from the specs.)
2. Prototype `SPRITE_DRAW` and `FLIP` in `fw/gpu/core` (host-tested like the
   other commands), and measure sprites per frame on the real binary in the
   emulator.
3. Decide the memory layout from 1 and 2, then specify the final commands in
   `gpu-protocol.md`.

Tests would follow the existing pattern: host tests of each command and its
malformed frames (GPU-001/003), golden images (GPU-002), and the real binary
with TMDS capture (GPU-005), plus a timing test for sprites per frame.

## Kernel and BASIC

- Kernel (`kernel/gpu.s`): wrappers for the new commands and an `IDENT`
  version check.
- BASIC: `SPRITE n, x, y`, `TILE c, r, n`, `SCROLL x, y`, `FLIP`, and a way to
  load sprite and tile data (DATA statements or a file).

## Not in scope

- Any hardware change. In particular, full-screen video streamed from the
  CPU stays out of reach (the slot SPI can't carry it); games send commands
  instead.
- Audio.

## Open questions

- 8 bpp or 4 bpp sprites, and the maximum size.
- Tile layer and sprite layer composited per scanline (little RAM, a fixed
  sprite budget per line), or drawn into a double-buffered bitmap (more RAM,
  simpler)?
- Collision detection on the GPU (a `SPRITE_HIT` query), or left to the game?
