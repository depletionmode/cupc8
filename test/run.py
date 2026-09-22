#!/usr/bin/env python3
"""Run the CUPC/8 test catalogue (test/catalogue.toml).

  test/run.py                 run every implemented test
  test/run.py CPU MB-00       run tests whose id starts with any given prefix
  test/run.py --list          list tests and their status, run nothing
  test/run.py --gate          fab gate: also fail while any non-hw test is pending
  test/run.py --kind hw ...   hw tests are skipped unless asked for by kind

Logs go to build/test/<id>.log and a summary to build/test/results.json
(which fab-readiness.md is generated from).
"""
import argparse
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
    results = []
    for t in tests:
        if "cmd" not in t:
            results.append({"id": t["id"], "status": "pending", "title": t["title"]})
            continue
        print("%-9s %s ... " % (t["id"], t["title"]), end="", flush=True)
        start = time.time()
        log = os.path.join(OUT, t["id"] + ".log")
        with open(log, "w") as f:
            rc = subprocess.run(t["cmd"], shell=True, cwd=ROOT, stdout=f,
                                stderr=subprocess.STDOUT).returncode
        secs = time.time() - start
        status = "pass" if rc == 0 else "FAIL"
        print("%s (%.0fs)%s" % (status, secs, "" if rc == 0 else "  log: " + os.path.relpath(log, ROOT)))
        results.append({"id": t["id"], "status": status, "title": t["title"], "seconds": round(secs, 1)})

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
