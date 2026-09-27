# Independent plotted Gerber audit — 2026-09-28

The eight current board receipts were validated before this audit. Run
`python3 tools/fab_diagnostics.py main cpu gpu io storage wifi eink system`
to reproduce the per-rule JSON lines. This diagnostic calls the same independent
Gerber and Excellon readers as the fabrication gate, but continues after a
failed rule so the connector notch does not hide another finding. The run's
JSON is in `build/rebuild-20260928/independent_fab_all.jsonl` locally.

| Board | Fresh KiCad DRC / opens / schematic parity | Implemented plotted rules | Plotted copper-to-edge |
|---|---:|---:|---|
| main | 0 / 0 / 0 | 10 of 10 pass | Pass |
| cpu | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| gpu | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| io | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| storage | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| wifi | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| eink | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at GND notch, minimum 0.300 mm |
| system | 0 / 0 / 0 | 9 of 10 pass | 0.200 mm at J2 A11 notch, minimum 0.300 mm |

Every row also passed fresh Gerber export parity, Excellon drill-to-board
matching, drill spacing, plotted copper clearance/width, via and PTH annular
rings, hole clearance, mask web/alignment, paste registration, and front/back
silkscreen clearance. The main board's `boardcheck main fab` reaches the
unfilled human CPL review receipt after all implemented plotted checks.

**This is not fabrication approval.** The card notch requires mechanical and
contact qualification or a revised socket/footprint; see
`card-notch-qualification.md` and `card-notch-socket-source-review.md`. The
main CPL positions and rotations require human overlay review. The final
Gerber checker still lacks complete minimum-neck coverage in complex filled
copper and silkscreen regions and a plotted text-height check; it deliberately
fails closed on those gaps even after a CPL receipt exists. The independent
diagnostic does not bypass those gates.
