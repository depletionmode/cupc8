#!/usr/bin/env python3
"""HOST-003: the lockstep harness itself. A clean run passes; a divergence
injected into the DUT trace (a state line, and a memory-write line) is
caught and reported at exactly that line.

    python3 test/host/test_lockstep.py
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROG = os.path.join(ROOT, "test", "isa", "mem.s")
bad = 0


def lockstep(*extra):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "lockstep.py"), PROG, *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


code, out = lockstep()
if code != 0 or "1 ok, 0 failed" not in out:
    bad += 1
    print("FAIL a clean run did not pass:", out.strip().splitlines()[-1:])

# the reference trace says which lines are state (S) and which are writes (W)
trace = open(os.path.join(ROOT, "build", "lockstep", "prog", "ghdl-w0-s1", "mem.sim.trace")).read().splitlines()
targets = [next(i + 1 for i, l in enumerate(trace) if l.startswith("S ") and i > 5),
           next(i + 1 for i, l in enumerate(trace) if l.startswith("W "))]
for n in targets:
    code, out = lockstep("--inject", str(n))
    m = re.search(r"line (\d+):", out)
    if code == 0 or not m or int(m.group(1)) != n:
        bad += 1
        print("FAIL divergence at line %d reported as %s" % (n, m.group(0) if m else out.strip()[-120:]))

print("HOST-003: lockstep self-test, %d failures" % bad)
sys.exit(1 if bad else 0)
