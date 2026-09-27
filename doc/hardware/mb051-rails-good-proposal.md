# MB-051 autonomous rail-good reset proposal — red

This is a source-bound design proposal, **not a board revision**. The
fitted U6 MAX811T supervises only +3V3; its RESET output reaches chipset
U7's `nPOR`. The main +1V2 has only an ADC sense branch. Each of six
`SLOTn_RST_n` lines has a 10 kΩ +3V3 pull-up and a TCA9555 pin that
starts as an input. CPU reset comes from the chipset through a 33 Ω
series resistor and has its own 10 kΩ pull-up. `sysctl` can later hold
slots, but the system card is optional. The model in
`hw/power/rail_reset_window.py` binds those facts to the exported KiCad
netlist and screens 64 abstract reset-state combinations.

## Binding threshold problem

The ±5% lower edges are **3.135 V** and **1.140 V**. The fitted
[MAX811T](https://www.analog.com/media/en/technical-documentation/data-sheets/max811-max812.pdf)
has a 3.00–3.15 V reset threshold over temperature. It can deassert while
+3V3 is 135 mV below its valid lower edge. Its ≥140 ms reset hold after
release is useful, but delay cannot correct that threshold.

As a 3V3 monitor, a [TPS389033](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
with 3.17 V nominal threshold, ±1% accuracy and ≤0.825% hysteresis would
have a worst falling threshold of **3.1383 V** and a worst rising threshold
of **3.2281 V**. These are respectively 3.3 mV above the 3V3 validity
floor and 17.9 mV below the modeled 3.246 V low DC corner. This is a
screening candidate, subject to local rail sensing and the actual fitted
orderable part.

The 1V2 rail is tighter. POW-002 models **1.172 V** at its worst 40 mA
step plus ripple and about **1.176 V** immediately before the step. A
TPS3890-family supervisor with ±1% threshold accuracy and at most
0.825% hysteresis needs nominal falling threshold at least
`1.140/0.99 = 1.1515 V` to assert before the valid floor. To guarantee
release by 1.172 V, it needs nominal threshold at most
`1.172/(1.01 × 1.00825) = 1.1509 V`. **No such threshold exists:** the
interval misses by 0.61 mV before resistor tolerance, noise, trace drop
or card supply loss. If release is assessed only at the 1.176 V
pre-step level, the nominal window is about 1.1515–1.1548 V, still only
3.3 mV wide. The existing CPU card's nominal 1V2 route scenario loses
about 7.9 mV at 40 mA, and its finished copper/contact bound is open.
Neither a fixed 1.15 V TPS389012 nor an adjustable 1.15 V comparator
provides a defensible remote-rail guarantee in this design as it stands.

## Circuit and RTL path once the threshold is qualified

1. Keep U6 as the final push-pull reset driver and its 140 ms release
   timer, preserving the existing U6→U7 `nPOR` copper and chipset reset
   behavior. Add independently powered, **open-drain** 3V3 and 1V2
   supervisors whose outputs pull U6's active-low `nMR` input low in
   parallel with SW1 and `SYS_nRST`. Power their logic from the always-on
   `3V3_STBY` rail; sense the main +3V3 and +1V2 at the loads. Leave
   `SYS_nRST` optional so removal of the system card does not block boot.
   The standby LDO and MAX16054 already keep the eFuse off until POWER
   is pressed, so this does not change cold-off policy.
2. Add a 100 kΩ nPOR pull-down so the reset qualification signal is low
   while U6 is unpowered and standby is alive. An always-on 3V3_STBY
   gate must make `CPU_nRST = nPOR AND chipset_cpu_nRST`, with its FPGA
   input pulled low during configuration and a safe output low while
   standby itself ramps. This replaces the current direct FPGA-to-socket
   33 Ω path; simply clamping that push-pull path low would risk output
   contention. Preserve the chipset's existing CDONE and 16-clock CPU
   release sequence after nPOR becomes high.
3. Give each of the six slot reset lines an independent open-drain
   pull-down, asserted whenever nPOR is low. These clamps operate in
   parallel with the TCA9555's software reset controls. Power the
   qualifier from standby so a +5V-powered card cannot leave RUN/EN
   released while the main +3V3 buck is absent. Keep the card pull-ups
   for normal release; do not depend on sysctl firmware to configure
   U13 at boot. Check any card-local +3V3/1V1 startup requirement
   separately if MB-051 is meant to cover those rails too.

The desired logic is: `nPOR = power_on & good_3v3 & good_1v2 &
manual_reset_released`, after U6's qualified hold interval;
`CPU_nRST = nPOR & chipset_cpu_nRST`; and each slot reset can release
only when `nPOR` is high **and** its software hold is released. A
brownout of either rail asynchronously reasserts nMR, nPOR, CPU reset
and all slot resets. The reset gate and clamp devices must have valid
output states over their own standby startup and brownout ranges.

## Evidence and next board step

The existing main schematic passes KiCad ERC with zero findings. Its
current **unrouted** PCB has no copper-clearance findings; KiCad reports
199 dangling vias and one dangling track before routing. These checks
apply to the old circuit only. There is no new symbol/footprint, netlist,
placement, preroute DRC or completed copper route for this proposal.
Committing speculative board-source changes would make that old route
invalid without answering the 1V2 threshold and cold-off gate questions.

First choose a guaranteed 1V2 monitor and rail target with measurable
margin at the **load** after worst copper/contact drop, or revise the
RT9013 rail so its minimum operating voltage rises enough for a robust
supervisor window without exceeding the FPGA's 1.260 V maximum. Then
bind actual supervisor input and output thresholds, delay, POR behavior,
gate and clamp logic levels, and orderable symbol/footprint pins to the
netlist. A new source-replayed PCB needs ERC, zero-open KiCad DRC,
socket/cold-off checks and a new full route. Finally test 3V3-first,
1V2-first, slow ramp, both brownouts, button reset, sysctl absent,
and card-local supply lag. **MB-051 remains red.**
