#!/usr/bin/env python3
"""Lockstep test: VHDL CPU (GHDL) vs sim.nim, instruction by instruction.

Assembles every test program, runs it through tools/simtrace (reference) and
soc/tb/tb_cpu_trace.vhd, and diffs the traces. Verification row 1.2.

  lockstep.py                 run all programs
  lockstep.py FILE.s ...      run the given programs
  lockstep.py --waits N       every bus cycle gets N wait states
  lockstep.py --waits -1 --seed S   random 0..15 wait states per cycle
  lockstep.py --engine verilator    run the synthesised netlist instead of RTL
  lockstep.py --engine mainboard [--noise]   CPU + chipset + memory models

Programs that touch SPI ($f1xx) are skipped: the SPI devices live in the
chipset, which this CPU-only testbench does not model.
"""
import argparse
import concurrent.futures
import contextlib
import fcntl
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


@contextlib.contextmanager
def build_lock():
    """Serialise builds between concurrent test runs (test/run.py -j)."""
    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def up_to_date(target, sources):
    if not os.path.exists(target):
        return False
    t = os.path.getmtime(target)
    return all(os.path.getmtime(os.path.join(ROOT, src)) < t for src in sources)


def build():
    with build_lock():
        _build()


def _build():
    os.makedirs(GHDL_WORK, exist_ok=True)
    simtrace = os.path.join(BUILD, "simtrace")
    if not up_to_date(simtrace, ["tools/simtrace.nim", "tools/sim.nim"]):
        r = run(["nim", "c", "--hints:off", "-d:release", "-o:" + simtrace,
                 os.path.join(ROOT, "tools", "simtrace.nim")])
        if r.returncode:
            sys.exit("simtrace build failed:\n" + r.stdout + r.stderr)
    if up_to_date(os.path.join(GHDL_WORK, "tb_cpu_trace"), VHDL):
        return
    ghdl = os.path.join(OSS, "ghdl")
    for step in (["-a", "--std=08", "-fsynopsys"] + [os.path.join(ROOT, f) for f in VHDL],
                 ["-e", "--std=08", "-fsynopsys", "tb_cpu_trace"]):
        r = run([ghdl] + step, cwd=GHDL_WORK)
        if r.returncode:
            sys.exit("ghdl %s failed:\n%s%s" % (step[0], r.stdout, r.stderr))


VERILATOR = os.path.join(BUILD, "verilator")
MAINBOARD = os.path.join(BUILD, "mainboard")
MAINBOARD_VHDL = ["soc/alu.vhd", "soc/cpu.vhd", "soc/spi_master.vhd", "soc/bridge.vhd",
                  "soc/chipset.vhd", "soc/tb/models/sram_model.vhd",
                  "soc/tb/models/sst39_model.vhd", "soc/tb/tb_mainboard.vhd"]


def build_mainboard():
    """The CPU + chipset + memory models (tb_mainboard) under GHDL."""
    with build_lock():
        if up_to_date(os.path.join(MAINBOARD, "tb_mainboard"), MAINBOARD_VHDL):
            return
        os.makedirs(MAINBOARD, exist_ok=True)
        ghdl = os.path.join(OSS, "ghdl")
        for step in (["-a", "--std=08", "-fsynopsys"] + [os.path.join(ROOT, f) for f in MAINBOARD_VHDL],
                     ["-e", "--std=08", "-fsynopsys", "tb_mainboard"]):
            r = run([ghdl] + step, cwd=MAINBOARD)
            if r.returncode:
                sys.exit("ghdl %s failed:\n%s%s" % (step[0], r.stdout, r.stderr))


def build_verilator():
    """Synthesise the CPU (ghdl synth → Verilog) and build the Verilator harness.
    The netlist is what the FPGA flow synthesises, so this is also SYN-001."""
    with build_lock():
        if not up_to_date(os.path.join(VERILATOR, "obj_dir", "cpu_trace"),
                          ["soc/alu.vhd", "soc/cpu.vhd", "soc/tb/verilator/cpu_trace.cpp"]):
            _build_verilator()


def _build_verilator():
    os.makedirs(VERILATOR, exist_ok=True)
    r = run([os.path.join(OSS, "ghdl"), "synth", "--std=08", "--out=verilog",
             os.path.join(ROOT, "soc/alu.vhd"), os.path.join(ROOT, "soc/cpu.vhd"), "-e", "cpu"],
            cwd=VERILATOR)
    if r.returncode:
        sys.exit("ghdl synth failed:\n" + r.stderr)
    with open(os.path.join(VERILATOR, "cpu.v"), "w") as f:
        f.write(r.stdout)
    r = run([os.path.join(OSS, "verilator"), "--cc", "--exe", "--build", "-O3", "-Wno-fatal",
             "-Wno-lint", "-Wno-style", "--top-module", "cpu", "-o", "cpu_trace", "cpu.v",
             os.path.join(ROOT, "soc/tb/verilator/cpu_trace.cpp")], cwd=VERILATOR)
    if r.returncode:
        sys.exit("verilator build failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])


def trace_lines(text):
    return [l for l in text.splitlines() if l[:2] in ("S ", "W ", "E ")]


def check(src, waits, seed, engine, noise=False, stall=0, reset_at=0):
    name = os.path.splitext(os.path.basename(src))[0]
    with open(src) as f:
        if SPI_RE.search(f.read()):
            return "skip", "uses SPI (needs the chipset model)"
    # each (engine, waits, seed) combination gets its own directory, so
    # concurrent runs (test/run.py -j) never share files
    progs = os.path.join(PROGS, "%s-w%d-s%d%s%s%s" % (engine, waits, seed, "-noise" if noise else "",
                                                     "-st%d" % stall if stall else "",
                                                     "-r%d" % reset_at if reset_at else ""))
    os.makedirs(progs, exist_ok=True)
    obj = os.path.join(progs, name + ".o")
    r = run(["python3", os.path.join(ROOT, "tools", "as.py"), src, obj])
    if r.returncode or not os.path.exists(obj):
        return "skip", "does not assemble"
    return compare_image(obj, waits, seed, engine=engine, noise=noise, stall=stall, reset_at=reset_at)


def compare_image(obj, waits=0, seed=1, max_steps=100000, engine="ghdl", noise=False, stall=0, reset_at=0):
    """Run a binary image (loaded at $1000) on both models and diff the traces.
    Returns (status, message); the traces are left next to the image."""
    base = os.path.splitext(obj)[0]
    image = open(obj, "rb").read()
    hexf = base + ".hex"
    with open(hexf, "w") as f:
        f.write("\n".join("%02x" % b for b in image) + "\n")

    ref = trace_lines(run([os.path.join(BUILD, "simtrace"), obj, str(max_steps)]).stdout)
    if engine == "mainboard":
        romf = base + ".rom.hex"
        with open(romf, "w") as f:
            f.write("b0\n00\n10\n")              # b $1000 at the reset vector
        r = run([os.path.join(MAINBOARD, "tb_mainboard"), "-gIMAGE=" + hexf,
                 "-gIMAGE_LEN=%d" % len(image), "-gROM_IMAGE=" + romf,
                 "-gNOISE=%s" % ("true" if noise else "false"), "--ieee-asserts=disable"],
                timeout=3600)
    elif engine == "verilator":
        r = run([os.path.join(VERILATOR, "obj_dir", "cpu_trace"), obj, str(waits), str(seed)],
                timeout=1200)
    else:
        r = run([os.path.join(OSS, "ghdl"), "-r", "--std=08", "-fsynopsys", "tb_cpu_trace",
                 "-gIMAGE=" + hexf, "-gWAITS=%d" % waits, "-gSEED=%d" % seed,
                 "-gSTALL=%d" % stall, "-gRESET_AT=%d" % reset_at,
                 "--ieee-asserts=disable"], cwd=GHDL_WORK, timeout=1200)
    if r.returncode:
        return "FAIL", "testbench error: " + (r.stdout + r.stderr).strip().splitlines()[-1]
    dut = trace_lines(r.stdout)
    with open(base + ".sim.trace", "w") as f:
        f.write("\n".join(ref) + "\n")
    with open(base + "." + engine + ".trace", "w") as f:
        f.write("\n".join(dut) + "\n")

    if ref and ref[-1] == "E limit":
        # the program never stops: compare the prefix the reference produced
        ref = ref[:-1]
        dut = dut[:len(ref)]
    for i, (a, b) in enumerate(zip(ref, dut)):
        if a != b:
            ctx = ref[max(0, i - 4):i]
            msg = "line %d: sim %r != %s %r" % (i + 1, a, engine, b)
            msg += "\n      context (sim): " + " | ".join(ctx)
            return "FAIL", msg
    if len(ref) != len(dut):
        return "FAIL", "length: sim %d lines, dut %d lines (last sim %r, last dut %r)" % (
            len(ref), len(dut), ref[-1:], dut[-1:])
    instrs = sum(1 for l in ref if l.startswith("S "))
    return "ok", "%d instructions, %s" % (instrs, ref[-1] if ref else "no trace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--waits", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-j", type=int, default=os.cpu_count(), help="parallel jobs")
    ap.add_argument("--engine", choices=["ghdl", "verilator", "mainboard"], default="ghdl",
                    help="ghdl: CPU RTL; verilator: the synthesised CPU netlist (SYN-001); "
                         "mainboard: CPU + chipset + memory models")
    ap.add_argument("--noise", action="store_true",
                    help="mainboard only: bridge traffic to SRAM during the run (BRG-003)")
    ap.add_argument("--stall", type=int, default=0,
                    help="ghdl only: one cycle in eight stalls up to N extra clocks (BUS-003)")
    ap.add_argument("--reset-at", type=int, default=0,
                    help="ghdl only: reset mid-cycle once at cycle N (or at HALT), then compare the rerun (BUS-003)")
    args = ap.parse_args()
    files = args.files or sorted(glob.glob(os.path.join(ROOT, "tools", "testdata", "*.s")) +
                                 glob.glob(os.path.join(ROOT, "test", "*.s")) +
                                 glob.glob(os.path.join(ROOT, "test", "isa", "*.s")))
    build()
    if args.engine == "verilator":
        build_verilator()
    if args.engine == "mainboard":
        build_mainboard()
    counts = {"ok": 0, "FAIL": 0, "skip": 0}
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.j) as pool:
        jobs = [pool.submit(check, os.path.abspath(src), args.waits, args.seed, args.engine, args.noise,
                            args.stall, args.reset_at)
                for src in files]
        for src, job in zip(files, jobs):
            status, msg = job.result()
            counts[status] += 1
            print("%-5s %-22s %s" % (status, os.path.relpath(src, ROOT), msg))
    print("\n%(ok)d ok, %(FAIL)d failed, %(skip)d skipped" % counts)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
