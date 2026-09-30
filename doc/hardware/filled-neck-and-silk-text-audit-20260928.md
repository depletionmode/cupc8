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
