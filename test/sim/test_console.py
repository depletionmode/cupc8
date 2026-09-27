#!/usr/bin/env python3
"""SIM-020: tools/sim --console, the USB console's rings on the terminal the
simulator runs in (doc/proposals/usb-console.md), as the system card carries
them to a PC.

  - stdin a pipe (headless): the banner comes out on stdout with CR LF; typed
    lines (LF ends) reach the prompt and BASIC, their echo and output come
    back, the program's output is on the graphics card too; the sim's own
    status line goes to stderr, not into the console's stream; it exits once
    stdin has ended and the machine is quiet.
  - stdin a terminal (a pty): raw, key by key (no line discipline: a CR is
    Enter), and Ctrl-] quits with the terminal's settings put back.

    python3 test/sim/test_console.py        (builds tools/sim)
"""

import os
import pty
import select
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(ROOT, "tools")
SIM = os.path.join(TOOLS, "sim")
failures = 0


def check(name, cond, detail=""):
    global failures
    if cond:
        print("ok:", name)
    else:
        failures += 1
        print("FAIL:", name)
        if detail:
            print("   ", repr(detail)[:600])


def main():
    r = subprocess.run(["nim", "c", "-d:release", "--hints:off", "sim.nim"], cwd=TOOLS,
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout + r.stderr)
        sys.exit(1)
    work = os.path.join(ROOT, "build", "sim-console")
    os.makedirs(work, exist_ok=True)
    text = os.path.join(work, "screen.txt")

    # ---------------------------------------------------------------- a pipe
    typed = b"10 for i = 1 to 3\n20 print i * 7\n30 next i\nhelp\nrun\n"
    r = subprocess.run([SIM, "--headless", "--console", "--settle:500", "--dump-text:" + text],
                       input=typed, capture_output=True, timeout=300)
    out, err = r.stdout, r.stderr.decode(errors="replace")
    check("exits once stdin has ended and the machine is quiet", r.returncode == 0, err)
    check("the banner and the prompt on stdout", b"CUPC/8 BASIC" in out and b">> " in out, out)
    check("newlines as CR LF, and only so", b"\r\n" in out and b"\n" not in out.replace(b"\r\n", b""), out)
    check("typed lines echoed at the prompt", b">> 10 for i = 1 to 3\r\n" in out and b">> help\r\n" in out, out)
    check("help typed on stdin runs", b"NEW RUN LIST CLR" in out, out)
    check("the BASIC program typed on stdin runs", b">> run\r\n7\r\n14\r\n21\r\n" in out and b"DONE." in out, out)
    screen = open(text).read() if os.path.exists(text) else ""
    check("the same on the graphics card", "14" in screen and "21" in screen and "DONE." in screen, screen)
    check("the sim's status line on stderr, not in the console's stream",
          "retired=" in err and b"retired=" not in out, err)
    check("no escape codes in the console's stream", b"\x1b" not in out, out)

    # ------------------------------------------------------------- a terminal
    master, slave = pty.openpty()
    before = termios.tcgetattr(slave)
    p = subprocess.Popen([SIM, "--headless", "--console"], stdin=slave, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    got = b""

    def read_until(want, secs):
        nonlocal got
        end = time.time() + secs
        while want not in got and time.time() < end:
            if select.select([p.stdout], [], [], 0.2)[0]:
                chunk = os.read(p.stdout.fileno(), 4096)
                if not chunk:
                    break
                got += chunk
        return want in got

    check("terminal: the prompt", read_until(b">> ", 120), got)
    time.sleep(0.3)
    for ch in b"print 5*5\r":
        os.write(master, bytes([ch]))
        time.sleep(0.02)
    check("terminal: raw keys, CR as Enter", read_until(b"print 5*5\r\n", 60), got)
    raw = termios.tcgetattr(slave)
    check("terminal: raw while it runs (no ICANON, no ECHO)",
          not raw[3] & termios.ICANON and not raw[3] & termios.ECHO, raw[3])
    os.write(master, b"\x1d")
    try:
        rc = p.wait(30)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = None
    check("terminal: Ctrl-] quits", rc == 0, rc)
    after = termios.tcgetattr(slave)
    check("terminal: its settings put back", after[3] == before[3] and after[0] == before[0], (before, after))
    os.close(master)
    os.close(slave)

    if failures:
        print("FAILED %d check(s)" % failures)
        sys.exit(1)
    print("SIM-020: ALL CONSOLE CHECKS PASSED")


if __name__ == "__main__":
    main()
