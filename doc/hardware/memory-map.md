# Memory map, I/O registers and boot chain (Milestone 1)

This supersedes §3.2–3.3 of `doc/CUPC8 Manual.md` where they differ. The
manual gets updated to match once the hardware is implemented.

## CPU address space

| Range | ROM enabled (after reset) | ROM disabled |
|---|---|---|
| $0000–$0001 | RAM: soft reset vector | same |
| $0002–$000f | RAM: reserved | same |
| $0010–$00ff | RAM: interrupt vector table | same |
| $0100–$0fff | RAM: stack | same |
| $1000–$7fff | RAM: program | same |
| $8000–$bfff | **RAM window**: SRAM bank `RAM_BANK` (reset 2: the identity map) | same |
| $c000–$dfff | RAM: program | same |
| $e000–$e7ff | **ROM fixed window**: ROM $00000–$007ff (boot ROM) | RAM |
| $e800–$efff | **ROM banked window**: ROM `(bank << 11) \| A[10:0]` | RAM |
| $f000–$ffff | I/O (never RAM) | same |

Changes from today's hardware and manual:
- **Hard reset vector is $e000** (already true in `cpu.vhd`; the manual says $f000).
- **ROM is an external chip.** It was 128 bytes inside the FPGA.
- **$e000–$efff turns back into RAM** once the kernel disables the ROM.

Reads of RAM-backed addresses go to the SRAM. SRAM $0f000–$0ffff, under the
I/O space, is reached only through the RAM window (bank 3).

## RAM banks

The main board's SRAM (IS62WV5128, 512 KB) has all 19 address lines on the
memory bus (A16–A18 on MEM_A16–A18). It is 32 banks of 16 KB; the chipset
forms the SRAM address of a CPU RAM cycle as:

| CPU address | SRAM address (19 bits) |
|---|---|
| $8000–$bfff | `RAM_BANK[4:0] & A[13:0]` |
| any other RAM address | `000 & A[15:0]` (as without banking) |

So banks 0, 1 and 3 are the normal memory at $0000–$7fff and $c000–$ffff,
and bank 2 is what $8000–$bfff shows at reset. The window can show any bank,
including 0, 1 and 3 (then the same bytes appear at two CPU addresses). The
ROM windows, `ROM_OFF` RAM at $e000–$efff and the I/O space ignore
`RAM_BANK`. There are no extra wait states.

| SRAM | Bank | CPU view with `RAM_BANK` = 2 |
|---|---|---|
| $00000–$03fff | 0 | $0000–$3fff |
| $04000–$07fff | 1 | $4000–$7fff |
| $08000–$0bfff | 2 | $8000–$bfff (the window) |
| $0c000–$0ffff | 3 | $c000–$dfff, $e000–$efff with `ROM_OFF`; $f000–$ffff only through the window |
| $10000–$7ffff | 4–31 | only through the window |

**The kernel keeps nothing in $8000–$bfff** (code, data, bss, the stack and
the API block all sit below it), so interrupts need not save `RAM_BANK`. A
program that switches banks and has its own interrupt handler using the
window saves and restores `RAM_BANK` there. The kernel's `api_bank_set`,
`api_bank_get`, `api_bank_count` and `api_bank_far_copy` (`kernel/bank.s`)
are the programs' interface; the system card reaches every bank with the
bridge's 24-bit RAM commands.

## I/O registers

| Address | R/W | Name | Description |
|---|---|---|---|
| $f000 | W | GPO | 8 output bits → LEDs D1–D8. Readback returns the last value written. Bit 0 is **no longer** the display D/C line. |
| $f1X0 | W | SPI_TX | TX byte for SPI device X (0–7) |
| $f1X1 | R | SPI_RX | RX byte of the last transaction |
| $f1X2 | W | SPI_GO | Start a transaction |
| $f1X3 | R | SPI_STAT | bit 0: 1 = idle/done, 0 = busy |
| $f1X4 | R/W | **SPI_CS** (new) | bit 0 = 1 holds this device's CS_n asserted across bytes, which frames a card command. Writing 0 releases CS_n. With bit 0 = 0, CS_n is asserted only for the duration of each SPI_GO byte, as today. |
| $f1Xf | W | SPI_CFG | `clk_div[7:3] cpha[2] cpol[1] cont[0]`. `clk_div` = 0 is treated as 1. SCK = CPU_CLK / (2 × clk_div), so the fastest is 6 MHz at 12 MHz. `cont` is kept for compatibility, but new code frames with SPI_CS instead. |
| $f200 | R/W1C | IRQ_PEND | pending IRQ bits 3:0; bits 7:4 read 0 |
| $f201 | R/W | IRQ_MASK | bits 3:0, 1 = enabled; bits 7:4 read 0 |
| $f202 | R | **SLOT_IRQ** (new) | bit n = SPI dev n (slots 1–6 → bits 0–5) is currently asserting IRQ_n (level, live). Bits 7:6 read 0. |
| $f203 | R/W | **SYSCTL** (new) | bit 0 `ROM_OFF` (reset 0). Bit 1 `PWR_HI`, read-only: the USB-C source advertises 3.0 A (a comparator on CC, so it works without the system card; `power.md`). When it is 0 the kernel's `net` command refuses to start the radio, and SAVE and DEL refuse to write the SD card. Bits 7:2 reserved, read 0. |
| $f204 | R/W | **ROM_BANK** (new) | Bank for the $e800 window, 0–255 (reset 0) |
| $f205 | R/W | **RAM_BANK** (new) | SRAM bank for the RAM window at $8000–$bfff, 0–31 (reset 2, the identity map); bits 7:5 read 0. See "RAM banks". |

### SPI devices

| Dev | CS line | Connected to |
|---|---|---|
| 0–5 | SLOT1_CS_n … SLOT6_CS_n | Slots 1–6 |
| 6 | AUX_CS_n | Spare 2×5 header on the main board (e.g. a future SD card) |
| 7 | — | reserved (no CS pin; transactions complete with RX = $FF) |

This extends today's 4 devices: the `X` nibble in $f1X_ already had room.

The cards are not fixed to slots. Software identifies them with `IDENT` (see
`slot.md`).

### Interrupts

| IRQ | Vector | Source |
|---|---|---|
| 0 | $0010 | **Slot IRQ**: a new assertion on any slot's IRQ_n (was: keyboard). The handler reads $f202 to find the slot. |
| 1 | $0012 | Timer 0 |
| 2 | $0014 | Timer 1 |
| 3 | $0016 | SPI transaction complete |

A card holds IRQ_n low until its condition clears. IRQ0 latches when any
slot line goes from released to asserted, each line on its own, so a card
that holds its line low (unserviced events, say) never hides another card's
IRQ. The handler clears the pending bit and services the slots $f202 shows;
a line still held afterwards does not re-interrupt, and a new assertion
anywhere does.

## ROM chip

- **Part:** SST39VF040-70 (512 KB, 4 KB sectors), or the pin-compatible
  SST39VF010 (128 KB, ROM_BANK 0–63) depending on JLC stock (see `parts.md`).
  The boot ROM and tools read the chip ID to tell which one is fitted.
- **Chip pins:** A0–A15 come from the chipset's memory bus. ROM A16–A18 are driven by
  the FPGA.
- **Fixed window** ($e000–$e7ff): ROM address = `{000_0000_0, A[10:0]}`.
- **Banked window** ($e800–$efff): ROM address = `{ROM_BANK[7:0], A[10:0]}`.
- **CPU writes to either window are ignored.** The CPU can never program the
  ROM in M1. Only the bus bridge can (see "In-system programming").

### ROM image layout

| ROM offset | Size | Contents |
|---|---|---|
| $00000 | 2 KB | Boot ROM (`rom/boot.s`), assembled for $e000 |
| $00800 | 16 B | Kernel header |
| $00810 | ≤ 52 KB | Kernel body |
| … | | Free (future cupfs ROM disk) |

Kernel header (all fields little-endian):

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic `"CUP8"` |
| 4 | 1 | header version = 1 |
| 5 | 1 | flags (0) |
| 6 | 2 | load address (normally $1000) |
| 8 | 2 | length of body in bytes |
| 10 | 2 | entry address |
| 12 | 1 | body checksum: 8-bit sum of all body bytes |
| 13 | 1 | header checksum: 8-bit sum of bytes 0–12, two's-complemented, so bytes 0–13 sum to 0 |
| 14 | 2 | reserved (0) |

The limit on `load address + length` is **$e000**. The boot ROM rejects
anything larger.

`tools/mkrom.py boot.bin kernel.bin -o rom.bin` builds the image. Unused space
is `$ff`, the erased state, so a partial program leaves the rest erased.

## Boot chain

1. **Reset.** `ROM_OFF=0`, `ROM_BANK=0`, `RAM_BANK=2`, IRQs masked, `I=0`, PC=$e000.
2. **Boot ROM** runs in place from the fixed window. POST codes on GPO:

   | GPO | Stage | On failure |
   |---|---|---|
   | $01 | Boot ROM entered | — |
   | $02 | RAM test: walking bits over the stack page $0100–$01ff (done with no subroutine calls, since the stack lives there), then address-in-address at stride 16 over $0200–$0eff and $1000–$dfff. The boot ROM's own variables sit at $0f00–$0f1f. | halt showing `$82` |
   | $04 | Slot probe (`IDENT` on dev 0–5). Result stored at $0002–$0007. | — (empty slots are fine) |
   | $08 | Console: if a GPU card was found, set TEXT mode and print the banner and POST result | — |
   | $10 | Kernel header check | halt `$90` (bad magic/version/header sum) or `$91` (too large) |
   | $20 | Copy body through the banked window to the load address | — |
   | $40 | Verify body checksum | halt `$A0` |
   | $80 | Jump to entry | — |

   Failures also print a message if a console exists. "Halt" means `CLI`
   followed by `HALT`.
3. **Kernel** (entry $1000) sets `SYSCTL.ROM_OFF=1` first, reads the slot
   table at $0002–$0007 left by the boot ROM, and continues as today.

The slot table at $0002–$0007 holds one byte per slot (slots 1–6): the card
type from `IDENT` (`$00` = empty). It lives in the reserved $0002–$000f area.

## In-system programming (bus bridge)

The chipset FPGA contains an SPI-slave **bus bridge** connected to the sysctl
RP2040 on the system card. The chipset sits in-line between the CPU card and memory, so the CPU
never drives the memory bus. While the bridge is active, the chipset stalls any
CPU cycle by withholding /RDY. sysctl can also hold /CPU_RST, and the bridge
works with no CPU card fitted.

Bridge frames (sysctl is the master, SPI mode 0, **≤ 1 MHz**, framed by
BR_CS_n). The chipset oversamples SCK with its 12 MHz clock, so the rate is
bounded by the synchroniser latency (~250 ns), which must fit in half an SPI
period.

- Multi-byte fields are little-endian.
- **Every response is preceded by one dummy byte.** The chipset needs a whole
  byte-time to fetch the first data.
- Bytes marked → are clocked out by the host sending `$00`.

| Cmd | Bytes after cmd | Action |
|---|---|---|
| $01 RAM_WR | addr16, len8, data × (len+1) | write `len+1` bytes to SRAM $00000–$0ffff (the address wraps within it) |
| $02 RAM_RD | addr16, len8, dummy, → data × (len+1) | read `len+1` bytes from SRAM $00000–$0ffff |
| $09 RAM_WR24 | addr24, len8, data × (len+1) | write to the whole SRAM (19-bit physical address, bank × $4000 + offset; wraps at $7ffff) |
| $0A RAM_RD24 | addr24, len8, dummy, → data × (len+1) | read from the whole SRAM |
| $03 ROM_RD | addr24, len8, dummy, → data × (len+1) | read from the ROM chip (19-bit address) |
| $04 ROM_BUSW | addr24, data8 | one raw bus write cycle to the ROM (/CE_ROM, /WE). sysctl builds the JEDEC erase and program sequences from these. |
| $05 STATUS | dummy, → status | bit0 CPU stopped (bridge or step), bit1 HALTED, bit2 WAITING, bits5:3 reserved (0; CPU card presence and ID are on sysctl's expander U1), bit6 CPU cycle pending (/STB low), bit7 /CPU_RST asserted (power-on, waiting for the CPU card's CDONE, or `CPU_CTL` bit 6) |
| $06 GPO_RD | dummy, → gpo | current GPO value |
| $07 CPU_CTL | ctl8 | see `cpu-bus.md` |
| $08 TRACE_RD | dummy, → count16, → count × {addr16, data8, flags8} | Drain the trace ring, oldest first. count bits 9:0 = entries; bit 15 = entries were lost (ring full) since the previous drain. flags: bit0 RW, bit1 SYNC. |

Every memory access by the bridge stalls any CPU cycle (by withholding /RDY)
until it is done.

Program flow in sysctl firmware (`cupc8.py rom write rom.bin`):
1. Stall the CPU (or hold /CPU_RST).
2. Chip-erase (or erase only the needed sectors), polling DQ6 toggle via
   `ROM_RD`.
3. Program each byte with the 4-cycle JEDEC sequence, polling DQ7/DQ6.
4. Read back and verify all 512 KB.
5. Release the CPU.

CPU stop, single-step and trace also go through the bridge; see `cpu-bus.md`.
