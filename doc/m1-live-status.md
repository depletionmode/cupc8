# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Newest entries
first. Read `doc/m1-handoff-2026-09-28.md` for background and the release
definition; this file records what changed after it.

## 2026-09-28 (afternoon session)

### State right now

- Branch `milestone-1`, HEAD `ac9388a` (David approved the commit): all
  2026-09-27/28 agent and root work, this session's changes included. Not
  pushed. User artifacts left untracked on purpose: `.claude/`,
  `card.img`, `test/emu/golden/E2E-002.txt.local-backup`.
- Full run: `make verify JOBS=2` → **229 passed, 39 failed, 17 pending**
  (`build/verify-20260928.log`, per-test logs in `build/test/`).
  `doc/hardware/fab-readiness.md` was regenerated from it (red).

### Changes this session (uncommitted)

- `test/catalogue.toml`: added FAB-002 (filled-region neck proof over all
  eight boards; red by design until complex fills are proved) and SI-005
  (routed SPI SCK topology extraction; diagnostic, passes). COSIM-003's
  checks text now includes the sysctl host-VBUS sense.
- `test/hw/test_cosim_routed_subset.py`: COSIM-003 also runs
  `test_cosim_sysctl_vbus.py`. Standalone COSIM-003 passed (all six
  sub-tests) before the full run.
- `test/counterexamples.toml`: counterexample for the sysctl VBUS binding in
  `hw/cosim/gen_top.py`.
- `tools/counterexamples.py`: each scratch worktree gets a symlink to the
  checkout's `build/hw` (gitignored; the receipt-bound board tests only read
  it). Untested until the pending work is committed.
- No separate notch gate: the 0.30 mm copper-to-notch failure already fails
  by name in CC/GC/IC/SC/WC/EC/YC-009 (`boardcheck <card> fab`).

### Failures in the latest full run, by cause

- **Known external blockers (unchanged):** MB-005, MB-006, MB-008, MB-009,
  every card's -005/-006/-008/-009, WC-010, POW-003, MECH-001, FAB-002 (see
  handoff for each).
- **MUT-002:** stops at the first new counterexample ("fixed code is no
  longer in hw/cosim/gen_top.py") because the fixes are uncommitted and the
  runner uses a worktree of HEAD. Resolution: commit, then run the new
  entries (`python3 tools/counterexamples.py COSIM`, `... MB-052`,
  `... Fabrication`), then MUT-002 alone.
- **COSIM-003, COSIM-004: caused by in-place board rebuilds, now fixed.**
  WIFI-004/EINK-001 rebuilt wifi/eink into build/hw during verify. The
  routing is deterministic (agent-verified: identical route.ses and
  identical `sesreplay.preroute_digest` boards across rebuilds; an earlier
  note here claiming otherwise was a raw-diff misread caused by pcbnew item
  reordering). Raw bytes change every build (UUIDs, item order, netlist date,
  PNGs), and the receipts pin raw sha256, so any rebuild broke them; under
  -j the rebuild also deleted evidence.json mid-run. Fix: WIFI-004/EINK-001
  now run `tools/board_reproduce.py <board>`, which builds into a temp dir
  and requires identical normalized boards and route.ses vs build/hw.
  `ibis-final-receipts.json` re-pinned to the current wifi/eink builds (only
  those six hashes changed). Canonical rebuilds are now an explicit step
  followed by re-pinning (command in doc/hardware/si-models.md). Verified:
  each scratch rebuild matches alone; COSIM-003..006 pass on the re-pinned
  receipts. Two scratch builds failed while run concurrently with another
  board build / COSIM (error not captured; suspect Freerouting per-user state
  when two instances start together). Watch WIFI-004/EINK-001 logs under -j 2.
- **WIFI-003: load flake.** The self-signed-certificate refusal event did
  not arrive inside the 40 s `wait_event` (test/emu/test_wifi_qemu.py:296)
  while MUT-002 ran in parallel (63 s vs 24 s). Rerun alone: pass, 42 checks,
  24 s. Not yet fixed; the QEMU TLS handshake is slow under `-j 2` load.

### Counterexamples after the commit

- `COSIM-005` (e-ink panel) and `Fabrication: plotted copper` fail properly
  with their bug back: ok.
- `MB-052 subset` and `COSIM-003 subset` (sysctl VBUS) crashed in the
  worktree before testing anything: their node probes need
  `build/emu-machine/machine.node` and RP2040 firmware, which a fresh worktree
  lacks. Their `cmd` now builds both first (`tools/fw_rp2040.sh &&
  tools/emu_machine_build.sh && ...`, the convention other entries use).
  Those dirs are deliberately NOT symlinked like `build/hw`: other entries
  rebuild them with the bug in, which would write through a link into the
  real checkout. Rerun: both ok. All four new counterexamples now fail
  properly with their bug back, so MUT-002 should pass on the next full run.

### Parallel work started (goal: manufacturable release)

Agents, each owning disjoint files; none may rebuild boards in build/hw:
- board-determinism: why wifi/eink reroute differently each build; fix options.
- card thermal: RP2040 regulator dissipation (GC/IC/SC/EC/YC-006), CPU/main
  regulator binding (CC-006, MB-006). Owns hw/power/thermal.py.
- card power: GC-005 VREG droop, IC-005 SY6280 fault, CC-005 items, SC/EC/YC-005.
- mechanical (done): all eight *-008 rows run the same `hw/mech/fit.py` and fail only on
  MECH-001 key/notch fit. "smoke ... not yet designed: none" in their logs is
  informational (HW-000 pipeline test board excluded; no board undesigned).
- Wi-Fi: datasheet data for POW-003/WC-005/WC-010 F5-F8 and a droop-fix proposal
  (doc/hardware/wifi-droop-fix-proposal.md), not applied until boards are deterministic.

- MB-005 requirement: deriving the real input-loop resistance limit from the
  downstream power checks (doc/hardware/mb005-loop-requirement-derivation.md).
  David questioned the 20 mΩ assumption (USB-IF allows 50 mΩ per mated
  contact); the check stays at 20 mΩ until he decides.
- All five analysis agents hit the weekly API limit once and were resumed
  (no partial edits were left behind).

### David's decisions (2026-09-28)

- **MB-005:** replace the 20 mOhm assumption with a board-side input loop
  <= 60 mOhm at the hot corner (USB-C contacts inside the cable's Type-C
  R2.0 §4.4.1 IR-drop budget) plus a <= 20 C trace-rise rule at 3.213 A.
  Widen/pour J1->F1->U2. (Derivation: doc/hardware/mb005-loop-requirement-derivation.md;
  current inner F1-U2 trace models up to 562 C rise at the fault current.)
- **Card notch:** accept standard PCIe CEM geometry; JLC's copper-to-edge
  minimum only for the gold fingers at the key notch (0.30 mm elsewhere);
  positional key fit qualified by first-article test-fit in the real sockets.
- **MB-051:** redesign reset supervision for both rails with real margin.
- **GPU overclock:** David asked whether 252 MHz / 1.20 V is OK; answered,
  awaiting his choice.
- In progress (agents, scratch builds only): main board (MB-005 + MB-051),
  card notch rule/MECH-001. One coordinated canonical rebuild of all
  boards + evidence re-pin follows, only after both agents finish (a build
  racing their source edits fails with "board inputs changed during pipeline").
- **Card notch decision applied.** hw/tools/gerberdrc.py: only
  ConnectorPad flashes A11/A12/B11/B12 (with their pin-11/12 partner) against
  Edge.Cuts between those pad centres get JLC's 0.20 mm (capabilities page,
  "Copper clearance from routed board edges: >=0.2 mm", read 2026-09-28);
  everything else keeps 0.30 mm; 1 nm float slack at the rule. test_fabcheck
  (30 OK), 3 counterexamples. MECH-001 now passes (static CEM checks kept;
  positional fit is info + new hw test MECH-101 first-article fit).
  **Open with JLC:** their gold-finger pages mention a 0.5-1.0 mm finger-to-
  outline "safety distance" and engineer "optimization"; put a note in the
  order asking them not to trim fingers, and check at first article.
  MECH-101's >= 0.10 mm measured-gap acceptance needs David's OK.
  Card fab rows now stop at the CPL review blocker. Every board reads stale
  (hw/tools changed) until the coordinated rebuild.
- **Wi-Fi divider swap applied:** R9 C25818 -> C861412, R10
  C25803 -> C122538 (YAGEO RT0603BRD07 0.1 %, 25 ppm/C) in hw/boards/wifi.py;
  wifi_parts FITTED, design.WIFI_BUCK_RES_TOL = 0.001, POW-003 text updated.
  wifi_proposal.py: worst min 3.074 V, max 3.537 V (limits 3.0/3.6). Scratch
  build passed every step incl. BOM and JLC stock; POW-003 must be rerun on
  the canonical rebuild.

### Agent results

- **Card power (done).** No row turned green; all six fail only on their
  declared `GAPS['power']` in hw/tools/boardcheck.py. New
  `hw/power/rp2040_vreg.py` + `test/hw/test_rp2040_vreg.py` bind each RP2040
  card's VREG pins, caps, firmware voltage and clock to the RP2040 datasheet
  (build 2025-02-20): io/storage/eink/system pass; **gpu fails**: firmware
  (`fw/rp2040/gpu/main.c:191-193`) sets VREG 1.20 V (1.164-1.236 V at +/-3%)
  vs DVDD max 1.16 V, and 252 MHz vs 133 MHz documented. Wired into
  GC/IC/SC/EC/YC-005 cmds. **New David decision:** accept the out-of-datasheet
  GPU overclock (PicoDVI practice; requirement change + per-unit soak) or
  change the design. Remaining red needs external data: RP2040 DVDD load-step
  data, slot contact resistance max, SY6280 fault/limit data (IC-005; part
  change or requirement rewrite), CPU card items in
  doc/hardware/cpu-power-proof-gaps-20260928.md.
- **Card thermal (done).** New `hw/power/rp2040_thermal.py` (+ `thermal.py
  rp2040 BOARD DIR`, 8 tests incl. 3 mutations) bounds RP2040 package heat
  from datasheet rated maxima (VREG 3.63 V x 100 mA, IIOVDD/IIOVSS 50 mA,
  USB, ADC) and binds the netlist: 910 mW x 48 C/W -> 83.7 C vs 85 C case
  limit (1.3 C margin). io/storage/eink/system pass, gpu fails (TMDS sinks
  46 mA; steady IO 51.7 mA > 50 mA IIOVSS_MAX). **Not wired into
  GC/IC/SC/EC/YC-006 yet** (would need cmd `python3 hw/power/thermal.py
  rp2040 <board> build/hw/<board>`): the passes rest on assumptions David
  must accept: ADC_AVDD <= 2 mA (no datasheet max), IO switching current
  unbounded beyond the rated-total headroom (19.4 mA on storage/system),
  USB 2.0 cable figures quoted from memory; also 100-ohm green LEDs draw
  13.4 mA vs the 12 mA drive setting. CC-006/MB-006 need an iCE40 core
  current bound (iCEcube2 estimate or measurement; ceiling ~100 mA); main
  also lacks HT7533 standby LDO theta-JA.
- **Mechanical (done).** Bug fixed in hw/mech/fit.py: the system card's
  SOFNG x4 socket skipped the positional key check and passed on the EasyEDA
  model's nominal 1.75 mm rib; the SOFNG drawing has no toleranced rib width
  (its undesignated 1.78 at the title block's +/-0.15 allows 1.93 mm > the
  1.84 mm minimum notch). `key_position_check` now fails any socket without a
  published maximum rib. test/test_key_mating.py (4 tests) now runs under
  MECH-001; counterexample added. MECH-001 fails 6 UMAX lines (0.005 mm/side vs
  JLC +/-0.10 mm) + the SOFNG line; MECH-002..008 pass. Unblock: UMAX rib-to-
  contact registration / tolerance data (C404113, C404111), a toleranced SOFNG
  drawing (C19188869; also sources slot_w=1.78), or a socket/interconnect change.
- Note: any edit under hw/tools/ changes every board's evidence hash and makes
  all boards "stale"; such edits must be paired with re-pinning evidence.

### Next steps

1. Resolve board-build determinism; then re-pin receipts and regenerate the
   co-sim top/evidence against boards that will stay put.
2. Commit (David's call), validate the new counterexamples, rerun MUT-002.
3. External blockers from the handoff remain David's decisions.
