# Main input thermal qualification scope and model correction

Development audit, 2026-09-30. This is not a manufacturing receipt or a
thermal release pass. The decided 20°C rise, 3.288102 A worst-case eFuse
limit, material corner, external IPC coefficient policy and 3 mm maximum
neck extent remain unchanged.

## Required current paths

The original requirement in `power.md` is **every full-current conductor**,
not every connection to GND. The TPS25947 datasheet's pin-functions table
identifies pin 8 as the ground reference for its internal circuits; its
maximum enabled quiescent supply current is 610 µA. The load power path is
IN (5) to OUT (6). Driving the entire 3.288102 A load through GND (8)
therefore models an additional local solder bridge or internal control-pin
failure, rather than the sustained current-limited load condition required
by MB-005. Source: [TI TPS25947 datasheet](https://www.ti.com/lit/ds/symlink/tps25947.pdf),
pin functions and electrical characteristics; the cached official text was
independently inspected.

`main_input_heat.py` continues to extract both U2:8-to-J1 routes and includes
them in I1's conservative reference resistance and I2 convergence checks.
I3–I5 exclude only these two quiescent-reference thermal cases. All positive
input branches, genuine output power branches, and full-current C3/C5/U3 ground returns
remain required. Shorted C3/C5 capacitors and U3's power ground can actually
carry the full current limit. The external local load used by MB-109 can
return at C3's ground power connection; its current crosses that qualified
return copper rather than the eFuse's control-ground stub. This does not
qualify remote slot ground routing, connector contacts, or an enclosure
thermal boundary: their separate requirements still apply.

The fitted TLV62569PDDCR (`hw/parts/C398365.yaml`) has EN on pin 1
and VIN on pin 4. Both are tied to 5V_SYS, but EN is a logic input, not
a second full-current power input. Its existing extracted resistance and
source/net identity remain diagnostic; thermal acceptance requires VIN4
and excludes only EN1. Both positive capacitor escapes C3:1 and C5:1
are independently extracted and mandatory: a shorted capacitor draws full
fault current in its positive escape as well as its ground return. No
shared-net or other-endpoint coverage is assumed. A focused regression rejects an overheated VIN4
while accepting an artificial full-current EN1 diagnostic. The isolated
EN-only extra via/branch is being removed; any remaining shared copper
repair must demonstrably improve a genuine power-current case.

The parent review approved this physically derived distinction before
adoption. It is a correction to test current placement, not an exception
to the 20°C rule or a waiver for a full-current power conductor.

## Thermal accounting corrections

The 15°C body/neck classification threshold now uses each actual layer's
finished copper thickness. Previously an outer-copper density threshold
was applied to thinner inner copper, allowing short inner via transitions
to be incorrectly assigned to a long equivalent trace. The IPC external
coefficient remains the required policy for every layer; the internal
coefficient remains diagnostic.

Every copper cell outside a proved short neck contributes to the body
bound, including the immediate neck boundary. The old 0.5 mm halo exclusion
could understate that boundary's temperature. Body plus neck/barrel must
still meet 20°C. Both mandatory mesh pitches, 0.10 and 0.07 mm, contribute
to thermal acceptance; a failure at either cannot be hidden by the other.

Focused regressions cover actual-thickness 15°C classification, boundary
heat accounting, full-power-ground coverage and coarse-pitch failure.
The older 1.75 mm drawn width estimate also demonstrably exceeds 20°C at
the corrected resistor-temperature current corner; the regression now
records that failure and verifies the 1.80 mm comparison against 20°C.

## Numerical confidence and retained evidence

The original mesh gate requires 10% numerical convergence. The original
0.10/0.07 mm pair remains mandatory. If it has not converged, independently
solve 0.05 mm and then, only if necessary, 0.035 mm. The **last two observed
resistance estimates must agree within the unchanged 10%**. Every observed
resistance remains in the conservative maximum, and **every observed
thermal result must still meet 20°C**. The refinement cannot discard an
unfavorable coarse result or convert an actual thermal failure into a pass.
Failure to converge at the bounded finest pair remains red. This applies
the numerical-confidence requirement to actual refinement rather than
interpreting an arbitrary coarse pitch pair as a physical board defect.

The normal catalogue MB-005 command uses the explicitly selected AMG
solver, with the unchanged matrix, residual and verified numerical
equivalence to CG. `main_input_heat.py` still defaults to CG for direct
invocation. AMG requires the tested SciPy/pyamg environment. A geometry
cache exists only within an extraction call on an immutable board; every
terminal excitation is solved anew. The completed-receipt gate dumps every
observed density grid and terminal mask to NPZ with a JSON manifest outside
the board receipt tree, so it cannot invalidate the receipt it checks. The
manifest binds PCB, completed evidence, active model-source and NPZ hashes,
current, limits and solver; it revalidates receipt/source immutability
before writing and explicitly denies a manufacturing-release claim.

Example receipt-bound command with the tested solver dependencies on
`PYTHONPATH`:

```sh
python3 hw/power/main_input_heat.py build/hw/main --solver amg \
  --dump-results /tmp/main-thermal-results.json
```

## Physical trial status

Frozen v11 (`4b27f8df8ba725624862a6e4a1aaf1f4f6d2f2111f80f33ea733006eb5269d5b`)
needed local /5V_SYS branches and vias to address genuine output bottlenecks.
With corrected accounting, its R4 output branch still rises 21.046°C on
0.10 mm and fails. The previously extracted positive, C3/C5/U3 return and real output
cases other than R4 pass in that development mesh. The newly required
C3:1/C5:1 positive escapes still require actual extraction. Fresh production fill geometry
and final local repair require full extraction, source-bound receipts and
independent checks before any release claim. Rejected v12–v15 clearance
trials are isolated and have not been adopted.

Frozen v19 (`bc166ffad627ff7e6da78cb13f8327ac00ef20266ec30cf196ffda57f0982ef3`)
removes the EN-only added via/branch and replaces the upper OUT development
via with a short diagonal escape to (17.94, 158.20). Actual KiCad DRC and
opens are zero after the production fill helper. All eight mandatory real
output/capacitor thermal case/pitch results pass (maximum 18.248°C). R4
and C3 additionally converge at 0.07/0.05 mm (4.574% and 4.051%); their
refined thermal rises are approximately 17.02°C and every coarse bound is
retained. Source pads and all non-5V routed copper are unchanged. Full
actual post-helper input/return qualification, independent reset/neck
proofs and a fresh source-bound normal pipeline are still required.

## Completed receipt-bound development qualification

The v19 repair was adopted as an honest design-candidate route seed. A genuine
full generation pipeline reproduced all pads, all 8,143 routed copper items
and every filled-net/layer polygon coordinate exactly. The final round2
pipeline completed with current source-bound `evidence.json` under
`build/development-offline-20260930/round2/main`, including DRC/parity, actual
exports, BOM, order, renders and 381 pincheck contacts. Its bound
`pipeline-scope.json` explicitly records development offline mode, skipped
live stock, and `manufacturing_release_approved=false`.

Actual completed-provenance MB-005 and strict current-M1 MB-051 commands both
exit zero on that package. Their checks have not been converted into a
manufacturing-release approval.

| Actual gate | Worst result | Unchanged requirement |
| --- | --- | --- |
| Main full-current input/output/return resistance | 26.96192039 mΩ loop | <60 mΩ |
| Main body + neck rise, every observed grid | 19.51901964°C | ≤20°C |
| Main body + barrel rise | 16.106°C | ≤20°C |
| Last-pair resistance convergence | 9.8010289% | ≤10% |
| 3V3 reset assertion/release M1 margins | 16.295 / 10.921 mV | ≥5 mV |
| 1V2 reset assertion/release M1 margins | 7.962 / 7.178 mV | ≥5 mV |
| Strict reset copper convergence | 7.497% | ≤10% |

The additional conservative body + neck + barrel diagnostic also passes
19.51901964°C. All mandatory 0.10/0.07 mm grids and necessary finer grids are
included; no coarse overbound was discarded. The complete production-bound
thermal JSON/NPZ are stored outside the receipt directory at
`build/development-offline-20260930/round2/main-thermal-results.{json,npz}`.
Detailed actual command logs are preserved under
`/tmp/cupc8-main-thermal-audit-20260930/main-receipt-{thermal,reset}.log`.

The round2 main direct Gerber fab check found two separate, historical signal
clearance spots after an exact primitive-distance checker resolved earlier
polygonization uncertainty. Minimal signal-only correction and a genuine
fresh pipeline/qualification are being coordinated separately. The completed
round2 power evidence remains immutable; it is not rehashed to a later board.
Live stock and unsigned human CPL review remain release blockers.

## Final round3 physical and power qualification

Two historical signal-clearance vertices were moved +1 µm in X (four
segments total). The current cosmetic source, every pad/via, all power
copper and filled coordinates are preserved. The actual round3 normal
development pipeline completed with fresh evidence at
`build/development-offline-20260930/round3/main`. Its actual generated PCB
has SHA256 `e207e3072bb73a396f9e9ca4c0241344703ffc390b5cfb0829ffae510eb94081`.
`main-qualified-geometry-identity.json` proves exact 8,143-item routed
copper and filled-coordinate identity against the independently qualified
current-cosmetic candidate. No old receipt was rehashed.

Fresh actual MB-005 and strict current-M1 MB-051 both exit zero on that
completed package, with the same bounds in the table above. The complete
thermal manifest/grids are `round3/main-thermal-results.{json,npz}`. Actual
command logs are `main-final-round3-{thermal,reset}.log` under
`/tmp/cupc8-main-thermal-audit-20260930/`. The final actual fab check reaches
and fails only the unsigned human CPL review: `CPL overlay review missing:
fab/cpl-review.json`. All preceding physical geometry checks pass. Its
correct current log is `main-final-round3-fab.log` in that directory.
Human CPL review and live stock remain release blockers; the scope is
explicitly development offline, not manufacturing approval.
