# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Keep it current:
update it after every finding, commit, decision or agent result (David,
2026-09-28). Background and the release definition:
`doc/m1-handoff-2026-09-28.md`.

## DECISION NEEDED FROM DAVID: CPU-bus overshoot (bus SI agent, 2026-09-29)

CPU bus (12 MHz; CPU card U1 -> RN 33 ohm -> J1/J2 -> ~110 mm 0.1 mm stripline -> main U7) overshoots the iCE40 input limit (3.6 V, AC 3.66 V / 1.6 ns): 4.23 V at every one of 32 IBIS corners as built. Not an SPI-bus issue. Timing is not the constraint (period 83.3 ns, setup slack ~52 ns; a 68 ohm array adds ~1.2 ns).
- No drive-strength/slew setting exists for these I/O (DS Table 4.13; only a pull-up), so nothing to change in the bitstream.
- **BOM-only option (no reroute, same footprints):** CPU card RN1-RN8 33 -> 68 ohm and main R21-R34 (the 14 main-driven lines) 33 -> 56 ohm. Typical corner peak ~3.74 V (4 of 8 typical-corner cases pass), worst corner (VCCIO 3.47 V, -40 C fast silicon) ~4.0 V: does NOT reach 3.66 V at every corner. LCSC numbers/stock for the 68 ohm 0402x4 array (4D02WGJ0680TCE) and the 56 ohm 0402 are NOT verified (LCSC search from here returned nothing; only C25501 33 ohm is in hw/parts).
- **Full compliance options (MAIN-board change, 31+ lines beside the 0.5 mm TQ144, partial reroute):** 33 ohm + ~100 pF at U7 (peak 3.59 V but 92 mV monotonicity dip, +7.5 ns), or lower-Z0 routing. Series values alone cannot clear all corners (overshoot needs Rs+14 >= Z0 ~98 ohm, but the routed net's 53-165 ohm pieces then park the receiver in the 0.8-2.0 V band).
- **Accept as built (option 6):** out of spec by 0.57 V above 3.66 V and 2.5 ns vs 1.6 ns per edge; duty ~1.5 % (25 % allowed); small damage energy but the vendor gives no tolerance: a reliability risk, not compliance.
- Agent's recommendation: BOM-only 68/56 ohm, rebuild, measure a first article at U7.25 and CPU-card U1 with a >= 1 GHz probe. Decision: must the -40 C / 3.47 V corner comply? CC-007/MB-007 stay red until decided. Answer to 'which board': CPU card (RN1-8) for the CPU-card-driven lines and main (R21-R34) for the main-driven lines, as BOM value changes; a receiver-side fix would need the main board.

## Main-board routing log (root, 2026-09-29; David AFK, told Claude to carry on)

- 08:24 seeded build #1 (main-new): Freerouting fanout 6.5-11 min/pass, ~68 pins stuck. Stopped 08:53.
- 09:06 build #2 (main-new2) with our pre-placed fanout vias (hw/boards/main_fanout.py, 79 vias + stubs, all locked, in the DSN: verified): fanout pass #1 85-108 s, ~28-32 not routed; pass #2 125-455 s, still 27-32 not routed, ripup costs 100->200, plus 'normalizeTraces reached 2000 iterations' warnings. Not converging. Stopped 09:20.
- 10:20 build #3 (main-new3, fanout off): routing stage started 09:28:48 for 147 unrouted items; **pass #1 finished at 10:20-10:22 (salts 0 and 5, identical: score 931.21, 65 unrouted, 33 violations) after ~3,000-3,100 s** but only ~1,470-1,540 CPU-s: the box was CPU-oversubscribed (load 42-54 on 24 cores: ~20 ngspice jobs from the bus-SI sweep, the SI extractor workers, co-sim tests, all at nice 5 like the router). Root lowered every agent analysis job (and its parent) to nice 15 at 10:22 (`scratchpad/deprioritize.sh`; children inherit): Freerouting runs went from ~52 % to ~99 % CPU each. Different salts gave the same pass-1 score, so the 8 runs are probably near-duplicates: killing some would not speed the others (each is single-threaded), only lower contention. Re-run the script if the router is starved again.
- Finding: Freerouting 2.4.1 has an undocumented `--router.fanout.enabled=false` (FanoutSettings: enabled, max_passes, max_items, max_milliseconds_per_pin, ripup_allowed, alternate, min_escape_length_mm). Tested on the Wi-Fi DSN in scratch (scratchpad/frtest): no fanout stage. Main-board agent told to add a `fanout` flag through kicadgen (main passes False) and restart as main-new3.
- Pads still bare after pre-placement: 2 exempt (U19.2 /SLOT1_RST_n, U2.9 /EFUSE_ILM). My escape test (scratchpad/escape.py): U2.9 has a 4.6 mm F.Cu path to its only other pad R3.1 and a legal via spot 0.66 mm away; U19.2 has a legal via spot 2.2 mm away by an F.Cu trace (2.9 mm at 0.2 mm rules): both routable; not a probability, a feasibility check. Final DRC/connectivity decides.
- 26 of the 79 new vias are >1.5 mm from their pad (max 3.4 mm, U19.6 /SLOT3_RST_n), all on slow reset/monitor/CC nets.
- All 8 board pins counts: 1052 SMD pads = 530 track+via, 475 track-only (connected by the seed's locked F.Cu tracks, need no via), 45 no-connect, 2 bare.

## Decisions 2026-09-29 (David)

- Main-board routing: **pre-place fanout vias ourselves** (Freerouting's fanout took 6.5-11 min/pass with the failing set stuck at ~68 pins; my geometry test scratchpad/via_room.py found a legal via spot for all 79 bare connected pads). Main-board agent instructed to stop the old build, implement and restart into scratchpad/main-new2.
- **ninja is missing on this host** (build caches point at another project's venv): David to run `sudo pacman -S ninja` (needs his password; not installed by Claude). Needed for emulator/firmware builds, fresh counterexample worktrees and the full verify.
- CPU-bus overshoot (bus SI agent): /CPU_A0 (CPU card U1 -> RN1 33 ohm -> J1/J2 -> 110 mm 0.1 mm stripline Z0 89 ohm -> main U7.25) peaks 4.17-4.23 V vs the iCE40 3.6 V limit at all 32 corners; no single RN value clears them all. Options + which board changes requested from the agent (RN1 is on the CPU card).
- High-speed SI agent expects GC-007 impedance red (routed GPU D0 lower bound > 110 ohm vs 100 ohm +-10 %).

## INTERRUPTED 2026-09-29 morning: agents hit the weekly API limit

All four running agents stopped mid-task (Opus weekly limit, resets Oct 1
5 pm Asia/Jerusalem; David switched the session model to Sonnet 5.5, so new
agents should be launched with model "sonnet"). Their partial work is
committed as one "WIP" commit so it survives this machine; it is UNREVIEWED
and the tree needs the coordinated rebuild (hw/tools, hw/lib, hw/parts changed).
**Relaunched 2026-09-29 as Sonnet 5.5 agents** (verified from transcripts):
main board (MB-005 + MB-051, first seeded scratch build), bus SI (resolve the
4.234 V U7.25 overshoot, MB/CC/SC/EC-007), co-sim + E2E, high-speed SI. Each
writes progress under its own heading in this file. Routing speed notes
(David asked): main routing = 10 parallel salted single-thread Freerouting
runs (24 cores, 1 GB heap, 180 min cap), only salt 9 ever completed (~3 h);
fastest fix is the seeded build (main_seed.py). **David set (2026-09-29)
ROUTE_PARALLEL = 8 and ROUTE_HEAP = 3g** (8 x 3 GB = 24 GB of 35 GB free;
hw/boards/main.py); lower the 180 min cap once seeded timing is known; do NOT add threads per
run (breaks per-salt reproducibility).

Test state of the partial work (run 2026-09-29):

- **Main board MB-005 + MB-051 (agent a81e21b):** design and models written,
  **no scratch build/route exists yet** (main routing takes ~3 h per attempt:
  this is the critical path). Files: hw/boards/main.py (+177/-59),
  main_power_corner.py, main_seed.py + main-route-seed.json (locks the proven
  route outside re-laid areas), hw/power/{reset_supervisor,reset_sequence,
  copper_mesh,main_bind}.py, rail_reset_window.py, main_input_heat.py,
  design.py (R_RECEPTACLE 60 mOhm), budget.py, models/fetch.py, board_thermal.py,
  hw/tools/boardcheck.py (main power now runs main_bind + main_input_heat;
  GAPS['power']['main'] removed), new footprints/symbols/parts for the reset
  qualifier (TSSOP-14 SN74LVC07A, SOT-23 parts, OPA376). Tests:
  test_reset_supervisor OK, test_power_value_parsing OK;
  **test_main_input_heat FAILS**: test_narrow_conductor_fails_the_20_c_rule
  (rule not catching a narrow conductor yet: unfinished);
  test_board_thermal errors only because the built CPU netlist still has
  C21 1u (expected until rebuild). Last step: tests for the fetch VSWITCH
  suffix and board_thermal milliohm parsing.
- **Co-sim + E2E (agent aa8449e):** hw/cosim/{gen_top,coverage,run}.py,
  emu/machine (I2C expanders, fpgaconfig.h, addon/machine/board.h),
  test/emu/machinenative.mjs, tools/lockstep.py, soc/tb, new tests
  test_cosim_{card_leds,coverage,cpu_socket,fpga_config,mb052_bridge,
  sysctl_inputs}.py + probes. test_cosim_coverage passes. Last step: JS ADC
  volts + a ccLine option (sysctl inputs). Not yet run against the catalogue
  rows; no cmds/catalogue entries reported. E2E-001..004, MB-052, CC/SC/EC/
  YC-051 still pending.
- **Bus SI MB/CC/SC/EC-007 (agent a7fc4c7):** hw/si/{slowbus_*,route_si,
  xsection}.py, test/hw/test_slowbus_si.py, test_route_si.py. **test_baseline_
  passes FAILS: the baseline extraction reports main:U7.25 overshoot 4.234 V**
  (either a real SPI overshoot beyond the iCE40's input limit or an unfinished
  model: must be resolved, not waived). Waiting on CC-007 run when stopped.
- **High-speed SI GC/IC/YC-007 (agent af7e73c):** hw/si/{tmds_si,usb_fs_si}.py
  present, no tests or report; effectively just started.
- Loose ends to fix when resuming: tools/fab_neck_coverage.py modified (from
  the paused FAB-002 agent, unreviewed); scratch shells from the SI agents
  may still exist under scratchpad/si007.

Still true: pending rows not implemented: MB-007, CC-007, GC-007, IC-007,
SC-007, EC-007, YC-007, MB-052, CC-051, SC-051, EC-051, YC-051, E2E-001..004,
MB-051.

## Main board (MB-005 + MB-051), Sonnet resume 2026-09-29

- Fixed `hw/power/main_input_heat.py` `rises()`: it silently returned 0 rise
  for a mesh result with no density grids (the test fixture had none), so
  the 20 C rule passed anything. It now raises; the fixture builds a real
  grid; counterexample entry added. `test_main_input_heat.py` 10/10 OK.
- OPA376 as comparator verified: `reset_supervisor.py` and `--spice`
  (TI OPA376 model) all pass: swing 50 mV max, overload recovery 0.33 us,
  fast +3V3 collapse nPOR low in 5.3 us, hysteresis 4.4 mV (3V3) / 1.2 mV
  (1V2). Tight spot: W5 input-range margin 62 mV (3.7 %) at +3V3 = 3.00 V.
  Integrated comparators (TLV7011/TLV3012) rejected: offset wider than the
  1V2 window. All new parts checked on JLC 2026-09-29 (stock 2.9k-25k+).
- `test_board_thermal.py` gained the LVC07 test (6 inputs x 500 uA dICC, fits
  the HT7533 headroom). Its only error is the built CPU netlist C21 (expected
  until the rebuild).
- Build 1 (`scratchpad/main-new`, 08:24) was stopped by David's decision: its
  8 Freerouting runs spent 6.5-11 min per fanout pass with ~68 pins never
  routed. Preroute: 5162 seed items kept, 81 connected SMD pads bare.
- **Pre-placed fan-out** (`hw/boards/main_fanout.py`, called from
  `main.prepare` via `_fan_out`): a locked stub + 0.6/0.3 via on every bare
  connected SMD pad, nearest legal spot (class clearance 0.1/0.15/0.2 + 0.05,
  no via-in-pad, 0.85 hole spacing, out of no-via areas, all layers'
  copper), retried in reordered rounds for fine-pitch rows. 79 placed in ~7 s;
  **exempt (documented in `EXEMPT`, Freerouting fans out itself): U19.2
  (SLOT1_RST_n) and U2.9 (EFUSE_ILM)**. The build stops if any other
  connected SMD pad is bare (`bare_pads`). Test
  `test/hw/test_main_fanout.py` (6 tests; the own-pad-keepout mutation fails
  it). `hw/tools/boardevidence.py` now also hashes main_power_corner.py,
  main_seed.py, main_fanout.py and main-route-seed.json (they fed the board
  but were not in its evidence hash).
- Build 2 (`main-new2`, 09:04, stopped by root 09:20): the 79 pre-placed
  vias cut fanout pass 1 from 388-667 s to 85-108 s, but Freerouting's own
  fanout did not converge (pass 2: 125-455 s, "not routed" flat at 27-32,
  ripup costs rising; normalizeTraces hit 2000 iterations on /3V3_BUCK,
  /FL0_nCS, /FL0_MOSI).
- **Fanout stage off** (root's finding: Freerouting 2.4.1
  `--router.fanout.enabled=false`): `kicadgen._freerouting_cmd` +
  `fanout` kwarg through `autoroute`/`_route_parallel`/`pipeline
  (route_fanout=True default)`; only main.py passes `route_fanout=False`.
  Test `test/hw/test_freerouting_cmd.py`; counterexample entries for it and
  for the own-pad keep-out (both need the fix committed before the fresh-
  worktree run).
- Build 3 (`scratchpad/main-new3`, log `build3.log`, pid `build3.pid`,
  started 09:24). Routing stage started at once (09:28, 147 unrouted items,
  no fanout stage); pass #1 took 52-55 min per run (8 runs), ending at 62-71
  unrouted / 33 violations (10:22-10:25). Final result below when it finishes.

## Bus SI (MB/CC/SC/EC-007), resumed 2026-09-29 (sonnet agent)

### The 4.234 V: real, and it is the CPU bus (CC-007), not the SPI bus

`test_baseline_passes` simulated /CPU_A0: CPU-card U1.1 (iCE40 bank-3 IBIS) ->
RN1 33 ohm -> J1 -> J2 -> 110 mm of 0.1 mm In2/In3 stripline (Z0 89 ohm, x1.1
corner 98 ohm) -> main U7.25. Limits (FPGA-DS-02029-3.9 Table 4.1: I/O tri-state
voltage -0.5..3.60 V; note: 200 mV over VCCIO max 3.46 V = 3.66 V and -200 mV
under VIL min, each <= 1.6 ns and 25 % duty; Table 4.13 VIH max VCCIO + 0.2 V).
Not tuned: routed peak 4.234 V for 2.54 ns above 3.66 V, undershoot -0.76 V for
1.7 ns. Evidence it is not an artefact: (1) the IBIS driver alone into 1 Mohm /
5 pF is clean and monotonic (3.469 V); (2) one ideal lossless 98 ohm 0.9 ns line
with the same driver, TQ144 package and clamps gives 4.220 V at 33 ohm, 4.14 (47),
3.86 (68), 3.469 (100) (`AsBuiltCpuBus.test_ideal_line_reproduces_the_peak`);
(3) hand calc: Zs = 14 (IBIS pull-up) + 33 < Z0, so the open end doubles a 2.35 V
step; (4) package L 0.3..7 nH moves the peak < 15 mV, the connector < 10 mV; the
pin-side node peaks higher (4.40 V), the die probe is the kinder one; (5) all 32
corners fail (min corner 3.65-3.71 V, typ corner A0 3.99 V, max 4.17-4.23 V).
Clamp energy is not the issue (IBIS power clamp ~9 mA for ~2 ns, 8.5 pC per edge,
~50 uA average per line at 6 MHz toggling): the exceedance is amplitude (+0.57 V
over the 3.66 V allowance) and duration (2.5 ns vs 1.6 ns).

### Which lines (as built, 32 IBIS/line/connector corners each)

All 31 CPU-card-driven lines fail: address/control 0-4 of 32 pass, peak 4.21-4.28 V,
trough -0.75..-0.80 V; D0-D7 16/32 (max corner fails, 4.04-4.09 V; these nets also carry
the main-side 33 ohm R21..R28 tap, and all min corners pass); TMR_EXP/HALTED/WAITING 10-16/32 (4.17-4.19 V). The 14
main-driven lines (D0-7, IRQ0-3, nRDY, nRST; U7 -> R21..R34 33 ohm -> J2 -> CPU
card U1) fail the same way (sampled D0, D5, IRQ2; the full group is in the
MB-007 run): D0/D5 16/32 at 4.18/4.13 V, IRQ2 0/32 at 4.24 V. The
12 MHz clock nets (assumed oscillator bracket, weaker evidence) also fail:
cpu:U1.21 3.87 V for 1.2 ns. Full data: build/si-slowbus/CC-007.json.

### Fix options (tool: `hw/si/cpubus_options.py`; JSON in build/si-slowbus/cpubus-*.json)

All numbers are the routed model at 32 corners for /CPU_A0 unless stated; "pass" =
no overshoot/undershoot/ring-back/non-monotonic failure. Bus: 12 MHz, T = 83.3 ns,
BUS-005 setup slack 52.6 / 51.0 ns (63 %), hold margin 1.47 ns.

| # | Option | Boards / parts | pass /32 | worst peak / trough | ring-back / dip | added settle |
|---|---|---|---|---|---|---|
| 0 | as built, 33 ohm | - | 0 | 4.234 / -0.76 V | - | - |
| 1 | RN 47 ohm | CPU card RN1-8 value | 10 | 4.16 / -0.69 | 0 / 0 mV | +0.04 ns |
| 1 | RN 56 | same | 16 | 4.11 / -0.63 | 0 / 0 | +0.07 |
| 1 | **RN 68** | same | 16 (all min corners) | 4.01 / -0.52 | 0 / 0 | +0.11 |
| 1 | RN 75 | same | 16 | 3.92 / -0.45 | 66 / 0 | +2.2 |
| 1 | RN 82 | same | 12 | 3.90 / -0.42 | 177 / 0 | +2.3 |
| 1 | RN 100 | same | 4 | 3.85 / -0.37 | 424 / 0 | +2.4 |
| 1 | RN 120 | same | 0 | 3.75 / -0.27 | 648 / 520 | +2.4 |
| 4 | 33 ohm card + 22/33/47/68 ohm at U7 | main, 31 parts at U7 | 8 | 4.20/4.20/4.18/4.16 | 0 | <= +0.14 |
| 4 | split 47 card + 47 at U7 | both | 16 | 4.10 / -0.63 | 0 | +0.16 |
| 3 | AC term 91 ohm + 47 pF at U7 | main, 62 parts | 0 | 3.49 / -0.02 | 424 / 207 | +2.9 |
| 3 | AC term (22..47 ohm card, 68/91 ohm, 100/220 pF) | main | 0 (12 combos) | 3.36-3.47 | 320-790 / 250-830 | +4.8..+20 |
| 3 | Schottky clamps to rail and GND (BAT54 class) | main, 62 parts | 16 | 4.10 / -0.63 | 0 | +0.7 |
| 3 | 33 ohm + 100 pF at U7 | main, 31 caps | 16 | 3.59 / -0.11 | 6 / 92 mV | +7.5 |
| 3 | 33 ohm + 47 pF at U7 | main | 16 | 3.93 / -0.44 | 0 / 58 | +3.6 |
| 3 | 33 ohm + 22 pF at the CPU card RN | CPU card only, 31 caps | 2 | 4.17 / -0.69 | 170 / 0 | +4.0 |

Main-driven lines (R21..R34 value, BOM only): 33 ohm D0/D5 16/32 (4.18/4.13 V),
IRQ2 0/32; 56 ohm 18/12/10 of 32 (3.93/3.88/4.18 V); 68 ohm 10/6/4 with 177-253 mV
ring-back; >= 75 ohm worse. Other card lines (A9, D4, A11, D5, A15) track A0 within
0.05 V; best single value is 56-68 ohm on every line (A0 68: 16, A9 16, A11 16, A15
16, D4 8, D5 16; 56: 16/16/14/16/20/16), so per-line values (option 2) buy nothing:
the surviving failures are the max corner (VCCIO 3.47 V, -40 C fast silicon) and they
do not move below 3.9-4.0 V with any series value that keeps edges monotonic.
Typical corner (3.3 V, 25 C), A0: 33 ohm 3.99 V 0/8, 47 3.92 0/8, 56 3.87 2/8,
**68 3.74 V 4/8**, 75 3.71 V 5/8, 82 3.70 2/8, 100 3.64 V 1/8 (ring-back 338 mV).

Why no series value clears everything: overshoot needs Rs+14 >= Z0 (~98 ohm at the
x1.1 corner, i.e. R >= ~85), but the routed net is a chain of 53-165 ohm pieces and
the staircase then parks the receiver in the 0.8-2.0 V band (ring-back 177-650 mV).

Option 5 (drive/slew): none. FPGA-DS-02029-3.9 Table 4.13: LVCMOS33 IOL/IOH 8 mA
(16/24 mA only for the High Drive LED (RGB) outputs, footnote 2); the data sheet lists
only a programmable pull-up (no drive-strength or slew attribute for normal I/O), and
the Lattice IBIS has one model per bank/standard. Nothing to select in the CPU-card
bitstream.

Option 6 (accept): out of spec by 0.57 V over the 3.66 V allowance (0.63 V over
3.60 V) and by 2.5 ns vs 1.6 ns per edge; duty is ~1.5 % (25 % allowed) so only the
per-event amplitude/duration are violated. Damage energy is small (above) but the
vendor gives no tolerance beyond the note, so it is a reliability risk, not a
compliance.

Bus timing at the options: T = 83.3 ns; BUS-005 allows a 33 ohm RC of 1.09 ns; a
68 ohm array adds ~1.2 ns (2.2*R*15 pF), 100 ohm ~2.2 ns, of a 52 ns slack; hold
margin 1.47 ns improves by the first-band delay (+0.02..0.06 ns).

Which board: series value alone = CPU card RN1-RN8 (+ main R21-R34 for the 14
main-driven lines: a BOM value change, no reroute, same footprints). Any receiver-side
part (U7 caps, terminations, clamps) is a main-board change with parts beside a
0.5 mm TQ144 for 31+ lines, i.e. a partial reroute. 4D02WGJ0470TCE (47 ohm) and
4D02WGJ0680TCE (68 ohm) exist by MPN in distributor listings; LCSC numbers and JLC
stock NOT verified (only C25501 = 33 ohm is in hw/parts): check jlcpcb.com/parts
before committing.

Recommendation: change the 8 CPU-card RN arrays to 68 ohm and R21-R34 on the main
board to 56 ohm (BOM only), rebuild, and measure a first article at U7.25 and
CPU-card U1 with a >= 1 GHz probe. This removes the undershoot violations at the
typical corner and cuts the peak to ~3.74 V typ (4.0 V at the -40 C/3.47 V corner),
but does NOT reach 3.66 V at every corner: getting there needs a main-board change
(33 ohm + ~100 pF at U7: peak 3.59 V but 92 mV monotonicity dips and +7.5 ns), or
lower-Z0 routing. Decision needed from David on whether the -40 C/3.47 V corner
must comply. CC-007 stays red until then.

### Row status (2026-09-29): all four rows RED, on the routed boards, evidence stale

Reports: build/si-slowbus/{MB,CC,SC,EC}-007.json (`--artifacts-only`: every board in
build/hw is "stale: source inputs differ", so `valid_for_row_4_6` is false until the
coordinated rebuild; a strict run refuses stale boards). MB-007 had never completed
(crashed in extraction on the wifi 2-layer B.Cu void: fixed in slowbus_route.py);
it now runs 3712 cases: 3041 failing.

- **CC-007** 778/1008 failing: the CPU-bus overshoot above (sourced iCE40 IBIS,
  both ends). Timing ok (BUS-005 setup 63 % slack). Clocks (assumed oscillator
  bracket) also over.
- **MB-007** SPI on the six slots, SCK/MOSI/CS/MISO all fail: SCK and MOSI with
  storage cards in all slots ring back 0.5-1.8 V and dip non-monotonically up to
  1.7 V through the 0.8-2.0 V band at every corner; per-slot CS peaks 3.9-5.3 V.
  Series value of R35-R42 (SCK/MOSI/CS at U7) does not fix it: 33/47/68/100/150/220
  ohm gives 0/32 passing for SCK-all and MOSI-all at every value (peak falls 4.37 ->
  3.53 V, ring-back stays 360-1800 mV): a distributed six-stub star behind a source
  above Z0 launches a staircase. Only a lightly loaded corner (one card in J16,
  10 pF RP2040 input, max IBIS) passes as built. RP2040 pin C (1..10 pF) is unsourced
  and decides pass/fail for SCK-J16-only (rx_c=1 passes, rx_c=0 fails at max).
  MISO (74LVC1G125 family IBIS proxy, no series R on the cards): U7.48 peaks 4.54 V
  for 6.8 ns / -0.64 V for 4.9 ns, timing -27 ns at 6 MHz (slot MISO turnaround).
  SRAM/ROM bus: 406/624 failing (ring-back up to 527 mV on MEM_D2 at U10.15);
  chipset -> CPU socket (main-driven, 33 ohm at main): 294/448 failing. Convergence
  check fails on the SCK/CS cases (arrival time of ringing edges differs 2-4 ns
  between mesh and half mesh; amplitude agrees to 8 mV).
- **SC-007** 671/872: RP2040 -> microSD passes at the weak driver bound (170 ohm, 5 ns)
  and fails at the fast bound (20 ohm, 0.5 ns, UNSOURCED; RP2040 has no IBIS, no
  edge rate, no pin C): SD_SCK 4.46 V on the card (limit 3.6 V) with no series R. Red
  until RP2040 4 mA/slow-slew edges are measured. SD read timing -7.2 ns.
- **EC-007** 828/1128: same RP2040 bounds; HAT inputs undershoot -0.63 V at the fast
  bound over a 100-300 ohm loose cable (assumed cable). 150 ohm instead of 33 passes
  at 0.15 m and fails again at 0.3 m. UC8179 DIN setup/hold/SCL width -2.0 ns.
- Not covered anywhere: USB D+/D- 90 ohm (other agent's openEMS rows).

Focused tests (all 25 pass, ~2.3 min): `python3 test/hw/test_slowbus_si.py`.
Mutations that must fail: RN arrays shorted (CPU bus, from the 68 ohm baseline), a
60 mm and a 150 mm stub added (30 mm passes), R36 shorted (SPI), the EC series
resistor removed and the EC cable doubled, a 100 ohm "pull-up" on the storage card.

## State right now (2026-09-28 evening)

- Branch `milestone-1` (pushed to origin; the WIP commit on top is unreviewed). All work below is
  committed except what "In flight" lists. User files left untracked on
  purpose: `.claude/`, `card.img`, `test/emu/golden/E2E-002.txt.local-backup`.
- Last full run (before today's fixes): `make verify JOBS=2` → 229 passed,
  39 failed, 17 pending (`build/verify-20260928.log`). Not rerun since;
  every board currently reads "stale" because `hw/tools/gerberdrc.py` and
  board sources changed, until the coordinated rebuild (Everything left, A).
- Evidence hashing: `hw/tools`, `hw/lib`, `hw/parts` and `hw/boards/<board>.py`
  are hashed into each board's evidence. Any edit there, or any board build
  that adds an `hw/parts/easyeda/*.yaml` cache file, makes boards stale and
  makes any concurrently running board build fail with "board inputs changed
  during pipeline". `hw/power` is not hashed.
- Never rebuild a board into `build/hw` casually: WIFI-004/EINK-001 now
  build in a temp dir (`tools/board_reproduce.py`). Canonical rebuilds are an
  explicit step followed by re-pinning `doc/hardware/si-evidence/` (command in
  `doc/hardware/si-models.md`, "ibis_route_receipts.py").

### Interrupted by the weekly API limit (resets Oct 1, 5 pm Asia/Jerusalem)

- **Main-board agent (MB-005 + MB-051), partial, uncommitted, unreviewed:**
  - `hw/power/design.py`: R_RECEPTACLE assumption now <= 60 mOhm board-side
    loop + 20 C rise (David's decision) — the downstream power suite has NOT
    been rerun with it.
  - `hw/power/reset_supervisor.py`: proposed dual-rail qualifier: REF3425
    2.500 V reference (U17), OPA2333 as two comparators with resistor
    hysteresis (U18; the design now uses an OPA376 per the BOM audit) on 3V3 and 1V2, BAT54A OR into the MAX811T ~MR, and an
    SN74LVC07A (U19, on 3V3_STBY) driving the six SLOTn_RST_n from nPOR.
    Not yet simulated or reviewed (an op-amp used as a comparator needs its
    output swing/speed checked; LCSC stock unchecked).
  - `hw/power/copper_mesh.py`: multi-layer rasterized DC resistance of one
    net's routed copper (for the input path).
  - `hw/boards/main_seed.py` + `hw/boards/main-route-seed.json`: lock the
    proven main route (the main board takes Freerouting ~3 h per ordering and
    completed once, salt 9) outside the areas being re-laid.
  Resume: review these, finish the input-path copper and the supervisor
  simulations, then the scratch build.
- **GPU agent:** stopped before editing anything; relaunch with the same brief
  (Everything left, A.2).
- **JLC note text agreed with David:** "Gold fingers follow PCIe CEM r3.0
  geometry. Do not trim, narrow, shorten or shift any gold finger, and do not
  change the key notch. If your process requires any change, contact us
  before production."

- **JLC order checklist (done):** doc/hardware/jlc-order-checklist.md (all
  eight boards, click-by-click; gate, upload files, options, note, sequencing)
  + tools/jlc_production_diff.py (HOST-004). Mismatches to resolve before
  ordering (its section 0): M1 order.json lacks Confirm Production File and
  the note; M2 no impedance-control field though verification.md wants
  controlled impedance for the GPU; M3 no outline tolerance (MECH-101 assumes
  JLC's +/-0.1 mm high-precision option); M4 whether JLC "gold fingers" is
  hard gold (ask JLC); M5 main needs Standard PCBA (8 THT connectors); M6 no
  material/TG; M7 13 vias in mask openings around Wi-Fi U1 (via-in-pad);
  M8 no CPL reviews yet.

- **BOM risk audit (done):** doc/hardware/bom-risk-audit-20260928.md,
  data doc/hardware/bom-risk-20260928.json, `tools/bom_risk.py --pending`.
  Must-fix: reserve 3 x SST39VF040 C645939 (11 in stock) and 5 x iCE40HX4K
  C1521989 (51 JLC / 24 LCSC) before the first article (David action; first
  run is 2 of each board). Before a
  production run: RT9013-12GB C58464 obsolete -> TLV75512PDBVR C2877864
  (rerun RT9013 checks); W25Q16JVSSIQ C131025 and W25Q32JVSSIQ C179173 EOL ->
  GD25Q16ESIGR C2922792 / GD25Q32ESIGR C2832998 (boot2 check on hardware).
  Watch: C45783 NRND (-> C602037), ESP32-C3-MINI-1U-N4 NRND (N4X no JLC
  stock), thin stock x4 socket/SRAM/F1. Parts cost: 2 of each board $501
  (pending parts incl.), 10 of each $1,220.
- **Wi-Fi via-in-pad (checklist M7), David: fix in the design, don't accept:**
  move/tent the 13 vias in mask openings around U1 at the coordinated rebuild
  (hw/boards/wifi.py or kicadgen; hashed, so queued with the rebuild).

- **First-article plan (done):** doc/hardware/first-article-plan.md (7
  stages: loose parts, inspection incl. MECH-101, first power with short
  screen, fit + four-terminal R, bring-up, power under load, heat/burn-in);
  results JSON under doc/hardware/fa-results/<ID>/, limits in
  `tools/fa_results.py` (11 tests). 29 proposed hw catalogue rows (MB-107..114,
  CC-102..105, GC-102..104, IC-102..104, WC-102..106, SC/EC/YC-101..102) not
  yet added. Four limits marked proposed for David (>= 10 ohm short screen,
  5 C top-to-junction allowance, x1.25 iCE40 margin, 30 mVpp ripple).
  **Design item:** CPU card C21 (RT9013 output) can be 0.90 uF at tolerance vs
  the recommended 1 uF: change to 2.2 uF before ordering (queue with the
  rebuild; note the RT9013 itself is obsolete per the BOM audit).
  Special equipment: NanoVNA or LCR with DC bias, uV DMM, 40 C box, HDMI
  capture, USB microscope, thermocouples, 5 A USB-C breakout, >= 4 A load.

- **JLC assembly DFM audit (done):** doc/hardware/jlc-assembly-dfm-audit-20260928.md,
  `tools/jlc_dfm.py` (test/hw/test_jlc_dfm.py, 7 tests). **Blocks ordering:**
  (M1) gold fingers need JLC Standard PCBA, min 70x70 mm board/panel, fingers
  need >= 50 mm both ways: the six 62.0x47.45 mm cards and the 56x56.4 mm
  system card are too small -> panelize (2 cards side by side, fingers on the
  outer edge, 5 mm rails with fiducials/tooling holes, a top frame with slots
  for connectors overhanging the top edge: eink 6.1, gpu HDMI 1.2, io USB-A
  0.85, system USB-C 0.5 mm). David decision + hw/tools work. (M2) JLC lists
  gold fingers only via ENIG, no hard-gold option: quote hard gold or accept
  ENIG (then change the requirement and check_order). Also: Confirm
  Production File, keep-stencil note, green mask, main-board rails.
  Issues: solid pour connections -> tombstoning risk on 0402/0603 (77 on main,
  ~20/card; fix: thermal reliefs); open vias in pads (wifi ESP32 15 GND pads,
  system Y1 x2, RP2040 EP); io U7 SOT-563 lost its pin-1 silk mark (CPL
  review list); main has 328 THT joints (~$5.7 + $3.5 labour per board, +1
  day). Unconfirmed: 2.5 mm part-to-edge, stencil thickness.

- **David (2026-09-28): ENIG gold fingers accepted** (JLC lists gold fingers
  only via ENIG; no hard-gold option). At the rebuild: order_spec
  `finger_finish` "hard gold" -> ENIG, `check_order`, doc/milestone-1.md and
  the checklist's M4 updated to match; cards mostly stay seated, so tens of
  insertions is the design life. Revisit hard gold in a later revision.
- **Panel plan (David agreed direction; implement at the rebuild):** ONE card
  per panel, not 2-up: JLC's PCBA minimum (2) counts panels, so 2-up would
  assemble 4 cards. Each card: breakaway frame on the three non-finger sides
  (fingers stay on the outer edge for the bevel), 5 mm side rails (about 7 mm
  for the 56 mm system card) and a top frame to reach >= 70 x 70 mm (JLC
  Standard PCBA) and >= 50 mm (gold fingers, +/-0.1 mm high-precision outline),
  3 tooling holes (1.5+ mm) + fiducials on the rails, mouse-bite tabs away from
  the finger edge and the socket-contact sides, no parts near tabs, cut-outs
  for connectors overhanging the top edge (eink header 6.1, HDMI 1.2, USB-A
  0.85, USB-C 0.5 mm). Order 2 panels per card type. The panel's Gerbers get
  the same fab checks as the boards.

- **David (2026-09-28), more decisions:** first-article limits all accepted.
  EOL parts (RT9013 C58464, W25Q16 C131025, W25Q32 C179173) kept for this
  2-board run; David reserves 4 / 10 / 4 (stock 16,181 / 13,371 / 21,299);
  replace before any larger run. CPU card C21 (RT9013 input) 1u -> 4.7u
  (C23733, already on the board; David approved 2.2 uF, 4.7 uF chosen so
  >= 1 uF survives 0402 DC bias): hw/boards/cpu.py, cpu_board.py,
  thermal_bind.py updated; test_board_thermal's core-current test fails until
  the CPU rebuild (built netlist still 1u). Wi-Fi C1/C2 C45783 -> C602037
  (Wi-Fi only; done, uncommitted until now): Samsung spec sheet NOV.13.2025
  guarantees match the MAQ (+/-20 %, X5R, 25 V, DF <= 0.1); its typical DC-bias
  loss is larger (-41.1 % at 3.6 V vs -36.3 %). With the 0.1 % divider:
  burst min 3.066 V (+66 mV), max 3.580 V (**+20 mV**, was +33 mV with the
  MAQ). Passes, but the overshoot margin is thin; option: the proposal's
  optional second 22 uF on 3V3. JLC 79,508 in stock (extended).
  test_wifi_parts: 11/12; the fixture-netlist test fails until the Wi-Fi
  rebuild (built netlist still lists C45783/C25818/C25803). Panel: one card per panel (see above).

## Everything left before the boards can be ordered

### A. Engineering in progress or queued (Claude)

1. **Main board MB-005 + MB-051** (agent running, scratch builds only):
   new input-path requirement (<= 60 mOhm board-side loop, <= 20 C trace rise
   at 3.213 A), widen/pour J1->F1->U2, dual-rail reset supervisor with margin,
   simulations, rail_reset_window.py update. Deliverable includes the
   canonical rebuild command.
2. **GPU card: done except the rebuild.** Overclock recorded as a requirement
   (doc/hardware/power.md); `rp2040_vreg.py` OVERCLOCK allows exactly VSEL
   1.20 V + the DVI bit clock on the GPU only; GC-102 burn-in (hw) added. TMDS
   series arrays RN1/RN2 270 -> 360 ohm (UNI-ROYAL 4D03WGJ0361T5E, C182716,
   extended part, 4,617 in stock): IO 51.7 -> 41.5 mA vs 50 mA; worst DVI
   swing 215..939 mV vs 150..1200 mV (DVI 1.0 §4.2 figures not re-read from
   the spec text). **At the coordinated rebuild:** move
   `doc/hardware/pending-hw-parts-C182716.yaml` → `hw/parts/C182716.yaml`
   (**done 2026-09-29, Rebuild-prep agent**; C425067.yaml kept) before rebuilding gpu. GC-006 still red on R4
   (TMDS switching current unbounded).
3. **JLC order instructions** (David approved): tick JLC's "Confirm
   Production File" option (review their post-CAM Gerbers vs ours before
   production: fingers and notch unchanged), plus the do-not-trim note. Why:
   JLC's CAM adjusts designs outside their rules (gold-finger setback
   0.5-1.0 mm per their guidance; PCIe geometry is closer), sometimes via an
   EQ email, sometimes silently. Note text: add to
   `kicadgen.order_spec` (hw/tools/kicadgen.py:2722) → `fab/order.json`.
   Queued until the main-board agent finishes (hw/tools edit breaks its builds).
4. **MECH-101 criterion: done** (>= 0.10 mm measured notch-wall-to-
   finger gap): add to the MECH-101 checks text in test/catalogue.toml.
5. **Card thermal rows: done.** USB figures verified (26 ns §7.1.19; 90 ohm
   +-15 %; 20 pF transceiver pin-to-GND); GC/IC/SC/EC/YC-006 now run
   `python3 hw/power/thermal.py rp2040 <board> build/hw/<board> && python3
   test/hw/test_rp2040_thermal.py`. They pass for io/storage/eink/system once
   boards are rebuilt (evidence is stale now); GPU needs the TMDS fix (A.2).
6. **Coordinated rebuild** after 1-2 land: rebuild all eight boards into
   `build/hw` one at a time (never two Freerouting runs at once), re-pin
   `ibis-final-receipts.json` (and source audit/top if the main board changed:
   `doc/hardware/si-models.md`), rerun COSIM-003..006, POW-003 (Wi-Fi 0.1 %
   divider), all *-005/006/008/009, then full `make verify JOBS=2`, then
   `tools/fabready.py`.
7. **Pending rows with no implementation yet (17):**
   - Signal integrity: MB-007, CC-007, GC-007, IC-007, SC-007, EC-007, YC-007.
   - Board-level co-sim: MB-052, CC-051, SC-051, EC-051, YC-051.
   - End to end on the netlist-generated machine: E2E-001, E2E-002, E2E-003,
     E2E-004.
   - MB-051 (item 1).
   PAUSED by David (2026-09-28, no files written yet; relaunch later with
   the same briefs): card power data sourcing (CC/GC/SC/EC/YC-005),
   connector protection review, FAB-002 neck proof.
   More agents (2026-09-28 late): BOM lifecycle/stock audit, JLC assembly DFM
   audit, first-article plan
   (doc/hardware/first-article-plan.md), JLC order checklist
   (doc/hardware/jlc-order-checklist.md), WIFI-003 investigation.
   Agents now running (launched after David added credits): SI high-speed
   (GC/IC/YC-007), SI buses (MB/CC/SC/EC-007), co-sim + E2E (E2E-001..004,
   MB-052, CC/SC/EC/YC-051), CPU/main thermal (CC-006, MB-006), IO port-switch
   replacement proposal (IC-005). Main-board and GPU agents resumed. Rules for
   all: no board builds, no hw/tools|lib|parts edits, catalogue cmds reported
   to the root instead of edited.
8. **Other red rows needing work:**
   - FAB-002 filled-region neck proof: complex/holed fills are deferred
     (`tools/fab_neck_coverage.py --require-complete`); needs a general
     polygon min-width proof.
   - IC-005: SY6280 has no fault pin or guaranteed limit → replacement part
     proposal (needs David's approval to change the IO board).
   - CC-006 / MB-006: now run `python3 hw/power/thermal.py board <main|cpu>
     build/hw/<board>` (hw/power/board_thermal.py, 10 tests). HT7533 closed
     (Holtek HT75xx-2 Rev 1.30: 500 C/W; 169 uA of 3V3_STBY load, 42.0 C at
     24 V; four MAX16054-related loads are d.assume values, datasheet not
     downloaded; the new reset-qualifier parts must be added as loads when
     they land). iCE40HX4K power-up peak bound passes (F1). **F2 red:** no
     published iCE40 maximum operating current (DS1040 v3.2 typical only;
     Power Calculator coefficients unpublished, iCEcube2 not installed): set
     ICE40_CORE_MAX from a worst-corner Power Calculator report or a
     first-article measurement; passes if < ~107 mA.
   - **WIFI-003: fixed (not a verification bypass).** The certificate was
     refused every time; the Wi-Fi card then falsely reported CONNECTED: the
     backends' status() returned CLOSED for a failed connect only to its
     first caller and OPEN afterwards, and the card polls status from three
     places. Also a TLS refusal inside n_connect (slow QEMU) left the socket
     OPEN, and SEND on a failed TLS socket re-entered the handshake. Fix: a
     sticky `failed` flag in netesp.c and netposix.c (host/simulator too).
     New host test test_refused, a SOCK_STATUS check in WIFI-003, two
     counterexamples. Loaded stress variant: 1/6 fail before, 8/8 pass after.
     Open (unchanged): events can be missed if CONNECTING/LISTENING goes to
     PEER_CLOSED between polls; esp-tls CONNECTING select() can block up to
     10 s; log prints verify flags 0x0.

### B. Needs outside data or measurement (cannot be closed by analysis)

- CC-005: slot/socket maximum contact resistance, board maker's minimum
  finished copper/via resistance, guaranteed C22/C1-C4 capacitance and ESR,
  iCE40 core-current envelope (doc/hardware/cpu-power-proof-gaps-20260928.md).
- GC/SC/EC/YC-005: RP2040 DVDD load-step response (not published by
  Raspberry Pi); SD card and panel current waveforms; slot contact resistance.
- POW-003 F5/F7, WC-005: ESR and effective capacitance of the fitted C45783
  22 uF (impedance measurement on a reel sample: ESR <= 150 mOhm, C1 >= 5.8 uF,
  C2 >= 8.3 uF). F6/T4r: four-terminal return resistance through a mated
  slot. F8/T4p: ESP32 current at 40 C full-duty TX. T4c (WC-010): measured
  board temperature under sustained TX.
- These are first-article measurements. Options for David: measure on
  first articles before the full run (recommended: order a small first-
  article batch), or accept documented typical data.

### C. Needs David

- **CPL sign-off** (MB-009 and every card's -009): after the coordinated
  rebuild, regenerate overlays (`tools/fab_review_bundle.py`), review the 119
  risky placements from `tools/cpl_focus.py` (ICs, diodes/LEDs, transistors,
  connectors, crystals, switches, resistor networks), write
  `build/hw/<board>/fab/cpl-review.json` per board.
- IO port-switch replacement approval (after the proposal).
- Whether first-article measurements (B) gate the full order.
- Placing the order (never done by Claude).

## David's decisions (2026-09-28)

- MB-005: board-side loop <= 60 mOhm at the hot corner (contacts inside the
  cable's Type-C R2.0 §4.4.1 budget) + <= 20 C rise at 3.213 A; widen/pour
  the input path (doc/hardware/mb005-loop-requirement-derivation.md).
- Card notch: standard PCIe CEM geometry; JLC 0.20 mm only for A11/A12/B11/B12
  fingers at the notch walls; 0.30 mm elsewhere; first-article fit (MECH-101)
  with >= 0.10 mm measured gap; do-not-trim note on the JLC order.
- MB-051: redesign reset supervision for both rails.
- GPU: accept the 252 MHz / 1.20 V overclock as a requirement, add burn-in,
  fix TMDS resistors.
- RP2040 thermal: accept ADC <= 2 mA and IO switching within the rated 50 mA
  headroom, after verifying the USB figures.
- Commits: approved; Claude commits as work lands (not pushed).

## Done today (committed)

- `ac9388a` integrated 09-27/28 evidence; `eacfbbd` counterexamples build
  emulator/firmware in their worktree; `tools/counterexamples.py` symlinks
  `build/hw` into each worktree.
- `fdd9527` `hw/power/rp2040_vreg.py` (RP2040 VREG/clock vs datasheet, in
  GC/IC/SC/EC/YC-005 cmds).
- `565934f` fit.py: sockets without a toleranced rib fail (SOFNG bug) +
  `hw/power/rp2040_thermal.py` (not yet wired).
- `738d592` MB-005 loop derivation (`hw/power/mb005_loop_sweep.py`): binding
  check allows 89.8 mOhm; input traces overheat at 3.213 A (inner F1-U2 up
  to 562 C at thinnest copper).
- `bcf95c7` WIFI-004/EINK-001 build in scratch and prove reproducibility;
  receipts re-pinned; COSIM-003..006 pass. (Routing is deterministic; raw
  bytes differ by UUIDs/order/dates.)
- `c040ca4` Wi-Fi buck deck ground-reference bug fixed (the 2.979 V droop was
  the deck); sourced part data (`hw/power/wifi_parts.py`).
- `082a034` card notch decision applied (gerberdrc exemption, MECH-001
  passes, MECH-101 hw test) + Wi-Fi R9/R10 0.1 % parts (C861412, C122538).
- `643403a` `tools/cpl_focus.py`.

## Notes for a new agent

- Background shell waits: never `pgrep -f '<pattern>'` in a loop whose own
  command line contains the pattern (it matches itself forever); wait on a
  PID with `kill -0`.
- Run at most one board build (Freerouting) at a time.
- Counterexamples run in a fresh worktree of HEAD: commit fixes before
  running them; only `build/hw` is linked in.

## High-speed SI (GC/IC/YC-007), 2026-09-29 (Sonnet agent)

- Started: reviewing hw/si/tmds_si.py, hw/si/usb_fs_si.py (on top of
  hw/si/route_si.py + xsection.py, a 2-D quasi-static extractor; rigorous
  lower-bound impedance, so no unconverged field solve is involved).
  test/hw/test_route_si.py (already on disk) asserts the routed GPU D0
  lower bound is > 110 ohm: expect GC-007 impedance to be RED on the design.

## Co-sim (MB-052, CC/SC/EC/YC-051, E2E-001..004), 2026-09-29 (Sonnet agent)

- Environment: /usr/bin/ninja is gone on this host (build/emu-machine and
  build/rp2040 CMake caches pinned it); `cmake -DCMAKE_MAKE_PROGRAM=<a ninja>`
  once per build dir fixes an existing tree (a fresh worktree finds ninja on
  PATH if one is installed). Emulator and RP2040 firmware rebuilt: OK.
- Every existing co-sim row (COSIM-003..006) is RED at HEAD, for two reasons
  that predate this agent's edits: (1) all eight board receipts are stale
  (hw/tools, hw/lib, hw/parts, hw/boards/main.py changed; matches commit
  c040ca4), so `boardevidence.validate` refuses; (2) the WIP changed
  hw/cosim/gen_top.py, whose hash is pinned in
  doc/hardware/si-evidence/ibis-final-receipts.json (and the pinned top).
  Both clear at the coordinated rebuild + the re-pin command in
  doc/hardware/si-models.md. To test meanwhile: a scratch worktree at HEAD
  with hw/tools|lib|parts|boards taken from c040ca4 and build symlinked
  (scratchpad/cosim-w/wt), then re-pin there.
- 09:15 GC-007 first full run (hw/si/tmds_si.py on build/hw/gpu; note the built
  netlist still has 270 ohm packs, the tool reads whatever the netlist has).
  RED on the routed design, not on the tool: differential impedance lower
  bound proven > 110 ohm on 9.6-21 mm of every lane's trace (pairs run
  loosely coupled; d0 92.9-137.7 ohm); intra-pair skew D1 34.9 ps and CK
  33.3 ps (limit 5; D0 1.1, D2 4.0 pass); line return loss -18.4..-19.05 dB
  vs the -19.58 dB (=+-10 % tolerance) budget; insertion loss >= -0.15 dB.
  New: hw/si/si_cache.py (disk cache of the 10-40 s cut solves under
  build/si/cache, keyed by solver-source hash), swing check in tmds_si
  (rp2040_thermal.tmds_swing at the netlist R: 360 ohm gives >= 215 mV,
  <= 939 mV pp against DVI 150-1200), test/hw/test_hs_si.py.
  A full run costs ~45 min on a loaded machine (538 cut solves); cached reruns are fast.

### Co-sim progress (2026-09-29, same agent)

- Unmodeled nets 129 -> 92 so far (build/hw at c040ca4 boards, HEAD
  gen_top). New bindings (all in hw/cosim/gen_top.py, each with a copper or
  netlist mutation in test/hw): rail indicator LEDs (`rail_indicator_routes`,
  16 nets; `Machine.powerLeds()`; test_cosim_card_leds.py), slot presence and
  CPU card ID (`i2c_expander_routes`, 15 nets; `Machine.expanders()` new
  addon call; test_cosim_sysctl_inputs.py), system Type-C Rd on CC1/CC2
  (`system_usb_routes`, 2 nets; test_cosim_system_usb.py), IO VBUS switch
  enable/fault sense (`io_vbus_routes`, 2 nets; test_cosim_io_vbus.py, new).
  Analog/static waivers added in coverage.py: wifi STRAP2/STRAP8 (WC-006),
  main PWR_BTN/PWR_EN (MB-053, POW-004): judgment calls for David.
- Remaining after that (92): the card programming port (SWD, mux, PROG_n,
  RST_n/RUN, BOOTSEL: ~70 nets; needs an SWD target and card reset in the
  emulator), UART_TX test points (4), GPU DDC/HPD (6, the firmware never
  uses them), Wi-Fi LEDs/USB/UART/EN/BOOT (14), AUX header CS (2), system
  presence (2).
- Development method: never sync the scratch worktree while a run is going
  (it overwrites the re-pinned doc/hardware/si-evidence files); use
  scratchpad/cosim-w/cycle.sh (sync, re-pin, run).

- 2026-09-29 (later): card programming port modelled: `prog_port_routes`
  (45 legs: sysctl PROG_CLK/PROG_IO/MUX_SEL0-2, the two 4051 muxes, each
  slot's 33 ohm SWCLK/SWDIO legs, each RP2040 card's debug pins; mux channel
  and select bit read from the netlist) and `ProgPort` in emu/machine (a
  bit-level SW-DP, `fw/test/swdtarget.c`, in every slot with an RP2040 card;
  decoded from the select pins sysctl really drives; card flash starts as the
  card's real flash). Real `cupc8.py` `Rp2040.flash` programs and verifies
  through it on the native machine (1.15 s of machine time for 2 cards);
  `Machine.progTarget(slot)`. Unmodeled nets now 50 (from 129):
  card RUN/BOOTSEL/UART_TX (12), system BOOTSEL/RUN/SWCLK/SWDIO/PRSNT (5),
  main SLOTn_PROG_n/SLOTn_RST_n/AUX_CS_n/SPI_nCS6_SRC/SYS_PRSNT2_n (15), GPU
  DDC/HPD (6), Wi-Fi card BOOT/EN/LEDs/USB/UART (12). `routed_distances` got
  `pad_reach` (a track ending inside a long edge finger counts as connected:
  system J2.B11 was reported open by the centre-only test; off by default).
- 10:05 IC-007 (hw/si/usb_fs_si.py io) RED on the routed IO card: Zdiff lower
  bound proven > 99 ohm on 13.5 of 15.6 mm (RP2040 side) and 14.3 of 24.7 mm
  (connector side); USB 2.0 7.1.6.1 +-15 % line proven > 103.5 ohm on 13.7 mm.
  The D+/D- routes run mostly uncoupled (single-ended lines add up to >100).
  Passing: skew 64 ps (limit 100 = cable TSKEW), board delay bound 240 ps
  (< 3 ns), line C 5.0/7.3 pF (< 75), edges: Fig 7-9 VCRS 1.653-1.694 V,
  monotonic, 32/32 cable cases without threshold re-crossing (Z lower and upper).
  ngspice notes: T elements of 15-60 ps stall (minutes): board lines are now
  20 ps LC ladders; .options method=gear; 0.5 ns ramp floor; 300 s timeout fails the row.

- 2026-09-29 10:35 results (scratch worktree with c040ca4 hw tools, the
  boards' own receipts valid): PASS card_leds (rail indicators), sysctl_inputs
  (presence/ID), io_vbus, system_usb (CC Rd), prog_port, coverage (waivers),
  cpu_socket (CC-051, 6 mutations incl. 2 copper). E2E-002 (8 checks), E2E-003
  (7), E2E-004 (22) pass on the netlist-generated top (not gated on the net
  accounting). Pending: COSIM-003..006 re-run, MB-052 bridge, the E2E fault
  injection (test_cosim_e2e_mutants.py), then the row commands in a fresh tree.

## Main routing build #3 update (2026-09-29 11:55)
- Passes 11-14 of 8 salts; best 53 unrouted (salt 0 pass 14), range 53-64; all "33 violations" = baseline (fixed copper), none added by us.
- New vs build #1: a /5V_SYS via overlapping the +5V trunk at (8.4, 152.2) (input corner layout). Harmless if same net; else real DRC error. Must check in final KiCad DRC; fix in corner layout if flagged.
- Improvement ~1 unrouted/pass; per-ordering cap (180 min from 09:28) ends ~12:28. Expect ~50 unrouted -> fallback: hand-place remaining connections (agreed with David).

## IC-005 agent
- 11:58 started: applying TPS2553DBVR-1 (45.3k, C25=1u, no R13, FW retry)
- 12:00 done: jlc.kicad_sym symbol, hw/parts C111738.yaml+easyeda C111738/C26980, rotation yaml, hw/boards/io.py (U5 rot 180, C25, no R13, R10=45k3 C26980, R12 10k to 3V3). Next: tests/catalogue, design.py, model script, gen_top/cosim, thermal_bind, firmware retry, docs

## Catalogue agent (2026-09-29)
- test/catalogue.toml: cmd added to MB-007/CC-007/SC-007/EC-007 (`test_slowbus_si.py && slowbus_si.py --row <ROW>`); rows stay red, no thresholds touched. HOST-003 intact.
- 28 new hw rows from first-article-plan.md added (MB-107..114, CC-102..105, GC-103/104, IC-102..104, WC-102..106, SC-101/102, EC-101/102, YC-101/102), cmd = tools/fa_results.py <ID> (pending, exit 1 until records exist). GC-102 already existed (bring-up burn-in): kept, cmd added. MB-101 and MECH-101 amended per plan (+cmd). Catalogue parses, 326 ids, no duplicates.
- MB-051: reset_supervisor.py --spice all pass (25 checks), test_reset_supervisor.py 13 OK; row now has a cmd. Only red part: rail_reset_window.py R0 (stale board evidence, needs the main-board rebuild).

## Decisions 2026-09-29 (David, later)
- CPU-bus overshoot: BOM-only series R (RN1-8 -> 68 ohm, R21-R34 -> 56 ohm); compliance required over the normal operating range only, extreme corner (3.47 V/-40 C) reported, not a gate. Residual non-compliance goes in first-article measurement.
- IO port switch approved: TPS2553DBVR-1 latch-off (IC-005 agent applying).
- CPL sign-off: Claude generates a per-board review pack for the 119 placements; David signs off in fab/cpl-review.json.
- David's own actions remaining: reserve parts in JLC Parts Manager (3 ROM, 5 FPGA, EOL 4/10/4), ask JLC about ENIG gold fingers, place the order.
