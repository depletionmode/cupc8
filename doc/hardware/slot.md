# I/O slots and the common card protocol (Milestone 1)

The main board has **six I/O slots**. They are PCIe x1-style vertical
card-edge sockets: 36 contacts, 1.0 mm pitch, with the key between pins 11
and 12. The pinout is custom. Never plug a real PCIe card in.

- **Slots are electrically identical.** Slot *n* (1–6) is SPI device *n−1*
  (see `memory-map.md`).
- **M1 uses three slots:** graphics, IO and Wi-Fi. Slots 4–6 are free for
  future cards.
- **Card:** a 1.6 mm PCB with gold fingers (hard gold, 45° bevel), 18 per
  side.

## Pinout

| Pin | Side B (component side) | Side A (solder side) |
|---|---|---|
| 1 | +5V | PRSNT1_n (GND on main board) |
| 2 | +5V | +5V |
| 3 | GND | GND |
| 4 | +3V3 | +3V3 |
| 5 | GND | GND |
| 6 | SWCLK | RSVD_A1 |
| 7 | SWDIO | RSVD_A2 |
| 8 | GND | GND |
| 9 | CARD_RST_n | RSVD_A3 |
| 10 | IRQ_n | RSVD_A4 |
| 11 | GND | GND |
| — | *key* | *key* |
| 12 | GND | GND |
| 13 | SCK | GND |
| 14 | GND | CS_n |
| 15 | MOSI | GND |
| 16 | MISO | RSVD_A5 |
| 17 | GND | GND |
| 18 | PRSNT2_n | PROG_n |

- **Power:** 3× +5V and 2× +3V3, about 1 A per contact.
- **Presence detect:** the card joins A1 to B18, so the main board sees
  PRSNT2_n low only when the card is fully seated. PRSNT2_n goes to sysctl
  through an I²C expander.
- **SCK** has GND on both neighbours and opposite.
- **RSVD pins:**
  - Main board: go to test pads only. They are **not** connected to the
    chipset in M1, because it has no spare pins.
  - Cards: must leave them unconnected.

## Electrical

| Signal | Direction | Notes |
|---|---|---|
| SCK, MOSI, CS_n | main → card | 3.3 V push-pull from the chipset, 33 Ω series at the source. SCK ≤ 6 MHz. |
| MISO | card → main | Push-pull while this card's CS_n is low, **Hi-Z otherwise** (all slots share MISO). 47 kΩ pull-up on the main board. |
| IRQ_n | card → main | **Open-drain**, active low, level. 4.7 kΩ pull-up on the main board, one per slot. Read in `$f202`. |
| CARD_RST_n | main → card | Per slot, open-drain from the sysctl I²C expander. Low = the card MCU is held in reset (RP2040 RUN, ESP32 EN). Released 10 ms after the rails are good. |
| SWCLK, SWDIO | main ↔ card | The card **programming port**, driven by sysctl through a 1-of-6 analog mux (2× 74HC4051). It speaks **SWD** to RP2040 cards, or **UART** to cards whose MCU has a UART ROM bootloader (e.g. ESP32): SWCLK = card RX, SWDIO = card TX. 33 Ω series on the main board. |
| PROG_n | main → card | Boot-mode strap for UART-bootloader cards: low while CARD_RST_n rises = enter the ROM bootloader (e.g. ESP32 GPIO9). Open-drain from the sysctl I²C expander. RP2040 cards leave it unconnected. |
| +5V | main → card | Each slot is fed through its own 750 mA-hold PTC fuse, a 0 Ω isolation link and a 50 mΩ sense resistor with test pads. |
| +3V3 | main → card | From the main 3V3 buck. Max 300 mA per card. Cards with heavy loads regulate from +5V instead. |

Budget per card: ≤ 1 A total from +5V and +3V3 combined. The whole-system
budget is in `power.md`.

## Common card protocol

Every card is an SPI slave in **mode 0**, MSB first. The CPU (through the
chipset) is always the master.

### Framing

- **A command is one CS_n-low frame.** The host sets `SPI_CS=1`, sends
  opcode and argument bytes, clocks any response bytes, then sets
  `SPI_CS=0`.
- **Resync.** A CS_n rising edge ends the frame. The card discards any
  incomplete command, so a lost byte can never desynchronise a card for
  longer than one frame.
- **Status byte.** While the host shifts out the **opcode** byte, the card
  shifts out its **status byte**. The card preloads it before CS_n falls.
  Its meaning is card-specific, but **bit 7 is always 0**, so an empty slot
  (MISO pulled up) reads as `$FF`.
- **Responses come in a separate READ frame.** A command frame carries only
  the opcode and arguments, and the card returns `$00` after the status byte.
  If the command has a response, the host collects it with a **READ frame**:
  1. Send `$FE`, and receive the status byte in return.
  2. The next byte returned is **RESP_LEN**, the number of response bytes that
     follow. `$00` means the response isn't ready yet: end the frame and try
     again.
  3. Clock out RESP_LEN more bytes, sending `$00`.

  A new command discards any unread response. The rule suits every MCU:
  RP2040 cards use PIO, and ESP32 cards use a DMA SPI slave that can't change
  its reply part-way through a frame. An empty slot returns RESP_LEN `$FF`,
  because MISO is pulled up.
- **Response deadline:** a card must have its response ready within **5 ms**
  of the command frame's CS_n rising, unless the command says otherwise.
  Network operations complete asynchronously and signal through events
  instead.
- **Timing the host must meet:**
  - ≥ 2 µs from CS_n falling to the first SCK edge
  - ≥ 1 µs between bytes
  - ≥ 20 µs between the end of one frame and the start of the next, so the
    card can re-arm

  At CUPC/8 speeds, the per-byte `st`/`ld` polling loop meets these with
  room to spare. The co-simulation still checks them.

### Opcodes common to all cards ($F0–$FF)

| Opcode | Name | Args → response | Action |
|---|---|---|---|
| $F0 | IDENT | → type, fw_major, fw_minor, `$C8` | Identify. `$C8` is a signature byte. Any other value means "no card / not a CUPC/8 card". |
| $F1 | SOFT_RESET | — | Card returns to its power-on state (e.g. the GPU clears the screen, the IO card empties its FIFO). |
| $F2 | IRQ_EN | en8 | 0 = never assert IRQ_n, 1 = assert per card rules. Power-on default is 0. |
| $F3–$FD | reserved | | Cards ignore them. |
| $FE | READ | → RESP_LEN, response… | Collect the response to the previous command (see Framing) |
| $FF | — | | Never an opcode, so an idle or floating MOSI does nothing |

Card types (the `type` returned by IDENT, stored by the boot ROM in the slot
table):

| Type | Card |
|---|---|
| $00 | empty slot (IDENT failed) |
| $01 | Graphics / HDMI (`gpu-protocol.md`) |
| $02 | IO / USB keyboard (`io-card.md`) |
| $03 | Wi-Fi networking (`wifi-card.md`) |
| $04–$FE | reserved |

Opcodes $00–$EF are card-specific. In every card spec, **→** marks response
bytes, which are collected with a READ frame.

### Probe sequence (boot ROM)

For each dev 0–5:
1. Set SPI_CFG to `clk_div=2` (3 MHz), mode 0.
2. Send the frame `$F0`.
3. Wait ≥ 5 ms, then send a READ frame: `$FE`, then read RESP_LEN and 4 bytes.
4. If RESP_LEN = 4 and the 4th byte is `$C8`, record the 1st byte as the type.
   Otherwise record `$00`.

## In-system programming of card firmware

sysctl selects the slot on the programming-port mux. It then uses one of two
engines, both implemented in PIO on the same two sysctl pins. The host command
is `cupc8.py card flash <slot> firmware.{elf,bin}`.

- **SWD** (RP2040 cards): the Raspberry Pi `debugprobe` engine.
- **UART bootloader** (ESP32 cards):
  1. Hold PROG_n low.
  2. Pulse CARD_RST_n.
  3. Flash with Espressif's `esp-serial-flasher` protocol at 921600 baud.

`cupc8.py card flash` tries SWD first. If no debug port answers, it tries the
ESP ROM bootloader sync.

- **Blank cards.** A blank card from JLC has an empty QSPI flash. SWD loads
  the flash through the RP2040 boot ROM's flash routines, so blank cards need
  no BOOTSEL.
- **Fallback pads.** Each card still has a BOOTSEL pad and SWD test pads, for
  bring-up debugging only.

## Mechanical

- **Slot pitch:** 20.32 mm, for the full-height cards. Six slots take ≈ 122 mm.
- **Card outline:** max 100 mm × 60 mm above the socket.
- **Connectors:** on the card's top edge, facing away from the main board.
- **Mounting:** each card has an M3 hole that lines up with a standoff on a
  main board mounting rail.
- **Fit check:** the exact drawing is in `hw/lib/cards/card-outline.kicad_pcb`
  and is checked by the FreeCAD fit script.
