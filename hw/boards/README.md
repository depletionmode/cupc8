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
  included) is in kicadgen's `Fine` class: 0.15 mm tracks, 0.15 mm clearance
  (JLC: 0.127) and 0.65 mm vias. With the Default 0.2/0.2, a track can't
  turn out of a pad beside its neighbour, and Freerouting left QFN pins
  unrouted.
- **Four layers** (JLC04161H-7628, the stackup `order_spec` names): In1 a
  solid GND plane (a power layer Freerouting doesn't route), In2 routed with
  a GND pour. On two layers Freerouting never completed around the QFN on
  any of the cards; four layers also put every fast line (TMDS, SD, USB)
  over a solid ground.
- **Hand-laid copper before Freerouting** (`preroute`): TESTEN straight in
  to the exposed pad (a GND pin between two signal pins, which no pour
  reaches); on the turned cards (GPU, storage) the seven pins in the middle
  of the chip's top edge escape by vias, three in the ring under the chip
  and four just outside (`pocket_escapes`), because on the GPU they are
  walled in by the TMDS pairs; on the IO card DVDD 23 is tied to its cap.

## IO card (`io.py`)

Spec: `doc/hardware/io-card.md`.

- **J2, USB-A USB-302S-T** (C112455) at the top edge, with our footprint
  `cupc8:USB_A_SOFNG_USB-302S-T` (EasyEDA's has a malformed courtyard that
  misses the pads' rear ends). The shell face is on the board edge.
- **U7, TPS61023DRLR** (C919459) boosts the slot's +5V to 5.06 V for the
  keyboard (power.md, IO card keyboard boost): 1 µH FXL0420 (C167203),
  10 µF in, 2 × 22 µF out, 750k/100k feedback. Always on. Its pins are
  0.3 mm pads, so the board script lays their tracks (VIN/EN to the input
  cap, SW to the inductor, VOUT to the output caps, FB to the divider) with
  the loops short, as TI's layout guide asks.
- **U5, SY6280AAC** (C55136) switches the boost's output to VBUS, enabled by
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
- **TMDS routing:** with the pairs in order they need no vias between the
  chip and the receptacle, over In1's solid ground. 252 Mb/s over < 20 mm
  is electrically short (a bit is ~0.6 m of FR-4), so the pairs are not
  impedance-controlled; PicoDVI's own 2-layer boards pass the DVI eye mask.
- **GND between the lines** (`preroute`): the receptacle's shield and DDC
  ground pins get a via 2 mm behind the pad, under the receptacle's body;
  each ESD's GND pins, in the middle of its rows, are joined through the
  package and taken down by a via.
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

- **FPGA pins** are read from `hw/pins.yaml` (`cpu_fpga`), the file that also
  generates `build/hw/cpucard.pcf`, so the schematic and the bitstream agree
  by construction. Each side of the package carries its bus lines in the
  order of their fingers, left to right. The bottom side (bank 3) has A0–A15
  on pins 1–20, then CPU_CLK (21, GBIN6), /RST, /STB, /RDY, RW and SYNC
  (22–26). The right side (bank 2), bottom up, has D0–D7 (37–45), IRQ0–3
  (47–52), TMR_EXP0/1, HALTED and WAITING (55–61). So the front-side lines
  reach their fingers without crossing, and A drops to the back layer
  through its arrays. With the first two pin orders, Freerouting left 5–7
  bus nets unrouted on every try, even when it could also route on In2.
- **Footprints** are JLC's own (`jlc:`, imported from the LCSC part) for the
  FPGA, the flash and the resistor arrays, so the BOM check (BRD-001) matches
  them pad for pad. The pin tables are in `hw/parts/`. The FPGA's table is
  Lattice's HX4K TQ144 pinout. All 144 pins were cross-checked against
  KiCad's symbol and icestorm's chipdb. EasyEDA's symbol for C1521989 has
  another device's pin names, and nothing uses it.
- **Power** (Lattice FPGA-TN-02006, the iCE40 hardware checklist). VCC 1V2
  comes from an RT9013-12GB off the socket's +3V3. All four VCCIO banks,
  SPI_VCC and VPP_2V5 are on 3V3; VPP_2V5 may be 2.5–3.3 V when the FPGA
  boots from SPI flash. The PLLs are unused, but each VCCPLL still gets
  100 Ω + 4.7 µF + 100 nF, as the checklist asks. The caps go to that PLL's
  own GNDPLL pin, which is *not* joined to board ground. VPP_FAST is left
  open. Each supply pin has 100 nF beside it, and each rail group has 4.7 µF.
  The card takes nothing from +5V.
- **Configuration.** SPI_SS_B and SPI_SCK are pulled up (controller mode).
  CRESET_B and CDONE are pulled up on the card as well as on the main board.
  /WP and /HOLD are pulled high, because the FPGA uses plain 0x0B reads.
- **Bus.** Every card output (A, D, RW, /STB, SYNC, TMR_EXP, HALTED,
  WAITING) has 33 Ω at the driver: eight 4D03 arrays, 4 × 33 Ω each.
  CPU_CLK and the other inputs go straight to the FPGA.
- **Straps.** CARD_ID = `10`: CARD_ID0 goes to GND, and CARD_ID1 is left to
  the main board's pull-up. PRSNT1_n is joined to PRSNT2_n.
- **LEDs.** The PWR LED (red, 1 kΩ from 3V3) sits at the common power-LED
  spot, 3 mm in from the body's top-left corner. Next to it along the top
  edge is the 1V2 rail LED ([power.md](../../doc/hardware/power.md)). 1.2 V
  cannot light an LED, so an MMBT3904 driven from 1V2 switches a red LED on
  3V3. The silkscreen labels them "PWR" and "1V2". There are test pads for
  1V2, 3V3 and GND, and an M3 hole 4 mm in from the top-right corner, as on
  the I/O cards. The board's title and revision are "CUPC/8 CPU rev A".
- **Parts** (LCSC): iCE40HX4K-TQ144 C1521989, W25Q32JVSSIQ C179173,
  RT9013-12GB C58464, 4D03WGJ0330T5E 33 Ω × 4 C25508, MMBT3904 C20526,
  KT-0603R red LED C2286, and 0603 basics: 100 nF C14663, 1 µF C15849,
  4.7 µF C19666, 10 kΩ C25804, 1 kΩ C21190, 100 Ω C22775.
- **Stackup.** 4 layers, JLC04161H-7628, 1.6 mm, with hard-gold fingers, bevelled per the fab order spec (`kicadgen.order_spec`).
  The layers are signal + GND pour / GND plane / 3V3 plane / signal + GND
  pour. 1V2 is routed as tracks. With a TQ144 there
  are 16 supply pins on all four sides, plus 31 series-terminated bus lines
  and the clock. Two planes give every one of them a short via to its supply
  and a solid return path under the whole bus, without cutting up a pour. On
  two layers the fan-out would have to share its layers with the power.
- **Placement.** Each 33 Ω array sits at its pins. A0–15 and /STB-RW-SYNC
  are in a row under the bottom side. D0–3, D4–7 and the timer lines are in
  a column right of the right side. The flash sits by the config pins, top right,
  clear of the M3 hole. The PWR LED is at the common spot, 3 mm in from the
  top-left corner. Nothing sits in the 4.5 mm strip above the fingers.
