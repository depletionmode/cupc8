#!/usr/bin/env python3
"""Check the QEMU settle wakeup contract used by the MUT-002 counterexample.

The network integration run alone cannot reliably expose a missing wakeup:
other QEMU events may happen to turn the main loop during the settle window.
"""

from pathlib import Path
import re


patch = (Path(__file__).resolve().parents[2] /
         "tools/patches/qemu-esp-lockstep.patch").read_text()
match = re.search(r"^\+static void net_settle\(void\)\n(?P<body>.*?)(?=^\+static void |\Z)",
                  patch, re.MULTILINE | re.DOTALL)
body = re.sub(r"/\*.*?\*/", "", match.group("body") if match else "",
              flags=re.DOTALL)
operations = [body.find(s) for s in ("bql_unlock();", "qemu_notify_event();",
                                     "for (;;)", "bql_lock();")]
if any(i < 0 for i in operations) or operations != sorted(operations):
    raise SystemExit("FAIL: net_settle must wake QEMU's main loop after releasing "
                     "the BQL and before waiting for a network reply")

print("lockstep wakeup: PASS")
