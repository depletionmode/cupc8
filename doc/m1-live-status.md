# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Keep it current:
update it after every finding, commit, decision or agent result (David,
2026-09-28). Background and the release definition:
`doc/m1-handoff-2026-09-28.md`.

## State right now (2026-09-28 evening)

- Branch `milestone-1`, pushed to origin on David's request (2026-09-28). All work below is
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
    hysteresis (U18) on 3V3 and 1V2, BAT54A OR into the MAX811T ~MR, and an
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
   More agents (2026-09-28 late): card power data sourcing (CC/GC/SC/EC/
   YC-005), BOM lifecycle/stock audit, JLC assembly DFM audit, connector
   protection review, FAB-002 neck proof, first-article plan
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
   - **WIFI-003: possible security bug, under investigation (agent).** The
     failing loaded run saw WIFI_EV_CONNECTED (0x10) for socket 0 while
     waiting for the self-signed-certificate refusal: either a TLS verify
     bypass under slow timing (fw/wifi/port/esp32c3/main/netesp.c tls_step /
     n_status) or a stale event from an earlier socket. Not a plain timeout.
     The failing log was overwritten by the passing rerun.

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
