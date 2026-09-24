# E-ink graphics card (card type $01)

The e-ink card is the second option for the graphics card (Milestone 1,
`doc/proposals/eink-gpu.md` and its Decisions). It drives an e-paper panel
instead of HDMI. **A machine has one or the other**: the e-ink card takes the
same card type, **$01**, speaks the same slot SPI and the same command set
(`gpu-protocol.md`), and says what it is in `INFO`. The boot ROM uses it as
the console with no change; the kernel asks `INFO` and knows which it has.

## Hardware

| | |
|---|---|
| MCU | RP2040 at 125 MHz, the GPU and IO cards' core (`hw/pins.yaml`, `eink_mcu`) |
| Slot | the GPU card's slot group: SCK 2, MOSI 3, MISO 4, CS_n 5, IRQ_n 6 |
| Panel header | 2.54 mm 1 x 9 pin, with a TVS array; the panel's **driver module** (Good Display DESPI-C02 or a Waveshare e-Paper HAT/Driver HAT) plugs in by cable and carries the booster |
| Panel lines | SPI1 as master, write-only: CLK 10, DIN 11; CS_n 9, DC 12 (1 = data), RST_n 13, BUSY 14 (UC8179: **low while busy**), PWR 15 (high = module on; Waveshare HAT rev 2.3) |
| LED | REFRESH (GPIO 24): lit while the panel refreshes |
| Panel | **Good Display GDEY0583T81, 5.83", 648 x 480** (the build `eink.elf`); the 7.5" GDEY075T7, 800 x 480, works with `eink750.elf`. Both have the UltraChip **UC8179** controller. |

The card cannot ask the panel which it is (the header has no MISO), so the
panel is chosen by the firmware image. `INFO` reports it.

## Protocol

Everything in `gpu-protocol.md` holds: the status byte (FIFO FREE, 8 KB
FIFO, the acceptance guarantee), every TEXT and GFX command, FENCE, the error
rules. IDENT answers type $01 at once, whatever the panel is doing. What
differs:

### TEXT (mode 0)

- **80 x 30 cells of 8 x 16**, centred on the panel: 4 white pixel columns
  each side on the 5.83", 80 on the 7.5".
- **The ink rule:** per cell, the brighter of its two colours is ink (black)
  and the darker is paper (white); equal colours are all paper. Brightness is
  the palette entry's luminance, Y = 0.299 R + 0.587 G + 0.114 B. So the
  default `$07` is black text on white, and `$70` (inverse) white on black.
- **The cursor is drawn but does not blink** (a blink would mean a refresh
  every half second): underline (rows 14-15 of the cell inverted) or block.

### GFX (mode 1)

320 x 240 at 8 bpp as on HDMI, pixel-doubled to 640 x 480 and centred. Each
pixel's palette entry becomes a grey by the same luminance, **not inverted**:
black is ink. A 1-bit refresh shows greys with a 4 x 4 ordered (Bayer)
dither; a greyscale refresh (`REFRESH 3`) shows 4 levels.

### Native mode 2

`MODE 2`: the panel's own resolution (648 x 480 or 800 x 480) at **2 bits a
pixel**: grey 0 black, 1 dark grey, 2 light grey, 3 white. `MODE 2` clears it
to white, `CLS g` fills it with grey `g`. Its buffer is the GFX buffer (the
two modes are exclusive), so mode 1's commands ($20-$28) are ignored in mode
2 (GETPIXEL answers 0) and mode 2's are ignored in modes 0 and 1.
Coordinates are **16-bit little-endian, signed for positions**; everything is
clipped to the panel.

| Op | Name | Args | |
|---|---|---|---|
| $40 | PIXEL2 | x16, y16, g | |
| $41 | FILL_RECT2 | x16, y16, w16, h16, g | |
| $42 | RECT2 | x16, y16, w16, h16, g | 1-pixel outline |
| $43 | LINE2 | x0_16, y0_16, x1_16, y1_16, g | Bresenham, both ends drawn |
| $44 | BLIT1_2 | x16, y16, w16, h16, fg, bg, then ⌈w/8⌉ x h bytes | 1 bpp, MSB left; `bg = $FF` transparent |
| $45 | BLIT2 | x16, y16, w16, h16, then ⌈w/4⌉ x h bytes | 2 bpp, the leftmost pixel in bits 7-6 |
| $46 | TEXT16 | x16, y16, fg, bg, len, ch x len | the 8 x 16 TEXT font (DEFCHAR16's glyphs) anywhere; `bg = $FF` transparent |
| $47 | TEXT8_2 | x16, y16, fg, bg, len, ch x len | the 8 x 8 font (DEFCHAR8's) |
| $48 | VSCROLL2 | dy16 (signed), g | scroll up by dy rows (down if negative), fill with g |
| $49 | GETPIXEL2 | x16, y16 → g | after every earlier command; 0 off the panel or outside mode 2 |

A grey that is not 0-3 (or `$FF` where transparent is allowed) makes the
command an error: counted, nothing drawn. A frame is limited to 8128 bytes
as for BLIT8, so a picture goes in several BLITs.

### E-paper commands ($08-$0B)

| Op | Name | Args → response | |
|---|---|---|---|
| $08 | INFO | → kind, w16, h16, greys, flags, cols, rows | kind 1 = e-paper; w, h the panel (648 x 480 or 800 x 480); greys 4; flags bit 0 partial refresh, bit 1 mode 2; cols, rows 80, 30. **The HDMI card answers** 0, 640, 480, 0, 0, 80, 30. |
| $09 | REFRESH | m | Refresh the panel now, with everything before it. m: 0 partial (the rows that differ), 1 fast full (one flash, clears ghosting), 2 clean full (the slow waveform), 3 greyscale full (4 levels). **Execution waits until the panel has the picture**, so a `FENCE` after it fires when the picture is on the glass; commands keep queuing in the FIFO meanwhile. m > 3 is an error. |
| $0A | AUTO | on, idle10, full_after | The automatic refresh policy: on 0/1, idle10 the quiet time in 10 ms steps (default 15 = 150 ms), full_after partial refreshes before a ghost-clearing full one (0 = never; default 30). |
| $0B | EPD_STATUS | → busy, dirty, partials | busy: a refresh is running or waiting; dirty: changes not on the glass yet; partials since the last full refresh. |

The HDMI card executes REFRESH, AUTO and EPD_STATUS as NOPs (EPD_STATUS
gives no response there), and ignores `MODE 2`. Software asks `INFO` first.

`SOFT_RESET` restores the power-on state, including AUTO's defaults.

## Refresh policy

The card refreshes the panel by itself, so the kernel only prints. It keeps
the 1-bit picture last sent to the panel, and every turn of its loop:

1. **Automatic refresh** (AUTO on), when there are unshown changes and no
   refresh is running: once the command stream has made no change for
   `idle10` (150 ms), or changes have waited **1 s** (continuous output),
   it renders the screen, **compares it with the picture on the panel** row
   by row, and sends a **partial refresh of the rows that differ** (the
   window spans the panel's width). A change undone before then costs
   nothing. Commands that change nothing (NOP, FENCE, the reads) do not
   count as activity.
2. After `full_after` partial refreshes it does a **fast full refresh** the
   next time the stream has been quiet for **2 s**, to clear the ghosting.
3. `CLS`, a form feed, `MODE` and `SOFT_RESET` make the next refresh a
   fast full one.
4. The first refresh after power-on is a **clean full** one. Until then the
   panel keeps the picture from before power-off.
5. A change made while the panel refreshes goes into the next refresh.
6. After **10 s** unused the controller goes into deep sleep; the next
   refresh wakes it with a reset.

In use, from the vendors' times: a typed key reaches the glass about 0.5 s
after the key (150 ms quiet, then a 0.3 s partial refresh); a `LIST` or a
program's output makes one refresh when it stops, and continuous output
about one a second. The defaults are to be tuned on the real panel.

## Panel controller (UC8179)

`fw/eink/core/uc8179.c`, from the UC8179c datasheet (UltraChip, rev 0.6,
2019; page numbers below are that document's):

- **Start** (the module's PWR on, 10 ms; RST_n low 1 ms (≥ 50 us, p.39),
  then 2 ms before any command (> 1 ms, p.43)): PWR `07 07 3F 3F` (internal
  DC/DC, VGH/VGL ±20 V, VDH/VDL ±15 V, p.13), BTST `17 17 28 17` (p.16), PSR
  `1F` (LUTs from OTP, KW black/white mode, scan up, shift right, p.12), TRES
  the panel's size (p.31), DUSPI `00` (single SPI, p.18), TCON `22` (p.30).
- **Each refresh:** CDI `21 07` (DDX = 01: data 1 is white; {NEW, OLD} picks
  the LUT, p.27-28; the border white), or `A1 07` for a partial one (the
  border Hi-Z); the waveform (below); PON and wait for BUSY; for a partial
  refresh PTL with the changed rows and PTIN (p.33); DTM1 the OLD picture,
  DTM2 the NEW one (p.17); DRF and wait for BUSY; PTOUT after a partial one;
  POF and wait for BUSY, so the panel has no high voltage between refreshes.
  Deep sleep is DSLP `A5` (p.17), left only by RST_n (p.52).
- **The waveform** is the panel's OTP one chosen by forcing the temperature:
  CCSET `02` (TSFIX, p.38) and TSSET `5A` fast full, `5F` 4-grey, `6E` partial;
  the clean full refresh uses the real temperature (CCSET `00`). These values
  are the panel vendors' (Waveshare's MIT-licensed `EPD_7in5_V2.c`), not the
  UC8179 datasheet's, and are to be confirmed on the panel.
- **4 greys:** grey level g (0-3) is sent as NEW = g's high bit, OLD = its low
  bit, so the four {NEW, OLD} pairs select the four LUTs, which the 4-grey
  waveform gives four greys.
- **BUSY_N:** the card waits for it without stalling the slot: the panel loop
  is a state machine polled by the main loop, and a picture goes out 8 rows
  a turn (about 0.5 ms at the 10 MHz panel SPI). A wait starts at the first
  poll after the command went out (BUSY_N may take a moment to fall), and a
  controller busy for 10 s is given up on: the refresh is released, and the
  next one starts with a reset.

## Firmware

| Where | What |
|---|---|
| `fw/gpu/core` | the graphics card's interpreter, reused: an extension hook (every command goes to the e-ink core first), a hold flag (REFRESH), INFO, and the GFX buffer in a union sized by `GPU_GFX_BYTES` (96,000 for the e-ink card: mode 2 on the 7.5") |
| `fw/eink/core/eink.c` | the e-paper commands, mode 2, the rasteriser (ink rule, dither, greys), the refresh policy and the panel loop, on an injected clock |
| `fw/eink/core/uc8179.c` | the controller's command sequences over a four-function bus (command, data, pin, busy) |
| `fw/rp2040/eink/main.c` | the RP2040 port: slot SPI, SPI1 at 10 MHz with GPIO CS and DC around each command and its data, RST, PWR, BUSY, the REFRESH LED. One core, one loop. `tools/fw_rp2040.sh eink` (or `eink750`) |

Memory: about 200 KB of the RP2040's 264 KB (the 96 KB GFX / mode-2 buffer,
the 48 KB picture on the panel, the FIFO, fonts and the text buffer).

## Kernel

`kernel/gpu.s` drives either card. `gpu_init` sends `INFO` and keeps the
first response byte in `gpu_kind` (0 HDMI, 1 e-paper, `$ff` if nothing
answers). `kernel/eink.s` has `eink_refresh` (REFRESH m, on e-paper only)
and the terminal's **`refresh`** command: a clean full refresh, to clear
ghosting by hand. On HDMI it does nothing.

## Tests

| Test | What |
|---|---|
| GPU-006..008 | host tests of the core with the UC8179 model (`fw/test/test_eink.c`, `make -C fw test_eink`): every command, malformed frames, the ink rule for all 256 attributes, TEXT/GFX/mode 2 pictures on the glass against golden images (`test/eink/golden`), the policy's timing, deep sleep, a dead panel; and GPU-001's suite on the e-ink build (`test_gpu_eink`) |
| GPU-009 | the real `eink.elf` and `eink750.elf` on the native emulator with the panel model (`build/emu-machine/einkcard`) |
| KRN-007 | the kernel on the simulator's e-ink card (`tools/run_tests.sh testKernelOnEink`) |
| E2E-007 | the whole machine with the e-ink card: boot to BASIC on the panel, a program, `refresh` |

**The UC8179 model** (`fw/test/epdmodel.c`) is one model for the host
tests, the simulator and the emulator. It takes SPI bytes with DC, RST_n and
PWR, holds BUSY_N low for each operation's time (the vendors' figures: full
3 s, fast 1.5 s, 4-grey 2 s, partial 0.3 s, PON 50 ms, POF 30 ms, BUSY_N
falling 200 us after the command; `time_scale` scales them), and applies a
refresh to its glass only when the refresh ends. It counts as an error
anything the chip would ignore or do wrong: a command while BUSY, a byte
during reset or within 1 ms of it, in deep sleep or unpowered, a refresh
with the booster off or with more or less pixel data than the window, a
reserved command, a read (the header has no MISO). A partial refresh moves
only the pixels whose NEW differs from their OLD, so a wrong OLD picture
leaves wrong pixels on the glass.

**Seeing it:** `node tools/machine_view.mjs --native --slots eink,io` (or
`eink750,io`) shows the panel's glass in the browser, which changes only when
a refresh completes; `CUPC8_EINK_SCALE=0.2` shortens the panel's busy times,
`CUPC8_EINK_LOG=FILE` logs every controller command.

**Not testable before hardware:** the waveforms (ghosting, how the greys look,
how many partial refreshes before a full one is needed), and the forced
temperature values.
