#!/usr/bin/env python3
"""Run the CUPC/8 test catalogue (test/catalogue.toml).

  test/run.py                 run every implemented test
  test/run.py CPU MB-00       run tests whose id starts with any given prefix
  test/run.py --list          list tests and their status, run nothing
  test/run.py --gate          fab gate: also fail while any non-hw test is pending
  test/run.py --kind hw ...   hw tests are skipped unless asked for by kind
  test/run.py -j 4            run up to 4 tests at once (default: 1)

Logs go to build/test/<id>.log and a summary to build/test/results.json
(which fab-readiness.md is generated from).
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "test")


def load():
    with open(os.path.join(ROOT, "test", "catalogue.toml"), "rb") as f:
        tests = tomllib.load(f)["test"]
    seen = set()
    for t in tests:
        for key in ("id", "title", "checks", "method", "kind", "vrow"):
            if key not in t:
                sys.exit("catalogue: %s is missing %r" % (t.get("id", "?"), key))
        if t["kind"] not in ("sim", "static", "formal", "hw"):
            sys.exit("catalogue: %s has unknown kind %r" % (t["id"], t["kind"]))
        if t["id"] in seen:
            sys.exit("catalogue: duplicate id %s" % t["id"])
        seen.add(t["id"])
    return tests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefixes", nargs="*", help="only tests whose id starts with one of these")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--gate", action="store_true", help="pending non-hw tests fail the run")
    ap.add_argument("--kind", action="append", choices=["sim", "static", "formal", "hw"])
    ap.add_argument("-j", type=int, default=1, help="tests to run at once")
    args = ap.parse_args()

    kinds = set(args.kind or ["sim", "static", "formal"])
    tests = [t for t in load()
             if t["kind"] in kinds and
             (not args.prefixes or any(t["id"].startswith(p) for p in args.prefixes))]

    if args.list:
        for t in tests:
            print("%-9s %-7s %-8s %s" % (t["id"], t["kind"],
                                         "ready" if "cmd" in t else "pending", t["title"]))
        print("\n%d tests, %d implemented" % (len(tests), sum("cmd" in t for t in tests)))
        return 0

    os.makedirs(OUT, exist_ok=True)

    def execute(cmd, log):
        start = time.time()
        with open(log, "w") as f:
            rc = subprocess.run(cmd, shell=True, cwd=ROOT, stdout=f,
                                stderr=subprocess.STDOUT).returncode
        return rc, time.time() - start

    # tests with an identical command run it once and share the result
    runnable = [t for t in tests if "cmd" in t]
    first = {}
    for t in runnable:
        first.setdefault(t["cmd"], t["id"])
    outcome = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.j)) as pool:
        jobs = {cmd: pool.submit(execute, cmd, os.path.join(OUT, tid + ".log"))
                for cmd, tid in first.items()}
        for t in runnable:
            rc, secs = jobs[t["cmd"]].result()
            status = "pass" if rc == 0 else "FAIL"
            log = os.path.join(OUT, first[t["cmd"]] + ".log")
            print("%-9s %-58s %s (%.0fs)%s" % (t["id"], t["title"][:58], status, secs,
                                               "" if rc == 0 else "  log: " + os.path.relpath(log, ROOT)))
            outcome[t["id"]] = {"id": t["id"], "status": status, "title": t["title"],
                                "seconds": round(secs, 1)}
    results = [outcome.get(t["id"], {"id": t["id"], "status": "pending", "title": t["title"]})
               for t in tests]

    counts = {s: sum(r["status"] == s for r in results) for s in ("pass", "FAIL", "pending")}
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "counts": counts,
                   "results": results}, f, indent=1)
    print("\n%(pass)d passed, %(FAIL)d failed, %(pending)d pending" % counts)
    if counts["FAIL"]:
        return 1
    if args.gate and any(r["status"] == "pending" for r, t in zip(results, tests) if t["kind"] != "hw"):
        print("gate: pending tests remain, so hardware must not be ordered")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
