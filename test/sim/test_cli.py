#!/usr/bin/env python3
"""SIM-010: the simulator CLI (tools/sim) runs the Milestone 1 machine.

Runs the sim binary headless, typing with --type and reading the console with
--dump-text (and the picture with --dump-fb):
  - the default machine (hdmi,io) boots through the boot ROM to the prompt
    and runs a typed program;
  - hdmi,io,storage,wifi with --sd on an image that does not exist yet (the
    sim makes a blank FAT one): SAVE, NEW, DIR, LOAD, RUN; the image as a PC
    reads it (tools/fatcheck.py); a second run of the sim LOADs it again;
    `net join` any SSID, `net get` from an HTTP server this script runs on
    localhost (the Wi-Fi card uses the host's own sockets);
  - the e-ink cards (eink, eink750): the program runs, and the dumped picture
    (the panel's glass) shows the text;
  - --legacy still runs a program loaded at $1000;
  - SIM-012: --run:PROG runs a program for $7000 (tools/mkprg.py) once the
    kernel is at its prompt, as cupc8.py run does: a .prg and the bare
    binary run and return to the prompt, a header of another version is
    refused; examples/hello ticks once a second of guest time headless, and
    of wall time in the interactive sim (SDL's dummy video driver: the
    real-time loop without a window).

    python3 test/sim/test_cli.py
"""

import atexit
import fcntl
import http.server
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = os.path.join(ROOT, "tools", "sim")
failures = 0


def check(name, cond, detail=""):
    global failures
    if cond:
        print("ok: " + name)
    else:
        failures += 1
        print("FAIL: " + name + (("\n" + detail) if detail else ""))


def build():
    """Build tools/sim (one build at a time: a lock) and run a copy of it of
    this run's own, so a SIM-010 or simtest beside this one cannot replace it."""
    global SIM
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", ".sim.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        r = subprocess.run(["nim", "c", "-d:release", "--hints:off", "sim.nim"],
                           cwd=os.path.join(ROOT, "tools"), capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("building tools/sim failed:\n" + r.stdout + r.stderr)
        own = tempfile.mkdtemp(prefix="sim-cli-bin-")
        atexit.register(shutil.rmtree, own, True)
        SIM = os.path.join(own, "sim")
        shutil.copy2(os.path.join(ROOT, "tools", "sim"), SIM)


def sim(*args, timeout=300):
    """Run the sim headless; (the console's text, the whole output)."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        text_path = f.name
    r = subprocess.run([SIM, "--headless", "--dump-text:" + text_path, *args],
                       capture_output=True, text=True, timeout=timeout)
    text = open(text_path).read() if os.path.exists(text_path) else ""
    os.unlink(text_path)
    return text, r.stdout + r.stderr + "\nexit %d" % r.returncode


SETTLE_BOUND = 200_000_000     # guest instructions: 20 times what a headless run takes to settle


def retired(out):
    """The instructions a headless run retired (its last status line)."""
    m = re.findall(r"retired=(\d+)", out)
    return int(m[-1]) if m else SETTLE_BOUND


def ink_rows(ppm, y0, y1):
    """Dark pixels in rows y0..y1 of a binary PPM."""
    data = open(ppm, "rb").read()
    header_end = 0
    for _ in range(3):                          # P6, size, max value
        header_end = data.index(b"\n", header_end) + 1
    w = int(data.split(b"\n")[1].split()[0])
    px = data[header_end:]
    return sum(1 for y in range(y0, y1) for x in range(w) if px[(y * w + x) * 3] < 0x80)


def pixel(ppm, x, y):
    """(r, g, b) of pixel x, y in a binary PPM."""
    data = open(ppm, "rb").read() if os.path.exists(ppm) else b"P6\n1 1\n255\n\0\0\0"
    header_end = 0
    for _ in range(3):
        header_end = data.index(b"\n", header_end) + 1
    w = int(data.split(b"\n")[1].split()[0])
    i = header_end + (y * w + x) * 3
    return tuple(data[i:i + 3])


def hello_pace(hello, env):
    """examples/hello in the interactive sim: the wall-clock gaps between its
    light's steps (its "second" is ten 100-101 ms waits and its printing:
    1.01 s of guest time), their mean, and the step times."""
    p = subprocess.Popen([SIM, "--run:" + hello], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    os.set_blocking(p.stdout.fileno(), False)
    t0 = time.monotonic()
    buf, started, steps = b"", None, []
    while time.monotonic() - t0 < 30 and len(steps) < 6:
        chunk = p.stdout.read(65536)
        if not chunk:
            time.sleep(0.002)
            continue
        buf += chunk
        *lines, buf = buf.replace(b"\r", b"\n").split(b"\n")
        now = time.monotonic()
        for line in lines:
            s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line.decode(errors="replace"))
            if "API_RUN = 1" in s:
                started = now
            elif started is not None and s.startswith("GPO:"):
                steps.append(now)
    p.kill()
    p.wait()
    gaps = [b - a for a, b in zip(steps, steps[1:])]
    return gaps, (sum(gaps) / len(gaps) if gaps else 0), steps


def wai_pace(img, env):
    """test/sim/waitloop.s (WAI woken every 50 instructions) for 12 s of wall
    time in the interactive sim: the MHz of guest clock on its speed lines."""
    try:
        r = subprocess.run([SIM, "--cards:hdmi,io,storage", "--sd:" + img, '--type:exec "WAIT.PRG"\\n'],
                           capture_output=True, text=True, timeout=12, env=env)
        out = r.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    return [float(m) for m in re.findall(r"([0-9.]+) MHz of CUPC/8 clock", out)], out


class Handler(http.server.BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        Handler.requests.append(self.path)
        body = b"SIM-CLI-OK\r\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    build()
    work = tempfile.mkdtemp(prefix="sim-cli-")
    atexit.register(shutil.rmtree, work, True)

    # the default machine: hdmi,io, booted through the boot ROM
    text, out = sim("--type:10 print 6*7\\nrun\\n")
    check("default machine: the BASIC banner", "CUPC/8 BASIC" in text, out + text)
    check("default machine: the typed program ran", "\n42\n" in text and "DONE." in text, text)

    # typed keys with no IO card to take them: the run still ends. Judged in
    # guest instructions, not wall time (a loaded host once took the 60 s
    # this had): headless it settles in about 10 M; a sim that never settles
    # runs into --max-ins, and the wall-clock timeout only guards a real hang
    try:
        text, out = sim("--cards:hdmi", "--type:help\\n", "--max-ins:%d" % SETTLE_BOUND, timeout=1800)
        check("--type with no IO card: headless still exits (%s instructions)" % retired(out),
              "CUPC/8 BASIC" in text and "exit 0" in out and retired(out) < SETTLE_BOUND, out + text)
    except subprocess.TimeoutExpired:
        check("--type with no IO card: headless still exits", False, "the sim hung")
    # ... and when nothing at all wakes the CPU (a program parked with only
    # the slot IRQ unmasked; the kernel's own wait has the chipset's tick)
    park = os.path.join(work, "park.prg")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mkprg.py"),
                    os.path.join(ROOT, "tools", "testdata", "park.s"), "-o", park], check=True, capture_output=True)
    try:
        text, out = sim("--cards:hdmi", "--run:" + park, "--type:ab", "--max-ins:%d" % SETTLE_BOUND, timeout=1800)
        check("--type at a program parked with nothing to wake it: headless still exits (%s instructions)"
              % retired(out), "CUPC/8 BASIC" in text and "exit 0" in out and retired(out) < SETTLE_BOUND, out + text)
    except subprocess.TimeoutExpired:
        check("--type at a program parked with nothing to wake it: headless still exits", False, "the sim hung")

    # storage: a new image, SAVE / NEW / DIR / LOAD / RUN
    img = os.path.join(work, "card.img")
    cards = "--cards:hdmi,io,storage,wifi"
    text, out = sim(cards, "--sd:" + img,
                    '--type:10 print "from the card"\\n20 print 3*5\\nsave "t.bas"\\nnew\\ndir\\n'
                    'load "t.bas"\\nrun\\n')
    lines = text.split("\n")
    check("a missing --sd image is made (blank FAT)", "made a blank FAT image" in out and os.path.exists(img), out)
    check("SAVE", "SAVED" in lines, text)
    program = '10 print "from the card"\r\n20 print 3*5\r\n'
    check("DIR lists the file and its size", "T.BAS        %d" % len(program) in lines, text)
    check("LOAD", "LOADED" in lines, text)
    check("the loaded program runs", "from the card" in lines and "15" in lines, text)
    expect = os.path.join(work, "expect")
    os.makedirs(expect)
    with open(os.path.join(expect, "T.BAS"), "w", newline="") as f:
        f.write(program)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fatcheck.py"), "check", img, expect],
                       capture_output=True, text=True)
    check("the image is valid FAT with the saved file (fatcheck, fsck.fat)", r.returncode == 0, r.stdout + r.stderr)

    # a second run of the sim: the file is still there; then the network
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    text, out = sim(cards, "--sd:" + img,
                    '--type:load "t.bas"\\nrun\\nnet join anynet anypass\\nnet get 127.0.0.1 %d\\n' % port)
    server.shutdown()
    lines = text.split("\n")
    check("the file LOADs in a new run of the sim", "LOADED" in lines and "from the card" in lines, text)
    check("net join: any SSID joins, the host's address", "joined, address 127.0.0.1" in lines, text)
    check("net get: the local server got the request", Handler.requests == ["/"], str(Handler.requests))
    check("net get: the reply is on the screen", "HTTP/1.0 200 OK" in lines and "SIM-CLI-OK" in lines, text)
    text, out = sim("--cards:hdmi,io,wifi", "--type:net join anynet anypass\\nnet config\\nnet ping 127.0.0.1 2\\n")
    check("net config: the card's settings", "mode dhcp" in text, text)
    check("net ping 127.0.0.1 2: two replies, times from the ms counter",
          re.search(r"seq 1 time \d+ ms", text) and re.search(r"seq 2 time \d+ ms", text)
          and "2 sent, 2 received" in text, text)

    # the e-ink cards: text model and the glass
    for kind in ("eink", "eink750"):
        ppm = os.path.join(work, kind + ".ppm")
        text, out = sim("--cards:%s,io" % kind, "--dump-fb:" + ppm, "--type:10 print 6*7\\nrun\\n")
        check(kind + ": the program ran", "\n42\n" in text and "DONE." in text, out + text)
        # rows 0-7 of text are 16 px each: the banner (row 1), the typed lines and 42
        check(kind + ": the text is on the glass", ink_rows(ppm, 16, 128) > 500, ppm)

    # BASIC graphics (doc/proposals/basic-graphics.md) through the kernel on
    # the sim's cards: GFX mode on hdmi (the ended program keeps its picture
    # while it waits for a key), mode 2 on the e-ink panel after a
    # greyscale refresh
    ppm = os.path.join(work, "gfx.ppm")
    text, out = sim("--cards:hdmi,io", "--dump-fb:" + ppm,
                    "--type:10 mode 1\\n20 cls 1\\n30 box 20, 20, 60, 40, 196, 1\\nrun\\n")
    red, blue = pixel(ppm, 100, 80), pixel(ppm, 20, 20)
    check("hdmi: mode 1, cls 1, a filled box in 196: red in it %s, VGA blue around it %s" % (red, blue),
          red[0] > 240 and red[1] < 16 and red[2] < 16 and blue[0] < 16 and blue[1] < 16 and 160 < blue[2] < 180,
          out + text)
    ppm = os.path.join(work, "grey.ppm")
    text, out = sim("--cards:eink,io", "--dump-fb:" + ppm,
                    "--type:10 mode 2\\n20 cls\\n30 box 20, 20, 100, 60, 0, 1\\n40 box 140, 20, 100, 60, 1, 1\\n"
                    "50 box 260, 20, 100, 60, 2, 1\\n60 refresh\\nrun\\n")
    greys = [pixel(ppm, x, 50)[0] for x in (70, 190, 310, 500)]
    check("eink: mode 2, boxes in greys 0, 1, 2 on white, refresh: the four greys on the glass %s" % greys,
          greys == [0, 85, 170, 255], out + text)

    # the whole panel in the picture: 648 or 800 wide, as the emulator shows it;
    # a box in mode 2 at x 790 on the 7.5" panel
    ppm = os.path.join(work, "wide.ppm")
    text, out = sim("--cards:eink750,io", "--dump-fb:" + ppm,
                    "--type:10 mode 2\\n20 cls\\n30 box 780, 460, 20, 20, 0, 1\\n40 plot 5, 5, 1\\n50 refresh\\nrun\\n")
    size = open(ppm, "rb").read().split(b"\n")[1] if os.path.exists(ppm) else b""
    check("eink750: the picture is the whole 800 x 480 panel (%s)" % size.decode(), size == b"800 480", out)
    got = [pixel(ppm, x, y)[0] for x, y in ((790, 470), (799, 479), (779, 470), (5, 5))]
    check("eink750: mode 2 drawn at x 790 (and to the corner) is in --dump-fb %s" % got, got == [0, 0, 255, 85], out + text)
    text, out = sim("--cards:eink,io", "--dump-fb:" + ppm, "--type:10 print 1\\nrun\\n")
    size = open(ppm, "rb").read().split(b"\n")[1] if os.path.exists(ppm) else b""
    check("eink: the picture is the whole 648 x 480 panel (%s)" % size.decode(), size == b"648 480", out)

    # SIM-012: --run
    def mkprg(src, dest):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mkprg.py"), os.path.join(ROOT, src),
                        "-o", dest], check=True, capture_output=True)
    prg = os.path.join(work, "exec_prog.prg")
    mkprg("tools/testdata/exec_prog.s", prg)
    text, out = sim("--run:" + prg)
    check("--run a .prg: it runs and the prompt is back", "NATIVE OK" in text and text.rstrip().endswith(">>")
          and "exit 0" in out, out + text)
    raw = os.path.join(work, "exec_prog.bin")
    with open(raw, "wb") as f:
        f.write(open(prg, "rb").read()[4:])
    text, out = sim("--run:" + raw)
    check("--run the bare binary", "NATIVE OK" in text, out + text)
    bad = os.path.join(work, "v2.prg")
    with open(bad, "wb") as f:
        f.write(b"C8P\x02" + open(prg, "rb").read()[4:])
    text, out = sim("--run:" + bad)
    check("--run refuses a header of another version", "not a program for $7000" in out and "exit 1" in out
          and "NATIVE OK" not in text, out)
    hello = os.path.join(work, "hello.prg")
    mkprg("examples/hello/hello.s", hello)
    text, out = sim("--run:" + hello, "--max-ins:8000000")
    ms = re.search(r"ms=(\d+)", out)
    secs = re.findall(r"seconds (\d{3})", text)
    check("--run examples/hello headless: it counts seconds (%s at %s ms)" % (secs[-1:], ms and ms.group(1)),
          "Hello from a native CUPC/8 program!" in text and secs and int(secs[-1]) >= 6 and ms, out + text)
    # the interactive sim holds guest time to the host clock: hello's light
    # steps once a second of wall time (its "second" is ten 100-101 ms waits
    # and its printing: 1.01 s of guest time)
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    for attempt in (1, 2):
        gaps, mean, steps = hello_pace(hello, env)
        if len(gaps) >= 5 and 0.98 <= mean <= 1.04:
            break
        print("   (the interactive sim fell off the wall clock, attempt %d: a loaded host?)" % attempt)
    check("the interactive sim: hello steps once a wall-clock second (%s s)" % ", ".join("%.3f" % g for g in gaps),
          len(gaps) >= 5 and 0.98 <= mean <= 1.04, "%d steps" % len(steps))
    # interactive pacing: a machine woken from WAI every 50 instructions must
    # still run at about 1 MHz (the sim once slept a millisecond per WAI: 0.17)
    prg = os.path.join(work, "WAIT.PRG")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mkprg.py"),
                    os.path.join(ROOT, "test", "sim", "waitloop.s"), "-o", prg], check=True, capture_output=True)
    img2 = os.path.join(work, "pace.img")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fatcheck.py"), "blank", img2, "2048"],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fatcheck.py"), "put", img2, "WAIT.PRG", prg],
                   check=True, capture_output=True)
    for attempt in (1, 2):
        mhz, out = wai_pace(img2, env)
        if len(mhz) >= 3 and all(11 <= x <= 13 for x in mhz[-3:]):
            break
        print("   (the interactive sim fell off the wall clock, attempt %d: a loaded host?)" % attempt)
    check("interactive: a WAI-heavy guest keeps its 12 MHz clock (last %s)" % (mhz[-3:],),
          len(mhz) >= 3 and all(11 <= x <= 13 for x in mhz[-3:]), out[-400:])


    # the window's GPO LED strip: D8..D1 under the picture, lit from $f000
    win = os.path.join(work, "win.ppm")
    env = dict(os.environ, SDL_VIDEODRIVER="offscreen", SDL_AUDIODRIVER="dummy")
    subprocess.run([SIM, "--cards:hdmi,io", "--type:10 poke 240,0,165\\nrun\\n", "--max-ins:20000000",
                    "--dump-window:" + win], capture_output=True, text=True, timeout=600, env=env)
    lights = ""
    if os.path.exists(win):
        d = open(win, "rb").read()
        parts = d.split(b"\n", 3)
        w, h = map(int, parts[1].split())
        y, x0 = h - 14, (w - (8 * 14 + 7 * 12)) // 2
        lights = "".join("1" if parts[3][(y * w + x0 + i * 26 + 7) * 3] > 200 else "0" for i in range(8))
    check("the window's LED strip shows GPO $A5 as 10100101 (%s)" % lights, lights == "10100101")

    # the old I/O model
    obj = os.path.join(work, "gpo.o")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "as.py"),
                    os.path.join(ROOT, "test", "gpo-test.s"), obj], check=True, capture_output=True)
    r = subprocess.run([SIM, "--legacy", "--headless", obj], capture_output=True, text=True, timeout=600)
    check("--legacy runs a program at $1000", "GPO: 10101010 AA" in r.stdout and "hf=true" in r.stdout, r.stdout)

    if failures:
        print("FAILED %d check(s)" % failures)
        sys.exit(1)
    print("ALL SIM CLI CHECKS PASSED")


if __name__ == "__main__":
    main()
