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
  - --legacy still runs a program loaded at $1000.

    python3 test/sim/test_cli.py
"""

import http.server
import os
import subprocess
import sys
import tempfile
import threading

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
    r = subprocess.run(["nim", "c", "-d:release", "--hints:off", "sim.nim"],
                       cwd=os.path.join(ROOT, "tools"), capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("building tools/sim failed:\n" + r.stdout + r.stderr)


def sim(*args, timeout=300):
    """Run the sim headless; (the console's text, the whole output)."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        text_path = f.name
    r = subprocess.run([SIM, "--headless", "--dump-text:" + text_path, *args],
                       capture_output=True, text=True, timeout=timeout)
    text = open(text_path).read() if os.path.exists(text_path) else ""
    os.unlink(text_path)
    return text, r.stdout + r.stderr + "\nexit %d" % r.returncode


def ink_rows(ppm, y0, y1):
    """Dark pixels in rows y0..y1 of a binary PPM."""
    data = open(ppm, "rb").read()
    header_end = 0
    for _ in range(3):                          # P6, size, max value
        header_end = data.index(b"\n", header_end) + 1
    w = int(data.split(b"\n")[1].split()[0])
    px = data[header_end:]
    return sum(1 for y in range(y0, y1) for x in range(w) if px[(y * w + x) * 3] < 0x80)


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

    # the default machine: hdmi,io, booted through the boot ROM
    text, out = sim("--type:10 print 6*7\\nrun\\n")
    check("default machine: the BASIC banner", "CUPC/8 BASIC" in text, out + text)
    check("default machine: the typed program ran", "\n42\n" in text and "DONE." in text, text)

    # typed keys with no IO card to take them: the run still ends
    try:
        text, out = sim("--cards:hdmi", "--type:help\\n", timeout=60)
        check("--type with no IO card: headless still exits", "CUPC/8 BASIC" in text, out + text)
    except subprocess.TimeoutExpired:
        check("--type with no IO card: headless still exits", False, "the sim hung")

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

    # the e-ink cards: text model and the glass
    for kind in ("eink", "eink750"):
        ppm = os.path.join(work, kind + ".ppm")
        text, out = sim("--cards:%s,io" % kind, "--dump-fb:" + ppm, "--type:10 print 6*7\\nrun\\n")
        check(kind + ": the program ran", "\n42\n" in text and "DONE." in text, out + text)
        # rows 0-7 of text are 16 px each: the banner (row 1), the typed lines and 42
        check(kind + ": the text is on the glass", ink_rows(ppm, 16, 128) > 500, ppm)

    # the old I/O model
    obj = os.path.join(work, "gpo.o")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "as.py"),
                    os.path.join(ROOT, "test", "gpo-test.s"), obj], check=True, capture_output=True)
    r = subprocess.run([SIM, "--legacy", "--headless", obj], capture_output=True, text=True, timeout=60)
    check("--legacy runs a program at $1000", "GPO: 10101010 AA" in r.stdout and "hf=true" in r.stdout, r.stdout)

    if failures:
        print("FAILED %d check(s)" % failures)
        sys.exit(1)
    print("ALL SIM CLI CHECKS PASSED")


if __name__ == "__main__":
    main()
