# IO port-switch power gate binding

The unconditional IO power gap claiming that a TPS2553-1 transient model is
missing is stale. `io_port_switch.py` already runs five behavioral scenarios
and eight scenarios using TI's actual TPS61023 transient model. IC-005 names
that model and its regressions. The declared stress response and 20 nH loop
remain engineering scenarios, not guaranteed maximum silicon response or a
physically extracted loop inductance.

`io_switch_bind.py` now binds that existing scenario to a genuine completed
IO development receipt. It checks the actual fitted latch-off switch, ILIM
45.3k part and tolerance/TCR model parameters, EN/fault GPIOs and pull resistors,
local input and port capacitor values, all modeled net endpoint inventories,
actual PCB pad maps/package/BOM, and positive/return/control copper. It also
runs the existing full IO thermal part/pin/model binding. The supply launch
is exactly 13.85 mm from C24 to U5; the C25 local launch is 3.62 mm. These
are geometry diagnostics against the modeled source layout, **not** proof
that the loop inductance is ≤20 nH. Metadata records that distinction and
binds checker/model/PCB/receipt hashes without claiming manufacturing approval.

Sixteen focused source/model mutations pass, including wrong switch family,
ILIM, caps, controls, pull-up, unknown loads, disconnected return, and changed
behavioral current/inductance/capacitance. The actual round3 development
package passes the binding. The genuine existing nominal-capacitance transient suite passes: U5 IN
maximum 6.690 V against 7 V, and TPS61023 VOUT maximum 5.431 V against 6 V.
All four engineering-stress cases run at the true 647.4 mA maximum. Three
typical-response cases use the previously approved, explicitly logged
5 mA numerical current retries (642.4 or 637.4 mA); these are not guaranteed
full-current physical bounds. The eight original model regressions pass.

Evidence logs:

- `/tmp/cupc8-io-switch-binding-final-current.log`
- `/tmp/cupc8-io-switch-current-transients.log`

Integration into `boardcheck.POWER['io']` and replacement of the stale
switch-model gap with the genuine **RP2040 internal-regulator transient/droop**
gap await the coordinated shared-source freeze. The existing VREG script proves
DC operating point only; whole IC-005 remains red until its separate droop
requirement is qualified. That change requires
genuine fresh receipts; none are rehashed. RP2040 VREG transient checks remain
separate catalogue gates. The existing IC-104 physical port/load/short tests,
live stock and unsigned human placement review remain required.

## Effective-capacitance sensitivity remains open

C25 is C52923, Samsung CL05A105KA5NQNC, 1 µF ±10%, 25 V X5R 0402.
[Samsung's primary product page](https://product.samsungsem.com/mlcc/CL05A105KA5NQN.do)
confirms the identity and labels its characteristic information typical
design-reference data. No guaranteed operating minimum after DC bias,
temperature and aging has been established. Nominal capacitance is not that
minimum. The Samsung simulation link was inaccessible in this environment.

The actual 647.4 mA no-retry sweep at 1.0/0.8/0.6/0.4 µF converges in five
of eight cases at each capacitance, including all four stress cases. Its
maximum observed U5 IN peaks are 6.347/6.537/6.790/**7.141 V**, respectively.
Thus 0.4 µF has a genuine failure of the unchanged 7 V absolute limit.
The three unconverged typical-response cases prevent a claim that 0.6 µF
is a sufficient all-case minimum. Increasing Newton iterations, halving
the maximum timestep, tightening tolerance, using trapezoidal integration
and increasing numerical gmin have not closed those convergence failures.
The nominal model's 6.690 V peak has only 0.310 V margin.

Evidence: `build/io-switch-cap-sweep-20260930/cap-sweep.json`, with the
actual PCB/model hashes and per-case results; numerical probes are in its
`numerics/` and `numerics2/` directories. No board/capacitor change, added
waiver or manufactured measurement is inferred from this sensitivity audit.
The guaranteed C25 effective-capacitance/response/loop-inductance closure
remains separate from repairing the stale model-availability gate.

The existing approved numerical-current-retry sensitivity additionally runs
all eight cases to the full 1 ms endpoint at each capacitance. It retains
actual 647.4 mA for all stress cases and records the three typical-response
retries. Peaks at 0.9/0.8/0.7/0.6 µF are 6.801/6.922/7.081/7.267 V.
A separate first-100-µs-after-short diagnostic at the **true 647.4 mA**
confirms the fast-plug failure at 0.7 µF: **7.08056 V**. The same diagnostic
at 0.8 µF gives 6.92168 V. Shortening that diagnostic window does not
replace the mandatory full 1 ms model or resolve its remaining cable
convergence failure. Approximately 0.75 µF is therefore a necessary
capacitance under this scenario, not a proven sufficient all-corner bound.

Higher effective capacitance reduces the existing full-window retry-suite
peak to 6.515/6.273/6.104 V at 1.2/1.6/2.0 µF. This supports investigating
a small same-pad capacitor increase or parallel local capacitor, but does
not establish a guaranteed minimum for an unselected replacement. The
current C25 tolerance-only floor is 0.9 µF; adding a possible 15% X5R
temperature reduction leaves 0.765 µF before DC bias and aging. Actual
operating-capacitance evidence or physical repair is needed for a guaranteed
corner claim. IC-104 now explicitly requires U5 IN and boost OUT peak
waveforms against their unchanged absolute maxima. No record is signed.

Additional artifacts:
`build/io-switch-cap-sweep-20260930/approved-retry/results.json` and
`local-window/results.json`, both with per-case actual simulated currents
and explicit diagnostic scope. No live shared tool or board change was
made during this audit. The prepared isolated gate-availability repair
passes the current genuine IO package; adoption awaits the coordinated
SPI/shared-tool freeze and fresh actual pipelines.

Refining only the local fast-plug diagnostic at the true 647.444 mA gives
7.01493 V at 0.74 µF, 6.99885 V at 0.75 µF, and 6.98291 V at 0.76 µF.
The 0.75 µF case has only 1.15 mV margin and is unsuitable as a practical
minimum specification. These are explicit diagnostic results, not a
replacement for full-window, all-corner or physical effective-capacitance
qualification. Data: `local-threshold/results.json` under the sweep folder.

The corrected isolated tool patch therefore runs the genuine switch subchain
then fails on the retained RP2040 droop gap. The earlier isolated overall
`PASS io power` was only a gate-repair development trial and cannot be used
as current full power-coverage evidence.
