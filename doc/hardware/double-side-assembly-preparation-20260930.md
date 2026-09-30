# Proposed double-side Wi-Fi assembly support

The local Wi-Fi SPI buffer layout is being prepared on the back surface to
preserve the existing routed board. It is an isolated candidate, not an adopted
board or manufacturing release. The slot permits a 2.67 mm solder-side envelope;
actual component heights, clearances, final STEP fit and supplier assembly still
need qualification.

## Required tool changes

The existing native exporter already writes Bottom CPL rows. However, the BOM
checker explicitly rejects them, order.json always requests top-only assembly,
and the review pack plots and models only the top side. Merely emitting Bottom
rows therefore does not provide a valid assembly package.

Tested isolated candidates are under
`build/double-side-assembly-prep-20260930/proposed-source/`:

- `assembly_geometry.py`: bottom local reflection, package rotation correction
  and placement-origin reflection in an explicit top-view coordinate frame.
- `kicadgen.py`: correct side-dependent CPL geometry and assembly order derived
  from the actual fitted CPL sides.
- `bomcheck.py`: actual native board-side matching, positions and rotations;
  rejects duplicate references and nonfinite placements.
- `cpl_autochecks.py` and `cpl_review_pack.py`: native top/bottom plots, matching
  side overlays and geometry, explicit viewing frame, and no reuse of prior
  top-side decisions for new bottom placements.
- `fabcheck.py`: a bottom-side package's human review also binds the exact bottom
  render hash. A stale or omitted bottom render is rejected.

The fab agent separately owns the isolated side-aware silkscreen candidate.
It distinguishes front/back bodies, courtyards, pads and words, while through-hole
pads and open vias obstruct both surfaces. It preserves the old all-top branch.
The two kicadgen candidates are now composed against their recorded common
source in `merged-source/`, with an exact patch and no fuzz. Composition checks
pass all eight current Top packages, the native mixed-side fixture and the
side-aware silk cases. `merged-proposals.json` binds the sources and proofs.

## Evidence and limits

- `native-geometry-proof.json`: 24 native KiCad/cached-supplier comparisons,
  including asymmetric ICs, nonzero rotation corrections and a header origin
  offset. Seven meaningful reflection/rotation/origin/input counterexamples.
- `tool-qualification.json`: all eight actual round3 Top packages still pass;
  native selected mixed-side export/check passes; eight corrupted CPL/order
  cases fail. Board receipts remain current.
- `review-qualification.json`: all 124 focus-part analysis/check results across
  the eight actual Top packages remain unchanged. An actual unsigned native
  mixed-side review renders three bottom and one top component on separate
  plots. New C7833 supplier CAD remains unknown/human; no record was fabricated.
  Wrong-side input and two synthetic bottom-render binding mutations fail.
- `unsigned-native-bottom-review.html`, `native-top.svg`, `native-bottom.svg`:
  inspectable candidate placement fixture, not a complete routed board review.

Synthetic review-binding tests operate only in a declared test directory and
remove their approval-shaped fixture afterward. No human review, production
signature, manufacturing receipt, supplier preview, upload or order was created.

JLC's [Pick & Place file specification](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly)
(last updated September 9, 2026) requires explicit Top/Bottom placement and
counterclockwise positive rotation. The geometric mirror model is an inference
checked against native KiCad and cached supplier pads; it does not prove the
supplier's final preview or machine interpretation. Exact new-part supplier
CAD, bottom rotation review and hash-bound human approval remain required.

## Adoption

Keep shared manufacturing inputs frozen while receipt-bound SPI jobs run.
Adopt qualified physical changes, IO capacitor repair and the necessary combined
assembly-tool changes in one coordinated source freeze. Then run genuine new
pipelines, all affected fabrication/power/reset/SI checks, final mechanical fit,
unsigned all-board review packs and complete verification. Select both assembly
sides for Wi-Fi only if its final fitted board needs them; the other boards derive
their options from their own final placements. Final order documentation must
match these actual options.
