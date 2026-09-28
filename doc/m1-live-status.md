# CUPC/8 M1 live status

Running status for whoever picks up the M1 release work. Newest entries
first. Read `doc/m1-handoff-2026-09-28.md` for background and the release
definition; this file records what changed after it.

## 2026-09-28 (afternoon session)

### State right now

- Branch `milestone-1`, HEAD `ce161e5`. **Nothing from 2026-09-27/28 is
  committed**; the worktree holds all agent and root edits (see the handoff's
  git status plus the files below). User artifacts to preserve: `.claude/`,
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

### Next steps

1. Resolve board-build determinism; then re-pin receipts and regenerate the
   co-sim top/evidence against boards that will stay put.
2. Commit (David's call), validate the new counterexamples, rerun MUT-002.
3. External blockers from the handoff remain David's decisions.
