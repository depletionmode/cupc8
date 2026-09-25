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
- **Finger tab (every card, done by `pipeline(card_edge=True)`):** GND
  fingers tied into the pour, the PRSNT1_n/PRSNT2_n presence link pre-routed
  (`presence={"layer": ..., "rise": ...}` puts its run on an inner layer: the
  CPU card and the system card use In2.Cu), no vias on the tab, pre-routed
  escapes for the signal fingers beside the key notch, and routed GND tracks
  cleared off the contacts.
- **Inner layers on 4-layer cards (both opt-in):**
  - `zones=(..., ("/GND", ("In1.Cu",)), ("/3V3", ("In2.Cu",)))` makes each named
    inner layer a solid **plane** (a power layer, which Freerouting never
    routes on): the **CPU card**.
  - `plane=True` pours the outer layers' net on In1.Cu as well but leaves In1
    a **signal layer**, which the pour fills around the routes: the **system
    card**. Its QFN-56 fan-out would not route with a layer lost to a plane.
- **Fine pitch:** `fine_nets=` puts nets in the "Fine" class (0.15 mm track
  and clearance, 0.7 mm vias), for parts at 0.4–0.5 mm pitch: the system
  card's RP2040 and USB-C.
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
[sysctl.md](../../doc/hardware/sysctl.md)), on a 56 × 48 mm card above a
PCIe x4 finger tab (the shared card rules above), with a USB-C port on
the top edge for the host PC. Everything is placed by JLC; nothing is fitted
by hand.

**Power.** The card runs from the slot's **+3V3** (contacts B1, B2, A2):
the main board's 3V3 buck, which is where [power.md](../../doc/hardware/power.md)
puts sysctl in its distribution tree and its current budget (50 mA max).
There is no AMS1117 on this card: running the RP2040 from the same rail as
the chipset, flashes and expanders it drives means its I/O can never be
powered while theirs is not, or the other way round, and it saves a part.
The slot's **+5V (A11) is not connected**. The ADC's reference (ADC_AVDD)
is the same slot +3V3, with 100 nF at the pin, which is what the power
analysis assumes for CC sensing (power.md: ±3 %, ≤ 12 LSB).

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

**Board.** Four layers (JLC04161H-7628), 56 × 48 mm above the tab. GND is
poured on F.Cu, B.Cu and In1.Cu; all four layers route (In1 as a power
plane left the QFN-56 fan-out unroutable). The body is taller than the parts
need: the 10 mm band above the tab is where 50-odd slot nets fan out of the
fingers. The RP2040's and J1's nets are in kicadgen's "Fine" class (0.15 mm
track and clearance, 0.7 mm vias): at 0.2 mm clearance Freerouting counts
every pair of the QFN's 0.2 mm-apart pads a violation and routes none of
them. Freerouting necks those tracks to 0.11 mm at the pads, inside JLC's
4-layer minimum (0.09 mm), which 4-layer boards now check against (0.1 mm).
The presence link (A1 to B32) crosses on In2.Cu 1.8 mm above the tab. J1 is
JLC's own footprint (jlc: import), since KiCad's splits the paired contacts
(A1/B12 ...) that JLC places as one pad; its EasyEDA 3D model is moved
2.27 mm onto the footprint. Passives are 0603 basic parts.

**Firmware and pins.** `hw/pins.yaml` gives GPIO0/1 to LED_USB_TX/RX (they
were a debug UART that nothing used; every other GPIO is taken).
`fw/rp2040/sysctl/main.c` lights each for 30 ms after USB data in its
direction. SYS-006 checks they light after a request and go dark after.

## CPU card (`cpu.py`)

    python3 hw/boards/cpu.py            # outputs in build/hw/cpu

The M1 CPU card: `cpu.vhd` in an iCE40HX4K-TQ144 on the PCIe-x8-style CPU
socket ([cpu-bus.md](../../doc/hardware/cpu-bus.md)). It boots from its own
W25Q32JVSSIQ, which the system card reprograms through the socket (FL1 bus,
CRESET_n, CDONE; [system-slot.md](../../doc/hardware/system-slot.md)).

- **Outline.** The I/O cards' outline (cpu-bus.md, CPU card outline): the
  62 × 39.05 mm body `kg.IO_CARD_BODY`, with the M3 hole and the PWR LED
  where every card has them. The x8 tab (x −0.65…50.65) sits under it with
  5.35 mm shoulders, and finger B1 is at the same offset from the body's left
  edge as on the x1 cards. `pipeline(io_card=True, tab=kg.X8_TAB)` draws and
  checks the outline. The width is set by the x8 tab plus its two 5 mm
  shoulders (61.3 mm, which the existing 62 covers). The height needed no
  change: everything fits single-sided in 39.05 mm, as described below.
- **FPGA pins** are read from `hw/pins.yaml` (`cpu_fpga`), the file that also
  generates `build/hw/cpucard.pcf`, so the schematic and the bitstream agree
  by construction. Each side of the package carries its bus lines in the
  order of their fingers, left to right. The bottom side (bank 3) has A0–A15
  on pins 1–20, then CPU_CLK (21, GBIN6), /RST, /STB, /RDY, RW and SYNC
  (22–26). The right side (bank 2), bottom up, has D0–D7 (37–45), IRQ0–3
  (47–52), TMR_EXP0/1, HALTED and WAITING (55–61). I also tried the other
  way round (D and the control lines on the bottom side, A on the right),
  and it routed worse.
- **Footprints** are JLC's own (`jlc:`, imported from the LCSC part) for the
  FPGA, the flash and the resistor arrays, so the BOM check (BRD-001) matches
  them pad for pad. The pin tables are in `hw/parts/`. The FPGA's table is
  Lattice's HX4K TQ144 pinout. All 144 pins were cross-checked against
  KiCad's symbol and icestorm's chipdb.
- **Power** (Lattice FPGA-TN-02006, the iCE40 hardware checklist). VCC 1V2
  comes from an RT9013-12GB off the socket's +3V3. All four VCCIO banks,
  SPI_VCC and VPP_2V5 are on 3V3; VPP_2V5 may be 2.5–3.3 V when the FPGA
  boots from SPI flash. The PLLs are unused, but each VCCPLL still gets
  100 Ω + 4.7 µF + 100 nF, as the checklist asks. The caps go to that PLL's
  own GNDPLL pin, which is *not* joined to board ground. VPP_FAST is left
  open. Every supply pin has 100 nF and its own via to its plane or rail,
  and each rail group has 4.7 µF. The card takes nothing from +5V.
- **Configuration.** SPI_SS_B and SPI_SCK are pulled up (controller mode).
  CRESET_B and CDONE are pulled up on the card as well as on the main board.
  /WP and /HOLD are pulled high, because the FPGA uses plain 0x0B reads.
- **Bus.** Every card output (A, D, RW, /STB, SYNC, TMR_EXP, HALTED,
  WAITING) has 33 Ω at the driver: eight 4D02 arrays (0402x4, 4 × 33 Ω).
  Each array keeps its pins' order on both rows: FPGA side on pads 1–4,
  finger side on 8–5. CPU_CLK and the other inputs go straight to the FPGA.
- **Straps.** CARD_ID = `10`: CARD_ID0 goes to GND, and CARD_ID1 is left to
  the main board's pull-up. PRSNT1_n is joined to PRSNT2_n. On this wide
  card the link's run is on In2, because a run on B.Cu would wall the
  address lines off their fingers.
- **LEDs.** The PWR LED (D1, red, 1 kΩ from 3V3) is at the common power-LED
  spot, 3 mm in from the body's top-left corner. The 1V2 rail LED (D2,
  [power.md](../../doc/hardware/power.md)) is next to it along the top edge.
  1.2 V cannot light an LED, so an MMBT3904 driven from 1V2 switches a red
  LED on 3V3. The silkscreen labels them "PWR" and "1V2". There are test
  pads for 1V2, 3V3 and GND. The title and revision are "CUPC/8 CPU rev A".
- **Parts** (LCSC): iCE40HX4K-TQ144 C1521989, W25Q32JVSSIQ C179173,
  RT9013-12GB C58464, 4D02WGJ0330TCE 33 Ω × 4 C25501, MMBT3904 C20526,
  KT-0603R red LED C2286, and 0402 basics: 100 nF C1525, 1 µF C52923,
  4.7 µF C23733, 10 kΩ C25744, 1 kΩ C11702, 100 Ω C25076.
- **Stackup.** 4 layers, JLC04161H-7628, 1.6 mm, with hard-gold fingers,
  bevelled per the fab order spec (`kicadgen.order_spec`). The layers are
  signal + GND pour / signal + GND pour / solid 3V3 plane / signal + GND
  pour. Between the package and the fingers the bus has a 10 mm band, and
  two signal layers could not route it. So In1 carries signals too, and its
  GND pour fills round them. Every piece of that pour is tied by GND vias to
  the stitched outer pours. 1V2 is routed as tracks.
- **Placement.**
  - The FPGA sits against the top edge, with its top pad row 0.85 mm in.
    That leaves the 10 mm band under it for the arrays and the bus fan-out.
  - The four top-side supply pins (VPP, VCC and 2 × VCCIO1, the last an
    unused bank) are decoupled from the package's corners and sides, 5–10 mm
    away, all on planes or the 1V2 rail. Every other supply pin has its
    100 nF beside it.
  - The A and control arrays are in a row under the bottom side. The D and
    timer arrays are in a column right of the right side.
  - The flash is by the config pins, under the top edge beside the M3 hole.
    The configuration pull-ups are at the lower left, over their fingers.
  - The LDO, the 1V2 switch and the PLL1 filter are on the left, on a grid.
  - The logo is in the lower right.
  - The designators are at JLC's 0.8 mm minimum height (`silk_text`): the
    card is 0402s. Nothing sits in the 4.5 mm strip above the fingers.
