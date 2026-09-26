#!/usr/bin/env python3
"""SIM-014 (the CLI half): tools/sim --type presses the keys with no
character. tools/testdata/keys_prog.s (--run) prints the byte API_GETKEY gives
for each key as <hh>; the keys are typed as named keys ({UP} .. {F12}) and as
\\xHH escapes, and must give what the real IO card gives (fw/io/core/iocard.h).
The window's path (SDL scancodes as HID usages) and snake steered with the
arrows are tools/simtest.nim testSimKeys and testSnakeExample.

    python3 test/sim/test_keys.py
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cli  # noqa: E402  (build, sim, check)

ROOT = test_cli.ROOT
NAMES = ["UP", "DOWN", "LEFT", "RIGHT", "HOME", "END", "PGUP", "PGDN", "INS", "DEL"] + \
        ["F%d" % n for n in range(1, 13)]
BYTES = [0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x7F] + list(range(0x91, 0x9D))


def main():
    test_cli.build()
    work = tempfile.mkdtemp(prefix="sim-keys-")
    prg = os.path.join(work, "keys_prog.prg")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mkprg.py"),
                    os.path.join(ROOT, "tools", "testdata", "keys_prog.s"), "-o", prg],
                   check=True, capture_output=True)
    want = "".join("<%02X>" % b for b in BYTES)

    typed = "".join("{%s}" % n for n in NAMES) + "q"
    text, out = test_cli.sim("--run:" + prg, "--type:" + typed)
    flat = text.replace("\n", "")
    test_cli.check("--type named keys give the IO card's bytes: " + want, want in flat, out + text)
    test_cli.check("... and q ends the program: the prompt back", text.rstrip().endswith(">>"), text)

    typed = "".join("\\x%02x" % b for b in BYTES) + "{f1}{nope}q"
    text, out = test_cli.sim("--run:" + prg, "--type:" + typed)
    flat = text.replace("\n", "")
    # {nope} is not a key: its six characters are typed as they are
    got = want + "<91>" + "".join("<%02X>" % ord(c) for c in "{nope}")
    test_cli.check("--type \\xHH escapes, a lower-case name, and an unknown {name} as text: " + got,
                   got in flat, out + text)

    if test_cli.failures:
        print("FAILED %d check(s)" % test_cli.failures)
        sys.exit(1)
    print("ALL SIM KEY CHECKS PASSED")


if __name__ == "__main__":
    main()
