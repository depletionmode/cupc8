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
- **Cards:** 1.6 mm, with hard-gold fingers and a 45° chamfer. These are
  order options, written in `fab/order.json` and checked there.
- **Card edge:** each card's finger tab is KiCad's `BUS_PCIexpress_*`
  footprint. The script draws the body's outline and meets the tab where it
  starts.
- **Branding:** the Kaplan Labs logo on the top silkscreen of every board.
- **Assembly:** nothing is fitted by hand. The Wi-Fi card's U.FL antenna is
  the one exception: it is plugged in, not soldered.

## Wi-Fi card (`wifi.py`)

Spec: `doc/hardware/wifi-card.md`.

- **U1, ESP32-C3-MINI-1U-N4** (C2911374). The U.FL end sits at the card's top
  edge. The GPIOs follow `hw/pins.yaml`:
  - SCK: GPIO6
  - MOSI: GPIO7
  - MISO: GPIO5
  - CS_n: GPIO10
  - IRQ_n: GPIO3, open drain
  - LINK LED: GPIO4
- **U2, AMS1117-3.3** (C6186), fed from the slot's +5V, with 22 µF in and
  22 µF + 100 nF out. The slot's +3V3 pins are left unconnected: Wi-Fi TX
  peaks near 350 mA, and the slot's +3V3 is limited to 300 mA.
- **U3, 74LVC1G125** (C52140430). Its /OE is CS_n, so the card drives the
  shared MISO line only while it is selected.
- **EN:** 10 kΩ / 1 µF RC, per Espressif. CARD_RST_n, which is open drain on
  the main board, pulls it low.
- **Straps:** GPIO9 has a 10 kΩ pull-up and PROG_n pulls it low for the ROM
  bootloader. GPIO8 and GPIO2 each have a 10 kΩ pull-up and carry nothing
  else.
- **Programming port:** SWCLK drives U0RXD and SWDIO carries U0TXD. esptool
  runs through sysctl's UART tunnel.
- **LEDs:** power (red: a green LED drops ~3 V, too close to the 3.3 V rail), and link on GPIO4 (green, 100 Ω).
- **Test pads** for the native USB-Serial/JTAG (GPIO18/19). They are for
  debugging only.
- **PRSNT1_n (A1) is joined to PRSNT2_n (B18).** The RSVD pins are left
  unconnected.

## CPU card (`cpu.py`)

    python3 hw/boards/cpu.py            # outputs in build/hw/cpu

The M1 CPU card: `cpu.vhd` in an iCE40HX4K-TQ144 on the PCIe-x8-style CPU
socket ([cpu-bus.md](../../doc/hardware/cpu-bus.md)). It boots from its own
W25Q32JVSSIQ, which the system card reprograms through the socket (FL1 bus,
CRESET_n, CDONE; [system-slot.md](../../doc/hardware/system-slot.md)).

- **FPGA pins** are read from `hw/pins.yaml` (`cpu_fpga`), the file that also
  generates `build/hw/cpucard.pcf`, so the schematic and the bitstream agree
  by construction.
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
- **1V2 rail LED** ([power.md](../../doc/hardware/power.md)). 1.2 V cannot
  light an LED, so an MMBT3904 driven from 1V2 switches a red LED on 3V3.
  There are test pads for 1V2, 3V3 and GND.
- **Stackup.** 4 layers, JLC04161H-7628, 1.6 mm, with hard-gold 45° fingers.
  The layers are signal / GND plane / 3V3 plane / signal. With a TQ144 there
  are 16 supply pins on all four sides, plus 31 series-terminated bus lines
  and the clock. Two planes give every one of them a short via to its supply
  and a solid return path under the whole bus, without cutting up a pour. On
  two layers the fan-out would have to share its layers with the power.
- **Placement.** The FPGA is turned a quarter turn, so bank 3 (A[15:0],
  IRQ) faces the fingers and bank 2 (D, control, config) faces right. The A
  arrays sit between the package and the fingers. The D/control arrays sit
  on the right, and the flash is by the config pins.
