#!/usr/bin/env python3
"""CPU-002/CPU-003: random-program lockstep fuzzer with opcode coverage.

Generates random CUPC/8 programs, runs each on sim.nim and the VHDL CPU (with
random wait states), and diffs the traces (tools/lockstep.py). Coverage is
measured on what actually executed: every opcode byte $00-$ff must run.

  cpufuzz.py [--programs N] [--seed S] [--min-instructions M] [--engine ghdl|verilator]

A failing program is kept in build/lockstep/fuzz/ with both traces.

Programs are built from stack-neutral "units", so any forward branch to a
unit boundary keeps the stack balanced:
  simple   one random instruction (ALU/mov/ld/st/ldd/std/tmr/cli/sti/nop/undefined)
  pushpop  push x, 0-3 simple, pop y (includes pop f with a random flags value)
  call     push pch; push pcl; b sub   (sub = straight-line body; pop pcl; pop pch)
  wai      clear IRQ_PEND, unmask only timer 0, arm it, sti, wai
  branch   b / bzf forward to a later unit
Memory: stores go to $8000-$8eff (indexed bases keep +255 in range), the
pointer table for ldd/std is at $8f00, IRQ vectors all point at a handler that
clears IRQ_PEND and returns.
"""
import argparse
import concurrent.futures
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lockstep  # noqa: E402

FUZZ = os.path.join(lockstep.BUILD, "fuzz")
BASE = 0x1000
DATA = 0x8000          # data area, well above any generated code
PTR_TABLE = DATA + 0xF00
N_PTRS = 16

# opcode classes (bits 7..3)
ALU = {0x00, 0x08, 0x10, 0x18, 0x20, 0x30, 0x38, 0x40, 0x48, 0x60, 0x68}


def le(v):
    return [v & 0xFF, (v >> 8) & 0xFF]


class Gen:
    def __init__(self, rng):
        self.r = rng

    def simple(self):
        """One random stack-neutral, non-branching instruction (list of byte/label items)."""
        r = self.r
        while True:
            op = r.randrange(256)
            cls = op & 0xF8
            if cls in (0x90, 0x98, 0xB0, 0xB8, 0xF0, 0xF8):
                continue                                    # handled by other units
            break
        if cls in ALU or cls in (0x88, 0xE0, 0xE8):
            if op & 4:
                imm = r.randrange(256)
                if cls in (0xE0, 0xE8):
                    imm = r.randrange(0, 40)                # keep timers short
                return [op, imm]
            return [op]
        if cls == 0xA0:                                     # ld (index: Rb, up to +255)
            if op & 4:
                addr = r.randrange(DATA, DATA + 0xE00)
            else:
                addr = r.choice([r.randrange(DATA, DATA + 0xE00), 0xF200, 0xF201,
                                 r.randrange(0x1000, 0x1100), r.randrange(0x0010, 0x0020)])
            return [op] + le(addr)
        if cls == 0xA8:                                     # st (index: Ra, up to +255)
            if op & 4:
                addr = r.randrange(DATA, DATA + 0xD00)
            else:
                addr = r.choice([r.randrange(DATA, DATA + 0xE00), 0xF200, 0xF201, 0xF000])
            return [op] + le(addr)
        if cls in (0x70, 0x78):                             # ldd / std through the table
            return [op] + le(PTR_TABLE + 2 * r.randrange(N_PTRS))
        return [op]                                         # nop, cli, sti, undefined

    def pushpop(self):
        r = self.r
        push = r.choice([0x90, 0x91, 0x92, 0x93, 0x94, 0x95])
        items = [push] + ([r.randrange(256)] if push & 4 else [])
        for _ in range(r.randrange(4)):
            items += self.simple()
        items.append(r.choice([0x98, 0x99, 0x9A, 0x9B, 0x9C, 0x9D]))
        return items

    def wai(self):
        k = self.r.randrange(3, 12)     # tmr0 and sti tick it twice before the wai parks
        # push r0; mov r0,#$0f; st $f200,r0 (clear stale IRQs so none is taken at
        # the sti and eats the timer); mov r0,#$02; st $f201,r0 (timer 0 only);
        # pop r0; tmr0 #k; sti; wai
        return [0x90, 0x8C, 0x0F, 0xA8] + le(0xF200) + [0x8C, 0x02, 0xA8] + le(0xF201) + [0x98, 0xE4, k, 0xC8,
                                                          self.r.choice([0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7])]

    def program(self, units, halt_op=0xF8):
        r = self.r
        prog = []                       # list of units; a unit is a list of ints/labels
        # prologue: IRQ vectors → handler, pointer table, random registers
        pro = []
        for n in range(4):
            pro += [0x8C, ("lo", "handler"), 0xA8] + le(0x10 + 2 * n)
            pro += [0x8C, ("hi", "handler"), 0xA8] + le(0x11 + 2 * n)
        for i in range(N_PTRS):
            p = r.randrange(DATA, DATA + 0xD00)
            pro += [0x8C, p & 0xFF, 0xA8] + le(PTR_TABLE + 2 * i)
            pro += [0x8C, p >> 8, 0xA8] + le(PTR_TABLE + 2 * i + 1)
        pro += [0x8C, r.randrange(256), 0x8D, r.randrange(256)]
        prog.append(pro)

        n_subs = 4
        for _ in range(units):
            kind = r.choices(["simple", "pushpop", "call", "wai", "branch"],
                             weights=[70, 10, 6, 2, 12])[0]
            if kind == "simple":
                prog.append(self.simple())
            elif kind == "pushpop":
                prog.append(self.pushpop())
            elif kind == "call":
                sub = "sub%d" % r.randrange(n_subs)
                prog.append([0x96, 0x97, 0xB0, ("lo", sub), ("hi", sub)])
            elif kind == "wai":
                prog.append(self.wai())
            else:
                prog.append(["branch", r.randrange(0xB0, 0xC0)])     # any b/bzf encoding
        prog.append([0xC0, halt_op])                       # cli; halt

        # resolve branches to a random later unit boundary
        nunits = len(prog)
        for i, u in enumerate(prog):
            if u and u[0] == "branch":
                # short hops, so most of the program still executes
                tgt = "u%d" % r.randrange(i + 1, min(nunits, i + 9))
                prog[i] = [u[1], ("lo", tgt), ("hi", tgt)]

        tail = {}
        for s in range(n_subs):
            body = []
            for _ in range(r.randrange(1, 6)):
                body += self.simple()
            tail["sub%d" % s] = body + [0x9F, 0x9E]         # pop pcl; pop pch
        tail["handler"] = [0x90, 0x8C, 0x0F, 0xA8] + le(0xF200) + [0x98, 0x9C, 0x9F, 0x9E]

        # lay out and resolve labels
        labels, addr = {}, BASE
        for i, u in enumerate(prog):
            labels["u%d" % i] = addr
            addr += len(u)
        for name, body in tail.items():
            labels[name] = addr
            addr += len(body)
        out = bytearray()
        for u in prog + list(tail.values()):
            for item in u:
                if isinstance(item, tuple):
                    v = labels[item[1]]
                    out.append(v & 0xFF if item[0] == "lo" else v >> 8)
                else:
                    out.append(item)
        return bytes(out)


def executed_opcodes(obj):
    """Opcode bytes at every PC the reference trace says was fetched."""
    image = open(obj, "rb").read()
    seen = set()
    with open(os.path.splitext(obj)[0] + ".sim.trace") as f:
        for line in f:
            if line.startswith("S "):
                pc = int(line.split()[1], 16)
                if BASE <= pc < BASE + len(image):
                    seen.add(image[pc - BASE])
    return seen


def run_one(i, pseed, units, engine, outdir):
    """Generate, run and compare program i; returns (status, msg, obj, instrs, coverage)."""
    img = Gen(random.Random(pseed)).program(units, 0xF8 + i % 8)   # every halt encoding
    assert BASE + len(img) <= DATA, "generated code overlaps the data area"
    obj = os.path.join(outdir, "p%04d.o" % i)
    with open(obj, "wb") as f:
        f.write(img)
    status, msg = lockstep.compare_image(obj, waits=-1, seed=pseed % 65535 + 1,
                                         max_steps=200000, engine=engine)
    if status != "ok":
        return status, msg, obj, 0, set()
    cov = executed_opcodes(obj)
    for ext in (".hex", ".sim.trace", "." + engine + ".trace", ".o"):
        os.remove(obj[:-2] + ext)
    return status, msg, obj, int(msg.split()[0]), cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--programs", type=int, default=200)
    ap.add_argument("--units", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("-j", type=int, default=os.cpu_count(), help="parallel jobs")
    ap.add_argument("--engine", choices=["ghdl", "verilator"], default="verilator",
                    help="verilator (synthesised netlist, fast) or ghdl (RTL)")
    ap.add_argument("--min-instructions", type=int, default=0,
                    help="fail unless at least this many instructions ran")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1 << 30)
    print("cpufuzz: seed %d, %d programs" % (seed, args.programs))

    lockstep.build()
    if args.engine == "verilator":
        lockstep.build_verilator()
    outdir = os.path.join(FUZZ, "%s-s%d" % (args.engine, seed))     # private to this run
    os.makedirs(outdir, exist_ok=True)
    rng = random.Random(seed)
    seeds = [rng.randrange(1 << 30) for _ in range(args.programs)]
    coverage, total, hung = set(), 0, 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.j) as pool:
        jobs = [pool.submit(run_one, i, ps, args.units, args.engine, outdir) for i, ps in enumerate(seeds)]
        for i, job in enumerate(jobs):
            status, msg, obj, n, cov = job.result()
            if status != "ok":
                pool.shutdown(cancel_futures=True)
                print("FAIL program %d (seed %d, kept at %s):\n  %s" % (i, seeds[i], obj, msg))
                return 1
            total += n
            hung += msg.endswith("E limit")
            coverage |= cov
    missing = sorted(set(range(256)) - coverage)
    print("cpufuzz: %d programs, %d instructions, 0 divergences" % (args.programs, total))
    if hung:
        print("%d programs never reached HALT (generator bug: every program should end)" % hung)
        return 1
    print("coverage: %d/256 opcode bytes executed%s" % (
        len(coverage), "" if not missing else "; missing " + " ".join("%02x" % m for m in missing)))
    if missing:
        return 1
    if total < args.min_instructions:
        print("only %d instructions ran (need %d)" % (total, args.min_instructions))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
