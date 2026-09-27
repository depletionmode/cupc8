# Thermal regulator binding diagnostic

`hw/power/thermal.py bind BOARD BUILD_DIR` now checks each modeled heat
source against the exported KiCad netlist and PCB. It requires the fitted
component value and library identity, exact package for every regulator,
modeled rail/control pins, complete netlist-to-PCB pad parity for each
modeled part, and exact membership of feedback/switch nodes. The main,
GPU and IO checks also compare component values to `design.py` parameters.
The RP2040 cards check VREG_VIN, VREG_VOUT, DVDD, every 1V1 decoupler,
its GND pin, and exact membership of the 1V1 net. This is topology
binding, not a thermal solution.

The binding-only diagnostic passed on the currently saved CPU, GPU, IO,
storage, e-ink and system card netlist/PCB pairs. It also passed on the
isolated, **unrouted** main relocation board. These are direct artifact
checks, not fresh board receipts or evidence of KiCad DRC. Mutation probes
rejected a changed CPU regulator value, regulator package, netlist pin,
and main buck model package. The existing global THM-001 calculation still
passes. Normal `thermal.py bind BOARD BUILD_DIR` exits with failure after
successful binding because physical thermal coverage remains open;
`--binding-only` is explicitly diagnostic.

The `boardcheck.py thermal` rows remain red in this branch: it still runs
global THM-001 and retains the existing missing-coverage failures. The
binding entry point can be wired into those rows after the active board
routes finish. Wiring it alone must not remove the residual failure:

- Main: actual package-to-board/enclosure thermal resistance, hot input
  copper and return/pad/contact loss, neighbouring heat, standby LDO loss,
  and eFuse fault pulse are unbounded. THM-001's eFuse row uses its
  **2.62 A minimum** current limit, while a sustained fault analysis must
  address its **3.21 A maximum** and the PTC time history.
- CPU: the RT9013 heat path, hot 3V3 socket feed and 1V2 pad/spoke/contact
  losses, effective output capacitance/ESR, and FPGA maximum core-current
  assumption remain unbounded.
- GPU and IO: their external converter/switch packages and feedback
  networks are bound, but the RP2040 internal VREG maximum 1V1 current,
  loss versus operating corner, and local heat coupling are not. IO also
  needs the boost and SY6280 combined board/enclosure path.
- Storage, e-ink and system: RP2040 VREG topology is bound, while its
  internal loss and board/enclosure thermal path lack a maximum-load bound.
- Wi-Fi: WC-010 already binds the buck and copper; it remains red until a
  calibrated ESP32-to-buck thermal-transfer bound and pad/contact losses
  are available.

The needed closure evidence is a maximum internal-regulator load/loss for
the actual RP2040 operating modes, validated local heat-path and coupling
coefficients for the assembled board/enclosure at 40 °C ambient, and
temperature-coupled copper/contact losses using bounded finished geometry.
JEDEC θJA values alone do not supply those board-specific paths.
