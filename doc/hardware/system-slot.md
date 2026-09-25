# System slot and system card

The system card carries the system controller (sysctl, an RP2040), with its
own USB port for the host PC. It is removable: **the computer boots and runs
without it.** Each FPGA boots itself from its own configuration flash, the main
board has its own 12 MHz oscillator and reset supervisor, and the cards run by
default. With the card fitted, it adds everything that is programmed in-system
or debugged:

- the ROM chip, both FPGAs' flash, and the card MCUs
- stop, step and trace of the CPU
- status, and the USB-C power policy

Firmware and USB protocol: [sysctl.md](sysctl.md).

## The slot

- **Connector:** one PCIe x4 card edge (64 contacts), LCSC C19188869, an SMD
  vertical socket with posts. It is physically unlike the six x1 I/O slots,
  so neither kind of card fits the other's slot.
- **Board:** 1.6 mm, hard-gold fingers, 30° chamfer (see [milestone-1.md](../milestone-1.md)).
- **Insertion:** with the power off. The card is not hot-pluggable.
- **No card fitted:** every signal has a main-board pull that leaves the
  machine running. CRESET_n and the flash chip selects are pulled up, CDONE
  is pulled up, and the bridge chip select is pulled up. The expanders power
  up as inputs, so CARD_RST_n and PROG_n are left to their pull-ups.

## Buses

Three independent SPI buses. They cannot share wires: at power-up each FPGA is
the master of its own flash, so the two flash buses have their own drivers,
and the bridge is ordinary chipset logic.

| Bus | Signals | Far end |
|---|---|---|
| Bridge | BR_SCK, BR_MOSI, BR_MISO, BR_nCS | chipset user I/O: RAM, ROM, CPU control, trace ([memory-map.md](memory-map.md)) |
| Chipset flash | FL0_SCK, FL0_MOSI, FL0_MISO, FL0_nCS, CHIPSET_nCRESET, CHIPSET_CDONE | the chipset's W25Q config flash and its CRESET_B/CDONE |
| CPU-card flash | FL1_SCK, FL1_MOSI, FL1_MISO, FL1_nCS, CPUCARD_nCRESET, CPUCARD_CDONE | through the CPU socket to the CPU card's W25Q and FPGA ([cpu-bus.md](cpu-bus.md)) |

To program a flash, sysctl holds that FPGA's CRESET_n low, which makes the FPGA
release its configuration pins. It then writes the flash and releases CRESET_n,
and the FPGA reboots from the new image. While CRESET_n is high, the sysctl
pins on that bus are inputs.

Other signals:
- I2C to the main board's two TCA9555 expanders (CARD_RST_n, PROG_n, presence)
- the card-programming port and its slot mux
- CC1/CC2 of the main board's USB-C (for the power policy), and the 1V2 rail
- SYS_nRST, open drain onto the reset supervisor's output

## Pinout

Side B is the component side. Every bus signal has a GND on at least one
neighbour.

| Pin | Side B (component side) | Side A (solder side) |
|---|---|---|
| 1 | +3V3 | PRSNT1_n |
| 2 | +3V3 | +3V3 |
| 3 | GND | GND |
| 4 | SYS_nRST | CC1 |
| 5 | V1V2_SENSE | CC2 |
| 6 | GND | GND |
| 7 | I2C_SDA | MUX_SEL0 |
| 8 | I2C_SCL | MUX_SEL1 |
| 9 | GND | MUX_SEL2 |
| 10 | PROG_CLK | GND |
| 11 | PROG_IO | +5V |
| — | *key* | *key* |
| 12 | GND | GND |
| 13 | BR_SCK | GND |
| 14 | GND | BR_MOSI |
| 15 | BR_MISO | BR_nCS |
| 16 | GND | GND |
| 17 | FL0_SCK | GND |
| 18 | GND | FL0_MOSI |
| 19 | FL0_MISO | FL0_nCS |
| 20 | GND | GND |
| 21 | CHIPSET_nCRESET | CHIPSET_CDONE |
| 22 | GND | GND |
| 23 | FL1_SCK | GND |
| 24 | GND | FL1_MOSI |
| 25 | FL1_MISO | FL1_nCS |
| 26 | GND | GND |
| 27 | CPUCARD_nCRESET | CPUCARD_CDONE |
| 28 | GND | GND |
| 29 | RSVD_B1 | RSVD_A1 |
| 30 | RSVD_B2 | RSVD_A2 |
| 31 | GND | GND |
| 32 | PRSNT2_n | RSVD_A3 |

PRSNT1_n is GND on the main board and the card joins it to PRSNT2_n, as on
PCIe. Nothing reads it in M1: the machine behaves the same with or without the
card. PRSNT2_n goes to a test pad.

## The system card

As built (`hw/boards/system.py`; the design notes are in `hw/boards/README.md`):

- **Power: the slot's +3V3 only** (B1, B2, A2), the main board's 3V3 rail, which
  the chipset, flashes and expanders it drives share. No regulator on the card;
  +5V (A11) is not connected. The ADC reference is that same +3V3.
- RP2040 (C2040) with a W25Q16 for its own firmware and a 12 MHz crystal
- A USB-C receptacle for the host, **data only**: 5.1 kΩ Rd on CC1/CC2, 27 Ω
  on D+/D−, USBLC6-2SC6 ESD (its rail pin on +3V3, not VBUS). VBUS powers
  nothing: it only drives a 2N7002's gate, which pulls GPIO29 (USB_nVBUS) low
  while a host is there. The firmware starts USB, and pulls D+ up, only then,
  and lets go of D+ when VBUS goes (a self-powered device, USB 2.0 7.1.5)
- 33 Ω source termination on the SPI outputs it drives (SCK, MOSI, nCS of the
  bridge and both flash buses); 10 kΩ I2C pull-ups
- **LEDs**, in a row along the top edge: PWR (red, +3V3), TX and RX (green,
  GPIO0/1: USB data to and from the host, lit ~30 ms). There is no status LED
  and no debug UART: GPIO0/1 were the UART, GPIO29 the status LED.
- **Test pads**, not a button: SWCLK, SWDIO, RUN, BOOTSEL (short it to GND
  while powering up for the USB boot ROM; it reaches QSPI_SS through 1 kΩ),
  +3V3, 1V1, GND, and RSVD_B1/B2
- PRSNT1_n (A1) is joined to PRSNT2_n (B32); RSVD_A1–A3 are not connected
- 4 layers, a 56 × 48 mm body above the x4 finger tab
