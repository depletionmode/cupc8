#!/usr/bin/env python3
"""IOC-002: record a real keyboard for the IO card's replay test.

    sudo python3 tools/kbdrecord.py [--list] [--device /dev/hidrawN] [--name NAME]

Reads the keyboard's raw HID reports (/dev/hidraw*, which needs root) while
you type a few prompts into this terminal. What the terminal receives is the
ground truth for what you typed; the reports are what the keyboard sent.
Both go into test/io/recordings/NAME.rec, with each report also converted to
the 8-byte boot format the IO card asks keyboards for (using the keyboard's
own report descriptor). test/io/test_recorded.c replays the boot reports
through the IO core and requires exactly the typed text.

Rules while recording: US layout; don't hold keys down (no auto-repeat); if
you make a mistake press Ctrl-C and that prompt starts again.
"""

import argparse
import glob
import os
import select
import sys
import termios
import time
import tty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "test", "io", "recordings")

# (prompt, expected bytes or None). None: what the terminal received is the
# truth. The Caps Lock prompt has fixed text: desktops remap Caps Lock (the
# first recording's terminal lost "HELLO W"), and the card does its own.
CAPS_PROMPT = "Press Caps Lock, type hello, press Caps Lock again, then type World"
PROMPTS = [
    ("The quick brown fox jumps over the lazy dog.", None),
    ("Sphinx of black quartz, judge my vow? 1234567890 [a-b] 'ok' (x=y+z)", None),
    (CAPS_PROMPT, b"HELLOWorld\r"),
    ("Type asdf jkl; five times as fast as you can, rolling your fingers", None),
    ("Shift-type ALL CAPS then lower case: TESTING testing 42!", None),
]


# ------------------------------------------------------------ HID descriptors

def parse_descriptor(desc):
    """Input fields of every keyboard application collection (Generic
    Desktop / Keyboard), as dicts: report id, bit offset, size, count, usage
    page, usages (list or (min, max)), variable, logical min."""
    fields, stack, gstack = [], [], []
    g = {"page": 0, "lmin": 0, "size": 0, "count": 0, "id": 0}
    local = {"usages": [], "min": None, "max": None}
    offsets = {}
    app = []                     # stack of (page, usage) of open collections
    i = 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:            # long item
            i += 3 + desc[i + 1]
            continue
        n = [0, 1, 2, 4][b & 3]
        data = int.from_bytes(bytes(desc[i + 1:i + 1 + n]), "little")
        sdata = data - (1 << (8 * n)) if n and data >> (8 * n - 1) else data
        kind, tag = (b >> 2) & 3, b >> 4
        i += 1 + n
        if kind == 1:            # global
            if tag == 0: g["page"] = data
            elif tag == 1: g["lmin"] = sdata
            elif tag == 7: g["size"] = data
            elif tag == 8: g["id"] = data
            elif tag == 9: g["count"] = data
            elif tag == 10: gstack.append(dict(g))
            elif tag == 11: g = gstack.pop()
            continue
        if kind == 2:            # local
            full = data if n == 4 else (g["page"] << 16) | data
            if tag == 0: local["usages"].append(full)
            elif tag == 1: local["min"] = full
            elif tag == 2: local["max"] = full
            continue
        if kind == 0:            # main
            if tag == 10:        # collection
                u = local["usages"][0] if local["usages"] else 0
                app.append(u)
            elif tag == 12 and app:
                app.pop()
            elif tag in (8, 9, 11):
                rid = g["id"]
                off = offsets.get((tag, rid), 0)
                if tag == 8 and 0x00010006 in app and not data & 1:
                    usages = ((local["min"], local["max"]) if local["min"] is not None
                              else list(local["usages"]))
                    fields.append({"id": rid, "off": off, "size": g["size"], "count": g["count"],
                                   "usages": usages, "var": bool(data & 2), "lmin": g["lmin"]})
                offsets[(tag, rid)] = off + g["size"] * g["count"]
            local = {"usages": [], "min": None, "max": None}
    return fields


def bits(report, off, size):
    v = 0
    for k in range(size):
        byte, bit = divmod(off + k, 8)
        if byte < len(report) and report[byte] >> bit & 1:
            v |= 1 << k
    return v


def pressed(fields, report):
    """(modifier byte, set of key usages, rollover) from one input report"""
    numbered = any(f["id"] for f in fields)
    rid = report[0] if numbered else 0
    body = report[1:] if numbered else report
    mods, keys, rollover = 0, set(), False
    for f in fields:
        if f["id"] != rid:
            continue
        for k in range(f["count"]):
            v = bits(body, f["off"] + k * f["size"], f["size"])
            if f["var"]:
                if not v:
                    continue
                u = (f["usages"][0] + k if isinstance(f["usages"], tuple)
                     else f["usages"][min(k, len(f["usages"]) - 1)])
            else:
                if isinstance(f["usages"], tuple):
                    u = f["usages"][0] + v - f["lmin"]
                else:
                    u = f["usages"][v - f["lmin"]] if 0 <= v - f["lmin"] < len(f["usages"]) else 0
            if u >> 16 != 7:
                continue
            u &= 0xffff
            if 0xE0 <= u <= 0xE7:
                mods |= 1 << (u - 0xE0)
            elif u in (1, 2, 3):
                rollover = True
            elif u:
                keys.add(u)
    return mods, keys, rollover


class BootConverter:
    """Keeps keys in the order they went down, as boot keyboards do."""

    def __init__(self):
        self.order = []

    def convert(self, mods, keys, rollover):
        if rollover or len(keys) > 6:
            return bytes([mods, 0] + [1] * 6)
        self.order = [k for k in self.order if k in keys] + sorted(k for k in keys if k not in self.order)
        return bytes([mods, 0] + self.order + [0] * (6 - len(self.order)))


def keyboards():
    found = []
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            desc = open(os.path.join(path, "device", "report_descriptor"), "rb").read()
            name = [l.split("=", 1)[1].strip() for l in open(os.path.join(path, "device", "uevent"))
                    if l.startswith("HID_NAME=")][0]
            ident = [l.split("=", 1)[1].strip() for l in open(os.path.join(path, "device", "uevent"))
                     if l.startswith("HID_ID=")][0]
        except (OSError, IndexError):
            continue
        fields = parse_descriptor(desc)
        if any(isinstance(f["usages"], tuple) and f["usages"][0] >> 16 == 7 or
               isinstance(f["usages"], list) and any(u >> 16 == 7 for u in f["usages"]) for f in fields):
            found.append(("/dev/" + os.path.basename(path), name, ident, desc, fields))
    return found


# ------------------------------------------------------------ recording

def record_prompt(fds, prompt):
    """One prompt: returns (typed bytes, [(ms, interface, raw report)]) or None to retry."""
    print("\r\n\r\n  %s\r\n> " % prompt, end="", flush=True)
    typed, raw, t0 = bytearray(), [], time.monotonic()
    stdin = sys.stdin.fileno()
    while True:
        r, _, _ = select.select(fds + [stdin], [], [])
        for i, fd in enumerate(fds):
            if fd in r:
                raw.append((int((time.monotonic() - t0) * 1000), i, os.read(fd, 64)))
        if stdin in r:
            b = os.read(stdin, 64)
            if b"\x03" in b:
                print("\r\n  (again)", end="", flush=True)
                return None
            typed += b
            os.write(sys.stdout.fileno(), b.replace(b"\r", b""))
            if b"\r" in b:
                # let the Enter key's release arrive
                end = time.monotonic() + 0.3
                while time.monotonic() < end:
                    r, _, _ = select.select(fds, [], [], max(0, end - time.monotonic()))
                    for i, fd in enumerate(fds):
                        if fd in r:
                            raw.append((int((time.monotonic() - t0) * 1000), i, os.read(fd, 64)))
                return bytes(typed), raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--device")
    ap.add_argument("--name")
    args = ap.parse_args()
    kbds = keyboards()
    if args.list or not args.device:
        for dev, name, ident, _, fields in kbds:
            print("%-14s %-40s %s  (%d keyboard fields)" % (dev, name, ident, len(fields)))
        if not args.device:
            print("\nrun: sudo python3 tools/kbdrecord.py --device /dev/hidrawN --name some-keyboard")
        return 0
    chosen = [k for k in kbds if k[0] == args.device]
    if not chosen:
        sys.exit("%s is not a keyboard interface (see --list)" % args.device)
    # every keyboard interface of the same device: keys may come on any of them
    ifaces = [k for k in kbds if k[2] == chosen[0][2]]
    name, ident = chosen[0][1], chosen[0][2]
    label = args.name or name.strip().replace(" ", "-").replace("@", "-").lower()
    fds = [os.open(k[0], os.O_RDONLY) for k in ifaces]
    old = termios.tcgetattr(sys.stdin)
    lines = ["# IOC-002 recording: %s (HID_ID %s), interfaces %s" % (name.strip(), ident, " ".join(k[0] for k in ifaces))]
    lines += ["# descriptor %d %s" % (i, k[3].hex()) for i, k in enumerate(ifaces)]
    try:
        tty.setraw(sys.stdin.fileno())
        print("Recording %s. Type each prompt and press Enter. Ctrl-C redoes a prompt.\r" % name)
        for prompt, fixed in PROMPTS:
            got = None
            while got is None:
                got = record_prompt(fds, prompt)
            typed, raw = got
            conv = BootConverter()
            state = [(0, set(), False)] * len(ifaces)     # per interface
            lines.append("prompt " + prompt)
            lines.append("expect " + (fixed or typed).hex())
            for ms, i, rep in raw:
                state[i] = pressed(ifaces[i][4], rep)
                mods = 0
                keys, roll = set(), False
                for m, k, r in state:
                    mods |= m
                    keys |= k
                    roll |= r
                lines.append("raw %d %d %s" % (ms, i, rep.hex()))
                lines.append("boot %d %s" % (ms, conv.convert(mods, keys, roll).hex()))
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        for fd in fds:
            os.close(fd)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, label + ".rec")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    if os.environ.get("SUDO_UID"):
        os.chown(path, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
    print("\nwrote %s (%d prompts)" % (os.path.relpath(path, ROOT), len(PROMPTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
