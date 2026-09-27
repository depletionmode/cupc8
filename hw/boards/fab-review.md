# Fabrication file review receipt

`boardcheck.py <board> fab` checks every Gerber command and aperture against a
fresh export of the DRC-clean board, then checks each Excellon drill hit
against a footprint pad or via. This export parity is not Gerber re-import DRC.
The board also needs a recorded visual CPL review before the fab gate passes.
Gerber re-import DRC remains a separate missing check; a completed review
receipt alone does not make this gate pass.

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
