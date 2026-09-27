#!/usr/bin/env python3
"""Strict entry point for the netlist-driven E2E-001..004 verification rows."""
import argparse
import fcntl
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args, env=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run([str(x) for x in args], cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=('E2E-001', 'E2E-002', 'E2E-003', 'E2E-004'))
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    args = parser.parse_args()
    output = ROOT / 'build/hw/cosim' / (args.case + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Each make-verify row owns its manifest. The strict generator refuses an
    # incomplete route, even though development probes may use it provisionally.
    generation = [sys.executable, ROOT / 'hw/cosim/gen_top.py', '--main-netlist',
                  args.main_netlist, '--require-route', '--require-coverage', '--output', output]
    run(generation)
    # Firmware and the native addon are shared build products. Parallel E2E
    # rows wait here so their build steps cannot overwrite each other.
    with (output.parent / 'build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run([ROOT / 'tools/fw_rp2040.sh'])
        run([ROOT / 'tools/emu_machine_build.sh'])
        if args.case == 'E2E-003':
            run([ROOT / 'tools/fw_esp32c3.sh', 'qemu'])
            run([ROOT / 'tools/qemu_build.sh'])
    if args.case == 'E2E-001':
        run([sys.executable, ROOT / 'test/hw/test_cosim_wiring.py', '--main-netlist', args.main_netlist])
        run([sys.executable, ROOT / 'test/hw/test_cosim_runtime.py', '--top', output])
    else:
        env = dict(os.environ, CUPC8_EMU='native', CUPC8_COSIM_TOP=str(output))
        run(['node', ROOT / 'test/emu/test_e2e.mjs', args.case], env=env)


if __name__ == '__main__':
    main()
