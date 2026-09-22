#!/usr/bin/env python3
"""Lockstep test: VHDL CPU (GHDL) vs sim.nim, instruction by instruction.

Assembles every test program, runs it through tools/simtrace (reference) and
soc/tb/tb_cpu_trace.vhd, and diffs the traces. Verification row 1.2.

  lockstep.py                 run all programs
  lockstep.py FILE.s ...      run the given programs
  lockstep.py --waits N       every bus cycle gets N wait states
  lockstep.py --waits -1 --seed S   random 0..15 wait states per cycle

Programs that touch SPI ($f1xx) are skipped: the SPI devices live in the
chipset, which this CPU-only testbench does not model.
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "lockstep")
GHDL_WORK = os.path.join(BUILD, "ghdl")    # GHDL objects (e.g. alu.o) must not
PROGS = os.path.join(BUILD, "prog")        # collide with assembled programs
OSS = "/opt/oss-cad-suite/bin"
SPI_RE = re.compile(r"\$f1[0-9a-f]{2}", re.I)
VHDL = ["soc/alu.vhd", "soc/cpu.vhd", "soc/tb/tb_cpu_trace.vhd"]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def build():
    os.makedirs(GHDL_WORK, exist_ok=True)
    os.makedirs(PROGS, exist_ok=True)
    r = run(["nim", "c", "--hints:off", "-d:release", "-o:" + os.path.join(BUILD, "simtrace"),
             os.path.join(ROOT, "tools", "simtrace.nim")])
    if r.returncode:
        sys.exit("simtrace build failed:\n" + r.stdout + r.stderr)
    ghdl = os.path.join(OSS, "ghdl")
    for step in (["-a", "--std=08", "-fsynopsys"] + [os.path.join(ROOT, f) for f in VHDL],
                 ["-e", "--std=08", "-fsynopsys", "tb_cpu_trace"]):
        r = run([ghdl] + step, cwd=GHDL_WORK)
        if r.returncode:
            sys.exit("ghdl %s failed:\n%s%s" % (step[0], r.stdout, r.stderr))


def trace_lines(text):
    return [l for l in text.splitlines() if l[:2] in ("S ", "W ", "E ")]


def check(src, waits, seed):
    name = os.path.splitext(os.path.basename(src))[0]
    with open(src) as f:
        if SPI_RE.search(f.read()):
            return "skip", "uses SPI (needs the chipset model)"
    obj = os.path.join(PROGS, name + ".o")
    r = run(["python3", os.path.join(ROOT, "tools", "as.py"), src, obj])
    if r.returncode or not os.path.exists(obj):
        return "skip", "does not assemble"
    return compare_image(obj, waits, seed)


def compare_image(obj, waits=0, seed=1, max_steps=100000):
    """Run a binary image (loaded at $1000) on both models and diff the traces.
    Returns (status, message); the traces are left next to the image."""
    base = os.path.splitext(obj)[0]
    image = open(obj, "rb").read()
    hexf = base + ".hex"
    with open(hexf, "w") as f:
        f.write("\n".join("%02x" % b for b in image) + "\n")

    ref = trace_lines(run([os.path.join(BUILD, "simtrace"), obj, str(max_steps)]).stdout)
    r = run([os.path.join(OSS, "ghdl"), "-r", "--std=08", "-fsynopsys", "tb_cpu_trace",
             "-gIMAGE=" + hexf, "-gWAITS=%d" % waits, "-gSEED=%d" % seed,
             "--ieee-asserts=disable"], cwd=GHDL_WORK, timeout=1200)
    if r.returncode:
        return "FAIL", "testbench error: " + (r.stdout + r.stderr).strip().splitlines()[-1]
    dut = trace_lines(r.stdout)
    with open(base + ".sim.trace", "w") as f:
        f.write("\n".join(ref) + "\n")
    with open(base + ".vhdl.trace", "w") as f:
        f.write("\n".join(dut) + "\n")

    if ref and ref[-1] == "E limit":
        # the program never stops: compare the prefix the reference produced
        ref = ref[:-1]
        dut = dut[:len(ref)]
    for i, (a, b) in enumerate(zip(ref, dut)):
        if a != b:
            ctx = ref[max(0, i - 4):i]
            msg = "line %d: sim %r != vhdl %r" % (i + 1, a, b)
            msg += "\n      context (sim): " + " | ".join(ctx)
            return "FAIL", msg
    if len(ref) != len(dut):
        return "FAIL", "length: sim %d lines, vhdl %d lines (last sim %r, last vhdl %r)" % (
            len(ref), len(dut), ref[-1:], dut[-1:])
    instrs = sum(1 for l in ref if l.startswith("S "))
    return "ok", "%d instructions, %s" % (instrs, ref[-1] if ref else "no trace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--waits", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    files = args.files or sorted(glob.glob(os.path.join(ROOT, "tools", "testdata", "*.s")) +
                                 glob.glob(os.path.join(ROOT, "test", "*.s")))
    build()
    counts = {"ok": 0, "FAIL": 0, "skip": 0}
    for src in files:
        status, msg = check(os.path.abspath(src), args.waits, args.seed)
        counts[status] += 1
        print("%-5s %-22s %s" % (status, os.path.relpath(src, ROOT), msg))
    print("\n%(ok)d ok, %(FAIL)d failed, %(skip)d skipped" % counts)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
