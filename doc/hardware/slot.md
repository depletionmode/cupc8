# I/O slots and the common card protocol (Milestone 1)

The main board has **six I/O slots**. They are PCIe x1-style vertical
card-edge sockets: 36 contacts, 1.0 mm pitch, with the key between pins 11
and 12. The pinout is custom. Never plug a real PCIe card in.

- **Cards are plugged or removed only with the power off.** They are not
  hot-pluggable, and nothing is built to survive a card pulled while running.
- **Slots are electrically identical.** Slot *n* (1–6) is SPI device *n−1*
  (see `memory-map.md`).
- **M1 uses four slots:** graphics, IO, Wi-Fi and storage. Slots 5–6 are free for
  future cards.
- **Card:** a 1.6 mm PCB with gold fingers (hard gold, 30° bevel: `milestone-1.md`), 18 per
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

Budget per card: ≤ 0.55 A from +5V and ≤ 300 mA from +3V3. The +5V figure is
what the slot's 0.75 A-hold PTC fuse still holds at 40 °C (0.65 A) less a
margin (`hw/power`, POW-006 B9). Every M1 card is well inside it. The
whole-system budget is in `power.md`.

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
  the opcode and arguments. The MISO bytes after the status byte in a command
  frame mean nothing, and the host ignores them. A card preloads a whole
  frame's MISO before CS_n falls, so it may already be offering its current
  response there.
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
  instead. The storage card's commands are **exempt** (`storage-card.md`):
  an SD card can be busy for 250 ms on a write, so READ returns RESP_LEN
  `$00` until the answer is ready, and the host retries for seconds, not
  milliseconds. The common opcodes ($F0–$F2) keep the 5 ms deadline on every
  card.
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
| $01 | Graphics: HDMI (`gpu-protocol.md`) or e-paper (`eink-card.md`); `INFO` says which |
| $02 | IO / USB keyboard (`io-card.md`) |
| $03 | Wi-Fi networking (`wifi-card.md`) |
| $04 | Storage (`storage-card.md`; M1: microSD) |
| $05–$FE | reserved |

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

sysctl selects the slot on the programming-port mux, then moves raw SWD
transfers or UART bytes on the same two pins (`sysctl.md`, "The card
programming port"). The protocols run in the host command,
`cupc8.py card flash <slot> firmware.{elf,bin}`.

- **SWD** (RP2040 cards): the RP2040's multi-drop SWD, then the boot ROM's
  flash routines, as a debugger uses them.
- **UART bootloader** (ESP32 cards):
  1. Hold PROG_n low.
  2. Pulse CARD_RST_n.
  3. Flash with Espressif's `esptool`, at 115200 baud, through sysctl's UART
     tunnel.

`cupc8.py card flash` tries SWD first. If no debug port answers, it tries the
ESP ROM bootloader sync.

- **Blank cards.** A blank card from JLC has an empty QSPI flash. SWD loads
  the flash through the RP2040 boot ROM's flash routines, so blank cards need
  no BOOTSEL.
- **Fallback pads.** Each card still has a BOOTSEL pad and SWD test pads, for
  bring-up debugging only.

## Mechanical

- **Slot pitch:** 20.32 mm, for the full-height cards. Six slots take ≈ 122 mm.
- **Card outline:** every I/O card has the **same outline**, so that cards
  line up in the case and their power LEDs sit in one row. In KiCad's
  `BUS_PCIexpress_x1` footprint frame (finger B1 at the origin, fingers
  pointing +y):
  - the body is x −6.0 … 56.0 mm, y −44.0 … −4.95 mm (62 × 39.05 mm above the
    finger tab);
  - **M3 mounting hole** (3.2 mm, non-plated, 6.4 mm keep-out) centred at
    (52.0, −40.0), 4 mm in from the top-right corner;
  - **power LED** (0603, lit from the card's own 3.3 V rail) centred at
    (−3.0, −41.0), 3 mm in from the top-left corner, the same on every card;
  - **other LEDs** (link, activity) in a row along the top edge to the
    right of the power LED, centred on the same line (y = −41.0);
  - the board's **name and revision** (`<name> rev <X>`) on the silkscreen
    in the bottom-right corner of the body;
  - nothing but the fingers' ground ties within 5 mm above the tab.
  `hw/tools/kicadgen.py` carries these as `IO_CARD_*`. Every I/O card's
  script builds with `pipeline(io_card=True)`, which takes the outline from
  there and refuses a card whose outline, finger connector, M3 hole or power
  LED is not at these positions. The system card, in its own keyed slot, has
  its own outline (`system-slot.md`).
- **Connectors:** on the card's top edge, facing away from the main board.
- **Mounting:** each card has an M3 hole that lines up with a standoff on a
  main board mounting rail.
- **Fit check:** the exact drawing is in `hw/lib/cards/card-outline.kicad_pcb`
  and is checked by the FreeCAD fit script.
  - The script is `hw/mech/fit.py` (MECH-001…008 in `test/catalogue.toml`,
    verification.md 4.7). It checks the outline against `IO_CARD_*` as
    built, since `hw/lib/cards/card-outline.kicad_pcb` does not exist yet.
    Until the main board is drawn, it places the slots from a stand-in:
    six C404113 sockets at 20.32 mm.
  - *Measured 2026-09-24, from the datasheets.* The x1 socket (UMAX
    3183-10200P1T) is 11.25 mm tall, with a 1.78 mm slot 7.60 mm deep. So a
    seated card's edge sits 3.65 mm above the main board, and the card's
    shoulder sits 0.80 mm above the housing (the finger tab is 8.40 mm).
  - With the Wi-Fi card in every slot: 16.28 mm between one card's tallest
    part (the ESP32-C3 module, 2.44 mm) and the next card's back. The 20.32
    mm pitch leaves 18.72 mm clear of the 1.6 mm board. The PCIe CEM
    envelope is 14.47 mm on the component side and 2.67 mm on the solder side.
  - The M3 hole axis (the rail) is 47.10 mm above the main board's top, and
    the power LEDs are 48.10 mm above it.
