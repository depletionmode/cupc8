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
- **COSIM-003, COSIM-004: new, caused by board rebuilds during verify.**
  WIFI-004 (`hw/boards/wifi.py`) and EINK-001 (`hw/boards/eink.py`) rebuild
  their boards in place in `build/hw/`. The netlists differ only by a
  timestamp, but **the autorouter is not deterministic**: a second wifi
  rebuild produced different copper (e.g. an `/EN` track). The pinned
  `doc/hardware/si-evidence/ibis-final-receipts.json` hashes therefore no
  longer match, and the pinned wifi/eink boards no longer exist anywhere on
  disk. Every full verify will repeat this. Under investigation (agent
  `board-determinism`); decision needed on the fix (deterministic routing vs.
  suite rebuilding into scratch and comparing vs. committed canonical boards).
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
- mechanical: the *-008 rows ("smoke not yet designed") vs. the MECH-001 notch issue.
- Wi-Fi: datasheet data for POW-003/WC-005/WC-010 F5-F8 and a droop-fix proposal
  (doc/hardware/wifi-droop-fix-proposal.md), not applied until boards are deterministic.

### Next steps

1. Resolve board-build determinism; then re-pin receipts and regenerate the
   co-sim top/evidence against boards that will stay put.
2. Commit (David's call), validate the new counterexamples, rerun MUT-002.
3. External blockers from the handoff remain David's decisions.
