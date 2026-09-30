# Guarded route reuse — 2026-09-30

This helper is a design seed mechanism. It is not a completed board pipeline,
DRC certificate, procurement check, or substitute receipt. The helper and exact-geometry adapters are now adopted in the board sources; completed manufacturing receipts still require fresh full pipelines.

## Proven behavior

`test/hw/test_route_seed.py`: 14 tests pass, including fail-closed geometry changes,
source-stage incompleteness, route opens, origin-state misuse, exact via
roundtrip and preserved routing under silk-only changes.

The main, CPU, GPU, storage, Wi-Fi and System adapters preserve 7475, 1208,
784, 731, 526 and 1177 routed copper items respectively. Their design seeds
come from actual fresh pipeline route stages. Stock lookup was blocked by
restricted-network DNS, so the records explicitly say `pipeline-incomplete`.
No completed pipeline receipt was written or manually refreshed.

Fresh-source probes verify exact compatibility and no clearance/short/crossing
errors before pours on main, CPU, GPU, storage and Wi-Fi. Main's physical
post-route escape repair is already present and is not repeated; its freshly
generated silk still gets the current guarded cleanup.

System required three local GND-via moves because its old weak seed restored
via drills in U2.4/Y1.2/Y1.4 mask openings. All non-GND copper, including USB,
was preserved exactly. The first genuine repaired pipeline passed via-mask,
DRC/parity, Gerber/drill and BOM/CPL steps before stock DNS failed. Its actual
routed stage then supplied the stronger seed; a second genuine pipeline using
that seed repeated the same physical passes. Three native regressions and the
registered no-move counterexample protect the repair.

CPU C8/R8, GPU C13/F1 and storage C13 have explicit one-nanometre decimal
placement normalization: only the exact source and SES-roundtrip states are
accepted. The seed geometry guard remains exact; arbitrary movement still
fails. The source correction is checked before any route is adopted.

## Board-wrapper API

After a genuine pipeline writes `<card>-routed.kicad_pcb` and the applicable
board-specific post-route transformations have finished:

```python
route_seed.extract(
    routed_pcb, seed_path,
    board_name="gpu",
    pour_nets=("/GND",),
    post_route_contract="gpu-postroute-v1",
    origin_note="Route stage completed; later pipeline step blocked; no receipt",
)
```

A complete validated pipeline may instead supply `completed_build=build_dir`.
The helper then validates the actual existing receipt and confirms the routed
stage's byte hash appears in its artifacts. The seed still makes no claim that
manufacturing gates passed: it always records `manufacturing_pass=False`.

Every adopted seed is explicitly included in `boardevidence.inputs` for its consuming board. A seed under `hw/boards` is not automatically hashed for other boards.
The generic helper itself belongs under `hw/tools` and would be hashed already.
Record the helper/seed adoption once, then run all new full pipelines.

A board's `seeded_route` callback calls:

```python
result = route_seed.apply(
    board, seed_path, board_name="gpu", pour_nets=("/GND",),
    post_route_contract="gpu-postroute-v1",
)
# Set this board's own seeded-state flag only after apply succeeded.
# Log result's origin state/hash. Return zero to the existing pipeline.
return 0
```

Never catch incompatibility and invoke the autorouter. Every guard failure or
open non-pour net raises `ValueError`, which the existing pipeline does not
turn into another routing attempt. The new full pipeline still regenerates
fills, silk, Gerbers, BOM/CPL, checks, renders and a legitimate new receipt.

## Post-route transformations

The helper cannot determine whether a GPIO repair, copper nudge, fanout
removal or impedance launch edit may be replayed. The board wrapper must:

1. Establish that the saved routed stage contains the current post-route
   transformation, not an earlier physical circuit.
2. Use a versioned contract ID whose meaning names those transformations.
3. On seeded builds, verify the transformation's intended final geometry or
   skip only a transformation proven already present and non-idempotent.
4. On normal builds, perform the current transformation normally.
5. Bump the contract and reject the old seed when its semantics change.

System's existing `_SYSTEM_SEEDED` shell-fanout verification is an example.
A generic callback must not blindly run/skip every board's `post_route`.
Physical pad/net/shape changes are rejected even if all references and
centres happen to match. Footprint values are also guarded conservatively:
a BOM change requires a deliberate engineering review and new seed.

## Guard scope and limits

Guards compare actual native serialization of every pad: copper geometry,
layer set, custom primitives, position/orientation, drill and ancillary pad
attributes. UUIDs and obsolete numeric net codes are normalized; actual net
names remain exact. Guards also include footprint placements/layers/library
identities/values, footprint copper or Edge.Cuts graphics, board copper stack,
settings, outline/copper graphics and keepouts. Silk graphics/text size are
excluded so a proven logo correction does not reroute the board.

Only straight tracks and ordinary through vias with uniform per-layer
widths are supported. Unknown copper objects, blind/micro vias and variable
via diameters fail closed. Final DRC remains mandatory and can reject a seed
when current clearance/fabrication requirements change. Non-pour connectivity
is checked on an isolated board clone with every zone removed. The live target
is changed only after the clone passes.

The System v1 helper is weaker: it only compares placement and pin/net names;
its main_seed extractor does not preserve via spans or full pad geometry.
Adopting this stronger API requires new real routed-stage extraction, not
upgrading an old incomplete seed by inventing guards from today's board.

## Evidence

- `/tmp/cupc8-route-reuse-20260930/current-source-probe.log`: main/CPU source compatibility and post-route checks.
- `/tmp/cupc8-route-reuse-20260930/cards-source-probe.log`: GPU/storage/Wi-Fi source compatibility checks.
- `/tmp/cupc8-route-reuse-20260930/system-actual-pipeline.log`: actual System local-repair pipeline, physical gates pass then supplier DNS failure.
- `/tmp/cupc8-route-reuse-20260930/system-strong-pipeline.log`: actual System stronger-seed pipeline, same physical gates pass then supplier DNS failure.
- `test/hw/test_route_seed.py`, `test/hw/test_boardcheck.py`, `test/hw/test_system_seed_vias.py`: 16 + 18 + 3 focused regressions pass.
- `test/counterexamples.toml`: reverting System's three local movements reproduces the three forbidden pad holes and fails the physical regression.

The current input hashes invalidate older packages. Canonical adoption must
copy complete directories from genuinely completed full pipelines, then
validate receipts and regenerate the co-simulation/SI evidence. These design
seeds never authorize manufacture by themselves.

Manual local repairs may be extracted with explicit `design_candidate=True`.
Their real origin filename and SHA are recorded as `design-candidate`, with no
receipt or manufacturing pass. Exact geometry and nonpour connection guards
still apply; a fresh real pipeline must subsequently validate the candidate.
The independent external filled-geometry checker is now also hashed as a
manufacturing input, so changing its proof invalidates existing receipts.
