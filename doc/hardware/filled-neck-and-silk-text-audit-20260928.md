# Filled-region and silkscreen text evidence — 2026-09-28

## Current checker status — 2026-09-30

The committed checker was extended after the original audit. It now parses
region arcs, unions all plotted ink, constructs a conservative erosion/opening
certificate, checks disconnected erosion components and merged holes, and
allows certified convex corner caps. The isolated orthogonal scanline proof
remains an additional certificate. Results contain `proved`, `failed_regions`,
`failures`, and `complete_for_filled_regions`; there is no `deferred` category.
A failed morphological certificate does not by itself prove a physical narrow
neck: its thin witness width is twice the distance from a residue point to the
ink boundary, rather than a measured opposing-edge neck width.

The 2026-09-30 repair caches immutable GEOS boundaries per geometry engine.
Previously each width witness retained another copy of the entire board ink
boundary. A main B_Cu diagnostic exceeded 22 GB RSS and was stopped. Reusing
the identical boundary completed the same default-resolution analysis in
33.5 seconds with 1.12 GB peak RSS. All rules, 128-segment arc resolution,
radius inflation, and 5 nm numerical tolerance remain unchanged.

The diagnostic examined the staged main B_Cu plot at the 0.100 mm rule:
17 regions, 8,452 reported thin witnesses, zero proved regions. The full result
is `/tmp/cupc8-resume-main-20260930/fab-neck-cached.log`. This was a standalone
geometry diagnostic, not a current receipt-bound release certificate. It
**does not justify rerouting the main board**. Many reported witness widths
round to zero because the witness lies almost on a boundary. A simple wide
beveled polygon also fails four corner witnesses despite having only convex
corners of at least 90 degrees; the old corner certificate rejected infinitesimal floating-point slivers
outside diagonal tangent edges (outside areas approximately 1.6e-18 mm²).
The correction shifts the unchanged full-radius tangent disk and the cap
contact vertices 0.1 nm along the interior bisector. Strict GEOS containment
is still required for both candidates. The rule, disk radius, arc resolution,
and tolerance are unchanged. The wide beveled polygon now passes; this is
a certificate repair, not a copper repair. Current plots must be rechecked
before their remaining witnesses can identify necessary repairs.

The corrected standalone main B_Cu diagnostic completed in 30.6 seconds
with 1.13 GB peak RSS and a 6 GiB address-space cap. The result improved to
1 proved region, 16 unproved regions, and 1,074 thin witnesses. Its complete
JSON report is `/tmp/cupc8-resume-main-20260930/fab-neck-corners.log`.
`complete_for_filled_regions` remains false. There is still no complete
release certificate or established need for a main copper change.

The focused regression now matches the actual API: exact-rule orthogonal
regions pass, 80 µm copper and silk necks fail at the 100 µm rule, acute terminal
tips remain unproved, a wide nonorthogonal beveled region passes the corner proof, and that
region covered by a wider plotted flash passes the union proof. One thousand repeated boundary queries
retain one boundary geometry. Run
`python3 test/hw/test_fab_neck_coverage.py`.

The full release gate remains incomplete. No complete eight-board neck
certificate has been recovered or claimed. `--require-complete` must continue
to reject any failed certificate; the earlier orthogonal-only table has been
removed because it describes a superseded implementation.

For silkscreen text, the existing `hw/tools/silktextaudit.py` was rerun on all
eight current receipts and compared their Gerbers with a fresh export. Its
reports are in `build/hw/silk-text-current/` outside the receipt-owned board
directories. Each board's source minimum is 0.8 mm, and the source inventory
passes: main 369 visible text objects, CPU 53, GPU 57, IO 57, storage 47,
Wi-Fi 28, e-ink 59, system 59. The reports bind each board receipt, PCB, and
both silkscreen Gerber hashes. Gerber operations do not identify which strokes
are text or which strokes form a glyph, so these source-backed heights are not
an independent plotted text-height proof. The final fabrication gate remains
red for that reason, as well as the deferred filled-region widths.

The seven card notches still fail the 0.300 mm copper-to-edge rule at
0.200 mm. All CPL reviews remain unsigned and require per-designator human
placement, pin-one, polarity and rotation review.

## Frozen geometry follow-up — 2026-09-30

An isolated, hash-recorded snapshot of the refreshed main B_Cu Gerber was
checked at its actual 0.100 mm rule. The current candidate-halo lookup and
zero-bisector guard yield 17 regions, one proved, 1,067 thin residues and no
pinch or web. The combined unproved area is 0.0089704 mm². The largest
residue is 0.0006541 mm² at approximately (108.024, 56.875) in PCB coordinates:
the +1V2 island/corridor union has a 70.47-degree convex tip there. This is a
specific corner-certificate failure, not a measured narrow opposing-edge
power conductor or a justification for a main signal reroute.

A scratch extension tested convex hulls containing a full rule-size disk,
with every hull angle at least 90 degrees and strict containment inside the
ink. It reduced the uncovered area to 0.0051846 mm² but did not prove any
additional region. It is **not adopted** as a release certificate. Reports
and immutable inputs are under `/tmp/cupc8-fab-release/`; these standalone
diagnostics do not validate stale or incomplete manufacturing receipts.

Front-silk snapshots available during the sequential rebuild (main, CPU,
GPU, Wi-Fi and e-ink) each have 43 unproved filled-region residues at the
same translated KaplanLabs logo shapes. Their back silkscreens contain no
filled regions. This identifies shared logo geometry as a separate local
repair candidate; it does not establish a text-height defect. IO, storage
and system plots were unavailable at the instant of that snapshot, so the
diagnostic is not an eight-board release pass.

The isolated logo repair now has a complete positive certificate: the native
KiCad polygon generator applies a 0.080 mm round erosion followed by an
equal round dilation, before fracture, with 2 nm curve error and 1 nm saved
vertices. Both 10 mm and 12 mm candidates were loaded as KiCad footprints,
saved in standalone boards, and exported with `kicad-cli`; the unchanged
0.150 mm plotted neck checker passes every region (21/21 and 20/20).
Regeneration is byte-for-byte deterministic. Compared with the old 100 nm
rounded footprint vertices, removed ink is 0.3061% / 0.1170%; additional ink
from retaining the SVG's finer coordinates is 0.0051% / 0.0045%, and bounding
coordinates change by no more than 0.197 µm. The proposed generator patch
and its exact supplier-independent artwork outputs are recorded in
`/tmp/cupc8-fab-release/`. Root authorized and adopted the generator and both
regenerated library footprints after coordination; their hashes exactly
match the tested candidates. Complete board rebuilds and their resulting
release checks remain required.

A separate scratch main-board trial rounds only the +1V2 island/corridor
filled polygons with a 0.060 mm opening, unfracturing before the operation
and fracturing afterward to preserve holes. It removes 0.05037 mm² out of
364.5755 mm², passes actual KiCad DRC with zero unconnected items, and proves
both formerly unproved +1V2 regions. The remaining main B_Cu proof is still
red (3/17 regions proved). Independent electrical solves reach all four
chipset core pins and the R116 sense tap. Relative to the unchanged routed
baseline, resistance increases are at most 0.0241 mΩ at 0.050 mm pitch and
0.00458 mΩ at 0.035 mm pitch. These comparisons support the local repair;
they do not replace the full receipt-bound reset qualification. The main
signal tracks have not been changed, and the trial is not released hardware.

### Complete isolated fill trials

The main trial now covers every copper zone. A native circular opening of
0.060 mm radius preserves the six-layer 0.100 mm rule and passes all six
exported copper layers: B 17/17, F 42/42, In1 1/1 and In4 1/1; In2/In3
have no filled regions. Actual KiCad DRC reports zero violations and zero
unconnected items. Every track, via and pad is unchanged. Ground polygons
are normalized through fracture/unfracture before exact contact checks;
three unanchored 2 nm² rounding fragments are removed. Larger unanchored
fragments, uncertain contact with other zones, invalid areas or removal
above 0.1% fail closed. Holes and narrow bridges have regression coverage.

The final helper's routed inventory and every raw +1V2/+3V3 filled-polygon
coordinate match the candidate that passed the full adaptive current-M1
reset extraction. An exact row-indexed raster replaces only redundant
point/edge work, preserving the original Matplotlib binary64 crossing
predicate, every grid and the strict 10% convergence limit. Equality covers
31,356,376 fixed-grid sites using a per-row directed-crossing-edge identity
certificate and Matplotlib reference, plus 51,760 unchanged-contour points
including actual vertices and their adjacent floating values. Holes,
multiple outlines and native pad polygons have focused regressions.

The genuine U7.131 refinement is 29.4723848072 mΩ at 0.050 mm and
29.6072167925 mΩ at 0.035 mm. All supply, monitor-tap and PLL load-transfer
checks converge. Current 625.3 mA M1 threshold margins are 16.295/10.921 mV
on 3V3 and 7.962/7.178 mV on 1V2, above the unchanged 5 mV requirement.
This is an isolated source-geometry reset PASS, not a complete receipt.
The superseded slow extraction was stopped only after the verified exact
accelerated extraction completed. Its 36 common completed terminal results
agree within 0.0000000619 mΩ of numerical solver roundoff.

The refreshed CPU, GPU, IO, Wi-Fi, storage, e-ink and system physical outputs
were separately surveyed at their actual PCB minimum widths. Each has
unproved filled corners. Individually guarded isolated fill trials use
0.060 mm opening radius for their 0.100 mm rules, and 0.090 mm radius for
Wi-Fi's 0.150 mm rule. All seven actual trial PCBs pass DRC with no
unconnected items. All 28 exported copper layers completely pass the
unchanged plotted neck certificate. The maximum removed fill area per
board is 0.00087–0.00155%; CPU additionally removes one exactly unanchored
2 nm² fragment. Tracks, pads and vias are preserved in each trial.

These trials are recorded in `/tmp/cupc8-fab-release/card-fill-trials/`,
with source surveys in `current-card-survey/`. System uses the completed
`system-strong-pipeline` output; IO uses the completed repaired output.
Root authorized adoption after these individual trials and the strict
baseline reset PASS. The source now has explicit guarded hooks for each
board, invoked after final fill/stitching and before saved-board DRC and
exports. The helper, hooks, exact raster and mesh sources are bound by
manufacturing input hashes for all eight boards. Eight fill regressions
and five raster regressions pass and are included in FAB-002 and MB-051.
Fresh full pipelines and applicable power/reset/SI qualifications remain
required. The unresolved sustained-fault input thermal gate is unchanged.
Any subsequent power repair that changes the 3V3 fill needs fresh reset
qualification and independent DRC and plotted-neck checks.

Fresh CPU and system full pipelines with the adopted hooks completed ERC,
guarded routing, final fill, DRC/schematic parity, all fabrication exports,
BOM/CPL and BOM checks. Both stopped at actual JLC stock DNS failure. Their
independent export parity, every copper/silk neck and 53/59 delivered text
identities pass. Full direct development `fabcheck.check` additionally
passes all drill, annulus, hole clearance, edge, mask, paste and ink checks;
it reaches the untouched final review check and reports only missing
`fab/cpl-review.json`. Machine overlays remain pending human review. These
are physical development results, not manufacturing receipts: stock failed,
and a shared evidence-binding update occurred during the pipelines.
