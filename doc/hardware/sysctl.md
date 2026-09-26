# System controller (sysctl)

The RP2040 on the removable **system card** ([system-slot.md](system-slot.md)),
with its own USB port. The host side is `tools/cupc8.py`.

The card runs from the slot's +3V3 and only listens on USB while the host's
VBUS is there (GPIO29, USB_nVBUS, low): until then the USB controller is off
and D+ is not pulled up, and it lets go of D+ whenever VBUS goes. GPIO0/1
light its TX and RX LEDs for ~30 ms after USB data out and in. It has no
debug UART; its USB link and SWD test pads are the ways in.

The machine does not need it to run. Each FPGA boots from its own flash, and
the main board has its own clock, reset supervisor and USB-C power sensing.
sysctl programs, resets and debugs, and carries the kernel's terminal to a PC
(the console, below) while a PC has that port open. At start-up it touches
nothing on the machine.

On USB it is a composite device (VID:PID 1209:C8C8) with **two CDC serial
ports**, each with its interface association:

| Interface | Port | Linux | |
|---|---|---|---|
| 0, 1 | the protocol (below) | `/dev/ttyACM0` | `cupc8.py`; its string is "CUPC/8 sysctl" |
| 2, 3 | the console | `/dev/ttyACM1` | any terminal program; "CUPC/8 console" |

(The ttyACM numbers are the usual ones with nothing else plugged in;
`cupc8.py` finds each port by its interface number.)

The firmware is a hardware-independent core (`fw/sysctl/core/`) plus an
RP2040 HAL, the same split as the cards. The core runs in the host tests
(SYS-001..005, SYS-007, SYS-008) against models of the bridge, the SST39, the two W25Q flashes,
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

A byte stream over the first USB CDC port. Requests and replies share one frame format:

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

Addresses are little-endian: 16 bits for RAM (the far forms: 24), 24 for ROM
and flash. RAM addresses are physical SRAM addresses: the 16-bit forms reach
$00000–$0ffff (the CPU's view with `RAM_BANK` at its reset value), the far
forms the whole 512 KB, bank × $4000 + offset (`memory-map.md`, "RAM banks").
`t` is a flash/FPGA target: 0 = chipset (FL0), 1 = CPU card (FL1).

| Cmd | Request payload | Reply payload |
|---|---|---|
| $00 PING | nonce (0–8 bytes, optional) | `CUPC8 sysctl <version>` (2.1: with the console), then the nonce. Replies carry no request id, so `cupc8.py` opens every session with a PING nonce and drops replies until its echo: a run killed after its request leaves a reply that would otherwise pass for the next run's. |
| $01 STATUS | – | bridge status (0 if the chipset is down), GPO, CDONE (bit0 chipset, bit1 CPU card), held FPGAs, USB-C class, CC mV (16), 1V2 mV (16), cards held in reset, CPU card present |
| $10 RAM_READ | addr16, len16 | data |
| $11 RAM_WRITE | addr16, data | – |
| $12 RAM_READ_FAR | addr24, len16 | data: `addr + len` ≤ $80000 (bridge `RAM_RD24`) |
| $13 RAM_WRITE_FAR | addr24, data | – : `addr + len` ≤ $80000 (bridge `RAM_WR24`) |
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
| $53 PROG_SELECT | slot (0–5, or $FF) | – : points the programming-port mux at that slot. $FF releases MUX_SEL2..0 to the board's pull-ups, which select the unconnected channel 7. |
| $54 SWD_SEQ | nbits16, bits (LSB first) | – : clocks raw bits out on SWDIO: line resets, the dormant-to-SWD wake-up |
| $55 SWD_XFER | n × (request8 [, data32 for a write]) | n × (ack8 [, data32 for a read]) : stops after the first ack that isn't OK |
| $56 UART_OPEN | baud32 (0 closes) | – : the port becomes a UART, SWCLK = card RX, SWDIO = card TX |
| $57 UART_XFER | bytes to send | the bytes received since the previous UART_XFER |
| $58 CARD_PROG | slot (0–5), low8 | – : drives that slot's PROG_n low (1) or releases it (0): with a CARD_RESET pulse, an ESP32 card starts in its ROM bootloader |

$00 PING, $01 STATUS, $32, $4x and $5x work with the chipset down.

**RAM writes while the CPU runs.** `RAM_WRITE` needs no `CPU_CTL` stop. The
bridge (`soc/bridge.vhd`) hands the chipset one byte at a time; the chipset's
memory controller serves it only when idle and takes no new CPU cycle while
the bridge's request is up (`soc/chipset.vhd`: the bridge goes first, the CPU
waits on /RDY), so every byte is one whole SRAM cycle between CPU cycles: no
bus contention and no torn byte. Nothing is atomic across bytes, though: the
CPU can see a block half written. So `cupc8.py run` writes a program at $7000
first and then, in a separate `RAM_WRITE`, sets `API_RUN` ($6f21) to 1, which
is the only byte the kernel's terminal looks at; and it refuses while
`API_RUN` is 2 (a program is running at $7000, which it would write over) or
still 1 (the last one not started yet).

### The card programming port

The port is two wires, SWCLK and SWDIO, switched to one slot by the mux
(`slot.md`). sysctl only moves bits and bytes; the protocols live in
`cupc8.py card flash`, so the firmware stays small and the same core runs in
`sysctl_sim`:

- **RP2040 cards, SWD.** `SWD_SEQ` sends the dormant-to-SWD wake-up and line
  resets; `SWD_XFER` runs ADIv5 transfers. The request byte is the host's
  (start, APnDP, RnW, A[3:2], parity, stop, park). For each transfer sysctl
  clocks the request, a turnaround, and the 3-bit ack; it retries WAIT up to
  100 times, and on OK clocks the data (with parity, checked on reads) and a
  turnaround. The ack byte is 1 OK, 2 WAIT, 4 FAULT, 7 no answer, or $08 for
  read data with bad parity. A write with request `$99` (TARGETSEL) has no
  ack phase, as SWD multi-drop requires. `cupc8.py` then does what a
  debugger does: power up the debug port, halt the core, and call the boot
  ROM's flash routines (`IF`, `EX`, `RE`, `RP`, `FC`, `CX`) with the image
  staged in RAM, then verify through XIP and reset the card.
- **ESP32 cards, the ROM bootloader.** `cupc8.py` holds PROG_n low and pulses
  CARD_RST_n (`CARD_RESET`, and the expander bit), opens the UART at
  115200 baud, and runs Espressif's `esptool` through a local socket that
  forwards to `UART_XFER`. Then it releases PROG_n and resets the card. $1x, $2x,
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

## The console port

The second CDC port is the kernel's terminal (`../proposals/usb-console.md`):
everything the terminal prints comes out of it, and what a PC types into it
reaches the kernel as keys, as from the USB keyboard. It goes through two
rings in the API block (`memory-map.md`), `CON_OUT` ($6f40–$6fbf, the
kernel writes) and `CON_IN` ($6fc0–$6fff, the card writes), with their
indices at $6f22–$6f25 and `CON_FLAGS` at $6f26.

Only while a PC has the port open (DTR set: opening it in a terminal program
does that), every 2 ms (`CON_POLL_MS`, `fw/sysctl/core/console.c`) the card:

1. reads the four indices and `CON_FLAGS` in one `RAM_RD` frame, and sets
   `HOST` (bit 0 of `CON_FLAGS`) if it is clear: the kernel zeroes it at
   boot, so a reset machine gets it back on the next poll. `CON_FLAGS` with
   any other bit set is the SRAM as it powered up, before the kernel has
   run: the card then moves its own indices to the kernel's (dropping both
   rings), sets `HOST` and sends nothing, so a terminal open across
   power-on sees the banner first, not a ring of junk;
2. copies the bytes from `CON_OUT_TAIL` to `CON_OUT_HEAD` to the PC, as many
   as its USB buffer takes, each `\n` as CR LF (never half of one), then
   writes `CON_OUT_TAIL`;
3. copies what the PC typed into `CON_IN`, as much as fits (one slot stays
   free), then writes `CON_IN_HEAD`. CR is Enter; the LF of a CR LF is
   dropped, and a lone LF is Enter (a paste with either line ending works).
   What does not fit stays in the card's USB buffer, and USB holds the PC
   back once that is full.

When the port closes (DTR clear, or the host's VBUS gone), the card clears
`HOST` once and stops: with the port closed there is no bridge traffic at
all, and none while the chipset is held or down. The indices are read afresh
on every poll (nothing is cached across a kernel reboot); each side writes
only its own index, after the data it covers, because the bridge's writes are
atomic per byte and not across bytes.

With `HOST` set the kernel waits for room in a full `CON_OUT`, as a serial
terminal with flow control would, but for 500 ms at most: a PC that holds the
port open but stops reading (a terminal program suspended, say) holds up the
terminal for half a second, then the kernel goes on, dropping what does not
fit until the PC reads again (then it waits for the PC again, so a reader
that keeps up loses nothing). With the port closed the kernel drops at once.

Open it with `cupc8.py console` (it finds interface 2; `Ctrl-]` quits), or
any terminal program: `picocom /dev/ttyACM1`, `screen /dev/ttyACM1`, PuTTY.
The baud rate is ignored. `sysctl_sim --console` serves the port on a second
pseudo-terminal against the model SRAM (HOST-002).

## USB-C source class

The main board's USB-C sink has 5.1 kΩ Rd on CC1 and CC2. The **policy lives on
the main board**, so it holds with or without the system card: a comparator
sets `PWR_HI` when either CC line is above ~1.30 V (a 3.0 A source;
`power.md`). The chipset shows it in `SYSCTL` bit 1 ($f203). Without it the
kernel's `net` command refuses to start the radio, and SAVE and DEL refuse to
write the SD card.

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
