# Proposal: an e-ink graphics card (a second option for the graphics card)

**Status: proposal, for exploration — not scheduled; raised 2026-09-24 by David.**

## Decisions (David, 2026-09-24)

These settle the open questions at the end; where the text below still
argues for an option, these win.

1. **A replacement for the HDMI graphics card, never fitted with it.** A
   machine has one or the other. It takes the **same card type, $01**
   (graphics / the console), so the boot ROM finds it the same way; it
   says what it is in `INFO`, and the kernel may carry a driver for each and
   choose by `INFO`.
2. **Connection: the panel on its driver module, by cable to one header on
   the card** (the module carries the booster). The header is a **2.54 mm
   9-pin header, with a TVS array** on its lines (it is touched from
   outside).
3. **Panel: the 5.83" 648 × 480** (Good Display GDEY0583T81 with the
   DESPI-C02 adapter, UC8179 controller): 80 × 30 text in the 8 × 16 font
   fills it almost exactly (640 × 480). The firmware keeps the 7.5"
   800 × 480 (same controller) working too, as `INFO` reports the panel.
4. **Text layout: 80 × 30, centred** (4 blank pixels each side on the
   5.83").
5. **Ink rule as proposed:** each text cell's brighter colour becomes ink,
   so the console is black text on white; GFX pixels keep their brightness.
6. **The native 4-grey graphics mode at the panel's full resolution is in
   the first version** (the 16-bit-coordinate commands below).
7. **Refresh defaults:** partial refresh after 150 ms idle, at least once a
   second under continuous output, a full refresh after 30 partials (to tune
   on a real panel).

**Hardware and software:** a new I/O card, the **e-ink card**, that drives an
e-paper display instead of HDMI. It plugs into any I/O slot and speaks the
same slot SPI, the same common card protocol and, as far as it makes sense,
the same GPU command set (`gpu-protocol.md`), so the boot ROM and the kernel
can use it as the console without change. It is an alternative to the HDMI
graphics card, not an addition to M1. The main board, the slot pinout and the
kernel stay as they are. Nothing here is drawn or written yet.

David's notes while this was written: the display is for **graphics as well
as text**, so graphics get their own mode at the panel's native resolution
(below), and the proposal gives **costs and availability** for the card and
the panels.

## Why

The HDMI card needs a monitor. An e-paper panel is a display that is part of
the machine: it is readable in daylight, needs no monitor or cable to a
monitor, draws almost nothing, and keeps its picture with the power off. A
text console is almost the ideal e-paper load. The screen changes in bursts
(a line typed, a `LIST`) and then sits still.

Two things make it harder than HDMI:

- **Refresh is slow and visible.** A full refresh takes 3–4 s and flashes
  the screen black and white several times. A partial refresh takes
  0.3–0.4 s on the panels below and doesn't flash, but it leaves ghosting
  that a full refresh has to clear from time to time.
- **There is no frame rate.** Nothing redraws 60 times a second. The card
  has to decide *when* to push changes to the panel. This proposal leaves
  that decision on the card, so the kernel keeps sending `PUTC` as it does
  today.

## Summary of the recommendation

- **Panel:** a **7.5" 800 × 480 black/white panel with a UC8179-class
  controller** (Good Display GDEY075T7, or Waveshare's 7.5" V2, which is
  the same class of panel). It has 4 grey levels, a 0.3–0.4 s partial
  refresh and 125 dpi. That gives 80 × 30 text in the existing 8 × 16 font,
  at a comfortable size (a character cell is 1.6 × 3.3 mm).
- **Card:** the same RP2040 core as the other cards, plus **one 9-pin
  header** on the top edge. The panel comes on its **driver module**
  (Waveshare's e-Paper HAT, or Good Display's DESPI-C02 adapter), which
  carries the high-voltage booster, and plugs into the header with a loose
  cable. That makes **26 placed parts** and about $2.60 of parts per card
  (tables below).
- **Protocol:** IDENT reports **type $01**, the graphics type, so the boot
  ROM and the kernel take it as the console with **no code change**. TEXT
  and GFX work as on HDMI. New commands say what the display is (`INFO`),
  force a refresh (`REFRESH`), set the automatic refresh policy (`AUTO`) and
  add a **native 800 × 480, 4-grey graphics mode** with 16-bit coordinates.
- **Refresh:** the card refreshes on its own. When the command stream goes
  idle (150 ms by default), it does a partial refresh of the rows that
  changed. After enough partial refreshes it does a full refresh, at the
  next idle moment, to clear ghosting. `CLS` also triggers a full refresh.
- **Alternative:** a bare panel's 24-pin FPC straight onto the card, with the
  booster circuit on the card. This adds 19 parts, and the panel then has to
  sit within its short FPC tail of the card.

## Display options

None of these panels is in JLC's assembly library with stock. Searching
`e-paper`, `e-ink display`, `GDEY` and `GDEW` with `jlcparts.py search` on
2026-09-24 found only zero-stock entries, and one 2.13" HAT (C359941) with a
stock of 1. So **the panel is bought separately** and plugged in by the
owner, like the Wi-Fi antenna. JLC only places the card's parts, including
the connector the panel plugs into.

| Panel | Size, resolution | Controller | Text at 8 × 16 | Refresh: full / fast / partial (25 °C) | Greys | What you buy | Price, 1 off (2026-09-24) | Availability | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Good Display GDEY075T7** | 7.5", 800 × 480, 125 dpi, 163 × 98 mm active | UC8179 | 100 × 30 (80 × 30 used), cell 1.6 × 3.3 mm | 3 s / 1.5 s / **0.3 s** | 4 | bare panel, 24-pin FPC; add the DESPI-C02 adapter ($8.50) | **$29.69** + $8.50 (buy-lcd.com) | panel and adapter both out of stock at buy-lcd; also at Evelta, AliExpress | **Primary.** Cheapest large panel. |
| **Waveshare 7.5" e-Paper HAT (V2)** | as above | UC8179-class (Waveshare's spec: GD7965) | as above | 4 s / 1.5 s / 0.4 s | 4 | panel + driver board + 20 cm GH1.25 9-pin cable | **$56.99** (raw panel $47.99) | listed at Waveshare, Amazon | **Primary, one-box option.** Same panel class, and the cable is included. |
| Good Display GDEY0583T81 | 5.83", 648 × 480, ≈ 139 dpi | UC8179 | **81 × 30**, cell 1.5 × 2.9 mm | 3 s / 1.5 s / 0.3 s (4-grey 2 s) | 4 | bare panel; add DESPI-C02 | ≈ $33 (Evelta ₹2,928 ex GST) | out of stock at Evelta | **Alternative.** 80 × 30 fills it almost exactly. Same controller as the primary, so the same firmware. |
| Good Display GDEY0426T82 | 4.26", 800 × 480, 219 dpi, 93 × 56 mm | SSD1677 | 100 × 30, but the cell is 0.9 × 1.9 mm (about 5 pt) | 3.5 s / 1.5 s / 0.42 s | 4 | bare panel; add DESPI-C02 | $16.07 (buy-lcd) | out of stock at buy-lcd; also AliExpress, OpenELAB | **Alternative** for graphics (sharp and small). Text is tiny. Needs a second panel driver (SSD1677). |
| Waveshare 4.26" e-Paper HAT | as above | not stated on the page (SSD1677-class) | as above | 4 s / — / 0.7 s | 4 | panel + driver board + cable | $31.99 | listed at Waveshare | As above, in one box. |
| Waveshare 2.9" module | 2.9", 296 × 128 | SSD1680-class | 37 × 8 | 3 s / — / 0.6 s | 4 | module + PH2.0 8-pin cable | $21.99 | listed | **No:** too small for a console. |
| Waveshare 10.3" e-Paper HAT | 10.3", 1872 × 1404 | IT8951 (its own timing controller) | 234 × 87 | < 1 s full, A2 mode faster | 16 | HAT, 5 V, 1.2 W while refreshing | $199.99 | listed | **Not now.** A different protocol (IT8951 host commands), and costly. A later card could drive it. |
| Waveshare 7.5" HD (880 × 528) | 7.5" | — | 110 × 33 | 5 s full | 2 | HAT | $61.99 | discontinued | No. |
| Pervasive Displays iTC panels (4.37", 7.4" …) | various | own iTC controller | — | fast and partial update with their EXT3 board | — | panel + EXT3-1 board | not listed (Mouser) | distributors | Not evaluated further: their own driver library and board, and dearer. |

Tri-colour (red/yellow) and Spectra colour panels are out: they refresh in
15–30 s and have no partial refresh.

Refresh times are the vendors' figures at 25 °C. Every vendor says to do a
full refresh after a run of partial refreshes (Good Display says after 5
fast or partial updates for the 5.83"). How long a run can be before the
ghosting shows is something to tune on the real panel (see Refresh policy).

## Hardware

### Recommended: the RP2040 core and one header (a module with its own booster)

The card is the RP2040 core that the GPU and IO cards use, plus a header for
the panel's driver module. The module (Waveshare's e-Paper HAT or Driver HAT,
or Good Display's DESPI-C02) carries the panel's FPC connector and its
booster (the inductor, MOSFET, three Schottky diodes and about ten capacitors
that make the ±15–20 V gate and source voltages). The card gives it 3.3 V
and six logic lines.

- **MCU: RP2040**, the same as the GPU, IO and system cards, so that:
  - the slot SPI slave (`fw/rp2040/common/slotspi.c`) and the card engine
    (`fw/common/cardproto.c`) are shared;
  - the GPU interpreter (`fw/gpu/core`) runs unchanged for TEXT and GFX;
  - sysctl flashes it over SWD like the other cards, including blank cards
    from JLC;
  - the native RP2040 emulator runs its real binary in the whole-machine
    tests.

  A smaller MCU with internal flash (an STM32G0, say, with 144 KB of RAM)
  would save the flash chip and crystal, about 4 parts. But it would need a
  new SWD flash algorithm in sysctl, a new emulator and a second firmware
  structure. A tiny one (CH32V003, 2 KB RAM) can't hold a framebuffer: 800 ×
  480 at 1 bit is 48 KB. RP2040 it is.

  A card with **no MCU** at all, with the CPU driving the panel controller
  directly, is out too. The panel needs D/C, RST and BUSY lines that the slot
  doesn't have, it wouldn't answer IDENT, and the kernel would have to render
  every glyph.
- **Clock:** 125 MHz. There is no TMDS, so it doesn't need the HDMI card's
  252 MHz.
- **Panel SPI on the RP2040's SPI1**, as the master:

  | Signal | GPIO | Header pin (Waveshare order) |
  |---|---|---|
  | +3V3 | — | 1 VCC |
  | GND | — | 2 GND |
  | EPD_MOSI (SPI1 TX) | 11 | 3 DIN |
  | EPD_SCK (SPI1 SCK) | 10 | 4 CLK |
  | EPD_CS_n | 9 | 5 CS |
  | EPD_DC | 12 | 6 DC |
  | EPD_RST_n | 13 | 7 RST |
  | EPD_BUSY (in) | 14 | 8 BUSY |
  | EPD_PWR | 15 | 9 PWR (Waveshare Rev 2.3 boards switch the panel's power with it; 8-pin modules leave it unconnected) |

  The slot side keeps the GPU card's GPIOs (SCK 2, MOSI 3, MISO 4, CS_n 5,
  IRQ_n 6), so `hw/pins.yaml` gets an `epd_mcu` block that is `gpu_mcu`'s
  slot group plus the table above. BUSY's polarity differs by controller:
  it is low when busy on the UC8179 and high when busy on the SSD1677. The
  firmware handles that per panel.
- **Connector: a 1 × 9 right-angle 2.54 mm male header** (PZ254R-11-09P,
  C492417), in Waveshare's pin order, with each pin's name on the
  silkscreen.
  - Waveshare's modules ship with a 20 cm cable, GH1.25 9-pin (Rev 2.3) or
    PH2.0 8-pin (older), whose other end is, as far as the product photos
    show, 2.54 mm female jumpers. The first 8 pins are in the same order, so
    either cable fits. *To confirm on a cable in hand.* If the far end turns
    out to be GH1.25 too, the header becomes an SM09B-GHS-TB (C265420, 8,866
    in stock, $0.34).
  - The DESPI-C02 has an 8-pin male header in a different order (BUSY, RES,
    D/C, CS, SCK, SDI, GND, 3.3V). It connects with eight loose
    female–female jumpers.
- **Power:** the card runs from the slot's +3V3, like the GPU and IO cards,
  and the module takes the same 3.3 V (both modules also accept 5 V; 3.3 V
  keeps their logic at the RP2040's levels).
- **LEDs:** the power LED at the standard spot. **ACT** (GPIO25, as on the
  GPU card) sits in the top-edge row and lights while the panel is
  refreshing. It is the one sign that the card is working while the panel
  still shows an old picture.
- **Placement:** the header is on the **top edge** (`slot.md`, "Connectors:
  on the card's top edge"), between the LED row and the M3 hole's 6.4 mm
  keep-out. The 9 pins take 23 mm of the 45 mm free there. The cable leaves
  through a slot in the case lid to wherever the panel is mounted. The panel
  itself (170 × 111 mm for the 7.5") is bigger than the card, so it can't
  live on it anyway. Mounting it on the case is the case design's job.
- **No level shifting and no ESD parts.** The lines stay at 3.3 V, and they
  go to a module in the same enclosure rather than to a user-facing socket.
  An open question asks whether a TVS array is still wanted, as on the IO
  card's microSD.

**Component count, recommended design** (stock and price from
`jlcparts.py` / JLC's API, 2026-09-24, unit price at 1–9):

| Ref | Part | LCSC | Type | Stock | Unit $ | Qty |
|---|---|---|---|---|---|---|
| U1 | RP2040 | C2040 | ext | 73,350 | 0.988 | 1 |
| U2 | W25Q16JVSSIQ flash | C131025 | ext | 17,261 | 1.204 | 1 |
| Y1 | 12 MHz crystal X322512MSB4SI | C9002 | basic | 72,053 | 0.095 | 1 |
| | 15 pF C0G 0603 (crystal) | C1644 | basic | 1,111,529 | 0.011 | 2 |
| | 1 kΩ 0603 (crystal series; power LED) | C21190 | basic | 23.9 M | 0.003 | 2 |
| | 1 µF 0603 (VREG in and out) | C15849 | basic | 6.2 M | 0.017 | 2 |
| | 100 nF 0603 (RP2040 supply pins ×10, flash ×1) | C14663 | basic | 51.4 M | 0.012 | 11 |
| | 10 µF 0603 bulk | C19702 | basic | 11.2 M | 0.032 | 1 |
| | 10 kΩ 0603 (RUN pull-up) | C25804 | basic | 23.0 M | 0.002 | 1 |
| D1 | red LED 0603 (power) | C2286 | basic | 4.0 M | 0.008 | 1 |
| D2 | green LED 0603 (ACT) + 100 Ω (C22775, basic) | C12624 | ext | 356,043 | 0.012 | 1 + 1 |
| J2 | 1 × 9 right-angle 2.54 mm header PZ254R-11-09P | C492417 | ext | 2,307 | 0.069 | 1 |
| | **Total** | | **4 extended types** | | **≈ $2.60 a card** | **26 parts** |

The slot's gold fingers, the M3 hole and the BOOTSEL, SWD and UART test pads
are part of the PCB, not placed parts. The RP2040 core above is the usual
minimal one (Raspberry Pi's *Hardware design with RP2040*). The GPU and IO
cards' own core will be drawn first, and this card copies it.

### Alternative: a bare panel on the card (FPC and booster)

The panel's 24-pin, 0.5 mm FPC goes straight into a connector on the card,
and the card carries the booster. This is the reference circuit from the
panel datasheets (Waveshare's 7.5" V2 spec §1.6, the same as Good Display's):

| Part | Value | LCSC | Type | Stock | Unit $ | Qty |
|---|---|---|---|---|---|---|
| FPC connector, 24 pin, 0.5 mm, double-sided contacts | FPC-05FB-24PH20 | C2856831 | ext | 33,064 | 0.201 | 1 |
| MOSFET (datasheet: Si1304BDL or Si1308EDL) | SI1308EDL-T1-GE3 | C469327 | ext | 43,318 | 0.319 | 1 |
| Schottky diodes | MBR0530T1G | C82046 | ext | 337,271 | 0.069 | 3 |
| Inductor, 10 µH, 1 A, wire-wound | FNR4012S100MT | C167785 | ext | 4,415 | 0.059 | 1 |
| RESE current-sense resistor | 0.47 Ω (UC8179) | C23411 | ext | 123,472 | 0.005 | 1 |
| GDR pull-down | 10 kΩ | C25804 | basic | 23.0 M | 0.002 | 1 |
| Capacitors 4.7 µF 50 V 0805 | | C98192 | ext | 398,079 | 0.095 | 2 |
| Capacitors 10 µF 50 V 1206 | | C13585 | basic | 2.6 M | 0.265 | 4 |
| Capacitors 1 µF 50 V 0805 | | C28323 | basic | 2.6 M | 0.040 | 5 |
| **Added** | | | **6 more extended types** | | **≈ $2.25** | **19 parts (45 in all)** |

Notes on the alternative:
- The datasheet asks for 50 V capacitors throughout, since the rails reach
  about ±20 V. AO3400A (C20917, basic, 1.08 M in stock) is Good Display's
  named substitute for the MOSFET.
- **RESE depends on the panel:** 0.47 Ω for the UC8179 panels, 3 Ω
  (C22356394) or 2.2 Ω for most SSD16xx panels (DESPI-C02 and Waveshare
  Driver HAT notes). Choosing one fixes the card to one controller family.
  A GPIO-switched second resistor (one more small MOSFET) would let the
  firmware choose, at the cost of 2 more parts.
- **FPC contact side:** Good Display asks for a connector with contacts on
  the upper side or both sides. Hence the double-sided FPC-05FB (the
  bottom-contact FPC-05F-24PH20, C2856805, is cheaper but may not mate the
  right way up). To check against the panel drawing.
- **The panel has to sit at the card.** The 7.5" panel's FPC tail is only
  a couple of centimetres long (Waveshare's drawing; to measure), so the panel would sit right at the card's
  top edge, or need an FPC extension. That is awkward in a case with the
  card vertical in a slot.
- **It can't be checked before ordering.** The booster can't be verified in
  our simulation beyond a netlist check, and a wrong RESE value or a
  wrong-side FPC means a board that doesn't work. The modules' boosters come
  already working.

**Why the module is recommended:** 26 parts instead of 45, 4 extended part
types instead of 10 (JLC charges a loading fee for each extended part type
on each order, about $3), no high-voltage circuit of ours that we can't test
before ordering, any SPI panel the module supports (the module's own RESE
switch sets the controller family), and a panel that can be mounted
anywhere the cable reaches. The cost is the module: about $8.50 (DESPI-C02)
or $10 (Waveshare Driver HAT), or $0 extra with the Waveshare 7.5" HAT,
which comes with it.

### Power

| Load | Rail | Typ mA | Max mA |
|---|---|---|---|
| RP2040 at 125 MHz + flash | 3V3 | 25 | 50 |
| Panel refreshing (7.5" V2 spec: 8 mA typ, 12 mA max, 26–45 mW) plus the module's booster and translator losses | 3V3 | 15 | 40 |
| Panel idle (standby 0.2 mA; deep sleep 2 µA) | 3V3 | 0.2 | 0.3 |
| LEDs | 3V3 | 3 | 5 |
| **e-ink card** | 3V3 | **≈ 45** | **≈ 95** |

That is inside the slot's 300 mA of +3V3 and draws nothing from +5V. It is
less than the HDMI card it replaces (`power.md`: 90 mA typ and 145 mA max on
3V3 for the RP2040 at 252 MHz and the TMDS drive, plus 55 mA on 5V for the
monitor's EDID). A machine with the e-ink card instead of HDMI has about
50–100 mA more headroom. The rows go into `hw/power/budget.py` and POW-006
when the card is drawn.

### Costs and availability

Per machine (the card is ordered at JLC's minimum of 2 assembled, like the
other cards):

| Item | Where | Cost | Availability, 2026-09-24 |
|---|---|---|---|
| Card parts (26) | JLC assembly | ≈ $2.60 a card | every part in stock at JLC, lowest 2,307 (the header) |
| Extended-part loading fees | JLC | ≈ $3 × 4 types, per order | some are shared with the other cards when ordered together |
| Card PCB, 4-layer, hard-gold fingers | JLC | as the other I/O cards | — |
| **Panel, option 1:** GDEY075T7 + DESPI-C02 + 8 jumpers | buy-lcd.com (Good Display's shop), Evelta, AliExpress | $29.69 + $8.50 + ~$1 | both **out of stock** at buy-lcd today; other sellers vary |
| **Panel, option 2:** Waveshare 7.5" e-Paper HAT (V2), cable included | Waveshare, Amazon | $56.99 | listed |
| Panel, option 3: GDEY0583T81 (5.83") + DESPI-C02 | Evelta, Good Display | ≈ $33 + $8.50 | out of stock at Evelta |
| Panel, option 4: Waveshare 4.26" HAT | Waveshare | $31.99 | listed |

So an e-ink console costs about **$40–$60 for the panel** plus a few
dollars for the card, against the HDMI card's connector and ESD parts plus a
monitor. Panel stock moves quickly at the small shops. Buy the panel with
the JLC order, as the antenna is.

## Protocol (card type $01, the GPU protocol plus e-paper additions)

### Identity: type $01, so nothing else changes

IDENT returns **type $01** (graphics). The boot ROM (`rom/boot.s`: "the first
graphics card becomes the console") and the kernel (`kernel/gpu.s`: "card
type 1 is graphics") look for exactly that, so the e-ink card becomes the
console with no ROM or kernel change. Everything they send (`MODE`, `CLS`,
`PUTC`, `ATTR`, `FILL_RECT`) means the same on e-paper. `slot.md`'s type
table becomes "$01 Graphics (HDMI or e-paper; `INFO` says which)".

The other way is a new type **$05** ($04 is the storage card, `storage-card.md`), which would change the boot ROM's and
the kernel's card search (`eq r1, #1` → 1 or 4). A new type is more honest,
but it touches the ROM for no gain that `INFO` doesn't also give. This is an
open question.

The IDENT deadline still holds. The boot ROM waits only 5 ms for IDENT, and
panel start-up takes hundreds of milliseconds (reset, BUSY, a full refresh
of 3–4 s). The slot side runs on its own core and answers at once, whatever
the panel is doing.

### TEXT mode on e-paper

- **Geometry: 80 × 30 cells of 8 × 16, exactly as on HDMI**, so no software
  changes. On the 800 × 480 panel the 640 × 480 text area is centred, with
  80 px of white margin on each side. This is `gpu_render()`'s 640 × 480
  frame as it is today, so the renderer is reused unchanged. Two other
  options, as an open question: 80 columns in 10-pixel cells (the 8-pixel
  glyph with a 1-pixel gap each side), which fills the width, or 100 × 30,
  which needs software that asks `INFO` for the size. On the 5.83" panel
  (648 × 480) 80 × 30 fills the screen with 4 px to spare each side.
- **Colours to ink.** The console's attributes assume a dark screen (the
  default `$07` is light grey on black). On paper that should come out as
  black text on white. The rule, per cell: **the brighter of the cell's two
  colours is ink (black), the darker is paper (white)**, and equal colours
  are all paper. So `$07` gives black text on white, and inverse video
  (`$70`, which the kernel uses) gives white text on a black bar, as
  expected. Brightness is the palette entry's luminance (Y = 0.299 R +
  0.587 G + 0.114 B from its RGB565). Colours beyond that are lost, as they
  must be on a black and white panel.
- **Cursor:** drawn, but **not blinking**. A blink would mean a partial
  refresh every half second for as long as the machine sits at a prompt,
  building up ghosting. `CURSOR` 1 (underline) and 2 (block) are static, and
  0 is off. A cursor move counts as a screen change like any other.
- `VSYNC_COUNT` still counts at 60 Hz from a timer, so software that times
  itself with it keeps working.

### GFX mode 1 (compatible): 320 × 240, as on HDMI

Mode 1 keeps its meaning: 320 × 240 at 8 bpp with the 256-entry palette,
every command as in `gpu-protocol.md`. It is shown pixel-doubled to
640 × 480 and centred, like TEXT. Each pixel's palette entry is turned into
a grey by luminance, **not** inverted here: in GFX mode black means black
ink.

- On a partial or fast refresh the panel shows only black and white, so
  greys are drawn with a **4 × 4 ordered (Bayer) dither**. An ordered dither
  is stable: changing one pixel changes only its own dot. With error
  diffusion, one changed pixel could change pixels far away, and so widen
  the partial refresh.
- A greyscale refresh (`REFRESH 3`, below) shows the 4 true grey levels
  instead.

BASIC's existing graphics and any program written for the HDMI card run
unchanged, and just look like a black and white print of the picture.

### GFX mode 2 (new): native 800 × 480, 4 greys

Graphics were raised as a real use, not only text. So the card offers the
panel's own resolution. The HDMI command set can't address it: Y is 8 bits
(0–255) throughout, and the panel is 480 rows tall. **Mode 2** is a native
bitmap of **800 × 480 at 2 bits a pixel** (grey 0 black, 1 dark grey, 2 light
grey, 3 white; `$FF` = transparent where noted), with its own drawing
commands in the free range **$40–$4F**. They are fixed-size like every GPU
command, and **both coordinates are 16-bit** little-endian:

| Op | Name | Args | Description |
|---|---|---|---|
| $40 | PIXEL2 | x16, y16, g | |
| $41 | FILL_RECT2 | x16, y16, w16, h16, g | |
| $42 | RECT2 | x16, y16, w16, h16, g | 1-pixel outline |
| $43 | LINE2 | x0_16, y0_16, x1_16, y1_16, g | Bresenham, both ends drawn |
| $44 | BLIT1_2 | x16, y16, w16, h16, fg, bg, then ⌈w/8⌉ × h bytes | 1 bpp, MSB left; `bg = $FF` transparent. The whole frame ≤ 8128 bytes, as for BLIT8. |
| $45 | BLIT2 | x16, y16, w16, h16, then ⌈w/4⌉ × h bytes | 2 bpp, 4 pixels a byte, leftmost in bits 7–6 |
| $46 | TEXT16 | x16, y16, fg, bg, len, ch × len | The 8 × 16 TEXT font at any pixel position; `bg = $FF` transparent |
| $47 | TEXT8_2 | x16, y16, fg, bg, len, ch × len | The 8 × 8 font |
| $48 | VSCROLL2 | dy16 (signed), g | Scroll up by dy rows (down if negative), fill with g |
| $49 | GETPIXEL2 | x16, y16 → g | After all earlier commands, like GETPIXEL |

`MODE 2` selects it and clears it to white. `CLS g` fills it. `MODE 2` on
the HDMI card is an unknown mode and is ignored, so software checks `INFO`
first.

**Moving whole pictures is practical here**, unlike 30 fps video on HDMI
(`m3-gpu-games.md`). A full 1-bit screen is 48,000 bytes: 6 `BLIT1_2`
frames. At the 200–300 KB/s that the CPU manages on the slot SPI (the
estimate in `m3-gpu-games.md`), it takes **0.16–0.24 s**, which is less than
one partial refresh. A full 4-grey screen is 96,000 bytes and takes
0.3–0.5 s. So a picture loaded from the microSD card (`io-microsd.md`) and
shown full screen is limited by the panel, not by the bus. A program that
draws should turn automatic refresh off (`AUTO 0`), draw, then send one
`REFRESH`, so the panel doesn't refresh half-way through a drawing.

### New general commands ($08–$0B)

These go in the free general range after `VSYNC_COUNT` ($07). The HDMI
card's firmware gets `INFO` too, and treats the other three as NOPs, so
software can send them to either card.

| Op | Name | Args → response | Description |
|---|---|---|---|
| $08 | INFO | → kind, w16, h16, greys, flags, cols, rows | `kind` 0 = HDMI, 1 = e-paper. `w`, `h`: native pixels (640 × 480 on HDMI; 800 × 480 for the 7.5"). `greys`: 4 (0 = colour, on HDMI). `flags`: bit 0 partial refresh, bit 1 mode 2 available. `cols`, `rows`: the TEXT grid (80, 30). |
| $09 | REFRESH | m | Refresh the panel now, with everything before it in the FIFO. `m`: 0 partial (only the changed rows), 1 fast full (one flash, about 1.5 s, clears ghosting), 2 clean full (the slow multi-flash waveform, 3–4 s), 3 greyscale full (4 levels, for pictures). Execution waits for the refresh to finish, so a `FENCE` after it fires when the picture is on the panel. Commands keep queuing meanwhile, up to the 8 KB FIFO. |
| $0A | AUTO | on, idle10, full_after | The automatic policy (below). `on` 0/1. `idle10`: the quiet time before a partial refresh, in 10 ms steps (default 15 = 150 ms). `full_after`: partial refreshes before a full one, 0 = never (default 30). |
| $0B | EPD_STATUS | → busy, dirty, partials | Whether the panel is refreshing, whether there are unshown changes, and partial refreshes since the last full one. |

The status byte stays as it is (FIFO FREE), and so does the FIFO's
acceptance guarantee. Unknown opcodes, including the M3 games range
$30–$3F, are ignored as on HDMI.

### Refresh policy (on the card)

The card keeps the picture it last sent to the panel. Every 10 ms, the panel
loop:

1. If automatic refresh is on, there are unshown changes, and the panel isn't
   busy: once the command stream has been **quiet for `idle10`** (150 ms),
   or changes have been waiting for **1 s** (continuous output, such as a
   long `LIST`), it renders the screen, **compares it with the shown
   picture**, and sends a **partial refresh of the band of rows that
   differ**. Comparing the finished image (48 KB, about 0.5 ms at 125 MHz)
   means the interpreter never has to track dirty regions itself, and a
   change that is undone before the refresh costs nothing.
2. After `full_after` partial refreshes, the next time the stream has been
   quiet for 2 s, it does a **fast full refresh**. Deferring the flash to a
   quiet moment keeps it from happening in the middle of typing.
3. `CLS`, form feed, `MODE` and `SOFT_RESET` make the next refresh a fast
   full one, since the whole screen changes anyway.
4. At power-on the card does one clean full refresh, of whatever the boot
   ROM has printed by then. Until then the panel still shows the picture
   from before power-off, which e-paper keeps.

What this means in use, from the vendors' refresh times:
- **Typing:** a key's echo reaches the panel about 0.5 s after the key press
  (150 ms quiet, then a 0.3–0.4 s partial refresh). Fast typing shows up in
  bursts. `idle10` can be lowered.
- **A `LIST` or a program printing:** the CPU sends a screen of text in
  well under 0.1 s, then goes quiet, so there is one refresh. Continuous
  output updates the panel about twice a second. Scrolling changes every
  row, so each of those is a whole-screen partial refresh, which the panels
  do in the same 0.3–0.4 s.
- Changes made while the panel is refreshing go into the next refresh, so
  nothing is lost.

The defaults (150 ms, 1 s, 30 partial refreshes) are guesses to be tuned on
the real panel. The simulation can check the policy and the controller
protocol, but not how the ghosting looks.

## Firmware

- **`fw/epd/core/`** (new, hardware-independent, host-tested like
  `fw/gpu/core`):
  - `epd.c`: the new commands, mode 2, the TEXT and GFX rasteriser to the
    panel's 800 × 480 (ink rule, dither), the compare-and-window step and the
    refresh policy on an injected clock.
  - `uc8179.c`, and later `ssd1677.c`: the panel controllers' command
    sequences (power on, the partial window, the old and new picture RAMs,
    refresh, deep sleep), over a four-function interface (SPI write, DC,
    RST, BUSY), written from the controller datasheets and the vendors'
    sample code (Waveshare's `e-Paper` repository; its licence to be checked before anything is borrowed).
    GxEPD2 is GPL-3.0, so it is a reference only and nothing is copied from
    it.
- **`fw/gpu/core/`** (small changes): a hook that passes unknown opcodes to
  an extension handler (the e-ink card's commands), `INFO` for the HDMI
  card, and the 320 × 240 GFX buffer in a union with mode 2's buffer (the
  modes are exclusive, and switching clears the buffer anyway).
- **`fw/rp2040/epd/main.c`** (new):
  - core 0: the slot SPI slave and the interpreter, as on the GPU card;
  - core 1: the panel loop (the refresh policy, rendering, SPI1 DMA to the
    panel, waiting on BUSY).
- **Memory** (RP2040, 264 KB):

  | Item | Size |
  |---|---|
  | TEXT buffer, fonts, FIFO | ≈ 19 KB |
  | GFX 320 × 240 (mode 1) / mode 2's 800 × 480 × 2 bpp, in a union | 96 KB |
  | The picture on the panel (1 bpp, for the comparison and the controller's "old picture" RAM) | 48 KB |
  | Band buffers for rendering and SPI DMA | ≈ 8 KB |
  | **Total** | **≈ 171 KB**, with no PicoDVI buffers |

- **Panel SPI time:** a full 1-bit picture, old and new, is 96 KB. At a
  10 MHz panel SPI that takes 77 ms, small next to the refresh itself.

## Kernel and BASIC

- **Kernel: no change is needed** for the console. The boot ROM and
  `kernel/gpu.s` find the card as type $01 and send the same commands.
- **Optional, later:**
  - `gpu_refresh` in `kernel/gpu.s`, a two-byte `REFRESH` frame;
  - BASIC: `REFRESH [m]`, `AUTO on`, and mode 2 drawing (`GMODE 2`, then the
    existing drawing statements with 16-bit coordinates);
  - picture loading from the microSD card, once `io-microsd.md` is in.
- A machine with both cards fitted uses the first type $01 card in slot
  order as the console (the boot ROM's rule), and the other one only if
  software looks for it.

## How it would be tested

Following the existing pattern, before anything is ordered:

- **Core, host tests** (`fw/epd/core`; new EPD-* rows next to GPU-001…003):
  - EPD-001: every new command with valid, boundary and malformed
    arguments, and the error counter. GPU-001's existing suite also runs
    against the e-ink build, so TEXT and GFX behave exactly as on HDMI.
  - EPD-002: the rasteriser against **golden 800 × 480 grey PNGs**:
    TEXT (all 256 attribute pairs through the ink rule, inverse video, both
    cursors, a redefined glyph), GFX mode 1 (the palette through luminance
    and dither), and every mode 2 command with clipping.
  - EPD-003: the refresh policy on a fake clock: the quiet time, the 1 s cap
    under continuous output, a full refresh deferred to a quiet moment, CLS
    making it full, the window covering exactly the changed rows, `AUTO 0`
    with an explicit `REFRESH`, and a `FENCE` after `REFRESH` firing only
    when the panel is done.
- **A panel controller model** (UC8179 first, then SSD1677):
  - It reads the SPI1 command stream with DC, RST and BUSY: power on and
    off, the partial window, the old and new picture RAMs, refresh, deep
    sleep.
  - It holds BUSY for the datasheet's refresh times (scaled for tests), and
    **fails the test on any command sent while BUSY**, or out of order
    (a refresh before power on, for example).
  - After each refresh it produces the panel's picture as an image.
  - It is checked against the controller datasheet's command table. It is
    one model, used by the host tests and by the emulator (and also compared
    between rp2040js and the native emulator, EMU-005 style).
- **Real binary in the emulator** (like GPU-004/005):
  - EPD-004, SPI side: the real `epd.elf` answers IDENT within 5 ms,
    including in the middle of a refresh and during start-up; FREE
    accounting; 300 PUTCs at full speed.
  - EPD-005, panel side: the same binary on the native RP2040 emulator with
    the controller model on SPI1. After each refresh, the model's picture
    equals the core's golden raster. It stays correct after SPI traffic at
    random moments, including traffic during a refresh.
- **End to end** (an e-paper twin of E2E-002):
  - The whole machine with the e-ink card in slot 1 instead of the HDMI
    card boots to BASIC. A typed program is run and listed, and the panel
    picture matches a golden image.
  - With both cards fitted, the first in slot order is the console.
- **Board:**
  - `pipeline(io_card=True)` (the standard outline, M3 hole, power LED);
  - the header nets in the co-simulation netlist check;
  - the +3V3 rows in POW-*;
  - the header on the top edge in MECH-*;
  - the ACT LED in the LED-row check;
  - `jlcparts.py check` on every LCSC number in the BOM (26 parts, stock
    ≥ 2 cards plus attrition).
- **Counterexamples** (`test/counterexamples.toml`) for the bugs these are
  meant to catch:
  - a change made during a refresh never shown;
  - a command sent while BUSY;
  - ghosting never cleared under continuous output;
  - IDENT answered late during a refresh.
- **Not testable before hardware:** how the ghosting looks, the waveform
  quality, and the partial refresh count before a full one is needed. The
  firmware is reprogrammed in-system, so these are tuned after the panel
  arrives. The panel is the one part that no simulation here stands in for,
  so the recommended design keeps the analogue side (the booster) on the
  vendor's module.

## What changes where (if it is taken up)

- `doc/hardware/eink-card.md` (new): the hardware, the ink rule, the refresh
  policy.
- `doc/hardware/gpu-protocol.md`: `INFO`, `REFRESH`, `AUTO`, `EPD_STATUS`,
  mode 2 and its commands. The e-paper behaviour of TEXT and GFX.
- `doc/hardware/slot.md`: type $01 is HDMI or e-paper.
- `doc/hardware/power.md`, `parts.md`: the card's rows. The panel as a loose
  purchase, like the antenna.
- `doc/hardware/verification.md` and `test/catalogue.toml`: the EPD-* rows
  and the E2E twin.
- `hw/pins.yaml` (`epd_mcu`), `hw/boards/eink.py` (new), `hw/cosim`,
  `hw/power/budget.py`.
- `fw/epd/core`, `fw/rp2040/epd` (new). `fw/gpu/core`: the extension hook,
  `INFO` and the buffer union.
- `emu/rp2040`: the panel controller model; `test/emu/test_epd.mjs` (new).
- The kernel and ROM: nothing for the console. Optional BASIC statements
  later.

## Not in scope

- Colour e-paper (tri-colour, Spectra): refreshes of 15–30 s and no partial
  refresh.
- The IT8951 large panels (10.3" and up): a different host protocol and 5 V
  at 1.2 W. That would be a separate card if ever wanted.
- Touch and front lights on the panel.
- Two consoles at once (HDMI and e-ink mirrored): the kernel has one
  console.
- Games at a frame rate: e-paper can't do it. The `m3-gpu-games.md`
  commands stay HDMI-only.
- Mounting the panel on the case, which is case design.

## Open questions

1. **Module on a header (recommended) or bare panel on the card?** 26 parts
   against 45, a panel anywhere the cable reaches against one at the card's
   edge, and a booster that already works against one we can't test before
   ordering.
2. **Which panel?** 7.5" 800 × 480 (UC8179) as the primary, as either a
   Good Display GDEY075T7 + DESPI-C02 (about $38, currently out of stock) or
   a Waveshare 7.5" HAT (about $57, cable included). Is the 5.83" (80 × 30
   exactly) or the 4.26" (sharp but tiny text) of interest, and should the
   SSD1677 driver be written up front?
3. **Card type:** $01 with `INFO` (no ROM or kernel change), or a new $05 ($04 is now the storage card)
   (a small ROM and kernel change, explicit in the slot table)?
4. **Text geometry:** 80 × 30 centred with white margins (reuses the
   renderer; recommended), 80 columns in 10-pixel cells filling the width,
   or 100 × 30 for software that asks?
5. **The ink rule:** is "the brighter colour of a cell is ink" right for the
   console, and should GFX (not inverted) and TEXT (inverted) really differ?
6. **Refresh defaults:** 150 ms quiet time, a 1 s cap, and a full refresh
   after 30 partial ones at the next 2 s pause. Or more conservative, as
   Good Display's "full after 5"? This is tuned on the real panel either way.
7. **Mode 2 now or later?** The native 4-grey mode is what makes pictures
   worth having, and it is the largest part of the new firmware and tests. Mode 1 works
   from day one.
8. **The connector:** a 2.54 mm header for the modules' jumper-ended cables
   (recommended), or a GH1.25 socket for a Waveshare cable used end to end?
   And is a TVS array wanted on the header lines?
9. **The build:** does an order build e-ink cards alongside the HDMI cards
   (2 more cards, about $5 of parts plus the PCB), and which slot does the
   e-ink card take when both are fitted?

## Sources

- Good Display GDEY075T7 (7.5", UC8179, 3 s / 1.5 s / 0.3 s, 4 grey):
  [good-display.com/product/396.html](https://www.good-display.com/product/396.html);
  price: [buy-lcd.com/products/gdey075t7](https://buy-lcd.com/products/gdey075t7)
- Waveshare 7.5" e-Paper HAT (V2) ($56.99, GH1.25 9-pin cable, 4 s / 1.5 s /
  0.4 s): [waveshare.com/7.5inch-e-paper-hat.htm](https://www.waveshare.com/7.5inch-e-paper-hat.htm);
  raw panel ($47.99): [waveshare.com/7.5inch-e-paper.htm](https://www.waveshare.com/7.5inch-e-paper.htm)
- Waveshare 7.5" e-Paper V2 specification (the 24-pin pinout, the §1.6
  reference booster circuit, 8/12 mA update current, 0–50 °C):
  [files.waveshare.com/…/7.5inch_e-Paper_V2_Specification.pdf](https://files.waveshare.com/upload/6/60/7.5inch_e-Paper_V2_Specification.pdf)
- Good Display DESPI-C02 specification (the 8-pin header, the RESE choice
  per panel, a 10 µH / 1 A inductor, Si1304BDL/Si1308EDL or AO3400, MBR0530,
  an FPC with contacts on the upper side or both sides):
  [laskakit.cz/…/despi-c02_connector_board_for_e-paper_display_v1-1.pdf](https://www.laskakit.cz/user/related_files/despi-c02_connector_board_for_e-paper_display_v1-1.pdf);
  product: [good-display.com/product/516.html](https://www.good-display.com/product/516.html);
  price ($8.50): [buy-lcd.com DESPI-C02](https://www.buy-lcd.com/products/development-kit-connection-adapter-board-for-eaper-display-demo-kit)
- Waveshare e-Paper Driver HAT ($9.99, 9-pin order, the 0.47 Ω / 3 Ω
  switch per panel): [waveshare.com/wiki/E-Paper_Driver_HAT](https://www.waveshare.com/wiki/E-Paper_Driver_HAT),
  [waveshare.com/e-paper-driver-hat.htm](https://www.waveshare.com/e-paper-driver-hat.htm)
- Good Display GDEY0426T82 (4.26", SSD1677, 3.5 s / 1.5 s / 0.42 s):
  [good-display.com/product/457.html](https://www.good-display.com/product/457.html);
  price: [buy-lcd.com/products/gdey0426t82](https://buy-lcd.com/products/gdey0426t82)
- Waveshare 4.26" e-Paper HAT ($31.99):
  [waveshare.com/4.26inch-e-paper-hat.htm](https://www.waveshare.com/4.26inch-e-paper-hat.htm)
- Good Display GDEY0583T81 (5.83", 648 × 480, UC8179; full refresh after
  every 5 fast or partial updates): [good-display.com/product/440.html](https://www.good-display.com/product/440.html),
  [buy-lcd.com/products/gdew0583t81](https://buy-lcd.com/products/gdew0583t81);
  price: [evelta.com GDEY0583T81](https://evelta.com/5-83-inch-648x480-e-ink-screen-e-paper-display-black-white/)
- Waveshare 2.9" module ($21.99): [waveshare.com/2.9inch-e-paper-module.htm](https://www.waveshare.com/2.9inch-e-paper-module.htm)
- Waveshare 10.3" e-Paper HAT (IT8951, $199.99, 5 V, 1.2 W):
  [waveshare.com/wiki/10.3inch_e-Paper_HAT](https://www.waveshare.com/wiki/10.3inch_e-Paper_HAT),
  [waveshare.com/10.3inch-e-paper-hat.htm](https://www.waveshare.com/10.3inch-e-paper-hat.htm)
- Waveshare 7.5" HD (discontinued): [waveshare.com/7.5inch-hd-e-paper-hat.htm](https://www.waveshare.com/7.5inch-hd-e-paper-hat.htm)
- Pervasive Displays EXT3 and iTC panels:
  [pervasivedisplays.com](https://www.pervasivedisplays.com/third-generation-extension-board-from-pervasive-displays-supports-all-itc-epds-and-provides-extensive-free-software-library/)
- JLC stock and prices: `hw/tools/jlcparts.py search` / `check` and JLC's
  parts API, 2026-09-24.
