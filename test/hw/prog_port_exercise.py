#!/usr/bin/env python3
"""Program RP2040 cards through the card programming port (run by prog_port_probe.mjs).

usage: prog_port_exercise.py PORT PLAN_JSON   PLAN: [{"slot": 1..6, "seed": n}, ...]

For each item: cupc8.py's real SWD flash routine (Rp2040.flash: DPIDR,
power-up, boot ROM erase and program calls, read-back verify) writes the
pattern image (image(seed)) at flash offset 0 of the card in that slot, and
one line says whether it worked ("slot N: flashed" or "slot N: FAILED ...").
"""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import cupc8  # noqa: E402

SIZE = 8192


def image(seed):
    return bytes((i * 7 + seed * 31 + (i >> 8)) & 0xFF for i in range(SIZE))


def digest(seed):
    return hashlib.sha256(image(seed)).hexdigest()


def main():
    port, plan = sys.argv[1], json.loads(sys.argv[2])
    sc = cupc8.Sysctl(port)
    try:
        sc.resync()
        for item in plan:
            slot = item['slot']
            try:
                cupc8.Rp2040(sc, slot - 1).flash(image(item['seed']), 0, log=lambda *a: None)
                print(f'slot {slot}: flashed', flush=True)
            except (cupc8.SwdError, cupc8.SysctlError) as error:
                print(f'slot {slot}: FAILED {error}', flush=True)
                sc.prog_select(None)
    finally:
        sc.close()


if __name__ == '__main__':
    os.environ.setdefault('CUPC8_TIMEOUT_SCALE', '300')
    main()
