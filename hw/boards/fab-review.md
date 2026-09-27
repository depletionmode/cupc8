# Fabrication file review receipt

`boardcheck.py <board> fab` compares every Gerber command and aperture with a
fresh export of the DRC-clean board, then matches Excellon round holes and G85
slots to pads or vias and their plated/non-plated tool attributes. It
independently parses plotted copper to check net
clearance, trace width, copper-to-edge distance, and via and plated-pad annular
width. It compares verified Excellon cuts with plotted copper (the project
hole-clearance rule) and non-plated cuts with plotted edges (JLC's 1.0 mm
non-plated hole-to-edge rule). It checks exposed pads against the plotted mask,
paste deposits against copper and mask openings, and silkscreen strokes against
mask openings and JLC's 0.15 mm minimum line width. Isolated filled copper
and silk regions whose entire bounding width is below the respective minimum
fail independently. A touching union of orthogonal, hole-free filled polygons
with an interior span below the rule also fails by an exact plotted-grid
scanline check; strokes, flashes, and other neck forms still need connected-layer
width analysis. It checks mask
webs if the KiCad project has a positive solder-mask minimum width. The board needs a
recorded visual CPL review. The fab gate remains red because text height,
filled ink necks, and other plotted-layer rules still lack independent
validation. Export parity and a review receipt do not complete Gerber re-import
DRC.

The plotted legend's `%TO.C` tags identify components, not text objects.
Stroke-font glyphs and ordinary graphic lines share the same Gerber `D01`
commands, so font recognition alone cannot prove the 0.8 mm text-height rule
for every label. A future text-height check needs a complete text-to-Gerber
operation mapping plus independent glyph rendering; source text-size fields
alone do not close this plotted-layer gap.

The GPU's `/1V1` and `/SWDIO` circular via flashes are 0.80 mm apart with
0.65 mm diameters, so their nominal plotted clearance is exactly 0.150 mm.
The earlier 0.149951 mm bound came from polygonizing the circles; the current
checker uses the aperture diameters and integer Gerber positions for this
case. It also measures nominal Excellon tool sizes directly and rejects input
with precision finer than its 0.001 mm hole keys. These corrections do not
waive any board-edge violation.

The 2026-09-27 GPU, Wi-Fi, and other card plots place connector fingers 0.20 mm from
their key-notch route. The project rule is 0.30 mm copper-to-edge, so the
independent checker fails. [JLCPCB's current FR-4 routed-edge capability](https://jlcpcb.com/capabilities/Capab)
states a 0.20 mm minimum. That vendor limit does not change the project rule
or approve these fingers. For example, the GPU B.Cu `/GND` ConnectorPad at
(10.00, 0.00) spans x=9.65..10.35 mm, and the adjacent notch wall is at
x=10.55 mm. The footprint's 0.70 mm finger width and 1.90 mm
notch meet the CEM dimensions recorded in `hw/mech/fit.py`; narrowing the notch
by 0.20 mm to gain 0.10 mm per side would fall below CEM's 1.84 mm notch
minimum. Shrinking the fingers by 0.20 mm would fall below CEM's 0.65 mm
finger-width minimum. Even taking both dimensions to their CEM minima gives
only 0.255 mm nominal copper-to-notch clearance with the specified pad centres.
Moving a key-adjacent finger away from the notch to obtain 0.30 mm would
change its CEM contact location and needs a qualified socket-contact drawing
or physical mating evidence. The current UMAX drawing does not provide that
qualification; there is no supported outline or pad edit that clears the
project rule while retaining the stated CEM geometry.

The completed system-board plot has the same failure: independent Gerber
measurement of B.Cu `unconnected-(J2-+5V-PadA11)` at the notch gives
0.200000 mm copper-to-edge against the 0.300000 mm project rule. It is a
common connector geometry issue, not a system-board routing error. The
candidate 0.65 mm/shifted fingers in `doc/hardware/card-notch-qualification.md`
need socket wipe and fabrication registration evidence before they can replace
the current mating pattern.

The UMAX manufacturer's drawing 318307001, page 1
(`hw/datasheets/C404113_UMAX-3183-10200P1T.pdf`), gives the socket key width
*along the card edge* as 1.78 +/-0.05 mm. Its separate 1.77 +0.20/-0.05 mm
dimension is the slot opening *across the card thickness*. With both key and
notch at their specified worst widths and perfectly centered, the remaining
side gap is just 0.005 mm. `MECH-001` reports this width comparison and fails
the production-fit check because the molded rib against the routed notch is
not qualified. [JLCPCB's routed-edge table](https://jlcpcb.com/capabilities/Capab)
lists +/-0.20 mm regular and +/-0.10 mm high-precision outline tolerance;
either exceeds the 0.06 mm CEM notch-width tolerance unless a tighter process
and inspection are agreed. Obtain manufacturer routing capability and mating
evidence before approving a narrowly scoped 0.20 mm key-notch copper-edge
exception; keep 0.30 mm everywhere else. The fab gate remains red.

The main board's independent plotted checks proceed through copper, drills,
mask, paste, and legend; its fab check then stops at the absent human CPL
review receipt. `cploverlay.py` renders 254 Top CPL positions for review,
including the JLC midpoint offset of the J4 pin header. Its overlay manifest
records pending review and does not serve as an approval receipt.

The CPU U2 pin-one dot originally had at most 0.145005 mm to its pad's mask
opening, below the 0.15 mm legend rule. GPU L1/U4, IO U4/U5/L1, and storage
J2 had plotted gaps at the 0.15 mm numerical boundary. Their individual card
generators now shorten or move those marks after footprint pad clipping. Fresh
plots of the generated board files pass the independent front/back silk-to-mask
check for CPU (1636 ink objects), GPU (1689), IO (1629), and storage (1464).
These local silk changes do not address the key-notch failure or close the
remaining text-height and filled-ink-neck gaps.

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
