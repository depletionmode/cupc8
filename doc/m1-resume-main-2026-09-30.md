# Main-board resume, 2026-09-30

Recovered Claude session `5c66b0bc-3cde-4cbe-94c0-0355e82c5b48`, main agent
`a3efcbadd3314d4c8`. Its final action compared runs 12 and 13: both had
390 hand-route items, 13 bridging vias relinked, 44 dangling pieces removed,
520 overlap joins noded and zero open connections; Freerouting was skipped.
It then hit the weekly limit. The working tree's deterministic `_node_joins`
sorting is preserved.

## Recovered final run8 heat evidence

`scratchpad/g_heat.log` finished after the last live-status entry:

- I1 passes: input loop 26.926 mOhm at 115 C, against 60 mOhm.
- I2 passes narrowly: two-pitch disagreement 9.908%, against 10%.
- I3/I4/I5 fail: output copper body 201.414 C rise, body plus neck
  208.728 C, body plus barrel 202.500 C, against 20 C.
- Largest contributors: U2 OUT to U3.1 201.4 C, U3.4 189.1 C,
  R4.1 79.0 C. GND return cases also reach about 38 C.

These are fine-pitch results (0.1/0.07 mm), superseding the earlier
45–79 C coarse estimates. MB-005 remains red despite the input-loop pass.

## Current scratch work

Frozen source snapshot: `/tmp/cupc8-resume-main-20260930/hw` and `doc`.
Fresh `run1` reproduces zero open connections, 520 joins, complete DRC and
schematic parity passes, and exports Gerbers. The pipeline stops at the three
missing D7/U17/U19 CPL rotations; root has now fixed those in the working tree.
Build log: `/tmp/cupc8-resume-main-20260930/build.log`.

A scratch widening of the output bus to 3 mm creates shorts and clearance
failures beside 3V3_STBY and the buck feedback/PG pads. It is rejected and has
not changed source copper.

MB-051 diagnosis: U7.6 has a 0.15 mm diagonal F.Cu escape. A local mesh to
U7.30 is open at 0.14 and 0.1 mm, but connects at 0.07 mm (30.175 mOhm).
A trial 0.8 mm In4 bridge from its via into the existing plane does not alter
that result. The plane is already continuous there. Widening the existing
escape to 0.3 mm connects all three pitches but misses the neighbouring GND
via's clearance by 0.0097 mm. The resulting 0.27 mm source fix in
`main_power_corner.widen_3v3_escape` guards the exact pad and route geometry.
The widening's local mesh connects at 0.14, 0.1 and 0.07 mm:
23.411, 21.183 and 21.322 mOhm (0.65% fine-pitch disagreement).
The actual MB-051 gate uses coarser 0.25/0.18 mm grids; 0.25 mm still
rasterizes the diagonal open. An orthogonal-elbow trial connects those grids,
but fails DRC at neighbouring U7.7 (0.165/0.121 mm clearance vs 0.2 mm),
so it is rejected and removed from the source. The accepted source fix is
the straight 0.27 mm widening already verified in run2. The coarse gate needs
numerical refinement to represent that constrained diagonal. The accepted
widening's full R7.2-to-U7.6 probe reports 24.645/23.881 mOhm at
0.1/0.07 mm (206.7/577.1 s). This exceeds the old 10 mOhm planning allowance;
the user's subsequent M1 scope decision and circuit-derived bound are below.
The rejected elbow also exceeded that allowance (25.327/28.293 mOhm).
No model, convergence criterion or threshold has changed.

`run2` includes this fix plus root's new silk clearance and rotation rows.
It reproduces zero open connections and 520 joins, then stops at footprint
silk checks: root's stronger mask-aware check exposes the old clipping margin.
The discrepancy is in shared `clip_silk_to_pads`; root has been notified.
The filled saved board is undergoing direct DRC independently of that silk
check: it passes with zero violations, zero unconnected items and zero
schematic parity issues (`run2/drc-stub.json`). Run3 stopped when the new
clipping moved J3's four guarded strokes by 0.01 mm. Their exact guards are
updated for the new clipping. Run4 rejected the elbow on DRC. Run5 verifies
the accepted straight widening with the shared clipping and updated J3
guards. Local connectivity alone does not close MB-051.

## Remaining release blockers

Main power rise and mesh binding require physical fixes and fresh complete
gates. Five sub-0.1 mm Gerber clearances from the merged DeepPCB route remain
unresolved. `fabcheck.PLOTTED_DRC_GAPS` also keeps fabrication approval red:
filled copper neck width, filled silk neck width and silk text height are not
implemented; CPL review is still required. A second scratch power trial adding
VIN vias and wider B.Cu failed on the BUCK_SW via and L1 pad clearance, and was
rejected. Manufacturing and canonical `build/hw/main` are untouched.

## User's M1 load decision and proof update

The user clarified that passing the current M1 load is the target. Slots 5–6
are future cards, as already stated in `power.md`; their full 300 mA each
case is retained as an advisory result, and can be required explicitly with
`rail_reset_window.py --future-slots`.

The old 10 mOhm copper allowance was a planning budget, not a component
voltage limit. `copper_limit_3v3()` now derives the required bound from the
same tolerance-corner comparator thresholds, M1 current and unchanged
5 mV margins. Its M1 bound is **39.646 mOhm**. At U7.6's measured worst
24.645 mOhm, M1 margins are 19.621/14.256 mV and the conservative 1V2
30 mOhm case margins are 9.564/9.280 mV: all exceed 5 mV. Future full
slots 5–6 margins are 4.760/−1.226 mV and remain explicitly visible.

The complete accepted-widening fine-grid probe is 24.645/23.881 mOhm at
0.1/0.07 mm (3.10% disagreement; 206.7/577.1 seconds). All chipset pins
and both sense taps still require full extraction before MB-051 can pass.
The gate now uses those fine pitches, with optional concurrent workers and
compiled sparse/AMG solvers for the identical Laplacian and convergence
tolerance. Sparse CG at U7.6 gives 24.645342566967 mOhm versus the original
24.645342566990 mOhm, and takes 112.4 seconds. Tests compare resistance,
current density and open-copper rejection, including geometry-cache reuse
with a different terminal pair; heat tests 12/12, reset tests 16/16. AMG's
full U7.6 result is 24.645342567033 mOhm (73.8 s), matching the native solver.
The default solver remains dependency-free; compiled solvers are opt-in.
The core rail's bound is likewise derived from the unchanged 5 mV margins:
134.385 mOhm, replacing its 30 mOhm planning estimate as the required bound.

Normal M1 heat, using the existing conservative `budget.chain('worst')`
60 mOhm input-loop assumption: buck VIN 0.561 A, R4 slot bus 1.209 A,
total input 1.770 A. Scaling the recovered fault result at fixed equivalent
width by IPC's current exponent, and neck/barrel bounds by current squared,
gives body plus neck rises about **4.0 C buck, 9.6 C R4, 12.1 C GND**.
These are conservative comparisons for normal operation, not a thermal
field solution and not closure of the sustained 3.213 A fault requirement.
TI's [TPS25947 datasheet](https://www.ti.com/lit/ds/symlink/tps25947.pdf)
confirms current limiting and thermal shutdown/retry for a hard short;
a partial load below the current limit need not trigger shutdown.

Final circuit build `run6` passes silk, DRC/parity (0/0/0), Gerber export and
BOM/rotations, stopping only at stock DNS inside the old sandbox. Root's
fresh live stock check passes all 63 parts for two assemblies with 2× stock
margin. Main's pipeline quantity is now two, matching the first-run decision.
`run7` rebuilds the accepted local copper and latest shared silk clipping with
that quantity. Root reran its normal frozen pipeline from an unrestricted
process: every pipeline step passes, including stock, order, renders and
receipt, and that receipt validates against the working tree. The board
entrypoint then fails the separate CPU pincheck on 14 series-resistor paths;
root is handling its stale 33/56 ohm binding after the CPU rebuild finishes.
Source signal seeds remain unchanged. Standalone reset ngspice checks pass
(`reset-spice.log`; root independently verified `reset-spice-current.log`).

Complete all-pin/sense-tap extraction is running in root's unrestricted
process with four AMG workers and one BLAS thread per worker, using the
validated `run7` board. Log: `reset-allpins-unrestricted.log` in the scratch
directory. It has already reproduced U7.6's fine-grid pair, plus several
other chipset supply pins around 20–21 mOhm. No physical repair for future
slots or R7 has been made; M1 closure waits for all points and convergence.

Fault heat audit: the classification cut is 15 C, reserving 5 C for necks.
A 2 mm drawn trunk is 1.6 mm at the width corner and its uniform IPC rise
is 15.8 C. Consequently, the entire long trunk is connected in the hot
component; the heuristic then converts its worst single corner/via density
into a long equivalent narrow trace, yielding the 201 C bound. This cannot
establish the actual PCB temperature. Spatial thermal conduction/cooling or
appropriate IPC-2152/measurement evidence is needed before deciding that
physical repair is necessary. The fault gate remains red with its 20 C rule.

### All-pin numerical refinement and current provenance

The first unrestricted all-pin extraction completed with R0 unresolved at
U7.131: its 0.15 mm diagonal escape can disappear on the 0.1 mm raster.
KiCad's completed board has zero open connections. Successful mesh results
were previously lost after the first failed future; the extractor now records
and flushes every job before handling failures. It refines only unresolved or
nonconverged terminals to 0.07/0.05 mm, sequentially to bound RAM. A real open
still fails, and the required convergence remains 10%. This numerical change
has three focused tests covering coarse-open recovery, retention of other
terminals, rejection of a true open, and rejection of poor fine convergence;
the reset suite passes 19 tests. No U7.131 copper has been changed.

Root completed a fresh full main pipeline after repairing the stale CPU
pincheck binding. Output `/tmp/cupc8-canonical-rebuild-20260930/main` passes
all steps, 381 pincheck contacts and current workspace provenance; the first
order is two boards. Earlier `run7` geometry remains useful for comparison,
but its receipt is stale against the later shared pincheck source. The next
all-pin gate uses the fresh completed output. Root owns its unrestricted
launch because the original child sandbox disallows ProcessPool semaphores.

### Sense-tap correction and residual numerical work

The full refined extraction exposes a modeling error: R116.1's ~314 mOhm
self resistance was multiplied by the entire 41 mA core load. That branch
carries monitor input current. The code now keeps load-pad and tap self
resistance separate, and uses passive-network maximum principle,
reciprocity and superposition to bound their effects conservatively. Additional
1V2 loads (R11 LED base and R100 ADC) are charged their full rail/minimum
resistor current, ~1.414 mA, plus the additional link drop. Sense current for
copper is bounded by the guaranteed operating common-mode voltage interval
across minimum input resistance (~3.623 mA for R116), rather than by the hot
input-bias typical curve. This is deliberately loose. The older threshold
analysis's 1 nA hot bias allowance is still an explicit assumption; the TI
OPA376 datasheet provides a 25 C bias maximum, not a hot maximum. Increasing
the conservative total source load also requires checking the existing
40 mA LDO step bound before claiming complete operating closure.

R49/R50 PLL filter input pads are now included as possible core-current
terminals and their circuit values/net topology are bound by the gate.
Their y26.6 mm location requires expanding the extraction window's north
edge from y30 to y20. PLL-only serial probes completed: R49.1 at 0.1/0.07 mm
167.500/201.428 mOhm; R50.1 112.300/96.816 mOhm. Neither pair yet meets 10%
convergence. Their self resistance must not silently extend the qualifier
contract from FPGA VCC pins to PLL filter input pads; a transfer calculation
at the qualified VCC pins and monitor tap under PLL load can bound their
actual effects without assuming the entire core load flows into the sense
branch or changing thresholds.

The first refined full run still fails convergence at U7.40 (0.07/0.05 mm
34.198/28.145 mOhm) and U7.111 (31.319/94.115 mOhm). Requested additional
0.035 mm solves run serially in session 22295, `reset-core-fine.log`, using
the original y30 window for comparison. No physical repair is proven or
adopted. Current reset suite: 22 tests pass, including an omitted high
resistance PLL branch counterexample and an independent passive star
transfer/superposition example.

### Qualified PLL transfers and strengthened source bound

The optional mesh probe API now measures source-to-pad voltage drop per ampere
at unloaded qualified targets. A real pcbnew straight-track test verifies
that adding a probe does not draw load or change driving resistance, that a
middle probe sees its expected transfer drop, and that the loaded terminal
probe equals driving resistance. The mesh/heat suite passes 13 tests.

Under PLL current injection, the qualified targets are the four FPGA VCC
pins and R116 rail tap. R49.1 driving self resistance is ~201 mOhm, but its
worst transfer to these targets is 26.500/26.125 mOhm at 0.1/0.07 mm. R50.1
transfers are 17.670/20.879 mOhm and require fine refinement. PLL input-pad
self resistance no longer silently extends the core qualifier floor to the
PLL filter input pad. The full 40 mA can be conservatively distributed among
all U7 VCC and PLL input terminals; linearity bounds the qualified drop by
total current times the worst extracted qualified transfer. Auxiliary and
sense currents remain charged separately in absolute magnitude.

U7.40 now converges at 0.05/0.035 mm, 28.145/29.608 mOhm (4.94%). U7.111
converges at 0.035/0.025 mm, 29.876/28.429 mOhm (4.84%); the intermediate
0.05 mm 94 mOhm result was a raster artifact. The gate refines only affected
paths, serially through 0.025 mm, preserving the 10% criterion.

The same existing vendor behavioral LDO model and fabrication/load corners
were checked at 46 mA, exceeding 40 mA core + 1.414 mA auxiliary + 3.623 mA
loose sense-current bound. All POW-002 checks pass. Exact L6 minimum is
1.171569217 V. The reset source floor is tightened to 1.1715 V, rounded down,
so the extra conservative source current is accounted for without changing
comparator thresholds or the required 5 mV margin. Evidence log:
`reset-ldo-bound.log`. Hot input bias remains an engineering allowance in the
pre-existing threshold proof, subject to first-article qualification, rather
than an unconditional vendor-guaranteed hot maximum.

Fresh complete qualified gate session 33132 is running with four AMG workers
and serial adaptive fine solves on the current valid main receipt:
`reset-qualified-final.log`. The reset suite passes 22 tests after the model
updates. No main physical source or signal route changed during these checks.

### Completed M1 reset qualification

The fresh complete all-pin/PLL/tap gate finished with exit 0:
`reset-qualified-final.log`. Maximum 3V3 qualified resistance is U7.131
29.607 mOhm; maximum core qualified transfer is U7.111 31.116 mOhm. The
core bound including auxiliary and deliberately loose sense-current terms
is 69.074 mOhm, below the tightened 122.190 mOhm allowance. Required mesh
convergence is 7.554%, passing the unchanged 10% rule. The expensive U7.131
full-path 0.05/0.035 mm pair converges at 29.472/29.607 mOhm (0.46%).

Peer review then corrected two small threshold-model omissions: independent
IN- bias currents are included by exact two-node reference-ladder KCL, and
independent IN+ bias currents are included in both comparator threshold
inversions. No component values or 5 mV margins changed. The header now
states modeled windows with an explicit 1 nA engineering bias allowance,
subject to first-article qualification, rather than a vendor-guaranteed hot
maximum. Tests compare ladder corners against an independent NumPy nodal
solve and check expansion of both threshold intervals under IN+ bias.

The authoritative final corrected-model command also reruns SPICE:

```sh
python3 hw/power/rail_reset_window.py \
  /tmp/cupc8-canonical-rebuild-20260930/main \
  --mesh-log-replay /tmp/cupc8-resume-main-20260930/reset-qualified-final.log \
  --mesh-audit /tmp/cupc8-resume-main-20260930/reset-qualified-final.inputs.json \
  --spice
```

It passes all numerical and S1–S8 sequence checks with exit 0. Log:
`reset-qualified-bias-final.log`. M1 low/high margins are approximately
16.540/11.175 mV for 3V3 and 7.962/7.178 mV for core; all exceed 5 mV.
The future full two-card load remains advisory and fails; no future-only
repair was made. Source and graph provenance is explicit: the cache checks
the normal live fabrication receipt, DRC, BOM and netlist; board/drc/net
hashes; completed raw log hash; saved original source hashes; unchanged
copper solver hash; and complete supply/PLL/tap inventory. Original/current
threshold-model hashes appear in the final log. This numerical cache does
not create or rewrite a fabrication receipt. Altered board/log/solver replay
is rejected by focused tests. Reset tests now pass 27/27; mesh/heat tests
pass 13/13. No signal reroute or U7.131 physical repair was necessary.

The independent fault-model audit now corrects installed eFuse RILM resistor
tolerance: maximum fault current is 3.245 A rather than the old 3.213 A.
The historical run8 heat numbers remain historical evidence, not a new
current-gate pass. Root and the co-simulation reviewer own that remaining
fault/thermal audit; normal M1 heating estimates are recorded separately.
