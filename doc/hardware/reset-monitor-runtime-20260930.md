# Fitted reset monitor native functional model

This closes functional electrical behavior of the fitted REF3425, two
OPA376 amplifiers used open loop with positive feedback, BAT54A common-anode
reset diode and six SN74LVC07A open-drain outputs. It does not claim manufacturing
release, cold-start timing qualification, guaranteed maximum analogue propagation,
or complete RP2040 peripheral response to RUN. The existing `card_control`
whole-chip reset model boundary and first-article obligations remain.

## Actual source and copper binding

`hw/cosim/gen_top.py:reset_monitor_runtime` first requires exact fitted part
identities, pin polarity, the eight sense/feedback resistor values, all seven
monitor net endpoint inventories, U6 supervisor pins, U19 power and channels,
the nPOR pull-down, and the complete four-node inventory of every slot reset
net. It requires proof of 64 physical legs on the actual board: all analogue ladder/sense/
feedback/diode paths, IC power and ground returns, six U19 inputs, the six fitted 10k pull-ups
and their supplies, and six output
paths to both the slot socket and U13. Missing geometry prevents coverage. Unsupported analogue-core geometry
forces native reset; separately modeled diode/slot branch disconnections
lose only their own electrical action. An isolated U6 MR pin uses its fitted
internal pull-up, with external controls and both diode couplings disconnected. Source hashes bind the actual
native header and the authoritative reset-supervisor model; the native wrapper
rejects a stale manifest.

## Executed behavior

`emu/machine/resetmonitor.h` independently computes the series ladder and input
conductance sums using the fitted values. Amplifier saturation is 50 mV from
each supply rail. Its previous output feeds the sense network, so the exact
same rail voltage can produce different states between falling and rising
trips. Either low output clamps MR through the diode; external button/system MR
also asserts reset. The MAX811 model asserts reset below the conservative
3.15 V threshold and waits 560 ms of continuously healthy MR before releasing.
A repeated fault restarts that timeout.

The source-bound machine starts from an **explicit settled powered functional
baseline**, with nominal 3.3 V, 1.2 V and standby supply. The old twelve-clock
RTL initialization pulse is not presented as the actual MAX811 timeout.
Dynamic faults use the real modeled 560 ms recovery. The separate cold-start
functional test does not release reset after twelve clocks. Its 2.5 ms reference
startup point is a deterministic functional convention, not a guaranteed maximum
physical settling claim. OPA376 overload recovery and MAX811 MR propagation
lack guaranteed maximum limits used by this model; their first-article checks
remain necessary.

The machine consumes modeled nPOR at the chipset input. U19's six electrical
output levels also feed U13 P00–P05 as a wired AND with the expander outputs.
These are observable with `resetMonitor()` and `expanders()`; fault injection
uses `setResetRails(v33, v12, standby)`. The model treats exactly zero standby
as the specified Ioff condition and rejects unsupported partially powered U19
operation below 1.65 V. It never calls the emulator's flash-erasing
`RP2040::reset()` or claims whole-chip RUN recovery.

## Evidence and remaining gate

`test/hw/test_native_reset_monitor.py` compiles the actual native model and tests
independently calculated ladder voltages, cold initialization, both rail faults,
MR clamp, exact recovery/retrigger, hysteresis, and broken diode, output,
reference and feedback counterexamples. `test/hw/test_native_reset_monitor.mjs`
exercises the actual native machine, six U19-to-U13 levels, restored-rail reset
hold, missing-diode behavior, unpowered Ioff and missing-binding rejection.
`test/hw/test_cosim_reset_monitor.py` rejects twenty-three exact source/polarity/value/
unknown-load mutations and a missing actual board.

All focused tests pass. The complete actual round2 board now passes all 64
mandatory electrical paths, with `missing=[]`. The independent diagnostic is
`/tmp/cupc8-resetmonitor-routed-64.log`. Supply/analogue paths use the separate
native `routed_connectivity` API and are recorded as connected booleans, never
as plane-transit SI distances. Queries are batched per net/source and cached
only within one immutable board-binding call. Final strict top generation must
repeat this proof on the current final board. This is a functional model, not
a waiver for those nets or for physical power qualification.

## Final actual round3 proof

The actual completed round3 main package passes the same 64-leg baseline.
Three native-copper mutation counterexamples pass against that package:
removing U6 MR launch isolates both diode coupling and manual-reset effects
while retaining the supervisor's own brownout reset; removing U18 IN+ launch
invalidates the analogue core and holds reset; removing U19 channel-1 output
launch removes only slot 1 clamp action. Receipt validation is required before
and after the source-board probe; mutations are isolated scratch copies.
Actual log: `/tmp/cupc8-resetmonitor-copper-mutations.log`. The parent also
completed strict actual round3 top coverage and CPU data/IRQ/timer native
source/copper counterexamples, preserving the declared functional/DC scope.
