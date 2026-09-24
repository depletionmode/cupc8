# Proposal: microSD storage on the IO card (target: Milestone 1)

**Status: proposal, set for Milestone 1. Not implemented yet.** Nothing in
the boards, firmware, kernel or tests changes until this is accepted and
scheduled. Raised 2026-09-24 by David.

**Hardware and software:** a microSD socket on the IO card, IO card firmware
for the card and a file system, new IO card commands, and kernel and BASIC
support for files. The main board, the slot pinout and the slot SPI stay as
they are. The IO card is not drawn yet (`hw/boards/` has only the Wi-Fi
card), so the socket can go in before its layout starts.

## Why

CUPC/8 has no storage the user can write. A program typed into BASIC is lost
at power-off, and the only way to get anything onto the machine is through
the system card's USB port. A microSD card gives the machine files: `SAVE`
and `LOAD` from BASIC, and a card that can be written on a PC and carried
across.

The IO card is the right place for it:
- its RP2040 is idle most of the time (a keyboard is a few bytes a second);
- it already has the code for a slot command interpreter, and has spare
  GPIOs and a free hardware SPI block;
- the card handles the SD protocol and the file system, so the 8-bit CPU
  never deals with SD initialisation, CRCs, 512-byte sectors or FAT.

The main board's `AUX_CS_n` header (`memory-map.md`, SPI device 6, "e.g. a
future SD card") stays free. An SD card there would put SD mode, sectors and
the file system on the CPU, in 64 KB of RAM.

## Hardware

- **Socket:** a push-push microSD socket with a card-detect switch, SMD, in
  JLC's parts library (the part is TBD; Hirose DM3-class or a JLC basic
  equivalent, checked by the JLC stock check like the other parts).
- **Wiring:** SD SPI mode on the RP2040's **SPI1** (SCK, MOSI, MISO, CS), on
  GPIOs not used by the slot SPI's PIO, the USB fault flag or the LEDs. It
  has 10 kΩ pull-ups on CMD/DAT0–3, as the SD spec requires. Card detect
  goes to a GPIO with a pull-up. DAT1 and DAT2 are pulled up and not used,
  but stay routed to spare GPIOs, so the firmware can move to 4-bit SD mode
  on PIO later without a board change.
- **Power:** the card's own 3V3 from the slot's +3V3, with a 10 µF + 100 nF
  bulk and decoupling pair at the socket. A microSD card draws up to about
  100 mA while writing, which is inside the slot's 300 mA +3V3 budget
  alongside the RP2040 (`slot.md`, `power.md`). `power.md` and POW-* need a
  new row.
- **ESD:** a TVS array on the socket lines (the socket can be touched from
  outside).
- **LED:** an **SD activity** LED in the top-edge LED row, to the right of
  the keyboard LEDs (`slot.md`, Mechanical: "other LEDs along the top
  edge").

### Placement: both connectors reachable from outside

The user must be able to reach both connectors with the case closed:

- **USB-A receptacle: on the card's back edge**, facing out through the
  case's rear panel, as on a PC expansion card. On the I/O card outline
  (`slot.md`, Mechanical: the body is x −6.0 … 56.0 mm, y −44.0 … −4.95 mm,
  in the `BUS_PCIexpress_x1` frame), the back edge is x = −6.0 mm, the end
  near finger B1, as with PCIe cards and their bracket. The receptacle
  overhangs that edge by its flange. It sits below the power LED at
  (−3.0, −41.0), clear of the LED and of the 5 mm keep-out above the finger
  tab.
- **microSD socket: on the card's top edge** (y = −44.0 mm, the edge away
  from the main board), with the card slot facing up and out, where it can
  be reached through a slot in the case lid. It sits along the top edge
  between the LED row and the M3 hole at (52.0, −40.0), clear of the hole's
  6.4 mm keep-out. The card sticks out past the board edge by the socket's
  push-push travel.

This is a deliberate exception to the current rule in `slot.md`
("Connectors: on the card's top edge, facing away from the main board") for
the IO card's USB-A. If accepted, `slot.md` changes to allow a card's
connectors on its **top edge or its back edge** (x = −6.0 mm), and
`hw/tools/kicadgen.py`'s `io_card=True` check and `hw/mech/fit.py`
(MECH-00x) learn the back-edge opening. The case needs one rear cut-out per
slot and a lid slot over the IO card's socket. Both need to go on the case
drawing when there is one.

## Protocol (IO card, card type $02)

New commands in the free range **$10–$1F**. The keyboard commands
$00–$05 are unchanged. As in `slot.md`, responses come in a `READ` frame
($FE) with a one-byte RESP_LEN, so no response is longer than 255 bytes.
File data therefore moves in chunks of up to **128 bytes**.

Status byte: the IO card's bit 7 is 0 and bits 6–0 are in use
(`io-card.md`). So SD state is reported by `SD_STATUS`, not in the status
byte.

**File level** (the card runs the file system; the recommended option,
below):

| Op | Name | Args → response | Description |
|---|---|---|---|
| $10 | SD_STATUS | → flags, err, free32 | Bit 0 card present (card detect), bit 1 mounted, bit 2 write-protected, bit 3 busy. `err` is the last error code. `free32` is the free space in KB. |
| $11 | SD_MOUNT | — | Initialise and mount the card (also done automatically on insertion). |
| $12 | F_OPEN | h, mode, len, name… → err | Open file `name` (8.3, ASCII) as handle `h` (0–3). `mode`: 0 read, 1 write (create/truncate), 2 append. |
| $13 | F_READ | h, n → n′, data… | Read up to `n` (≤ 128) bytes. `n′` < `n` means end of file. |
| $14 | F_WRITE | h, n, data… → err | Write `n` (≤ 128) bytes. |
| $15 | F_CLOSE | h → err | Close and flush. |
| $16 | F_SEEK | h, pos32 → err | |
| $17 | DIR_FIRST | → entry | First directory entry: `size32, attr, name…`. An empty response means no files. |
| $18 | DIR_NEXT | → entry | Next entry, as above. |
| $19 | F_DELETE | len, name… → err | |
| $1A | F_RENAME | len, old…, len, new… → err | |

**Block level** (raw 512-byte sectors, for tests and for a kernel file
system if the other option is chosen):

| Op | Name | Args → response | Description |
|---|---|---|---|
| $1C | BLK_READ | lba32 → err | Read a sector into the card's 512-byte buffer. |
| $1D | BLK_WRITE | lba32 → err | Write the buffer to a sector. |
| $1E | BUF_GET | off16, n → data… | `n` (≤ 128) bytes of the buffer. |
| $1F | BUF_PUT | off16, n, data… | Fill part of the buffer. |

**Deadlines:** SD writes and mounts can take far longer than the slot's 5 ms
response deadline (a card may be busy for up to 250 ms on a write). The SD
commands are exempt: a `READ` frame returns RESP_LEN `$00` ("not ready")
until the operation finishes, which the host already handles. The keyboard
keeps working meanwhile: USB host polling runs on core 0 and the SD work on
core 1, so no keys are lost while a file is being written.

**Hot removal:** card detect unmounts at once. Open handles fail with an
error. The firmware only ever has one write in flight, and flushes on every
`F_CLOSE`, so pulling the card loses at most the file being written.

## File system

Two options:

1. **FAT32 (and FAT16) on the card, with FatFs** (recommended). The RP2040
   runs ChaN's FatFs (BSD-style licence, small, widely used on the RP2040)
   and serves files through the file-level commands. Cards come from the
   shop formatted, and a PC reads and writes them directly. The CPU's side
   is a few hundred bytes of kernel code. Long file names are off. Names are
   8.3.
2. **cupfs on raw sectors, in the kernel.** Extend the existing cupfs format
   (`tools/mkcupfs.py`, `cupfsinfo.py`, `mount.cupfs.py`: a 256-byte metadata
   block with the version at bytes 0–1 and magic `$F00D` at 254, 16-byte
   directory entries of name, length and flags, and 15 file slots of 64 KB)
   and run it on the CPU over the block commands. It is simple and
   entirely ours, but a PC needs our tools to read the card, and the kernel
   carries the file system in its ROM and RAM.

Option 1 puts the complexity where there is RAM and speed for it (264 KB, 125
MHz), and keeps the kernel small. cupfs stays what it is today, the format for
the planned ROM disk (`memory-map.md`, "future cupfs ROM disk"). The block
commands stay in the protocol either way, for tests and for raw tools.

## Kernel and BASIC

- **Kernel** (`kernel/sd.s`, new): `sd_status`, `f_open`, `f_read`,
  `f_write`, `f_close`, `dir_first` and `dir_next`, `f_delete`. Each is a thin
  wrapper over the IO card commands using the existing slot SPI routines,
  with the card found by type $02 in the boot ROM's slot table. Errors come
  back in a register as small codes, with messages in one table.
- **BASIC** (`kernel/ubasic.s`):
  - `SAVE "NAME"`: write the program as text, one line per BASIC line, so it
    can be read and edited on a PC.
  - `LOAD "NAME"`: `NEW`, then read the lines as if typed.
  - `DIR` or `FILES`: list names and sizes.
  - `DEL "NAME"`.
  - Later, possibly: `OPEN`, `PRINT #`, `INPUT #`, and loading binary
    programs to an address.
- **Boot:** optional, later: if the card holds `AUTORUN.BAS`, load and run it.

## How it would be tested

Following the existing pattern, before anything is ordered:

- **Firmware core, host tests** (`fw/io/core`): the new command interpreter
  with each command and its malformed frames, on FatFs over an in-memory
  disk image. They cover handles, chunking, end of file, full card,
  write-protect, hot removal and 8.3 name rules. They also include a
  catalogue row alongside IOC-001…
- **SD SPI model:** an SD-card SPI-mode model for the RP2040 emulator
  (`emu/rp2040` and rp2040js) on SPI1, backed by an image file. It covers
  initialisation (CMD0/8/55/ACMD41/58), single-block read and write, busy
  time, CRC and card detect. `tools/simsd.nim` (the simulator's existing SD
  model) is a starting point for the command state machine. It is
  cross-checked against the SD Physical Layer Simplified Specification, and
  also includes an EMU-005 differential test between the native and JS
  models.
- **Real binary in the emulator** (like IOC-004): the IO card firmware on the
  emulated RP2040 with the SD model. It formats and mounts an image, writes
  files, and checks the image with a host FAT reader (mtools or Python's
  `pyfatfs`), and the reverse.
- **End to end** (like E2E-001/002): on the whole-machine emulator, type a
  BASIC program, `SAVE` it, reset, `LOAD` it and run it. It also covers
  `DIR`, and `SAVE` with no card, a full card and a write-protected card.
- **Board:** the socket, card detect and SPI1 nets in the co-simulation
  netlist check; the socket's position and openings in MECH-*; the +3V3
  budget in POW-*; the new LED in the silkscreen and LED-row checks.
- Counterexamples (`test/counterexamples.toml`) for the bugs the tests are
  meant to catch: a lost chunk, a missed flush on close, and a keyboard
  stall during a write.

## What changes where (when it is implemented)

- `doc/hardware/io-card.md`: hardware, commands, deadlines.
- `doc/hardware/slot.md`: connectors on the top or back edge. The SD
  commands are exempt from the 5 ms deadline.
- `doc/hardware/power.md`, `parts.md`: the socket, the TVS and the +3V3 load.
- `doc/hardware/verification.md` and `test/catalogue.toml`: the rows above.
- `hw/boards/io.py` (when the IO card is drawn), `hw/tools/kicadgen.py`,
  `hw/mech/fit.py`.
- `fw/io`, `emu/rp2040` and `test/emu`, `kernel`.

## Not in scope

- Booting the kernel from the card: the boot ROM and kernel stay in the
  parallel ROM, programmed in-system.
- 4-bit SD mode (the board keeps it possible), SDXC/exFAT, long file names,
  subdirectories in BASIC.
- Storage on any other card, or on the main board's `AUX_CS_n` header.

## Open questions

- FatFs on the card (recommended) or cupfs in the kernel?
- The socket part: push-push with card detect, a top-entry or right-angle
  body, and JLC stock.
- The IO card's back edge: is x = −6.0 mm (the B1 end) the rear of the case?
  This needs confirming with the case design. The USB-A overhang must not
  foul the next slot's card.
- Should `SAVE` write text (readable on a PC, slower) or tokenised
  program memory (faster, ours only)? Text is proposed.
- One card handle or several: 4 handles cost about 2.5 KB of FatFs state on
  the card, which is nothing on the RP2040. The limit is really what BASIC
  exposes.
