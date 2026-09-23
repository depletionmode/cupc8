#!/usr/bin/env python3
"""HOST-001: hw/tools/jlcparts.py parses JLC's parts API, reports basic vs
extended parts and stock, and fails on a missing or short part. Runs on
responses recorded from the real API (test/host/jlc_recorded/), so it is
repeatable and offline; re-record with JLCPARTS_RECORD=test/host/jlc_recorded.

    python3 test/host/test_jlcparts.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOL = os.path.join(ROOT, "hw", "tools", "jlcparts.py")
ENV = dict(os.environ, JLCPARTS_RECORDED=os.path.join(HERE, "jlc_recorded"))

bad = 0


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout


def expect(cond, what):
    global bad
    if not cond:
        bad += 1
        print("FAIL", what)


code, out = run("check", "C165948")
cols = out.split()
expect(code == 0 and cols[:3] == ["C165948", "ext", "103639"], "an extended part: %r" % out)

code, out = run("check", "C23186")
expect(code == 0 and out.split()[1] == "basic", "a basic part: %r" % out)

code, out = run("check", "C165948", "C9999999999")
expect(code == 1 and "C9999999999 NOT FOUND" in out and "C165948" in out, "a missing part fails the check")

code, out = run("check", "C165948", "--min-stock", "200000")
expect(code == 1 and "SHORT" in out, "a part below --min-stock fails the check")

code, out = run("search", "SST39VF040", "-n", "5")
lines = out.splitlines()
expect(code == 0 and len(lines) == 5 and any(l.startswith("C645939") for l in lines), "search: %d lines" % len(lines))

print("HOST-001: jlcparts.py, %d failures" % bad)
sys.exit(1 if bad else 0)
