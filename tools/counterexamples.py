#!/usr/bin/env python3
"""MUT-002: run test/counterexamples.toml. For each fixed bug: a scratch git
worktree of HEAD, the bug put back (pre-fix files, or a revert of the fixed
code), the bug's test run; it must fail, with every must_fail text in its
output.

    python3 tools/counterexamples.py [name-substring]
"""

import os
import shutil
import subprocess
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "build", "counterexamples")


def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    bugs = tomllib.load(open(os.path.join(ROOT, "test", "counterexamples.toml"), "rb"))["bug"]
    bad = 0
    for i, bug in enumerate(b for b in bugs if want in b["name"]):
        wt = os.path.join(WORK, "cx%d" % i)
        if os.path.exists(wt):
            subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=ROOT, capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
        git("worktree", "add", "--detach", wt, "HEAD")
        try:
            if "files" in bug:
                git("checkout", bug["before"], "--", *bug["files"], cwd=wt)
            for fname, fixed, buggy in bug.get("revert", []):
                path = os.path.join(wt, fname)
                text = open(path).read()
                if fixed not in text:
                    raise SystemExit("%s: the fixed code is no longer in %s; update the entry" % (bug["name"], fname))
                with open(path, "w") as f:
                    f.write(text.replace(fixed, buggy, 1))
            r = subprocess.run(bug["cmd"], shell=True, cwd=wt, capture_output=True, text=True, timeout=7200)
            out = r.stdout + r.stderr
            missing = [m for m in bug["must_fail"] if m not in out]
            if r.returncode == 0 or missing:
                bad += 1
                print("FAIL %s: %s" % (bug["name"],
                      "the test PASSES with the bug back" if r.returncode == 0 else
                      "not failing on: " + ", ".join(missing)))
                if r.returncode:
                    # it failed, but not as expected: show why
                    print("\n".join("     | " + l for l in out.strip().splitlines()[-15:]))
            else:
                print("ok   %s (fixed in %s)" % (bug["name"], bug["fixed_in"]))
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=ROOT, capture_output=True)
    print("MUT-002: %d counterexamples failed to fail" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
