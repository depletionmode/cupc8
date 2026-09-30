# Current M1 release gates and proof index

Snapshot: 2026-09-30. Latest genuine candidate packages are at
`build/spi-development-working-m1-firstarticle-20260930/source-tree/build/hw/`.
All eight normal DEVELOPMENT-OFFLINE builders pass with fresh quantity-two
receipts. This coherent tree includes the current affine copper solver,
firmware/logical sources, readiness/order contracts, and genuine WiFi
output270/cap15 source/seed/part identities. Main33 and the WiFi220/5.6p input
remain unchanged. **This is not a manufacturing release or full E2E pass.**
Seven boards have exact tracks/vias/pads/guards/raw-fill identity against their
previous qualified normal outputs. WiFi has exact physical identity to its
new qualified native candidate, including actual fitted270/15 values/SKUs.
Strict actual all-eight source/native topology passes 992 paths/535 runtime
nets with zero unmodeled nets, 44 existing accepted boundaries and six modeled
reset nets. Permanent actual-network mutations and fresh firmware/native
functional acceptance are tracked separately; source topology is not analogue
or whole-machine proof.

The user explicitly selected Main, system, CPU, IO, storage, WiFi and either
GPU/HDMI or eInk for the first article. The four tested mixed maps pass all
128 current actual clock cases. The six sole-WiFi clock failures remain
recorded outside that accepted initial population; any-slot, reduced-card and
six-WiFi general capacity claims remain open. Passing128 clock cases does
not replace full-byte, data/turnaround, power, firmware, host, storage, display,
keyboard, network or first-article measurements. Earlier selected15, v138,
round3 and round2 reports remain immutable historical/scoped evidence.
Proof index: `build/spi-development-working-m1-firstarticle-20260930/`,
including `normal-builder-status.json`, `source-construction-manifest.json`,
`accepted-source-construction-audit.json`, `qualified-physical-identity.json`,
`generated-wifi-physical-identity.json`, `qualification.json` and bound logs.
The normal USB host retry still fails `listen EPERM` on127.0.0.1. The existing
no-TCP native CDC/VBUS probe is a supported narrower firmware subset; it does
not execute the same full host-tool/ROM/network E2E. Its transport audit is
`build/firstarticle-output270-cap15-digital-preflight-20260930/supported-functional-transport-audit.json`.

The terminal selected15 endpoint study fails **14/6,144 cases: ten CS and
four SCK**. The true 3 MHz eight-pulse study fails **four SCK cases**.
The separate Main 68-ohm source trial fails **76/192 cases** and is rejected.
Its separate terminal audit verifies two M1 maps with 26 failures each and
a diagnostic six-WiFi profile with 24 failures. All 192 raw waveform hashes
match; rechecking 512 TI receiver waveforms preserves the worst 14.130 ns
falling transition against the unchanged 12 ns limit. This is SCK-only
one-pair coverage, not the full shared catalogue or the sampler2560 proof.
The newer 270-ohm SCK source / 15-ohm output hypothesis passes its 128-case
screen, but has no final physical/source freeze or full qualification.
The separate CS output270/cap-branch15 hypothesis now passes **1,280 scoped
cases: 128 MAX, 256 min/typ and 896 independent-body complement cases**.
The SCK output270/cap-branch15 endpoint/eight-pulse screens pass 384 cases
and its independent-body complement now passes 896 cases. CS and SCK each
have 1,280 scoped passing cases, 2,560 total; this does not establish all
independent PVT/population/body/ground/timing combinations. All these
value hypotheses remain unadopted hardware. Main47's 48-case focused screen
is separately reviewed to preserve the original fast/slow counterexamples;
it cannot substitute for a full affected SCK qualification.
The full 5,760-case shared-bus run remains owned by the root agent; its
partial upstream WiFi U5.A failures are real counterexamples, not a terminal
failure count. No selected15 build, model bridge or limited passing screen
overrides those electrical failures.
Sources are `verification.md`, current `test/catalogue.toml`, `Makefile`,
checkers, `fab-waivers.md`, first-article plan and bound logs.
**Do not use historical readiness greens.** `fab-readiness.md` is generated
from 2026-09-28 results and has obsolete order wording. `build/test/results.json`
currently contains only one focused MB-051 FAIL from 2026-09-29, not a full
catalogue run. The old 226/36/17 snapshot is historical. Every current
non-hardware catalogue entry has a command; that does not mean it passes.
Fresh full `make verify JOBS=2` remains required after the final physical
source freeze, actual canonical adoption and receipt/top/SI re-pinning.

David's latest target is a **working first article at the current M1 load**.
The separate [first-article scope audit](first-article-m1-scope-audit-20260930.md)
distinguishes an explicitly conditional four-card bring-up profile from
ordinary all-green manufacturing release. Six-WiFi fixture failures remain
red general-capacity evidence; historical v7 mixed passes lack the actual
physical-branch bridge and cannot certify current M1. SI owner job4449
completed the genuine actual33/220/5.6 baseline: all128 four-map cases pass,
six of64 sole-WiFi cases fail. A separate local WiFi R64=270 focused44
hypothesis is running, preserving Main33 and5.6pF. Supported sole-card
boot/debug behavior stays relevant; no Main reroute follows from this result.
Physical `kind=hw` sample measurements remain after-delivery obligations.

## Remaining gate matrix

| Contract / actual gate | Current evidence and classification | Concrete remaining action |
| --- | --- | --- |
| 4.1–4.3, 4.9: actual eight-board physical packages | All eight selected15 normal DEV builders PASS with fresh qty2 receipts. Seven pads/copper/raw fills are exact to prior qualified normal packages; WiFi exact to true15 frozen candidate. Fresh current WiFi full fab geometry PASS, ending only at missing human CPL review; Main/eInk full geometry proof remains scoped via exact bridge. **Native packages complete; affected final fab/human scope remains open.** | Storage tab repair is complete. Finish actual WiFi/Main electrical remedies, freeze final source/model and rebuild genuine affected packages; run final full actual fab checks. No receipt rehash or inherited whole manufacturing pass. |
| Eight-board assembly/order scope | All eight actual evidence files say **2 boards**. Cards use ENIG fingers, 30° bevel, one card per JLC panel, ±0.10 mm outline, do-not-trim note; multilayer orders require their named controlled-impedance stackup. **Options prepared; supplier confirmation open.** | Confirm exact final JLC production files/options, panel tabs and key/finger preservation before production. Run `tools/jlc_production_diff.py`; no upload/order was performed. |
| 4.8 BOM/stock | Pipeline cached BOM/rotation checks pass. Every bound scope says `development-offline`, live stock skipped and manufacturing release false. **Live supplier/environment blocker.** | Fresh online `boardcheck BOARD bom` for all eight final builds **and mandatory BRD-006** `python3 tools/aggregate_stock.py --board-root FINAL_ROOT`; stock must be ≥2× **SUM fitted demand across all eight types** (≥4× each per-board fitted count, summed for shared parts). Reserve agreed scarce/EOL parts; real stock must not be inferred from cached historical numbers. |
| 4.9 CPL and ordering signoff | Current all8 selected15 unsigned pack:127 focus rows,49 automatic checks,3 prior resolutions,75 human reviews,0 known mismatch. Demand1262 mounted parts/118 SKUs across sixteen assembled boards; no live stock/reservation guarantee. No final signed cpl-review.json or ordering signature. **Human gate open.** | Review final physical freeze including Bottom parts, polarity/rotation and supplier CAD; produce genuine hash-bound decisions, production-options confirmation and David ordering signoff. Refresh any newly changed electrical/source packages and their exact demand/review packs; never write human signatures autonomously. |
| MB-005 main full-current copper | Actual isolated round2 generated MB-005 PASS:26.962mΩ loop,19.519°C rise,9.801% convergence; latest actual Main copper/pads/all raw fills exactly identical and power model sources exact. **Qualified numerical physics bridged, original report/receipt unchanged.** | Bind/replay final actual geometry and model identity after physical freeze; retain all observed grids and unchanged20°C/10% limits. No sustained-fault waiver. |
| MB-051 dual-rail reset/current M1 | Fresh isolated round2 generated strict PASS:3V3 margins16.290/10.916mV,1V2 7.962/7.178mV, convergence7.497%; latest staged actual Main physics/models exact. **Current qualified physics bridge, not edited old receipt.** | Rerun if relevant supply geometry/model changes; proof replay needs exact scope/hash identity. Hypothetical fully loaded slots are advisory; currentM1 remains target. |
| MB-006 / CC-005 / CC-006 iCE40 supply/thermal | CPU power scenario passes but full coverage is red; actual CPU thermal F2 lacks worst-corner operating core current. A fresh actual round3 main package-thermal command also fails only F2; HT7533 standby load/heat passes. MB-005 copper success does not prove MB-006. CPU capacitor/ESR/contact/feed bounds also remain missing. **Unwaived pre-order analysis gate; named FA measurements are post-delivery and cannot yet clear it.** | Worst-corner actual-design Power Calculator report or existing MB-111/CC-104 current/rail/temperature measurements. Preserve approved 40 mA scenario and process margin as assumptions, not guaranteed silicon maxima. No speculative reroute from unknown current. |
| GC-005 / IC-005 / SC-005 / EC-005 / YC-005 RP2040 core droop | `rp2040_vreg.py` proves DC voltage/clock only and explicitly lacks load-step response/impedance/max workload current. GPU/storage/e-ink/system power gates remain red; IO integrated switch/C25 subchain passes; its whole power gate retains the same genuine RP transient/droop gap. **Unwaived pre-order transient/model-coverage gate. The named physical FA checks themselves are post-delivery.** | Existing GC-104/IC-103/SC-102/EC-102/YC-102 biased rails and workload measurements; do not count nominal capacitors or DC-only script as transient proof. |
| IO switch / C25 | Genuine isolated round2 normal IO pipeline PASS with same-pad4.7µF C23733 and exact qualified copper/fills. Its fresh receipt-bound integrated boost/switch/C25 subchain PASS at the1.6µF operating target: U5 IN6.273V<7V, boost OUT5.431V<6V; approved numerical retries remain explicit and true-current stress retained. **IC-005 as a whole still FAILS the RP2040 transient/droop coverage gap; canonical adoption, guaranteed Ceff and physical response/loop bounds remain open.** | Adopt candidate once with final source freeze; fresh IO pipeline/binder. IC-104 must measure Ceff≥1.6µF and U5 IN<7V/boost OUT<6V with uncertainty. No vendor-guaranteed Ceff/response/20nH claim. Whole IC-005 stays red on RP droop. |
| GC-006 GPU GPIO/thermal | Actual R5 junction83.7°C<85 passes; R4 lacks TMDS dynamic switching current within remaining8.5mA sink headroom. **Unwaived current bound.** | Genuine driver/pad/load-capacitance switching-current bound or physical measurement. Accepted252MHz/1.20V operation/burn-in does not waive GPIO current limits. |
| IC/SC/EC/YC-006 RP package thermal | Actual round3 direct RP package checks pass their declared ADC/50mA-rated assumptions. **Scoped conditional results.** | Preserve explicit accepted assumptions and per-board dynamic current headroom; all12 current card/pitch disabled-layer audits prove only terminal-free single-barrel dead leaves, so their Schur contribution is zero; current card DC results remain valid. A general enabled-layer guard is isolated review only; it is not necessary or authorized for this freeze. |
| WC-005 / WC-010 Wi-Fi | Actual power F5/F6/F7/F8 red: capacitor ESR, pad/contact returns, biased Ceff, max load. Thermal T4r/T4c/T4p red: return/thermal coupling and ESP current/power. **Unwaived pre-order power/thermal analysis gates; WC-102–106 are post-delivery checks, not an accepted pre-order deferral.** | Existing WC-102–106 measurements or guaranteed bounds; retain actual copper extraction. The actual ground evidence/disabled-layer audit is preserved; no duplicate solve launched here. |
| 4.6 shared SPI, MISO and other analog SI | Actual RP/WiFi filters, TI buffers and Main4.7k low-idle shunt are real native/source-qualified candidates. **Final electrical output/stress/timing/PVT/current/ground/package coverage remains open. New270/cap15 output has2560 scoped passing cases; historical selected15 failures are preserved.** | SI owner must bind exact final actual Main plus repaired storage/WiFi source/physical exports, emitted-deck/population equivalence, independent corners and real sample/turnaround budgets. Preserve1861 legal populations: GPU OR eInk, never together, +IO/WiFi/storage in any slots and missing subsets. No slot restriction or output-stress waiver; diagnostics/limited-case screens are not full final qualification. |
| 3.1 actual digital routes/monitor | Current coherent working-M1 all8 actual strict top PASS:992 paths/535 runtime nets, no unmodeled nets,44 unchanged accepted boundaries plus six modeled reset nets. Eight permanent source/native SPI groups and26 genuine candidate export/value/SKU/native-open counterexamples PASS. Functional/DC filter/buffer/idle model is separate from analogue SI. Earlier genuine reset/CPUdata/IRQ/timer native faults remain scoped evidence. **Current strict functional/topology proof PASS; analogue gates remain separate.** | Rebuild/recheck affected final source/copper/native scope after incoming repairs. No generic net aliases/new waiver; missing cap geometry fails strict completeness without fabricating a DC logic failure. Whole network E2E still required. |
| 2.6 / 3.1–3.3 whole network/native E2E | **Current authorized root transport works.143 actual functional checks pass**:65 normal/reviewed subset checks plus39 GPU and39 eInk full-target checks, including real USB programming/readback, storage SAVE/LOAD, HTTP/ESP, keyboard/display, then System removal. Programming-port source/copper/native counterexamples pass separately. Original restricted-environment failures remain preserved. FPGA configuration now has combined genuine intact/source/copper/native evidence for all9 mutants; both ineffective old mutations and their failed attempts remain preserved. | Bind `build/firstarticle-integrated-functional-20260930/terminal-functional-binding.json`; finish required individual native gates and final production source/physical binding. These functional results do not waive analogue/current/thermal or stock/release gates. |
| 4.7 mechanical/STEP | Storage R65 relocation completed native0/0 and source guard. Latest actual all8 direct mechanical execution on output-damping round2 PASS MECH001–008; current15 geometry is exactly bridged. No fresh15 STEP/MECH execution claimed. Old v138 tab failure remains historical, repaired evidence. | Final physical/source freeze must receive actual full mechanical execution with current validated roots/STEP sidecars; preserve current repaired-storage ground/192-case bounded SI proof and exact geometry linkage. Preserve exactPCB/root/exporter/config/model cache binding; no waiver or forged STEP sidecar. |
| 1.x/2.x/3.4 and final aggregate | Historical HDL/formal/firmware/pin/timing results do not constitute a current full report. Catalogue explicitly runs every implemented non-hardware row; `kind=hw` checks are post-delivery. **Fresh aggregate pending.** | After final freeze: adopt legitimate generated packages into canonical paths, validate all eight hashes/quantities, re-pin SI receipts and strict top, run full `make verify JOBS=2`, inspect every row and regenerate readiness. Never manually turn accepted electrical failures green. |

## Power and thermal phase classification

The current declared-M1 POW-006 command passes every actual check. B10 uses
the accepted0.80A IO branch budget with no extra10% margin; B8/B10b retain
10% fuse margins. The independently qualified Main fault-copper MB-005 proof
retains its20°C limit at3.288101537A. These passing scopes are separate from
missing iCE40, RP regulator and WiFi operating/thermal guarantees.

`verification.md` rule and rows4.4/4.5 require the implemented pre-order
analysis gates. `tools/verification_binding.py:release_problems` requires every
non-`hw` catalogue entry to pass. `tools/fabready.py` excludes only the physical
`kind=hw` entries. Therefore a post-delivery measurement being listed in the
first-article plan does not itself waive its corresponding red analysis row.
`hw/tools/boardcheck.py` explicitly identifies those missing models as contract
gaps, not accepted waivers. The plan's **Turning gates green** section says
analysis checks may consume FA records only when those records exist; none
has been fabricated or supplied.

- **Pre-order, no matching waiver:** MB-006/CC-006 iCE40 maximum operating
  current; CC-005 effective capacitance/feed/current coverage; GC/IC/SC/EC/YC-005
  unmodeled RP core transients; GC-006 TMDS dynamic-current headroom; POW-003 /
  WC-005 capacitor/load/contact guarantees and WC-010 local thermal coupling.
  New WiFi TI-stage operating-current, package/rail/ground conditions also
  remain required inputs to the unwaived analog qualification. Typical Cpd,
  test-point ΔICC or a passing current-allocation calculation does not close them.
- **Post-delivery, not itself a pre-order test:** MB-108–114, CC-103–105,
  GC-102/104, IC-103/104, SC/EC/YC-102 and WC-103–106 physical measurements.
  Their limits and sample counts remain unchanged. They can provide missing
  model inputs later, but their empty planned records are not a pre-order pass.
- **Already accepted first-article scopes:** exact GPU252MHz/1.20V with per-unit
  GC-102 burn-in; specified RP ADC≤2mA/ratedIO thermal assumptions; named CPU
  overshoot and IO/System USB failures; notch/bevel and RP exposed-pad conditions.
  Preserve each exception's exact boundary. GPU overclock acceptance does not
  waive unmodeled regulator droop, GPIO current or new TI-stage current.

No additional pre-order deferral is established by the accepted four FA
measurement limits in `first-article-plan.md` or by historical proposed options.
The old question about whether external measurements gate a first batch has no
recorded blanket answer in `fab-waivers.md`; it is not permission to turn these
other failed analyses green. Detailed immutable classification and genuine
current-M1 calculation: `build/power-gap-audit-20260930/`.

## Existing accepted first article conditions

Authoritative decisions are in `fab-waivers.md` and `m1-live-status.md`;
these are carried approvals, not new questions:

- Standard notch/fingers: exactly four matching notch fingers0.20mm; others0.30mm, first-article gap≥0.10mm and fit/continuity on two of each card.
- CPU-bus68/56Ω residual overshoot, IO/system USB impedance/balance: retained failed electrical checks plus physical receiving-pin/USB tests before a larger run.
- One RP2040 U1.57 gutter via open on the five named RP cards: first-article solder inspection. Other via defects were repaired, not waived.
- GPU252MHz/1.20V exact operating point plus per-unit1h DVI near40°C; ADC≤2mA/rated IO-headroom assumptions are conditional and do not prove missing dynamic-current terms.
- Fixed50 explicitly named co-sim boundary nets retain corresponding FA reset/program/ESP/HPD/DDC obligations; new monitor nets are modeled, not waived.
- Documented IO numerical retry may reduce simulated current only where stated; full stress cases retain the true limit. No physical current-limit waiver.
-30° bevel, hand-plugged antenna lead, no live hot-plug/missing-CPU case, and exact1.5A-source5% budget exception retain their existing limited scope.

The strict ordinary verification contract says all rows green. The explicit
first-article decisions above authorize their named exceptions while keeping
the underlying electrical tests red. They do not authorize other omissions,
unknown RP droop, Wi-Fi bounds, slot MISO stress or excessive sustained-fault
heat. A report must distinguish that approved scope from ordinary all-green
manufacturing readiness.

## Proof index

Current package proof index:

- `build/spi-development-r70-15-20260930/development-package-summary.json`: eight real quantity-two receipts and exact generated physical bridges.
- `build/spi-development-working-m1-firstarticle-20260930/qualification.json`: current fresh all8 source/native functional/DC topology proof; prior selected15 strict report remains historical.
- `build/manufacturing-prep-r70-15-20260930/review-index.json`: current unsigned review and aggregate demand,1262 mounted parts/118 SKUs.
- `build/wifi-r70-15-full-fab-20260930/qualification.json`: current WiFi geometry PASS, only missing human review.
- `build/wifi-r70-15-ground-binding-20260930/qualification.json`: exact actual current geometry linkage, with declared current/contact/reference limits retained.
- `build/scratch-si/wifi-selected15-actual-numerical-bridge6-v1/terminal-proof-index.json`: twelve genuine actual15 default/refined solves on six prespecified cases; four passes and both CS/SCK counterexamples retained. All eight receipts and frozen source inputs validate unchanged.
- `build/main-source68-terminal-audit-20260930/terminal-proof-index.json`: exact 192-case source/raw/qualified-result audit and independent frozen-classifier recheck; rejected 68-ohm value-only SCK trial, 76 failures. Original generic summary wording is preserved and corrected only in the audit scope.
- `build/full-shared-output270-cap15-independent-audit-20260930/terminal-proof-index.json`: independent terminal audit of root's 5,760 exact emitted-model comparisons for typed WiFi R63/R65=270 and R69/R70=15, using frozen `40821bd4…` source rather than current `043a9171…` helper. All indices/case names, original prepared manifests, exact production AST prefix and row hash validate. This is model dependency evidence, not a physical or universal electrical pass; a Main source/input change invalidates affected original SCK reuse.
- `build/upstream-source47-selection-review-20260930/focused48-review.json`: reviewed 24 exact fast/slow source points at two MainR36 tolerance endpoints; only R36 changes, WiFi220/5.6 input remains fitted. No numerical solver run by reviewer.
- `build/wifi-output270-cap15-firstarticle-prep-20260930/qualified-generator-handoff.json`: isolated actual value/SKU-only candidate, R63/R65=270/C25099 and R69/R70=15/C25083; all current normal copper/pads/rawfills exact. Genuine new schematic/ERC/pre-route829-item guard and26 true-export/native-open counterexamples PASS. Main33/WiFi220/5.6 preserved; coherent accepted-M1 constructor and all8 genuine normal builds now PASS at `build/spi-development-working-m1-firstarticle-20260930/`. All8 new qty2 DEV receipts validate, exact physical/native bridge passes. No canonical adoption or manufacturing approval.

The following index is historical, with only explicitly matched scopes carried forward.

The hash-bound audit index is
`build/release-gate-audit-20260930/proof-index.json`, outside all board
receipt directories. It records current contract/checker/catalogue hashes,
all eight round3 receipt/PCB/order/scope hashes and actual summarized log
hashes. Principal actual evidence (round3 means the directory named above):

- `round3/development-package-summary.json`: all eight DEV receipts/options/geometry.
- `round3/card-power-thermal-results.json` and `round3/logs/*-{power,thermal}.log`: exact current failures and conditional passes.
- `round3/digital/{cpu-results,development-digital-summary}.json`: genuine native passes/environment blockers.
- `round3/main-thermal-results.json`, `main-qualified-geometry-identity.json`, and `/tmp/cupc8-main-thermal-audit-20260930/main-final-round3-{thermal,reset,fab}.log`: completed main proof.
- `build/io-c25-upgrade-20260930/qualification.json`: isolated necessary same-pad repair, not a manufacturing receipt.

Actual new missing-gate logs: `build/release-gate-audit-20260930/main-package-thermal.log`
(MB-006 fails only F2), `mechanical-root-counterexamples.log` (4 tests pass),
and `mechanical-round3.log` (actual fresh eight-STEP/FreeCAD run, all eight mechanical checks PASS). Results, geometry, report and overview are preserved alongside it.

The subsequent STEP cache repair has independent counterexamples in
`mechanical-step-cache-counterexamples.log`. It was adopted only after this
terminal physical proof was preserved; no old sidecar ownership was invented.
It was not followed by a redundant full FreeCAD run. Final physical freeze
requires the genuine updated eight-board mechanical proof.

`eight-board-parts-demand.json` in the audit directory binds all eight actual
receipt/BOM hashes and aggregates the two-board order:111 distinct LCSC
parts,1,152 fitted units for16 assembled boards, and2× combined stock
requirements. It is not a stock quote/reservation; regenerate after final
SPI/C25 changes. Checking each BOM independently must not double-count the
same shared stock across eight planned orders.

Read-only current canonical-path validation also finds **all eight `build/hw`
receipts invalid** (recorded reasons in `canonical-path-validation.json` in
the audit directory). Passing explicit round3 commands does not make default
canonical catalogue commands current. No canonical artifacts were changed.

The aggregate stock release gate is now an explicit catalogue row BRD-006,
so `make verify` cannot omit combined demand. BRD-007 checks synthetic
shortages that pass every separate per-board stock check. Its test pass is
not actual stock evidence. `aggregate-stock-live.json` and the corresponding
log record the actual round3 live attempt: all eight receipts validate,
111 shared parts/1,152 fitted units, but DNS fails before any supplier answer.
This remains a release blocker, never a historical-stock pass.

Fresh candidate-source IO proof (not canonical manufacturing release):
`build/spi-development-isolated-round2-20260930/io-power-subchain-qualification.json`
binds the actual IO receipt/PCB/netlist/BOM, source/model hashes, cached-primary model
identity and integrated log. The whole power command exits1 only at the explicit
RP2040 transient/droop coverage gap; switch/boost success does not close that gap.

## Latest coherent candidate proof index

The older proof index above names historical round3 artifacts. The latest
actual source root is
`build/spi-development-isolated-round3-v138-20260930/source-tree/`; its sibling
reports bind the real normal outputs without editing original receipts:

- `development-package-summary.json`: all eight ordinary builders PASS,
  qty2, development-offline/live-stock skipped/manufacturing false.
- `qualified-physical-identity.json`: exact seven-board identity to isolated
  round2 plus WiFi frozenv138, pads/copper/all raw fill outer contours+holes.
- `prior-physics-identity-bridge.json`: preserved actual Main copper/reset,
  IO switch/C25, FPGA package-current red gate, eInk ground and Main/eInk
  fab reports; power/timing sources exact. Changed `slowbus_si.py` is
  explicitly excluded from inherited qualification.
- `strict-top-final-qualification.json` and `strict-top-final.json`: actual
  final v138 routed/coverage proof,44 accepted boundary waivers, six modeled
  reset nets and true fitted low-idle/RC/TI networks. Original failed
  generator attempts are preserved in `logs/strict-top*.log`.
- `logs/slot-spi-regressions-final.log`: six actual source/native mutation
  groups PASS; `strict-top-source-amendment-final.json` proves these cosim
  updates leave all eight board receipt inputs unchanged.
- `mechanical-all8-qualification.json`, `logs/mechanical-all8.log` and
  `source-tree/build/mech/{results.json,report.txt}`: **MECH-001 FAIL storage
  R65**, seven other mechanical checks PASS, no signed exception.

Fresh actual WiFi fullgeometry/unsigned-review report is
`build/wifi-v138-full-fab-20260930/qualification.json`; its native production
physics exactly matches frozenv138 via
`build/wifi-spi-local-layout-20260930/generated-v138-physical-comparison.json`.
Final ground/DC scope is in
`build/wifi-final-ground-v138-20260930/qualification-index.json`; remote
near-zero transfer convergence, package/contact/current and excessL bounds
remain explicit limitations, not newly guaranteed quantities.

The source adoption plan is
`build/final-source-integration-plan-20260930/{README.md,plan.json}`. It pins
32 proposed target files/shared baselines and64 genuine catalogue commands,
explicitly **ready_to_adopt=false** pending storage/WiFi repair freezes.
No shared canonical hardware adoption, fake receipt repinning, ordering or
human signature has occurred. Supplier-cache changes require genuine
subsequent source-bound builds; full `make verify` and authorized-environment
localhost/network/live-supplier gates remain open.

## Incoming storage R65 repair (separate preserved revision)

`build/spi-development-storage-r65-v4-20260930/source-tree/` stages only the
qualified storage wrapper/strong seed revision. The seven unchanged v138
normal packages are referenced read-only after exact new-source input and
artifact validation; their original receipts are untouched. The new storage
normal builder PASS qty2. Generated PCB
`dca645054b6013ae29ae5b6c503e4d1fa1b99b05e0ce60eafae88b48c05767f4`
exactly matches the frozen local repair's pads/copper/guards/all raw fills.

- `storage-package-fab-qualification.json`: genuine builder, full actual
  fab geometry PASS, overall fab FAIL solely missing human CPL review;
  current unsigned11-part pack has5 human decisions pending and0 mismatches.
- `strict-top.json`: repaired-storage actual all8 route/coverage PASS,
  no unmodeled nets and44 unchanged accepted boundary waivers.
- Actual all8 mechanical job47437 is terminal exit0: **MECH001–008 PASS**,
  including the repaired storage tab clearance. All8 receipts/qty2 and STEP
  PCB identities independently validate in `mechanical-all8-qualification.json`.
- Fresh generated-storage ground qualification PASS:16 contact/R61 self/transfer
  last pairs ≤7.147%, four cap self pairs ≤9.754%, transfer pairs ≤1.662%;
  C63 self9.9273mΩ to actual U4.3. Disabled-layer audits have no cross-barrel
  ghost components. This proves the declared numerical scope, without a
  package/contact/current/excess-inductance guarantee.
  `build/storage-r65-generated-ground-20260930/qualification.json` binds it.
  Changed storage CS/OE bounded screen is terminal PASS192/192 across six slots
  (`build/scratch-si/storage-actual-mechanical-oe-relocation-cs192-v1/terminal-summary.json`).
  Exact generated/candidate physical identity binds the scope; full mixed SPI
  catalogue/timing qualification remains open. This screen is not a final SPI pass.
- `build/final-source-integration-plan-20260930/plan-storage-r65-v4.json`
  pins the new source/seed without overwriting the earlier plan. Canonical
  adoption remains blocked by affected checks and eventual WiFi repair.

## C7833 exact supplier evidence gap

`build/supplier-c7833-audit-20260930/{README.md,qualification.json}` inventories
all8 actual TI buffers (four RP buffers and WiFi U3–U6). Manufacturer numeric
pin names and native/source nets match TI1OE/2A/3GND/4Y/5VCC. The recorded
0° footprint correction comes from **C151890**, not replacement C7833.
All Top pads match that historical DCK geometry; Bottom placements are
explicitly inventoried, without claiming supplier rotation certification.

No genuine C7833 supplier CAD was found. A historical local symbol is an
explicit manual clone and is rejected as supplier provenance. Official
supplier identity pages provide no placement-origin proof; supported
EasyEDA component/SVG endpoints are inaccessible and the genuine ordinary
importer fails DNS. No supplier cache, stock result or human signature was
fabricated; all8 frozen inputs/receipts remain unchanged. Authentic supplier
CAD and actual Top/Bottom CPL audit remain required in a permitted network
environment, with new genuine builds after any supplier-record source edits.

## Incoming real WiFi output damping and host timing

The final source/native candidate in
`build/wifi-local-output-damping-20260930/frozen-handoff.json` adds actual
10Ω R69/R70 in the private C61/C64 branches. Source/local-route/DRC proof is
complete; final actual analogue qualification remains required. The fresh
ordinary WiFi package in
`build/spi-development-output-damping-round2-20260930/source-tree/build/hw/wifi/`
passes qty2 DEV/offline, with exact copper/pad guards/all raw fill contours and
holes matching frozen `fa477e83…`. The new receipt is `3603389f…`; source-bound
primary C25077 metadata is stored as identity JSON, without claiming a
manufacturer pin table, supplier CAD or live stock. All eight genuinely fresh
normal builders are terminal PASS in the same source tree, with independently
validated qty2 receipts and exact prior/candidate copper/pad/raw-fill bridges.
`development-package-summary.json` records the proof. No shared/canonical
adoption has occurred. Actual strict top31565 and the seven permanent
source/native regression groups54714 are terminal PASS:992 paths,535 runtime
nets, no unmodeled nets,44 unchanged boundaries and low MISO idle. All8 receipts
remain valid. Affected all8 mechanical71505 is terminal PASS MECH001–008; receipt/STEP
identities independently validate in `mechanical-all8-qualification.json`.
The actual WiFi differential96 screen fails4/96 SCK cases (4.3mV falling
reversals), while all48 CS cases pass. A value-only R70 damping repair and
genuine affected build/analogue requalification remain required; current
proofs are preserved and no final adoption is approved.

`build/wifi-cap-branch-cosim-prep-20260930/qualification.json` validates the real
emitted capacitor-branch topology and16 source/native counterexamples. Both
resistor launch pins, private cap net and cap GND are strict requirements;
shunt opens invalidate strict coverage while preserving the separately scoped
functional DC signal. The helper and permanent test are staged candidates.

The independently rebuilt actual CPU/chipset RTL trace in
`build/host-spi-real-timing-20260930/qualification.json` uses the genuine
unmodified ROM/kernel/BASIC image. Twelve observed boot frames have3MHz eight
clock bytes, minimum CS lead12.250µs and final-sampling-rise hold16.083µs.
Conservative source bounds for the held ROM/kernel path are333.333ns lead
and333.333ns hold. Automatic RTL selection has only166.667ns lead and is
recorded separately; no boot use or strictly-greater-than-half-cycle ESP
compliance is inferred for that mode. Receiver-local analogue skew must still
be subtracted, and no unpublished ESP data timing bound is invented.

### Full-verification report contract repair (adopted tooling)

The exact patch in
`build/final-verify-gate-prep-20260930/adoption.json` was adopted after baseline
and proof-hash validation. It fixes two concrete
release-tool bugs: `make verify` previously ignored the readiness command's
failure, and direct readiness trusted stale result IDs and board timestamps.
The candidate requires the complete current non-hardware catalogue, unique
catalogue/result IDs, every required implemented command passing, matching
actual log hashes, unchanged source content before/after the run, and all eight
current quantity-two board receipts with genuine live-stock scope. Required
failures outside the displayed verification rows also block readiness.

Thirteen synthetic receipt/report regressions and an actual tiny runner to
readiness subprocess integration pass. These tests exercise the real receipt
validator; they certify the tooling behavior and do not certify board
manufacturing readiness. Explicit `verify-development` remains available and
reports no manufacturing readiness. Declared generated binaries/ROM outputs
are excluded from the source snapshot; source content remains bound despite
restored timestamps. The shared tooling and BRD-008 catalogue regression are adopted; the actual
post-adoption 13-test run also passes. Board wrappers, native packages and
receipts remain untouched. The minimal follow-on is also adopted and binds the stable ordering
checklist, parts policy and first-article acceptance conditions. Its
14 regressions pass, and the targeted post-adoption policy test passes;
`build/final-verify-order-policy-addon-20260930/adoption.json` records the
actual baseline-validated adoption.

The proposed order checklist also carries the existing accepted one-card
**panel by JLC** decision. It requires review of the supplier's production
preview rather than an invented customer-panel generator. Current assembled
demand remains two of each of all eight designs; the older three-main-board
spare suggestion is identified as an unadopted proposal.

### Shared SPI catalogue value dependency proof

`build/scratch-si/full-shared-spi-emitted-output-equivalence-v1/qualification.json`
records a terminal PASS for all 5,760 current catalogue cases: actual production
simulation code through the emitted deck produces identical lines, probes,
nets, notes and source rails under typed WiFi R70=22 and R65=100/R70=22
value-only changes. Actual PCB/net/graph inputs are held unchanged and no
solver is duplicated. This is a model dependency proof. Any later physical
candidate still requires genuine source/native/field/rail equivalence before
results can be rebound; shared ground/current independence is not inferred.
R70=22 remains a rejected electrical trial. The subsequently proposed 15-ohm
trial is not yet a qualified repair or release source freeze.

### Actual selected-15-ohm development packages

All eight fresh normal builders in
`build/spi-development-r70-15-20260930/source-tree` pass quantity-two
DEVELOPMENT-OFFLINE. The new C25083 primary identity changes all eight board
input maps; WiFi also changes its genuine source wrapper and strong design
seed. Every fresh receipt validates, with seven physical outputs exact to the
prior qualified generated set and WiFi copper, pads, board guards and raw
filled contours/holes exact to the genuine 15-ohm frozen candidate. Fitted
values and supplier IDs match; the removed scratch-only `ResearchScope`
annotations are recorded explicitly. No supplier CAD or live-stock pass is
claimed.

The fresh actual strict top passes 992 paths and 535 runtime nets with zero
unmodeled nets, 44 unchanged accepted boundaries and low MISO idle. Seven
permanent regression groups pass, plus 18 actual emitted-source/value/SKU and
native-open counterexamples. These are functional/DC and topology proofs;
analogue input/output quality and timing remain separate. No new mechanical
run is claimed: the prior actual mechanical result is linked only through the
explicit exact physical geometry bridge.

This is a bounded candidate, not a final electrical freeze. The full shared
catalogue has exposed genuine upstream WiFi U5.A SCK failures independent of
R70, and the true-3-MHz pulse study has exposed further 15-ohm output
counterexamples. The old 10-ohm and rejected 22-ohm studies remain immutable.
The actual production emitted-model bridge from old 10-ohm source with 1.5
scale to new 15-ohm source with unity scale passes all 6,144 declared endpoint
cases. Raw deck strings differ in native node/element order in every case.
`build/scratch-si/wifi-selected15-actual-deck-bijection6144-v1/terminal-proof-index.json`
proves exact physical-coordinate/pad/edge/crosssection correspondence and all
actual emitted RLC coefficients/connectivity under an anchored node bijection,
plus exact external nonlinear/source/rail/probe/reference expressions after
that mapping. No coefficient tolerance is used. Four checker counterexamples
pass. A separate actual-native numerical check now covers six prespecified
original indices: 0, 2574, 2575, 3072, 5646 and 5647. Twelve solves use the
default timestep/section length and half of each, preserving the unchanged
30 mV peak / 50 ps arrival convergence criteria. All four passing cases and
both genuine CS/SCK failures retain their verdicts. Old10/scaled versus
actual15/unscaled reported metric deltas are zero; maximum refinement arrival
change is 7.5 ps. Raw waveform comparisons retain ordered columns, including
duplicate probe labels; they do not introduce an acceptance threshold. This
is selected-case numerical evidence, not a duplicate full study or a waiver
of the real pulse/input failures.

The subsequently adopted root affine solver is not copied into this package
source tree. `affine-solver-input-impact.json` proves that `copper_mesh.py` is
explicitly bound by all eight board receipts; copying the new solver into the
same tree would stale every receipt. Preserve these packages and use a new
source stage with genuine rebuilds when the final physical/model freeze is
ready.

## Latest fresh functional execution

`build/spi-development-working-m1-firstarticle-20260930/fresh-functional-terminal-proof-index.json`
binds unchanged stage verification sources, all eight current receipts/inputmaps,
fresh native/RP/ESP/FPGA assets and an authentic512KiB ROM/kernel/BASIC image.
Fifty actual E2E checks pass: storage24 with the isolated file-FD FAT capture
fix, normal eInk-console14, normal HDMI-graphics6, normal eInk-graphics6.
The existing direct CDC/VBUS source/copper/native tests also pass.
These are their existing fixture populations, not a complete simultaneous
Main+system+CPU+IO+WiFi+storage+display acceptance run.
The restricted agent executor retried normal USB programming and WiFi HTTP
at19:18UTC and still received localhost `listen EPERM`. The root executor
independently verified Full access socket/DNS success at19:16:50UTC and owns
fresh normal functional retries; their outcomes are recorded separately. The original
storage captured-pipe failure is preserved alongside its corrected harness
version/hash; no frozen board source or receipt was edited.

The exact reviewed FAT logging helper is now adopted canonically in
`test/emu/test_e2e.mjs`; `test/emu/test_e2e_subprocess_capture.mjs` passes on
real FAT binary bytes, JSON output and a real missing-file failure.
`build/firstarticle-e2e-filefd-preparation-20260930/adoption-verification.json`
binds adopted/candidate hashes, original failures and unchanged frozen-stage
receipts. All eight root hardware input maps are unchanged by these test-only
source edits. Verification software source binding must include the adopted
files; no previous full software report is rehashed.

The root Full access executor subsequently passed unchanged normal E2E002
(8 checks: actual system USB ROM programming/reset/BASIC) and E2E003
(7 checks: actual ESP WiFi HTTP response and HDMI). Their log hashes and
fixture scopes are bound in
`build/spi-development-working-m1-firstarticle-20260930/root-fullaccess-functional-result-binding.json`.
The executed subset total is now65 passing checks; original restricted
executor failures remain historical evidence. These15 additional checks
resolve those normal fixture execution blocks, not the entire required
catalogue or simultaneous first-article population.

`build/firstarticle-integrated-functional-20260930/preparation.json` records
a separate prepared four-map scenario with all intended cards/System fitted,
real ROM programming/full-chip host readback, SD SAVE/LOAD, WiFi HTTP and
display output, then an actual cold boot with System removed. Its wrapper
validates all8 current receipt/input/source/assets before and after execution.
Preparation is not a functional pass; actual per-profile results are needed.


## Fresh full-target functional and practical power audit

The coherent working-M1 stage now has **143 passing functional checks**:65 subset checks plus39 actual GPU full-target and39 actual eInk full-target checks. Each full-target fixture includes CPU/Main, System, IO, storage and WiFi, genuine full512KiB ROM readback, real SAVE/LOAD and HTTP traffic, then boots and repeats after System removal. The full FPGA configuration gate's CDONE counterexample initially failed because its old mutation removed a centre stub while another real track still contacted the pad. The reviewed mutation helper now removes same-net/same-layer endpoints inside actual pad copper; actual route proof clears only `chipsetCdoneSysctl` and restores `system:CHIPSET_CDONE`. The reviewed full-stroke mutation also closes the1µm-outside-pad CRESET contact; all9 actual native counterexamples now pass in combined runs, with prior6 physical mutants byte-identical and original failed attempts preserved.

Read-only practical power audit: `build/firstarticle-practical-power-audit-20260930/README.md` and hash-bound `audit-index.json`. Fresh Main/CPU package thermal checks fail only missing guaranteed operating core current F2; no new physical copper repair is established. Existing RP transient, GPU switching-current, WiFi ESR/Ceff/current/contact/heat bounds remain red. Functional success does not clear them, and post-delivery measurements are not fabricated pre-order evidence.


## Final acceptance audit against the confirmed stack

Current final all8 LIVE-STOCK packages, current complete fab/127 delegated placement reviews, all8 mechanical checks, aggregate and loose-antenna stock,143 actual functional checks, all9 FPGA copper/native counterexamples, strict final runtime graph and genuine delivery assets are indexed in `build/final-firstarticle-acceptance-audit-20260930/{acceptance-matrix.md,proof-index.json}`. The matrix distinguishes incomplete final MOSI/U6/MISO model attachments, ordinary signed-release/production-preview requirements, red unknown electrical bounds, and after-delivery limits/sample counts. It makes no ordinary all-green or order-authorization claim.
