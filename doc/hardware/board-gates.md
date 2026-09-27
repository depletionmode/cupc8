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
- Wi-Fi strapping: reset RC and normal/download mode simulation.
- SI and board co-simulation remain separate workstreams; newly added rows
  remain pending until their checks are implemented.

`BRD-002` exercises receipt invalidation and report failures without requiring
KiCad, routing or network access. Three counterexamples prove that stale
inputs, changed routed boards and ignored unconnected/parity findings are
rejected for the intended reason.
