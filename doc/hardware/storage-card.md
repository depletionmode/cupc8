# Storage card (card type $04)

A card that gives CUPC/8 files. The card runs the storage medium and the
file system; the CPU sees files and directory entries over the common slot
protocol (`slot.md`) and never deals with sectors, SD initialisation or FAT.

**Milestone 1 medium: a microSD card.** The protocol names no medium: a
later storage card (a tape drive, a hard disk, a flash array) keeps the same
card type and commands, and says what it is in `ST_INFO`. Decided
2026-09-24 by David, replacing the earlier plan to put the microSD on the IO
card (`../proposals/io-microsd.md`, which this spec supersedes for the
hardware; its reasoning for FatFs, text `SAVE` and the tests stands).

## Hardware (M1: microSD)

- **MCU:** RP2040 (C2040) with W25Q16JVSSIQ flash (C131025) and a 12 MHz
  crystal, as on the GPU and IO cards: the same slot SPI slave
  (`fw/rp2040/common/slotspi`), the same SWD programming through the slot.
  Power from the slot's **+3V3** (`power.md`, ≤ 300 mA per card).
- **Standard I/O card outline** (`slot.md`, Mechanical): power LED at the
  common spot, M3 hole, `io_card=True` in its board script.
- **Socket:** a push-push microSD socket with a card-detect switch, SMD, in
  JLC's library with stock, on the card's **top edge** (y = −44.0 mm), the
  card slot facing up and out, reachable through a slot in the case lid;
  clear of the LED row and of the M3 hole's 6.4 mm keep-out.
- **Wiring:** SD in SPI mode on the RP2040's **SPI1** (`hw/pins.yaml`,
  `storage_mcu`): SCK GPIO14, MOSI (CMD) GPIO15, MISO (DAT0) GPIO12, nCS
  (DAT3) GPIO13. 10 kΩ pull-ups on CMD and DAT0–DAT3 (SD spec). Card detect
  on GPIO17 with a pull-up (low = card in). DAT1 and DAT2 are pulled up and
  routed to GPIO18/19, unused in SPI mode, so a later 4-bit mode on PIO needs
  no board change.
- **Power at the socket:** 10 µF + 100 nF. A microSD card draws up to about
  100 mA while writing.
- **ESD:** a TVS array on the socket lines (a user touches the socket).
- **LEDs** (`milestone-1.md`, Indicator LEDs): power at the common spot,
  then along the top edge **ACT** (media activity, lit ~30 ms after each
  access) and **CARD** (a card is inserted and mounted).

## Status byte (returned during every opcode byte)

```
bit 7    0
bit 6    MEDIA     a medium is present (card detect)
bit 5    MOUNTED   the file system is mounted
bit 4    BUSY      an operation is running (READ returns RESP_LEN 0 meanwhile)
bit 3    WP        the medium is write-protected
bit 2:0  0
```

## Commands

**→** marks response bytes, collected with a READ frame (`slot.md`). Names are
8.3 ASCII, length-prefixed (`len8` then bytes). Numbers are little-endian.
Errors are small codes (below). File data moves in chunks of up to **128
bytes** (RESP_LEN is one byte).

### Medium and volume

| Op | Name | Args → response | Description |
|---|---|---|---|
| $01 | ST_INFO | → media, err, flags, free32, total32 | `media`: 0 none, 1 microSD/SD (M1); later media take new codes. `flags` as the status byte. Sizes in KB. |
| $02 | ST_MOUNT | → err | Initialise and mount (also done on insertion). |
| $03 | ST_EJECT | → err | Flush and unmount before the card is pulled. |

### Files (FatFs on the card, M1)

| Op | Name | Args → response | Description |
|---|---|---|---|
| $10 | F_OPEN | h, mode, name → err | Handle `h` 0–3. `mode`: 0 read, 1 write (create/truncate), 2 append. |
| $11 | F_READ | h, n → n′, data… | Up to `n` (≤ 128) bytes; `n′` < `n` means end of file. |
| $12 | F_WRITE | h, n, data… → err | `n` ≤ 128 bytes. |
| $13 | F_CLOSE | h → err | Close and flush. |
| $14 | F_SEEK | h, pos32 → err | |
| $15 | DIR_FIRST | → entry | `size32, attr, name`; RESP_LEN 1 with `$FF` means no (more) files. |
| $16 | DIR_NEXT | → entry | As DIR_FIRST. |
| $17 | F_DELETE | name → err | |
| $18 | F_RENAME | old, new → err | |

### Blocks (raw 512-byte sectors: tests, tools, and a later kernel file system)

| Op | Name | Args → response | Description |
|---|---|---|---|
| $20 | BLK_READ | lba32 → err | Read a sector into the card's 512-byte buffer. |
| $21 | BLK_WRITE | lba32 → err | Write the buffer to a sector. |
| $22 | BUF_GET | off16, n → data… | `n` ≤ 128 bytes of the buffer. |
| $23 | BUF_PUT | off16, n, data… | Fill part of the buffer. |

Error codes: `$00` ok, `$01` no medium, `$02` not mounted, `$03` not found,
`$04` exists, `$05` full, `$06` write-protected, `$07` bad handle, `$08` bad
name, `$09` I/O error, `$0A` too many open.

**Deadlines:** medium operations can take far longer than the slot's 5 ms
(an SD card may be busy 250 ms on a write, a later tape far longer). The
storage card's commands are **exempt**: a READ returns RESP_LEN `$00` ("not
ready") until the operation finishes, which the host already handles, and
the status byte's BUSY bit is set meanwhile.

**Removal:** card detect unmounts at once; open handles then fail with `$01`.
Only one write is in flight at a time and `F_CLOSE` flushes, so pulling the
card loses at most the file being written.

## Firmware

- `fw/storage/core/`: hardware-independent: the command interpreter, the
  handles, FatFs (ChaN, BSD-style licence, LFN off) behind a disk-I/O
  interface. Host builds run it over a disk image.
- `fw/rp2040/storage/`: the SD SPI-mode driver on SPI1, card detect, LEDs,
  the slot SPI slave.

## Kernel and BASIC

`kernel/storage.s` finds the card by type `$04` in the boot ROM's slot table
and wraps the commands. BASIC gains `SAVE "NAME"` (the program as text, one
line per program line, readable on a PC), `LOAD "NAME"` (`NEW`, then the lines
as if typed), `DIR` and `DEL "NAME"`, with messages for no card, not found,
full and write-protected.

## Testing

As `../proposals/io-microsd.md`, "How it would be tested", with the storage
card in place of the IO card: host tests of the core over a FAT image
cross-checked with a host FAT reader; an SD SPI-mode model in the native
emulator on the storage card's SPI1; the real firmware on it; end to end on
the whole machine (`SAVE`, reset, `LOAD`, `RUN`, `DIR`, and no card, full
card, write-protected); the board through the usual pipeline, MECH, POW and
BRD checks; counterexamples for a lost chunk and a missed flush on close.
