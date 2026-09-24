# Board designs

Each board is a Python script that generates its KiCad schematic and PCB and
runs the whole pipeline in `hw/tools/kicadgen.py` (`pipeline()`):

1. schematic, ERC
2. netlist, board build, Freerouting
3. GND stitching, zone fill
4. silkscreen and 3D-model checks
5. DRC with schematic parity
6. Gerbers and drill
7. JLC BOM and CPL (every placed part carries an LCSC number), and `order.json`
8. 3D renders

Outputs land in `build/hw/<board>/`, and `fab/` holds what goes to JLCPCB.

```
python3 hw/boards/wifi.py
```

Shared rules:
- **Revision:** every board passes `title`, `revision` and `revision_at` to `pipeline()`, which prints `<title> rev <revision>` on the top silkscreen and puts the revision in the title block (and so in the Gerbers). Bump the board script's `REVISION` (A, B, ...) for every order that changes the board (`doc/milestone-1.md`, Board revision).
- **Cards:** 1.6 mm, with hard-gold fingers and a 30° chamfer. These are
  order options, written in `fab/order.json` and checked there.
- **Card edge:** each card's finger tab is KiCad's `BUS_PCIexpress_*`
  footprint. The script draws the body's outline and meets the tab where it
  starts.
- **Branding:** the Kaplan Labs logo on the top silkscreen of every board.
- **Assembly:** nothing is fitted by hand. The Wi-Fi card's antenna lead (MHF III to SMA) is
  the one exception: it is plugged in, not soldered.

## Wi-Fi card (`wifi.py`)

Spec: `doc/hardware/wifi-card.md`.

- **U1, ESP32-C3-MINI-1U-N4** (C2911374). The antenna receptacle (MHF III) end sits towards the card's top
  edge. The GPIOs follow `hw/pins.yaml`:
  - SCK: GPIO6
  - MOSI: GPIO7
  - MISO: GPIO5
  - CS_n: GPIO10
  - IRQ_n: GPIO3, open drain
  - LINK, TX and RX LEDs: GPIO4, GPIO0, GPIO1
- **U2, TLV62569DBVR buck** (C141836), fed from the slot's +5V, with L1
  2.2 µH (FNR3015S2R2MT, C167747), 22 µF in, 22 µF + 100 nF out, and a
  453k/100k feedback divider (3.32 V). An AMS1117 LDO failed the power
  checks: in a TX burst at the worst-case corner it left the ESP32-C3 at
  2.71 V (3.0 V minimum), and it ran at Tj ≈ 120 °C (`hw/power`, POW-003,
  THM-001). The slot's +3V3 pins are left unconnected: Wi-Fi TX peaks near
  350 mA, and the slot's +3V3 is limited to 300 mA.
- **U3, 74LVC1G125** (C52140430). Its /OE is CS_n, so the card drives the
  shared MISO line only while it is selected.
- **EN:** 10 kΩ / 1 µF RC, per Espressif. CARD_RST_n, which is open drain on
  the main board, pulls it low.
- **Straps:** GPIO9 has a 10 kΩ pull-up and PROG_n pulls it low for the ROM
  bootloader. GPIO8 and GPIO2 each have a 10 kΩ pull-up and carry nothing
  else.
- **Programming port:** SWCLK drives U0RXD and SWDIO carries U0TXD. esptool
  runs through sysctl's UART tunnel.
- **LEDs:** power at the standard spot (red: a green LED drops ~3 V, too
  close to the 3.3 V rail for 1 kΩ), then LINK (GPIO4), TX (GPIO0) and RX
  (GPIO1) in a row with it along the top edge, green with 100 Ω. TX and RX light for 30 ms whenever
  socket data moves.
- **Outline:** the standard I/O card outline, with its M3 hole
  (`slot.md`, Mechanical).
- **Test pads** for the native USB-Serial/JTAG (GPIO18/19). They are for
  debugging only.
- **PRSNT1_n (A1) is joined to PRSNT2_n (B18).** The RSVD pins are left
  unconnected.

## RP2040 cards: what the GPU and IO cards share (`rp2040card.py`)

- **U1, RP2040** (C2040), the minimal design from Raspberry Pi's *Hardware
  design with RP2040*: 100 nF on each IOVDD, DVDD, ADC_AVDD and USB_VDD pin,
  1 µF on VREG_VIN and VREG_VOUT, the core regulator feeding DVDD (1V1).
  TESTEN to GND.
- **U3, W25Q16JVSSIQ** (C131025), QSPI boot flash, 100 nF.
- **Y1, 12 MHz X322512MSB4SI** (C9002, CL = 20 pF): 33 pF each side
  (2 × (20 − ~3 pF stray)), and 1 kΩ in series with XOUT as the design guide
  has for drive level (the crystal is rated 10–200 µW).
- **3V3 from the slot's +3V3** (power.md: each card is well under the
  slot's 300 mA), with 22 µF where it comes on at B4/A4. No regulator.
- **Slot:** SCK, MOSI, CS_n, IRQ_n on GPIO2, 3, 5, 6 (IRQ_n is open drain in
  firmware). SWCLK/SWDIO go straight to the RP2040's SWD pins; CARD_RST_n
  is RUN, with a 10 kΩ pull-up. PRSNT1_n is joined to PRSNT2_n, the RSVD pins
  and PROG_n are unconnected.
- **MISO through U4, 74LVC1G125** (C52140430), enabled by CS_n, as on the
  Wi-Fi card. An RP2040 pad resets with its ~50 kΩ pull-down on, so a card
  held in reset, blank, or running firmware that never clears the pull would
  otherwise drag the shared MISO line against the main board's 47 kΩ
  pull-up (two cards: ~1.2 V), and an empty slot would no longer read `$FF`.
- **BOOTSEL:** a test pad on QSPI_SS through 1 kΩ (short to GND at power-up).
  Test pads also for SWCLK, SWDIO, RUN, UART TX and GND, down the left edge.
  Blank cards need none of them: SWD loads the flash (`slot.md`).
- **Power LED** (red, 1 kΩ) at the standard spot; the M3 hole at the
  standard spot.
- **Net classes:** every net on the RP2040's 0.4 mm-pitch pads (3V3 and 1V1
  included) is in kicadgen's `Fine` class, 0.15 mm tracks: with 0.2 mm
  tracks a track leaving a pad is exactly 0.2 mm from the next pad, and
  Freerouting won't route that.

## IO card (`io.py`)

Spec: `doc/hardware/io-card.md`.

- **J2, USB-A USB-302S-T** (C112455) at the top edge, with our footprint
  `cupc8:USB_A_SOFNG_USB-302S-T` (EasyEDA's has a malformed courtyard that
  misses the pads' rear ends). The shell face is on the board edge.
- **U5, SY6280AAC** (C55136) switches the slot's +5V to VBUS, enabled by
  GPIO7 (100 kΩ pull-down, so VBUS is off while the RP2040 is in reset).
  R_SET = 12 kΩ: I_lim = 6800 / 12k = 0.57 A nominal, 0.42–0.71 A over the
  datasheet's ±25 %, so a keyboard gets its 500 mA and the card stays under
  the slot's 750 mA PTC. 10 µF at IN, 100 µF + 100 nF on VBUS.
- **VBUS_nFAULT (GPIO8):** the SY6280AAC has no fault flag (io-card.md
  assumed one). GPIO8 reads VBUS through 15k/22k (5 V → 2.97 V), so it goes
  low when the switch limits and VBUS sags below ~3.4 V, or is shorted.
  The firmware's active-low sense is unchanged.
- **USB data:** 27 Ω in series with D+ and D− at the RP2040 (design guide),
  USBLC6-2SC6 (C7519) at the connector. **No external 15 kΩ pull-downs:**
  the RP2040's USB PHY switches its own on in host mode; external ones as
  io-card.md lists would halve them to 7.5 kΩ, outside USB's 14.25–24.8 kΩ.
- **LEDs:** PWR, KBD (red, GPIO25: keyboard connected) and KEY (green,
  100 Ω, GPIO24: lit 30 ms after each HID report, the one activity LED an
  input-only link needs). GPIO24 is new in `hw/pins.yaml`.
- **UART TX** (GPIO16) on a test pad.

## GPU card (`gpu.py`)

Spec: `doc/hardware/gpu-protocol.md`.

- **J2, HDMI type A** (C2858275) at the top edge, with our footprint
  `cupc8:HDMI_A_SHOUHAN_HDMI-19PIN-043`: EasyEDA's pads, the maker's drawing's
  leg slots (EasyEDA's are 0.2–0.4 mm smaller than the drawing asks), and a
  courtyard that covers the pads. The shell legs are through-hole.
- **TMDS:** 270 Ω in series with every line (two 4 × 0603 arrays, C425067),
  PicoDVI's DC-coupled output: the sink terminates each line with 50 Ω to its
  3.3 V, so a low GPIO sinks ~10 mA as TMDS asks (PicoDVI README, "Improved
  Output Circuit"; its mini board, R12–R19). 0402 arrays would put pads
  0.15 mm apart, under the 0.2 mm rule.
- **ESD:** two TPD4E05U06DQAR (C138714, 0.5 pF) by the receptacle, laid
  flow-through: each line crosses its pin and the NC pad opposite, which are
  on its net in the schematic (the datasheet: NC pads are for straight-through
  routing).
- **Pin order:** the RP2040's pins run counterclockwise, the receptacle's
  pads the other way round, so with the pins as they were every pair had to
  cross the others. `hw/pins.yaml` now puts green on GPIO14/15 and the clock
  on GPIO10/11, and the firmware sets PicoDVI's `invert_diffpairs` (P on
  GPIO n+1). Around the turned-round chip the pairs then come out in the
  receptacle's order, D2, D1, D0, clock, P before N: no crossings.
  `invert_diffpairs` is a pad output override, so the PIO lanes are the same;
  GPU-005 (the real gpu.elf, TMDS decoded) passes.
- **Two layers:** with the pairs in order, TMDS needs no vias. 252 Mb/s over
  < 20 mm is electrically short (a bit is ~0.6 m of FR-4), which is why
  PicoDVI's own 2-layer boards pass the DVI eye mask.
- **+5V to the sink:** 100 mA PTC (C20975) against a shorted cable, and a
  B5819W Schottky so a monitor can't back-feed the machine. The pin then sits
  ~0.3 V under the slot's +5V (HDMI asks 4.8 V min); EDID ROMs and
  hot-plug detect work far lower.
- **HPD** (GPIO18): 22k/33k from the connector, 5 V → 2.9 V, pulled low when
  nothing is plugged in.
- **DDC** (GPIO19/20, EDID): a 2N7002 (C8545) per line as a bidirectional
  level shifter, gate at 3V3, 2.2 kΩ to the HDMI +5V on the cable side (HDMI
  source pull-ups) and 4.7 kΩ to 3V3 on the RP2040's. The RP2040 is not 5 V
  tolerant; the monitor's EEPROM wants 0.7 × 5 V for a high.
- **LEDs:** only PWR. GPIO25 (LED_ACT in pins.yaml) is left unconnected.
- **UART TX** (GPIO0) on a test pad. CEC and the utility pin are unconnected.

## Storage card (`storage.py`)

Spec: `doc/hardware/storage-card.md` (card type $04).

- The RP2040 core of the other two cards (`rp2040card.py`), turned round as
  on the GPU card so its SD pins (GPIO12–19) face the socket. Four layers,
  In1 a GND plane.
- **J2, TF-01A** (C91145, 206k in stock): push-push microSD with a
  card-detect contact, JLC's own footprint. It sits on the top edge with its
  opening flush with the edge; a card sticks out by the push-push travel.
  The card-detect contact closes to the shell (GND) with a card in, so
  SD_nDETECT (GPIO17) reads low (as `hw/pins.yaml` expects).
- SD in SPI mode on SPI1 (`storage_mcu` in `hw/pins.yaml`): SCK GPIO14, CMD
  GPIO15, DAT0 GPIO12, DAT3/CS GPIO13; DAT1/DAT2 routed to GPIO18/19.
- **Pull-ups:** 10 kΩ on CMD, DAT0, DAT1, DAT2 (a 4 × 0603 array, C29718,
  basic) and on DAT3 and card detect (0402).
- **At the socket:** 10 µF + 100 nF on VDD (the card's 3V3, from the slot).
- **ESD:** two TPD4E05U06DQAR on the seven signal lines.
- **LEDs:** PWR at the common spot, then ACT (GPIO24) and CARD (GPIO25),
  green with 100 Ω, along the top edge.
