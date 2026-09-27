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
or approve these fingers. The footprint's 0.70 mm finger width and 1.90 mm
notch meet the CEM dimensions recorded in `hw/mech/fit.py`; narrowing the notch
by 0.20 mm to gain 0.10 mm per side would fall below CEM's 1.84 mm notch
minimum. Shrinking the fingers by 0.20 mm would fall below CEM's 0.65 mm
finger-width minimum. Even taking both dimensions to their CEM minima gives
only 0.255 mm nominal copper-to-notch clearance.

The UMAX manufacturer's drawing 318307001, page 1
(`hw/datasheets/C404113_UMAX-3183-10200P1T.pdf`), gives the socket key width
*along the card edge* as 1.78 +/-0.05 mm. Its separate 1.77 +0.20/-0.05 mm
dimension is the slot opening *across the card thickness*. With both key and
notch at their specified worst widths and perfectly centered, the remaining
side gap is just 0.005 mm. `MECH-001` reports this width comparison, but it
does not establish worst-case alignment of the molded rib against the routed
notch or qualify the board-route process. [JLCPCB's routed-edge table](https://jlcpcb.com/capabilities/Capab)
lists +/-0.20 mm regular and +/-0.10 mm high-precision outline tolerance;
either exceeds the 0.06 mm CEM notch-width tolerance unless a tighter process
and inspection are agreed. Obtain manufacturer routing capability and mating
evidence before approving a narrowly scoped 0.20 mm key-notch copper-edge
exception; keep 0.30 mm everywhere else. The fab gate remains red.

A GPU pad pair also has a 0.149951 mm *lower bound* against the
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
