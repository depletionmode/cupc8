#!/usr/bin/env python3
"""Run the four independent SI-003 HDMI field models concurrently."""

import concurrent.futures
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/hw/si'
PAIRS = ('d0', 'd1', 'd2', 'ck')


def command(pair):
    return [sys.executable, 'hw/si/openems_gpu_d0.py',
            '--pair', pair, '--board', 'build/hw/gpu/gpu.kicad_pcb',
            '--out', f'build/hw/si/gpu-{pair}-pml-fixed.json',
            '--pml-clearance-mm', '1', '--fixed-window',
            '--max-steps', '126000', '--threads', '1', '--require-evidence']


def run_pair(pair):
    log = OUT / f'gpu-{pair}-pml-fixed.log'
    try:
        with log.open('w') as stream:
            status = subprocess.run(command(pair), cwd=ROOT, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False).returncode
    except OSError as exc:
        log.write_text(f'Could not run {pair}: {exc}\n')
        status = 1
    return status, log


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Each child uses one openEMS thread and its own output and field directory.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(PAIRS)) as pool:
        jobs = {pair: pool.submit(run_pair, pair) for pair in PAIRS}
        results = {pair: jobs[pair].result() for pair in PAIRS}
    for pair in PAIRS:
        status, log = results[pair]
        print(f'{pair}: {"PASS" if status == 0 else "FAIL"} (exit {status}; {log.relative_to(ROOT)})')
    return int(any(status != 0 for status, _ in results.values()))


if __name__ == '__main__':
    sys.exit(main())
