# System controller (sysctl)

The RP2040 on the removable **system card** ([system-slot.md](system-slot.md)),
with its own USB port. The host side is `tools/cupc8.py`.

The machine does not need it to run. Each FPGA boots from its own flash, and
the main board has its own clock, reset supervisor and USB-C power sensing.
sysctl programs, resets and debugs: nothing more. At start-up it touches
nothing on the machine.

The firmware is a hardware-independent core (`fw/sysctl/core/`) plus an
RP2040 HAL, the same split as the cards. The core runs in the host tests
(SYS-001..005) against models of the bridge, the SST39, the two W25Q flashes,
the two iCE40s booting from them, and the TCA9555 expanders.

## FPGA configuration flash

Each FPGA has its own W25Q flash, and the raw bitstream sits at address 0,
where the iCE40 reads it at power-up (SPI master mode). FL0 is the chipset's
flash on the main board; FL1 is the CPU card's, reached through the CPU socket.

`cupc8.py fpga flash <chipset|cpu> file.bin`:
1. `FPGA_HOLD`: CRESET_n low. The FPGA releases its flash pins (and a held
   chipset takes the machine down with it).
2. Erase, program, and read back through `FLASH_*`. These are refused unless
   that FPGA is held, so the two can never drive the bus at once.
3. `FPGA_BOOT`: release CRESET_n and wait for CDONE (≤ 1 s; an HX4K reads its
   image in about 0.2 s). The chipset then holds the CPU in reset until the
   CPU card's CDONE, so rebooting either FPGA restarts the machine cleanly.

## USB protocol

A byte stream over USB CDC. Requests and replies share one frame format:

| Byte | Field |
|---|---|
| 0 | magic `$C8` |
| 1 | request: command. Reply: status (0 = OK) |
| 2–3 | payload length, little-endian, ≤ 4096 |
| 4… | payload |
| last | CRC-8 (poly $07, init 0) over bytes 1 to the end of the payload |

- Every request gets exactly one reply.
- Bytes outside a frame that are not `$C8` are dropped.
- A frame not completed within 100 ms is dropped, so a crashed host cannot wedge
  the parser.
- On an error the reply payload is empty, unless noted.

| Status | Meaning |
|---|---|
| $00 | OK |
| $01 | bad CRC |
| $02 | unknown command |
| $03 | bad length or argument |
| $04 | timeout (a busy flag never cleared, or CDONE stayed low) |
| $05 | verify failed. Payload: failing address, 24 bits |
| $06 | that FPGA is not held: its flash belongs to it (`FPGA_HOLD` first) |
| $07 | the chipset is not running (held, or not configured), so its bridge cannot answer |

Addresses are little-endian: 16 bits for RAM, 24 for ROM and flash. `t` is a
flash/FPGA target: 0 = chipset (FL0), 1 = CPU card (FL1).

| Cmd | Request payload | Reply payload |
|---|---|---|
| $00 PING | – | `CUPC8 sysctl <version>` |
| $01 STATUS | – | bridge status (0 if the chipset is down), GPO, CDONE (bit0 chipset, bit1 CPU card), held FPGAs, USB-C class, CC mV (16), 1V2 mV (16), cards held in reset, CPU card present |
| $10 RAM_READ | addr16, len16 | data |
| $11 RAM_WRITE | addr16, data | – |
| $20 ROM_READ | addr24, len16 | data |
| $21 ROM_ERASE | addr24, len24 (0 = whole chip) | – : erases the 4 KB sectors that cover the range |
| $22 ROM_PROGRAM | addr24, data | – : programs, polls and reads back each byte, retrying once |
| $23 ROM_ID | – | manufacturer, device |
| $30 CPU_CTL | ctl8 (bridge `CPU_CTL`) | bridge status |
| $31 TRACE | – | the bridge's raw `TRACE_RD` answer: count16, entries |
| $32 RESET | – | – : pulses SYS_nRST for 10 ms (the whole machine) |
| $40 FLASH_READ | t, addr24, len16 | data |
| $41 FLASH_ERASE | t, addr24, len24 | – : the 4 KB sectors that cover the range |
| $42 FLASH_PROGRAM | t, addr24, data | – : page programs, then read back |
| $43 FLASH_ID | t | JEDEC ID (3 bytes) |
| $44 FPGA_HOLD | t | – : CRESET_n low |
| $45 FPGA_BOOT | t | – : CRESET_n released (pulsed if it was not held), then CDONE awaited |
| $50 POWER | – | USB-C class, CC mV (16) |
| $52 CARD_RESET | slot (0–5), hold8 | – |

$00 PING, $01 STATUS, $32, $4x and $5x work with the chipset down. $1x, $2x,
$30 and $31 go through the bridge and return $07 while it is down.

### The ROM (SST39VF040) through the bridge

- **Erase:** JEDEC sector erase (4 KB), or chip erase for len = 0. Completion
  is detected by DQ6 no longer toggling across two `ROM_RD`s. Timeouts: 50 ms
  per sector, 200 ms per chip.
- **Program:** the 4-cycle JEDEC sequence, then poll DQ7 until it reads the
  true data bit (timeout 1 ms). Then read the byte back. A mismatch is retried
  once, then reported as $05 with its address.
- Bytes that are already `$FF` in the image are skipped, since an erased byte
  already reads `$FF`.
- sysctl stops the CPU (`CPU_CTL` bit 0) around every ROM write and restores
  the previous CPU_CTL afterwards.

## USB-C source class

The main board's USB-C sink has 5.1 kΩ Rd on CC1 and CC2. The **policy lives on
the main board**, so it holds with or without the system card: a comparator
sets `PWR_HI` when either CC line is at least 0.66 V (a source of 1.5 A or
more). The chipset shows it in `SYSCTL` bit 1 ($f203), and the kernel's `net`
command refuses to start the radio without it.

sysctl only reports the class, from its ADC readings of CC1/CC2 (the higher one):

| CC voltage | Class | Source current |
|---|---|---|
| < 0.20 V | 0 (unknown: no CC, e.g. an A-to-C cable) | treated as default |
| 0.20–0.66 V | 1 default USB | 500/900 mA |
| 0.66–1.23 V | 2 Type-C 1.5 A | |
| ≥ 1.23 V | 3 Type-C 3.0 A | |

## Expanders (TCA9555, I²C)

| Device | Port 0 | Port 1 |
|---|---|---|
| U0 $20 | bits 0–5: CARD_RST_n slots 1–6 (out) | bits 0–5: PROG_n slots 1–6 (out) |
| U1 $21 | bits 0–5: PRSNT2_n slots 1–6 (in) | bit 0: CPU PRSNT2_n, bits 2:1 CPU CARD_ID, bit 3: PWR_HI (in) |

Unused bits are inputs. Outputs power up as inputs, and CARD_RST_n and PROG_n
are pulled **up** on the main board, so every card runs, in run mode, whether
or not the system card is fitted. sysctl drives a line low only to reset or
program that card.
