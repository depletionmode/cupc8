# System controller (sysctl)

The RP2040 on the main board. It owns the USB-C port and everything that is
programmed in-system. The host side is `tools/cupc8.py`.

The firmware is a hardware-independent core (`fw/sysctl/core/`) plus an
RP2040 HAL, the same split as the cards. The core runs in the host tests
(SYS-001..005) against models of the bridge, SST39, W25Q32, iCE40
configuration port and TCA9555 expanders.

## Power-up sequence

1. Hold every CARD_RST_n low. The expanders power up that way (below).
2. Wait until the 1V2 rail is within 5% (ADC on GPIO28, 1:1).
3. Load the chipset's CRAM from the flash image in slot 0 (below). Check CDONE.
4. Hold /CPU_RST (bridge `CPU_CTL` bit 6). Load the CPU card's CRAM from
   slot 1, if a CPU card is present. Check CDONE.
5. Release CARD_RST_n, then /CPU_RST. The boot ROM probes the slots.
6. Wait for GPO to show $08–$80 (the probe is done). Read the slot table at
   RAM $0002–$0007 through the bridge, then apply the power policy (below).

A failure in step 2, 3 or 4 is reported by `status` and blinks the power LED.
Cards are released for the probe even on a weak source. Otherwise the boot ROM
could not see a Wi-Fi card to report it. The ESP32 draws little until its radio
starts, and the radio starts only when the kernel joins a network.
The chipset has no configuration flash of its own: its SPI_SS_B is on a
sysctl chip select (`nCS_CHIPSET_CFG`), so it always boots as an SPI slave.

## Configuration flash (W25Q32, 4 MB)

| Offset | Contents |
|---|---|
| $000000 | slot 0: chipset image |
| $100000 | slot 1: CPU-card image |
| $200000–$3FFFFF | free |

Each slot starts with a 16-byte header, and the bitstream follows at slot + $100:

| Bytes | Field |
|---|---|
| 0–3 | magic `C8BS` |
| 4–7 | bitstream length, little-endian (≤ 1 MB − $100) |
| 8–11 | CRC-32 (IEEE) of the bitstream |
| 12–15 | reserved, $FF |

`cupc8.py fpga flash <chipset|cpu> file.bin` erases the slot, writes the
bitstream and then the header, so an interrupted write leaves no valid header.

### iCE40 SPI-slave load (Lattice TN1248)

The bitstream is first read into RP2040 RAM and its CRC checked, then sent in
one burst with SS low. It can't be streamed straight from the flash: the flash
is on the same SPI bus, and TN1248 doesn't say whether SS may rise in the
middle of a bitstream. The staging buffer limits an image to 160 KB (an HX4K
bitstream is 135,100 bytes). `FPGA_LOAD` stages the host's data the same way.

1. SS low, CRESET_B low for ≥ 1 µs, then CRESET_B high with SS still low.
2. Wait ≥ 1200 µs (HX4K) for the CRAM to clear.
3. SS high, 8 dummy clocks, SS low.
4. Send the bitstream, MSB first.
5. SS high, then ≥ 100 dummy clocks. CDONE must be high after them.

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
| $06 | no valid image in the flash slot |
| $07 | refused by the power policy (use `power --force`) |

Addresses are little-endian: 16 bits for RAM, 24 for ROM and flash.

| Cmd | Request payload | Reply payload |
|---|---|---|
| $00 PING | – | `CUPC8 sysctl <version>` |
| $01 STATUS | – | bridge status, GPO, CDONE (bit0 chipset, bit1 CPU card), power class, CC mV (16), 1V2 mV (16), held-slot mask, boot status (a status code from the power-up sequence) |
| $10 RAM_READ | addr16, len16 | data |
| $11 RAM_WRITE | addr16, data | – |
| $20 ROM_READ | addr24, len16 | data |
| $21 ROM_ERASE | addr24, len24 (0 = whole chip) | – : erases the 4 KB sectors that cover the range |
| $22 ROM_PROGRAM | addr24, data | – : programs, polls and reads back each byte, retrying once |
| $23 ROM_ID | – | manufacturer, device |
| $30 CPU_CTL | ctl8 (bridge `CPU_CTL`) | bridge status |
| $31 TRACE | – | the bridge's raw `TRACE_RD` answer: count16, entries |
| $40 FLASH_READ | addr24, len16 | data |
| $41 FLASH_ERASE | addr24, len24 | – : 4 KB sectors that cover the range |
| $42 FLASH_PROGRAM | addr24, data | – : page programs, then read back |
| $43 FPGA_BOOT | target (0 chipset, 1 CPU card) | – : load CRAM from that flash slot |
| $44 FPGA_LOAD | target, phase (0 begin, 1 data, 2 end), data | – : load CRAM straight from the host |
| $50 POWER | – | class, CC mV (16), held-slot mask, forced |
| $51 POWER_FORCE | on8 | as POWER |
| $52 CARD_RESET | slot (0–5), hold8 | – |

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

## Power policy

The USB-C sink has 5.1 kΩ Rd on CC1 and CC2. sysctl reads both CC voltages
and uses the higher one:

| CC voltage | Class | Source current |
|---|---|---|
| < 0.20 V | 0 (unknown: no CC, e.g. an A-to-C cable) | treated as default |
| 0.20–0.66 V | 1 default USB | 500/900 mA |
| 0.66–1.23 V | 2 Type-C 1.5 A | |
| ≥ 1.23 V | 3 Type-C 3.0 A | |

On class 0 or 1, sysctl holds every Wi-Fi card (slot type $03) in reset and
reports "low-power source". The slot types come from the table the boot ROM
leaves at RAM $0002–$0007, which sysctl reads through the bridge once the boot
ROM has written it. `POWER_FORCE 1` releases the hold. `POWER_FORCE 0` re-applies it.

## Expanders (TCA9555, I²C)

| Device | Port 0 | Port 1 |
|---|---|---|
| U0 $20 | bits 0–5: CARD_RST_n slots 1–6 (out) | bits 0–5: PROG_n slots 1–6 (out) |
| U1 $21 | bits 0–5: PRSNT2_n slots 1–6 (in) | bit 0: CPU PRSNT2_n, bits 2:1 CARD_ID (in) |

Unused bits are inputs. Outputs power up as inputs, which are pulled low on
CARD_RST_n and high on PROG_n, so cards stay in reset and in run mode until
sysctl drives them.
