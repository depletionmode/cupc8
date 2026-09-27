# Salt-9 main route: one bounded no-optimizer rerun

The saved salt-9 DSN has SHA-256
`10cbd97dc043be4d4b86715b286c6924763b697cb44ab191190d82dd30072316`.
The matching preroute board has SHA-256
`71e33e9f197487dc417f5a0e2bd47bb10e12ab347ce5d8bbf29493814e388e61`.
The original Freerouting 2.4.1 run reached 10 router opens, all on power
(`/VBUS_F`: 1, `/+5V`: 7, `/5V_SYS`: 2), and 15 pre-existing router
violations after 28 passes. Its auto-routing stage took 7,120 seconds, then
entered optimization at 23:29:28 local time. It had not written an SES by
23:59. The original process has a 10,800-second wall cap.

Run only after the original batch ends:

```sh
python hw/power/main_route_noopt_trial.py \
  --dsn build/noopt-input/route-9.dsn \
  --out build/noopt-salt9-20260928 \
  --timeout 9000
```

The copied DSN is an ignored local artifact in this worktree; the script also
accepts the SHA-matching DSN from the original `build/hw/main/route-parallel`
directory. The script refuses to launch while the root route jobs are active.
It starts exactly one job, with `-mp 30 -mt 0
--router.optimizer.enabled=false`, and has no automatic retry. The 9,000
second cap gives roughly 31 minutes beyond the prior 7,120-second routing
stage while avoiding another three-hour optimization tail. The source DSN is
copied before launch; the job writes only to the new output directory. Its
manifest records the exact input, command, timing, log and SES hashes.

Freerouting 2.4.1 accepts `--router.optimizer.enabled=false`; its `-h` output
calls `-mt` the optimizer thread count. The advertised upstream `-im`
intermediate output flag is **rejected as an unknown argument** by this
installed binary. `-do` exports only at the end, so the trial has no
recoverable intermediate SES. There is no reason to extend a stalled trial
in hopes of an automatic checkpoint.

An exported SES is only a candidate. Import it onto the exact preroute board
with `main_ses_salvage.py`, then check filled-board KiCad DRC, connectivity,
and MB-005 resistance and thermal bounds. The saved 10 opens imply this DSN
may still finish with open power nets even if the no-optimizer job exits
normally. The existing board pipeline would launch additional salt batches
after failure; this standalone rerun avoids that cost.
