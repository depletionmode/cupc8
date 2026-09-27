#!/usr/bin/env python3
"""mkprg.py: build a CUPC/8 program for $7000 (doc/proposals/kernel-api.md).

    mkprg.py prog.s -o prog.prg      assemble (kernel/api.inc in front), then wrap
    mkprg.py a.s b.s ... -o prog.prg the sources one after the other (a.s has main)
    mkprg.py prog.bin -o prog.prg    wrap a binary already assembled for $7000

--map FILE keeps the assembler's map (addresses of the labels, lines).

A program file is a 4-byte header, "C8P" and version 1, then the body: a
flat binary loaded at $7000 and called there (the assembler puts `b main`
first). Up to 28 KB, $7000-$dfff, bss included. `exec "NAME"` runs it from
the storage card; `cupc8.py run prog.prg` (or the bare .bin) from the PC.

The source calls the kernel through the names in kernel/api.inc
(push pch / push pcl / b API_PUTC). Its data follows the code and its bss
the data; both bases are found with a first assembly.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE, END = 0x7000, 0xE000
HEADER = b"C8P\x01"


def assemble(merged, out, data, bss):
    mapf = out + ".map"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "as.py"), merged, out,
                        "0x%x,0x%x,0x%x" % (BASE, data, bss), "--map=" + mapf],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("mkprg.py: the assembler failed:\n" + (r.stderr or r.stdout)[-2000:])
    last, data_len, bss_end = BASE, 0, bss
    for line in open(mapf):
        f = line.split()
        if f[0] == "line":
            last = max(last, int(f[1], 16))
        elif f[0] == "data":
            data_len += int(f[2])
        elif f[0] == "bss":
            bss_end = max(bss_end, int(f[1], 16) + int(f[2]))
    return open(out, "rb").read(), last, data_len, bss_end


def build(srcs, map_path=None):
    with tempfile.TemporaryDirectory() as tmp:
        merged = os.path.join(tmp, "prog.ss")
        with open(merged, "w") as f:
            f.write("; @file api.inc\n" + open(os.path.join(ROOT, "kernel", "api.inc")).read() + "\n")
            for src in srcs:
                f.write("; @file %s\n" % os.path.basename(src) + open(src).read() + "\n")
        out = os.path.join(tmp, "prog.o")
        # the first pass finds where the code ends (its last instruction is at
        # most 3 bytes long); the data goes right after, the bss after that
        _, last, data_len, _ = assemble(merged, out, END, END)
        data = last + 3
        body, _, _, bss_end = assemble(merged, out, data, data + data_len)
        if map_path:
            shutil.copyfile(out + ".map", map_path)
    if bss_end > END:
        sys.exit("mkprg.py: the program needs $%04x-$%04x, past $%04x" % (BASE, bss_end - 1, END - 1))
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", nargs="+", help="prog.s (assembled; several are joined) or prog.bin (for $7000)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--map", help="write the assembler's map here")
    a = ap.parse_args()
    if all(s.endswith(".s") for s in a.input):
        body = build(a.input, a.map)
    elif len(a.input) == 1:
        body = open(a.input[0], "rb").read()
    else:
        sys.exit("mkprg.py: several inputs must all be .s sources")
    if body.startswith(HEADER[:3]):
        sys.exit("mkprg.py: %s already has a header" % a.input[0])
    if len(body) > END - BASE:
        sys.exit("mkprg.py: %d bytes, more than the %d from $7000 to $dfff" % (len(body), END - BASE))
    with open(a.output, "wb") as f:
        f.write(HEADER + body)
    print("%s: %d bytes at $7000" % (a.output, len(body)))


if __name__ == "__main__":
    main()
