# E-ink graphics card (card type $01)

The e-ink card is the second option for the graphics card (Milestone 1,
`doc/proposals/eink-gpu.md` and its Decisions). It drives an e-paper panel
instead of HDMI. **A machine has one or the other**: the e-ink card takes the
same card type, **$01**, speaks the same slot SPI and the same command set
(`gpu-protocol.md`), and says what it is in `INFO`. The boot ROM uses it as
the console with no change; the kernel asks `INFO` and knows which it has.

## Hardware

| | |
|---|---|
| MCU | RP2040 at 125 MHz, the GPU and IO cards' core (`hw/pins.yaml`, `eink_mcu`) |
| Slot | the GPU card's slot group: SCK 2, MOSI 3, MISO 4, CS_n 5, IRQ_n 6 |
| Panel header | 2.54 mm 1 x 9 male pins (J2), with a TVS array: **1 VCC (3.3 V), 2 GND, 3 DIN, 4 CLK, 5 CS, 6 DC, 7 RST, 8 BUSY, 9 PWR**, the Waveshare e-Paper Driver HAT's own order. The panel's **driver module** (a Waveshare e-Paper HAT / Driver HAT, or Good Display's DESPI-C02) plugs in by cable and carries the booster (Compatible panels, below) |
| Panel lines | SPI1 as master, write-only: CLK 10, DIN 11; CS_n 9, DC 12 (1 = data), RST_n 13, BUSY 14 (UC8179: **low while busy**), PWR 15 (high = module on; Waveshare HAT rev 2.3) |
| LED | REFRESH (GPIO 24): lit while the panel refreshes |
| Panel | Designed for the **Good Display GDEY0583T81, 5.83", 648 x 480** (the build `eink.elf`); the 7.5" GDEY075T7 or Waveshare 7.5" V2, 800 x 480, work with `eink750.elf`. All have the UltraChip **UC8179** controller. **M1's plan: the Waveshare 5.83" e-Paper HAT (V2)**, which plugs straight in, but whose glass does not advertise the fast, partial and 4-grey refreshes this firmware uses (Buying the panel, below) |

**Buying the panel (checked 2026-09-26).** The panel and its driver module
are not JLC parts: they are bought separately and plug into the header by
cable (no soldering).

| Option | Price | Stock (2026-09-26) |
|---|---|---|
| GDEY0583T81 at MicroHello | $19.90 | in stock |
| GDEY0583T81 at buy-lcd, Evelta, Good Display | $24.48 / INR 2,928 / - | out of stock |
| DESPI-C02 adapter at buy-lcd | $8.50 | out of stock |
| DESPI-C02 at AliExpress (Good Display's store) | $49.90 + $6.80 | available |
| Waveshare 5.83" e-Paper HAT, 648 x 480 (panel, driver board, 9-pin GH1.25 cable) | $39.99 | available (Waveshare, Amazon) |

The Waveshare HAT is the simplest (one box, the header follows its pinout);
**to verify before relying on it**: that its panel takes the UC8179 commands
and timings this firmware uses for the GDEY0583T81 (Waveshare's V2 driver
suggests so; check its datasheet).

The card cannot ask the panel which it is (the header has no MISO), so the
panel is chosen by the firmware image. `INFO` reports it.

### Buying the panel

The panel and its driver module are not JLC parts: they are bought
separately and plug into the header by cable (no soldering).

| Option | Price | Stock (2026-09-26) |
|---|---|---|
| **Waveshare 5.83" e-Paper HAT (V2)**, 648 x 480 (panel, e-Paper Driver HAT Rev2.3, GH1.25 9-pin cable ~20 cm) | $39.99 | available (Waveshare, Amazon) |
| Waveshare 7.5" e-Paper HAT (V2), 800 x 480 (the same Driver HAT and cable) | $56.99 | available (Waveshare) |
| GDEY0583T81 at MicroHello | $19.90 | in stock |
| GDEY0583T81 at buy-lcd, Evelta, Good Display | $24.48 / INR 2,928 / - | out of stock |
| DESPI-C02 adapter at buy-lcd | $8.50 | out of stock |
| DESPI-C02 at AliExpress (Good Display's store) | $49.90 + $6.80 | available |

**M1's plan is the Waveshare 5.83" HAT** (David, 2026-09-26): one box, and
its cable plugs straight into the card. Checked against Waveshare's and the
chip vendors' documents on 2026-09-26 (the sources are listed below):

- **Cable and connector: fits, no board change.** The HAT's cable is a
  GH1.25 9-pin plug (the HAT end) to **nine separate 2.54 mm single-way
  female Dupont housings** ([the cable's photo][ws-cable]). They push onto
  J2's 2.54 mm male pins. The Driver HAT Rev2.3's connector P2 is 1 VCC,
  2 GND, 3 DIN, 4 SCK, 5 CS, 6 DC, 7 RST, 8 BUSY, 9 PWR
  ([Rev2.3 schematic][ws-sch23]; the same order on the [product page][ws-583]
  and the [wiki][ws-583-wiki]), **the same as J2's pins 1 to 9**, so the
  wires go on in cable order, VCC on pin 1. Single-way housings can go on
  in any order, so each wire is to be checked against the pin names on
  J2's silkscreen.
- **Supply and levels: 3.3 V works.** The HAT runs at 3.3 V or 5 V, with
  the logic at the supply's level ([wiki][ws-583-wiki]). On the Driver HAT
  Rev2.3 ([schematic][ws-sch23]) the header's VCC goes through a P-FET
  switch (AO3401, Q31) to VCC, which feeds an RT9193-33 LDO (3V3_OUT, the
  panel's VCI/VDDIO) and the B side of a TXB0108E level translator (A side
  3V3_OUT, B side the header's lines). From the card's 3.3 V the LDO runs
  in dropout, about 3.2 V out at the panel's few mA (RT9193: 220 mV at
  300 mA, [datasheet][rt9193]); the panel wants 2.3 to 3.6 V, not below
  2.5 V ([wiki FAQ][ws-583-wiki]). The TXB0108 needs VCCA <= VCCB, which an
  LDO's output below its input gives, and pull resistors on its lines of
  50 kohm or more ([TI datasheet][txb0108], 7.3.5): the card has 33 ohm in
  series and only the RP2040's own pull-up (50-80 kohm) on BUSY.
- **PWR (Rev2.3): high = module on, low or open = off.** PWR drives an
  S8050 (through 10 kohm, 100 kohm to ground) that turns Q31 on, and the
  LDO's enable; the optional 47 kohm pull-up to VCC (R27) is not fitted
  ([schematic][ws-sch23]; "RST pin now is for reset control, and not for
  power on/off. Add a new PWR pin for power on/off", [Driver HAT
  wiki][ws-dhat]). While PWR is low the TXB0108's B side is unpowered and
  high-impedance with at most 2 uA of Ioff ([TI datasheet][txb0108]), so the
  card's lines (RST_n held high) do not power the module, and BUSY reads
  high (not busy) by the RP2040's pull-up, as the firmware expects of a
  missing module.
- **BUSY: low while busy.** The panel's BUSY_N pin "is low" while the driver
  IC works ([panel spec][ws-583-spec], note 5-4), through the non-inverting
  TXB0108.
- **Switches on the HAT:** "Display Config" to **B (0.47 ohm)**, which is the
  5.83" and 7.5" setting ([Driver HAT wiki][ws-dhat]); "Interface Config"
  (BS) to **0, 4-line SPI** (the card has a DC line).
- **Controller: UC8179**, the same as the GDEY0583T81: the panel spec's
  drawing names it, and its command table is the UC8179's
  ([panel spec][ws-583-spec]).
- **The glass is not the GDEY0583T81.** Every figure Waveshare publishes for
  the 5.83" V2 (active area 119.232 x 88.320 mm, pitch 0.184 mm, 125.40 x
  99.50 x 1.18 mm, 26.4 mW a refresh, 2 greys, full refresh only) is that
  of Good Display's **GDEW0583T8** (end of life; [Good Display][gd-t8]),
  not of the GDEY0583T81 (118.78 x 88.22 mm, pitch 0.1833 mm, 33 mW, 4
  greys; full 3 s, fast 1.5 s, partial 0.3 s, 4-grey 2 s; [Good
  Display][gd-t81]). Waveshare lists **no partial or fast refresh and 2
  greys** for the 5.83" HAT ([product page][ws-583]); its 7.5" V2 page
  lists "Partial Refresh Support", 4 greys, fast 1.5 s, partial 0.4 s,
  4-grey 2.1 s ([7.5" product page][ws-75]).

**What that means for this firmware.** The start and the clean full refresh
use the panel's OTP waveform at the measured temperature, which every
UC8179 panel has; they should work on the Waveshare 5.83" as they are
(the differences from Waveshare's reference sequence are in Panel
controller, below). The **fast, partial and 4-grey refreshes** pick OTP
waveforms by forcing the temperature (TSSET `5A`/`6E`/`5F`): values from
Waveshare's 7.5" V2 driver for panels whose OTP has those waveforms. On
glass that advertises none, what those forced temperatures select is
unknown until tried: possibly just the normal waveform (slow, but a
correct picture), possibly a weak one that leaves grey or ghosted pixels,
and 4-grey pictures probably come out in black and white. The refresh
policy sends a partial refresh for every typed key, so on a
full-refresh-only panel each key would cost a 4-5 s flashing refresh.
**Not changed yet; for David to decide:**

1. Buy the **Waveshare 7.5" V2 HAT** instead ($56.99, the same Driver HAT
   and cable, plugs straight in): its advertised fast, partial and 4-grey
   refreshes are the ones this firmware's values come from, with
   `eink750.elf` and no change. Buy stock sold after September 2023: the
   wiki says older 7.5" V2 panels need its `7.5V2_old` program
   ([wiki][ws-75-wiki]).
2. Buy the panel the card was designed for, a **GDEY0583T81 with a
   DESPI-C02** ($19.90 + $8.50 where in stock, table above).
3. Keep the **Waveshare 5.83"** and add a full-refresh-only build (every
   refresh on the OTP waveform at the real temperature; INFO without the
   partial flag; greys dithered), or try the forced temperatures on the
   real glass first.

**Not checked, and why:** Waveshare's driver for this panel
(`EPD_5in83_V2.c` in github.com/waveshareteam/e-Paper), which would show
whether Waveshare itself uses forced temperatures, a partial window or
greys on the 5.83" V2: fetching it was refused by this session's
permissions, so the comparison below is against the panel spec's reference
sequence instead. **Not verifiable without hardware:** the waveforms
(the forced temperatures above on either panel, ghosting, how many partial
refreshes before a full one), the LDO's dropout at the refresh's peak
current, and that Waveshare ships Rev2.3 of the Driver HAT with the HAT
(the product page lists the 9-pin GH1.25 cable, which only Rev2.3 has).

### Compatible panels

The card needs a module that takes 3.3 V and 3.3 V logic on a 2.54 mm
header, a write-only 4-wire SPI with DC, RST and BUSY, and a UC8179.

| Module | Its header | With this card |
|---|---|---|
| Waveshare 5.83" e-Paper HAT (V2) = 5.83" raw panel V2 + e-Paper Driver HAT Rev2.3 | GH1.25 9-pin: VCC GND DIN CLK CS DC RST BUSY PWR ([schematic][ws-sch23]) | **plugs straight in** (its cable, pins 1-9); `eink.elf`; the waveforms as above |
| Waveshare 7.5" e-Paper HAT (V2) = 7.5" raw panel V2 + the same Driver HAT | the same | **plugs straight in**; **`eink750.elf`** |
| Waveshare universal e-Paper Driver HAT Rev2.3 with a raw UC8179 panel (5.83" V2, 7.5" V2) | the same | plugs straight in; the build for the panel's size |
| Waveshare e-Paper Driver HAT Rev2.2 (older stock) | PH2.0 8-pin: VCC GND DIN CLK CS DC RST BUSY, no PWR ([Rev2.2 schematic][ws-sch22]) | pins 1-8 of J2, pin 9 unused. The module's power follows RST instead (RST low turns it off; Waveshare: keep the reset pulse short, [wiki FAQ][ws-583-wiki]); the card's 1 ms pulse is to be tried |
| Good Display DESPI-C02 with the GDEY0583T81 (or GDEY075T7) | 2.54 mm 8-pin P2: 1 3.3V, 2 GND, 3 SDI, 4 SCLK, 5 CS, 6 D/C, 7 RES, 8 BUSY ([DESPI-C02 schematic][gd-despi-sch], [spec][gd-despi]) | **plugs straight in** with an 8-wire 2.54 mm female-female jumper cable, pin n to pin n, pin 9 unused; `eink.elf` (`eink750.elf` for the 7.5"); 3.3 V only, no level translator (the card's 3.3 V logic is right); the module is always powered (PWR does nothing), the controller's deep sleep keeps its draw near zero; switch P3 to 0.47 (UC8179) |

- **Only a firmware change:** another size of UC8179 panel (a new build with
  its resolution, like `eink750.elf`), or a panel with another controller
  on the same kind of module (e.g. the Solomon SSD16xx family: BUSY high
  while busy, other commands; BUSY is a plain GPIO, so its polarity is
  firmware too). A new build also needs a simulator/emulator slot kind.
- **A board change:** a module that needs a 5 V supply (J2's VCC is the
  card's 3.3 V through a 100 mA PTC), one that must be read (J2 has no MISO,
  and DIN is SPI TX only), one that draws more than 100 mA, or one with a
  parallel or larger FPC interface (e.g. the 1600 x 1200 IT8951 boards).

[ws-583]: https://www.waveshare.com/5.83inch-e-paper-hat.htm
[ws-583-wiki]: https://www.waveshare.com/wiki/5.83inch_e-Paper_HAT_Manual
[ws-583-spec]: https://files.waveshare.com/upload/3/37/5.83inch_e-Paper_V2_Specification.pdf
[ws-cable]: https://www.waveshare.com/img/devkit/general/GH1.25-9PIN-20cm.jpg
[ws-dhat]: https://www.waveshare.com/wiki/E-Paper_Driver_HAT
[ws-sch23]: https://files.waveshare.com/upload/8/8e/E-Paper_Driver_HAT.pdf
[ws-sch22]: https://files.waveshare.com/upload/8/87/E-Paper-Driver-HAT-Schematic.pdf
[ws-75]: https://www.waveshare.com/7.5inch-e-paper-hat.htm
[ws-75-wiki]: https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_Manual
[gd-t81]: https://www.good-display.com/product/440.html
[gd-t8]: https://www.good-display.com/product/241.html
[gd-despi]: https://v4.cecdn.yun300.cn/100001_1909185148/DESPI-C02%20Connector%20Board%20for%20E-paper%20Display%20V1.1.pdf
[gd-despi-sch]: https://v4.cecdn.yun300.cn/100001_1909185148/DESPI-C02_SCH%20V1.0.pdf
[txb0108]: https://www.ti.com/lit/ds/symlink/txb0108.pdf
[rt9193]: https://www.mouser.com/datasheet/2/1458/DS9193_18-3104722.pdf

## Protocol

Everything in `gpu-protocol.md` holds: the status byte (FIFO FREE, 8 KB
FIFO, the acceptance guarantee), every TEXT and GFX command, FENCE, the error
rules. IDENT answers type $01 at once, whatever the panel is doing. What
differs:

### TEXT (mode 0)

- **80 x 30 cells of 8 x 16**, centred on the panel: 4 white pixel columns
  each side on the 5.83", 80 on the 7.5".
- **The ink rule:** per cell, the brighter of its two colours is ink (black)
  and the darker is paper (white); equal colours are all paper. Brightness is
  the palette entry's luminance, Y = 0.299 R + 0.587 G + 0.114 B. So the
  default `$07` is black text on white, and `$70` (inverse) white on black.
- **The cursor is drawn but does not blink** (a blink would mean a refresh
  every half second): underline (rows 14-15 of the cell inverted) or block.

### GFX (mode 1)

320 x 240 at 8 bpp as on HDMI, pixel-doubled to 640 x 480 and centred. Each
pixel's palette entry becomes a grey by the same luminance, **not inverted**:
black is ink. A 1-bit refresh shows greys with a 4 x 4 ordered (Bayer)
dither; a greyscale refresh (`REFRESH 3`) shows 4 levels.

### Native mode 2

`MODE 2`: the panel's own resolution (648 x 480 or 800 x 480) at **2 bits a
pixel**: grey 0 black, 1 dark grey, 2 light grey, 3 white. `MODE 2` clears it
to white, `CLS g` fills it with grey `g`. Its buffer is the GFX buffer (the
two modes are exclusive), so mode 1's commands ($20-$28) are ignored in mode
2 (GETPIXEL answers 0) and mode 2's are ignored in modes 0 and 1.
Coordinates are **16-bit little-endian, signed for positions**; everything is
clipped to the panel.

| Op | Name | Args | |
|---|---|---|---|
| $40 | PIXEL2 | x16, y16, g | |
| $41 | FILL_RECT2 | x16, y16, w16, h16, g | |
| $42 | RECT2 | x16, y16, w16, h16, g | 1-pixel outline |
| $43 | LINE2 | x0_16, y0_16, x1_16, y1_16, g | Bresenham, both ends drawn |
| $44 | BLIT1_2 | x16, y16, w16, h16, fg, bg, then ⌈w/8⌉ x h bytes | 1 bpp, MSB left; `bg = $FF` transparent |
| $45 | BLIT2 | x16, y16, w16, h16, then ⌈w/4⌉ x h bytes | 2 bpp, the leftmost pixel in bits 7-6 |
| $46 | TEXT16 | x16, y16, fg, bg, len, ch x len | the 8 x 16 TEXT font (DEFCHAR16's glyphs) anywhere; `bg = $FF` transparent |
| $47 | TEXT8_2 | x16, y16, fg, bg, len, ch x len | the 8 x 8 font (DEFCHAR8's) |
| $48 | VSCROLL2 | dy16 (signed), g | scroll up by dy rows (down if negative), fill with g |
| $49 | GETPIXEL2 | x16, y16 → g | after every earlier command; 0 off the panel or outside mode 2 |

A grey that is not 0-3 (or `$FF` where transparent is allowed) makes the
command an error: counted, nothing drawn. A frame is limited to 8128 bytes
as for BLIT8, so a picture goes in several BLITs.

### E-paper commands ($08-$0B)

| Op | Name | Args → response | |
|---|---|---|---|
| $08 | INFO | → kind, w16, h16, greys, flags, cols, rows | kind 1 = e-paper; w, h the panel (648 x 480 or 800 x 480); greys 4; flags bit 0 partial refresh, bit 1 mode 2; cols, rows 80, 30. **The HDMI card answers** 0, 640, 480, 0, 0, 80, 30. |
| $09 | REFRESH | m | Refresh the panel now, with everything before it. m: 0 partial (the rows that differ), 1 fast full (one flash, clears ghosting), 2 clean full (the slow waveform), 3 greyscale full (4 levels). **Execution waits until the panel has the picture**, so a `FENCE` after it fires when the picture is on the glass; commands keep queuing in the FIFO meanwhile. m > 3 is an error. |
| $0A | AUTO | on, idle10, full_after | The automatic refresh policy: on 0/1, idle10 the quiet time in 10 ms steps (default 15 = 150 ms), full_after partial refreshes before a ghost-clearing full one (0 = never; default 30). |
| $0B | EPD_STATUS | → busy, dirty, partials | busy: a refresh is running or waiting; dirty: changes not on the glass yet; partials since the last full refresh. |
| $0C | AUTO_EXT | cap10, full_kind, sleep_s | The rest of the policy: cap10 the longest a change waits under continuous output, in 10 ms steps (default 100 = 1 s; 0 = no limit, only the quiet time); full_kind the refresh used for the automatic full refresh and after `CLS` (REFRESH's m: 1 fast (default), 2 clean, 3 greyscale; anything else is an error); sleep_s the seconds unused before the controller's deep sleep (default 10; 0 = never). |
| $0D | AUTO_GET | → on, idle10, full_after, cap10, full_kind, sleep_s | The policy as AUTO and AUTO_EXT set it. |

The HDMI card executes REFRESH, AUTO, EPD_STATUS, AUTO_EXT and AUTO_GET as
NOPs (EPD_STATUS and AUTO_GET give no response there), and ignores `MODE 2`. Software asks `INFO` first.

`SOFT_RESET` restores the power-on state, including AUTO's and AUTO_EXT's
defaults (decided 2026-09-25: the settings do not survive a reset; the
software sets what it wants).

## Refresh policy

The card refreshes the panel by itself, so the kernel only prints. It keeps
the 1-bit picture last sent to the panel, and every turn of its loop:

1. **Automatic refresh** (AUTO on), when there are unshown changes and no
   refresh is running: once the command stream has made no change for
   `idle10` (150 ms), or changes have waited `cap10` (**1 s**; continuous output),
   it renders the screen, **compares it with the picture on the panel** row
   by row, and sends a **partial refresh of the rows that differ** (the
   window spans the panel's width). A change undone before then costs
   nothing. Commands that change nothing (NOP, FENCE, the reads) do not
   count as activity.
2. After `full_after` partial refreshes it does a full refresh of
   `full_kind` (**fast**) the next time the stream has been quiet for
   **2 s**, to clear the ghosting.
3. `CLS`, a form feed, `MODE` and `SOFT_RESET` make the next refresh a
   full one of `full_kind` (fast).
4. The first refresh after power-on is a **clean full** one. Until then the
   panel keeps the picture from before power-off.
5. A change made while the panel refreshes goes into the next refresh.
6. After `sleep_s` (**10 s**) unused the controller goes into deep sleep;
   the next refresh wakes it with a reset.

**From the kernel** (decided 2026-09-25; no BASIC command): `kernel/eink.s`
has `eink_auto` (sends AUTO and AUTO_EXT from the 6 bytes at `eink_cfg`, in
AUTO_GET's order), `eink_get` (AUTO_GET into `eink_cfg`) and `eink_status`
(EPD_STATUS into `eink_st`). On HDMI they do nothing (`eink_get` and
`eink_status` leave $ff). The kernel itself keeps the card's defaults.
Programs reach them through the kernel API's e-ink group (`API_EINK_AUTO`,
`API_EINK_GET`, `API_EINK_STATUS`, `API_EINK_REFRESH`; `kernel/api.inc`,
`../proposals/kernel-api.md`), with the six settings in `API_ARGS`
(KRN-013, E2E-012).

In use, from the vendors' times: a typed key reaches the glass about 0.5 s
after the key (150 ms quiet, then a 0.3 s partial refresh); a `LIST` or a
program's output makes one refresh when it stops, and continuous output
about one a second. The defaults are to be tuned on the real panel.

## Panel controller (UC8179)

`fw/eink/core/uc8179.c`, from the UC8179c datasheet (UltraChip, rev 0.6,
2019; page numbers below are that document's):

- **Start** (the module's PWR on, 10 ms; RST_n low 1 ms (≥ 50 us, p.39),
  then 2 ms before any command (> 1 ms, p.43)): PWR `07 07 3F 3F` (internal
  DC/DC, VGH/VGL ±20 V, VDH/VDL ±15 V, p.13), BTST `17 17 28 17` (p.16), PSR
  `1F` (LUTs from OTP, KW black/white mode, scan up, shift right, p.12), TRES
  the panel's size (p.31), DUSPI `00` (single SPI, p.18), TCON `22` (p.30).
- **Each refresh:** CDI `21 07` (DDX = 01: data 1 is white; {NEW, OLD} picks
  the LUT, p.27-28; the border white), or `A1 07` for a partial one (the
  border Hi-Z); the waveform (below); PON and wait for BUSY; for a partial
  refresh PTL with the changed rows and PTIN (p.33); DTM1 the OLD picture,
  DTM2 the NEW one (p.17); DRF and wait for BUSY; PTOUT after a partial one;
  POF and wait for BUSY, so the panel has no high voltage between refreshes.
  Deep sleep is DSLP `A5` (p.17), left only by RST_n (p.52).
- **The waveform** is the panel's OTP one chosen by forcing the temperature:
  CCSET `02` (TSFIX, p.38) and TSSET `5A` fast full, `5F` 4-grey, `6E` partial;
  the clean full refresh uses the real temperature (CCSET `00`). These values
  are the panel vendors' (Waveshare's MIT-licensed `EPD_7in5_V2.c`), not the
  UC8179 datasheet's, and are to be confirmed on the panel.
- **4 greys:** grey level g (0-3) is sent as NEW = g's high bit, OLD = its low
  bit, so the four {NEW, OLD} pairs select the four LUTs, which the 4-grey
  waveform gives four greys.
- **BUSY_N:** the card waits for it without stalling the slot: the panel loop
  is a state machine polled by the main loop, and a picture goes out 8 rows
  a turn (about 0.5 ms at the 10 MHz panel SPI). A wait starts at the first
  poll after the command went out (BUSY_N may take a moment to fall), and a
  controller busy for 10 s is given up on: the refresh is released, and the
  next one starts with a reset.

**Against the Waveshare 5.83" V2's reference sequence** ("BWR mode & LUT
from OTP", [panel spec][ws-583-spec] 4.2-2, p.21; checked 2026-09-26; its
driver `EPD_5in83_V2.c` could not be fetched, Buying the panel). The
reference: BTST `17 17 1E 17`, PWR `07 17 3F 3F`, PON and wait, PSR `1F`,
TRES `02 88 01 E0`, DUSPI `00`, TCON `22`, CDI `10 07`, DTM1 old, DTM2 new,
DRF and wait, CDI (border floating), POF and wait, more than 500 ms, DSLP
`A5`. The same as this firmware: PSR, TRES (648 = `02 88`), DUSPI, TCON,
the OTP LUTs, DTM1 then DTM2, POF after each refresh, DSLP; neither sends
PLL. The differences:

| | This firmware | The reference | Matters? |
|---|---|---|---|
| BTST phase C1 | `28`: strength 6, GDR off time 0.27 us | `1E`: strength 4, 3.34 us | the booster's soft start; both in the chip's range. The 7.5" V2's values; to try the reference's if the 5.83" booster misbehaves |
| PWR byte 2 | `07`: VCOM slow slew, VGH/VGL +-20 V | `17`: VCOM fast slew, +-20 V | VCOM's edge only; to confirm on the glass |
| Order | PSR, TRES, DUSPI, TCON after reset; PON at each refresh | PON first, then PSR ... CDI | none: the registers keep their values until VDD off or deep sleep (spec p.29, POF), and the firmware sets them again after every reset |
| CDI | `21 07`: DDX 01, data 1 = white, border LUTKW | `10 07`: DDX 00, data 0 = white, border LUTKW | none: the same LUTs for the same picture (the spec's CDI tables, p.38-39), the polarity is where 1 means white |
| Border after refresh | driven (`21`), Hi-Z only in a partial refresh (`A1`) | set floating before POF | cosmetic: the border's colour between refreshes |
| Waveform | clean: OTP at the measured temperature (CCSET `00`); fast, 4-grey, partial: forced temperature (CCSET `02`, TSSET `5A`, `5F`, `6E`) | the OTP at the measured temperature only | **yes**: the clean refresh is the reference's; the other three are not in any Waveshare document for this panel (Buying the panel) |
| Partial window | PTL + PTIN, PTOUT after | none | only with a partial waveform |

## Firmware

| Where | What |
|---|---|
| `fw/gpu/core` | the graphics card's interpreter, reused: an extension hook (every command goes to the e-ink core first), a hold flag (REFRESH), INFO, and the GFX buffer in a union sized by `GPU_GFX_BYTES` (96,000 for the e-ink card: mode 2 on the 7.5") |
| `fw/eink/core/eink.c` | the e-paper commands, mode 2, the rasteriser (ink rule, dither, greys), the refresh policy and the panel loop, on an injected clock |
| `fw/eink/core/uc8179.c` | the controller's command sequences over a four-function bus (command, data, pin, busy) |
| `fw/rp2040/eink/main.c` | the RP2040 port: slot SPI, SPI1 at 10 MHz with GPIO CS and DC around each command and its data, RST, PWR, BUSY, the REFRESH LED. One core, one loop. `tools/fw_rp2040.sh eink` (or `eink750`) |

Memory: about 200 KB of the RP2040's 264 KB (the 96 KB GFX / mode-2 buffer,
the 48 KB picture on the panel, the FIFO, fonts and the text buffer).

## Kernel

`kernel/gpu.s` drives either card. `gpu_init` sends `INFO` and keeps the
first response byte in `gpu_kind` (0 HDMI, 1 e-paper, `$ff` if nothing
answers). `kernel/eink.s` has `eink_refresh` (REFRESH m, on e-paper only)
and the terminal's **`refresh`** command: a clean full refresh, to clear
ghosting by hand. On HDMI it does nothing.

Mode 2 is in the kernel API (2026-09-26, `../proposals/basic-graphics.md`,
`../proposals/kernel-api.md`): `API_GFX_MODE` 2 (an error on HDMI, by
INFO) and one entry per mode-2 command, `API_GFX2_PIXEL` ... `API_GFX2_GETPIXEL`
($10e4-$10ff). BASIC reaches it with `mode 2` and its graphics statements
(`plot`, `line`, `box`, `cls` in greys 0-3), and `refresh [m]` asks for a
refresh (greyscale by default in mode 2); the policy's settings stay out of
BASIC.

## Tests

| Test | What |
|---|---|
| GPU-006..008 | host tests of the core with the UC8179 model (`fw/test/test_eink.c`, `make -C fw test_eink`): every command, malformed frames, the ink rule for all 256 attributes, TEXT/GFX/mode 2 pictures on the glass against golden images (`test/eink/golden`), the policy's timing, deep sleep, a dead panel; and GPU-001's suite on the e-ink build (`test_gpu_eink`) |
| GPU-009 | the real `eink.elf` and `eink750.elf` on the native emulator with the panel model (`build/emu-machine/einkcard`) |
| KRN-007 | the kernel on the simulator's e-ink card (`tools/run_tests.sh testKernelOnEink`) |
| E2E-008 | the whole machine with the e-ink card: boot to BASIC on the panel, a program, `refresh` |
| KRN-018, KRN-019 | BASIC's graphics statements in mode 2, and every mode-2 API entry, on the simulator's e-ink card (the card's mode-2 picture pixel by pixel, the greys on the glass after a greyscale refresh) |
| E2E-016 | the whole machine: a BASIC program draws in mode 2, `refresh`; the four greys on the panel model's glass |

**The UC8179 model** (`fw/test/epdmodel.c`) is one model for the host
tests, the simulator and the emulator. It takes SPI bytes with DC, RST_n and
PWR, holds BUSY_N low for each operation's time (the vendors' figures: full
3 s, fast 1.5 s, 4-grey 2 s, partial 0.3 s, PON 50 ms, POF 30 ms, BUSY_N
falling 200 us after the command; `time_scale` scales them), and applies a
refresh to its glass only when the refresh ends. It counts as an error
anything the chip would ignore or do wrong: a command while BUSY, a byte
during reset or within 1 ms of it, in deep sleep or unpowered, a refresh
with the booster off or with more or less pixel data than the window, a
reserved command, a read (the header has no MISO). A partial refresh moves
only the pixels whose NEW differs from their OLD, so a wrong OLD picture
leaves wrong pixels on the glass.

**Seeing it:** `tools/sim --cards:eink,io` (or `eink750,io`) shows the whole glass, 648 or 800 x 480, as of its last refresh; `node tools/machine_view.mjs --native --slots eink,io` (or
`eink750,io`) shows the panel's glass in the browser, which changes only when
a refresh completes; `CUPC8_EINK_SCALE=0.2` shortens the panel's busy times,
`CUPC8_EINK_LOG=FILE` logs every controller command.

**Not testable before hardware:** the waveforms (ghosting, how the greys look,
how many partial refreshes before a full one is needed), and the forced
temperature values: on the Waveshare 5.83" V2, whether they select any fast,
partial or grey waveform at all (Buying the panel).
