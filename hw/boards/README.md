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

## System card (`system.py`)

    python3 hw/boards/system.py [outdir]     (default build/hw/system)

sysctl, the RP2040 that programs and debugs the machine
([system-slot.md](../../doc/hardware/system-slot.md),
[sysctl.md](../../doc/hardware/sysctl.md)), on a 56 × 38 mm card above a
PCIe x4 finger tab (1.6 mm, hard-gold 45° fingers), with a USB-C port on
the top edge for the host PC. Everything is placed by JLC; nothing is fitted
by hand.

**Power.** The card runs from the slot's **+3V3** (contacts B1, B2, A2):
the main board's 3V3 buck, which is where [power.md](../../doc/hardware/power.md)
puts sysctl in its distribution tree and its current budget (50 mA max).
There is no AMS1117 on this card: running the RP2040 from the same rail as
the chipset, flashes and expanders it drives means its I/O can never be
powered while theirs is not, or the other way round, and it saves a part.
The slot's **+5V (A11) is not connected**. (parts.md budgets two AMS1117s
for the system card; that line can drop to 6.)

**USB-C.** A data-only device port: 5.1 kΩ Rd on CC1 and CC2, 27 Ω on
D+/D−, and a USBLC6-2SC6 between the receptacle and the resistors.
**VBUS is not connected to anything**, so the card cannot back-feed the host
or the slot rails. The USBLC6's rail pin goes to +3V3, not VBUS: tied to VBUS,
its steering diode would lift VBUS to about 2.7 V from the D+ pull-up
whenever the card is on and the host is not. VBUS is not sensed either, since
all 30 GPIOs are assigned; the firmware forces the USB controller's VBUS
detect on (the pico-sdk and TinyUSB default for the RP2040).

**RP2040.** Raspberry Pi's minimal design: W25Q16JVSSIQ on QSPI, a 12 MHz
X322512MSB4SI crystal (C_L 20 pF, so 33 pF load caps with about 4 pF of
stray capacitance) with 1 kΩ on XOUT, the internal 1V1 regulator (1 µF in
and out), and 100 nF on every supply pin.

**Slot signals.** Every signal goes to the GPIO in `hw/pins.yaml`, unchanged.
The nine SPI outputs sysctl drives (SCK, MOSI and nCS of the bridge, FL0 and
FL1) have 33 Ω source termination at the RP2040, as every card driver on
the CPU bus has ([cpu-bus.md](../../doc/hardware/cpu-bus.md)). MISO, CDONE,
the open-drain CRESET_n and SYS_nRST, the programming port (the main board
has its 33 Ω), MUX_SEL, CC1/CC2 and V1V2_SENSE (1.2 V fits the ADC's range
directly) connect directly. I2C has 10 kΩ pull-ups on the card, in parallel
with whatever the main board fits. PRSNT1_n (A1) is joined to PRSNT2_n (B32)
on the card, as on PCIe. RSVD_A1–A3 are not connected; RSVD_B1/B2 go to
test pads.

**Test pads** (not assembled parts): SWCLK, SWDIO, RUN, BOOTSEL (short it to
GND while powering up for the USB boot ROM; it reaches QSPI_SS through
1 kΩ), +3V3, 1V1, GND, and RSVD_B1/B2.

**LEDs** ([milestone-1.md](../../doc/milestone-1.md), Indicator LEDs):
power (D1, red KT-0603R, 1 kΩ from +3V3) at `kg.power_led_at`, 3 mm in from
the body's top-left; USB activity to the host (D3, TX, GPIO0) and from it
(D4, RX, GPIO1), green KT-0603G with 100 Ω, each lit for ~30 ms after data
in its direction; status (D2, green, GPIO29: on while the host has the USB
device configured). All 30 GPIOs were assigned, so the activity LEDs take
GPIO0/1, which `hw/pins.yaml` had as a debug UART that no firmware used; the
USB CDC link and the SWD pads cover debugging.

**Board.** Four layers (JLC04161H-7628), GND poured on both outer layers.
The fan-out of a 0.4 mm QFN-56 with 50-odd slot nets through the finger
tab did not route cleanly on two. The strip 4.5 mm above the fingers holds
no parts. Passives are 0603 basic parts.
