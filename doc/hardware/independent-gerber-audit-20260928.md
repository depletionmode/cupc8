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

## Separate release gates

| Gate | Current result | Evidence needed to close it |
|---|---|---|
| Seven card connector notches | Plotted clearance is 0.200 mm against the 0.300 mm board rule. | A contact-qualified card/socket revision and fabricator guarantee for finished notch, pad width and pad-to-route registration. Rebuild all seven cards and rerun the plotted edge check at the normal 0.300 mm rule. The [qualification plan](card-notch-qualification.md) gives the worst-case inequalities. |
| Main CPL placement | Pending human review after the implemented plotted checks. | Review every designator, physical pin 1, polarity and rotation against the board, BOM and part drawing. Record the review in `build/hw/main/fab/cpl-review.json` with hashes of the exact board, render, BOM and CPL. A generated template is unsigned. |
| Complete Gerber re-import DRC | The final gate deliberately fails after the implemented checks and CPL review. | Independently cover filled copper and silkscreen minimum necks and nominal silkscreen text height, or approve a narrower fabrication contract. The partial neck witness on `codex/gerber-next-sol` does not provide complete coverage. |

For the current main-board placement packet, run
`python3 tools/fab_review_bundle.py main` on a checkout whose receipt validates.
The overlay arrows show numeric CPL rotation; the reviewer must compare the
physical pin-one and polarity features. `python3 hw/tools/boardcheck.py main fab`
checks the completed receipt and stops at the next failing gate. Rebuilding a
board changes the artifact hashes and invalidates any earlier CPL review.

Changing `hw/tools` also changes the receipt's recorded source inputs, so a
checker improvement requires fresh board builds before it can be used as
receipt-bound release evidence. A document-only audit update leaves those
source inputs unchanged.
