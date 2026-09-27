# Fabrication file review receipt

`boardcheck.py <board> fab` compares every Gerber command and aperture with a
fresh export of the DRC-clean board, then matches Excellon round holes and G85
slots to pads or vias. It independently parses plotted copper to check net
clearance, trace width, copper-to-edge distance, and via and plated-pad annular
width. It checks exposed pads against the plotted mask, paste deposits against
copper and mask openings, and silkscreen against mask openings. It checks mask
webs if the KiCad project has a positive solder-mask minimum width. The board
needs a recorded visual CPL review. The fab gate remains red because
hole-to-copper/edge, minimum ink geometry, and other plotted-layer rules still
lack independent validation. Export parity and a review receipt do not complete
Gerber re-import DRC.

The 2026-09-27 GPU and Wi-Fi plots place GND connector fingers 0.20 mm from
their key-notch route. The project rule is 0.30 mm copper-to-edge, so the
independent checker fails. [JLCPCB's current FR-4 routed-edge capability](https://jlcpcb.com/capabilities/Capab)
states a 0.20 mm minimum. That vendor limit does not change the project rule
or approve these fingers; the mating geometry and a scoped rule decision still
need review. A GPU pad pair also has a 0.149951 mm *lower bound* against the
0.150000 mm copper clearance rule. The curved-pad approximation permits up to
0.150000002 mm for that pair, so the checker reports it as indeterminate and
keeps the gate red rather than asserting a physical clearance violation.

After viewing the placement overlay and checking designators, pin one,
polarized parts, and rotations against the board and BOM, put
`cpl-review.json` in the board's `fab/` directory. Use this shape:

```json
{
  "board": "wifi",
  "reviewer": "Your name",
  "reviewed_at": "YYYY-MM-DD",
  "result": "approved",
  "notes": "Describe the placement, pin-one, polarity and rotation review and any corrections.",
  "sha256": {
    "fab/bom.csv": "64 lowercase hex characters",
    "fab/cpl.csv": "64 lowercase hex characters",
    "wifi.kicad_pcb": "64 lowercase hex characters",
    "wifi-top.png": "64 lowercase hex characters"
  }
}
```

The four SHA-256 values bind the review to the exact files reviewed. The
receipt is intentionally separate from the generated pipeline evidence, so
it can be added after the build. A modified board, BOM, CPL, or render makes
the review stale. A receipt is a record of human review; the gate cannot
independently establish that the visual inspection occurred.

`python3 hw/tools/cploverlay.py <board-output-dir> --output-root <overlay-dir>`
renders a zoomable SVG and PNG with every Top CPL centre and rotation arrow over
the exported board drawing. Its manifest records source hashes and explicitly
marks human review pending. Check the physical pin-one and polarity against the
board and BOM; an arrow only shows the numeric CPL rotation. The generated
overlay and manifest are evidence for review, not an approval receipt.
