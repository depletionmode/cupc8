# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Keep it current:
update it after every finding, commit, decision or agent result (David,
2026-09-28). Background and the release definition:
`doc/m1-handoff-2026-09-28.md`.

## State right now (2026-09-28 evening)

- Branch `milestone-1`, HEAD `643403a`, not pushed. All work below is
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

## Everything left before the boards can be ordered

### A. Engineering in progress or queued (Claude)

1. **Main board MB-005 + MB-051** (agent running, scratch builds only):
   new input-path requirement (<= 60 mOhm board-side loop, <= 20 C trace rise
   at 3.213 A), widen/pour J1->F1->U2, dual-rail reset supervisor with margin,
   simulations, rail_reset_window.py update. Deliverable includes the
   canonical rebuild command.
2. **GPU card** (agent running, sources only, no builds): overclock recorded as
   a requirement; `rp2040_vreg.py` checks GPU against it; per-card DVI
   burn-in hw test (GC-1xx); TMDS series resistors raised so RP2040 IO current
   < 50 mA with valid DVI swing.
3. **JLC do-not-trim order note** (David approved): add to
   `kicadgen.order_spec` (hw/tools/kicadgen.py:2722) → `fab/order.json`.
   Queued until the main-board agent finishes (hw/tools edit breaks its builds).
4. **MECH-101 criterion: done** (>= 0.10 mm measured notch-wall-to-
   finger gap): add to the MECH-101 checks text in test/catalogue.toml.
5. **Card thermal rows** (David approved): verify the USB 2.0 full-speed
   cable figures in `hw/power/rp2040_thermal.py` against the spec, then set
   GC/IC/SC/EC/YC-006 cmd to `python3 hw/power/thermal.py rp2040 <board>
   build/hw/<board>` (GPU passes only after item 2 + rebuild).
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
   Agents for SI (high-speed USB/HDMI; slow buses), co-sim/E2E, CPU/main
   thermal (iCE40 core current, HT7533 theta-JA) and an IO port-switch
   replacement proposal were written but **not launched**: the permission
   classifier returned no verdict for Agent launches (transient). Relaunch
   them; prompts should carry the rules in this file (no board builds, no
   hw/tools|lib|parts edits, give catalogue cmds instead of editing it).
8. **Other red rows needing work:**
   - FAB-002 filled-region neck proof: complex/holed fills are deferred
     (`tools/fab_neck_coverage.py --require-complete`); needs a general
     polygon min-width proof.
   - IC-005: SY6280 has no fault pin or guaranteed limit → replacement part
     proposal (needs David's approval to change the IO board).
   - CC-006 / MB-006: iCE40 core current bound, HT7533 theta-JA.
   - WIFI-003 load flake (40 s TLS wait under -j 2).

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
