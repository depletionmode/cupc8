# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Keep it current:
update it after every finding, commit, decision or agent result (David,
2026-09-28). Background and the release definition:
`doc/m1-handoff-2026-09-28.md`.

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
fastest fix is the seeded build (main_seed.py); then raise ROUTE_PARALLEL
10->20 and lower the cap once seeded timing is known; do NOT add threads per
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
   (C425067.yaml with the new datasheet URL) before rebuilding gpu. GC-006 still red on R4
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
