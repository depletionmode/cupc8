# Board catalogue gates

`python3 hw/tools/boardcheck.py <board> <check>` requires a completed build
in `build/hw/<board>` (or `--out`). The board pipeline writes `evidence.json`
after success, recording SHA-256 of the board script, shared card code,
pin table, hardware tools, local libraries, part records and fabrication
outputs. Rebuilding invalidates the previous receipt first. Inputs changing
during a build fail receipt creation. Copied artifacts require identical
source content; an old success log or file timestamp is insufficient. The
receipt covers both board renders and requires nonempty Gerber and drill
exports, as well as the schematic, routed PCB, netlist and order files.
Existing builds made before receipts were added must be rebuilt.

ERC and DRC are run again, including schematic parity and all severities;
report fields must be present and every finding fails. BOM and footprint
checks run BRD-001 on the completed build. BOM also queries current JLC stock
at twice the receipt's assembly quantity. Offline mode cannot certify these
rows. Mechanical rows run the full fit check, including the real mainboard
and system card (the stand-in socket row is insufficient).

SC, EC and YC identify the storage, e-ink and system card board rows. WC-006
remains the Wi-Fi strapping check; its thermal row is WC-010.

## Coverage still required

A wired command is not proof of completion. The following checks deliberately
fail until their contract coverage exists:

- Fab: Gerber re-import with DRC, drills compared to footprint holes and
  recorded CPL review. Existing clean PCB DRC and exported files do not
  prove these requirements.
- Connectors: pincheck validates the source tables; connectorcheck compares
  every contact, including intended no-connects, of the board's external
  connectors with its KiCad netlist and the published pinout.
- Power: main and CPU models need binding to the actual board netlists;
  GPU needs the RP2040 internal regulator at its overclocked operating point;
  IO needs SY6280 current-limit, short and fault-flag transients; storage,
  e-ink and system need load-step/internal-regulator coverage. Existing
  buck, LDO, HDMI, USB boost and budget models still execute before these
  missing portions fail.
- Thermal: main/CPU regulator models need netlist binding, and RP2040 cards
  need internal-regulator dissipation at their maximum operating loads.
- Wi-Fi strapping: WC-006 checks the actual KiCad netlist's ESP32-C3 GPIO2/8/9,
  EN, slot reset and programming connections, and runs ngspice for both normal
  and download reset releases. The model holds the 3.3 V rail at nominal; the
  separate Wi-Fi power gate owns rail start-up and load transients.
- Wi-Fi power: WC-005 checks U2/L1/R9/R10/C1-C3 values and pins in the exported
  netlist, matches those pads to the routed PCB, and adds the board's +5V and
  3V3 track/via resistance to the TI TLV62569 transient deck. The card is the
  ordered 1.6 mm two-layer design. The check remains red because its GND pours,
  copper weight/temperature and capacitor ESR lack sufficient route and fab
  evidence for the 350 mA TX burst claim.
- SI and board co-simulation remain separate workstreams; newly added rows
  remain pending until their checks are implemented.

`BRD-002` exercises receipt invalidation and report failures without requiring
KiCad, routing or network access. Three counterexamples prove that stale
inputs, changed routed boards and ignored unconnected/parity findings are
rejected for the intended reason.
