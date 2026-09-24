# Boards

Each board is a Python script that runs the whole KiCad pipeline
(`kicadgen.pipeline`): schematic, ERC, netlist, board, Freerouting, zones,
silkscreen and 3D checks, DRC with schematic parity, Gerbers, JLC BOM/CPL,
order spec and renders, into `build/hw/<name>/`.

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
