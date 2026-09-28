#!/usr/bin/env python3
"""Run the receipt-bound digital co-simulation subset on canonical boards."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
from ibis_route_receipts import audit  # noqa: E402


def main():
    build = ROOT / 'build/hw'
    evidence = ROOT / 'doc/hardware/si-evidence'
    top = evidence / 'ibis-final-top.json'
    source_audit = evidence / 'ibis-final-source-audit.json'
    expected = json.loads((evidence / 'ibis-final-receipts.json').read_text())
    actual = audit(ROOT, build, build / 'system/system-routed.kicad_pcb',
                   top, source_audit, ROOT / 'hw/cosim/gen_top.py')
    if actual != expected or actual['unmodeled_nets'] != 288:
        raise AssertionError('canonical board receipts or co-simulation top changed')

    common = [
        '--main-netlist', str(build / 'main/main.net'),
        '--main-board', str(build / 'main/main.kicad_pcb'),
        '--card-board-dir', str(build),
        '--system-board', str(build / 'system/system-routed.kicad_pcb'),
        '--cpu-board', str(build / 'cpu/cpu.kicad_pcb'),
        '--top', str(top),
    ]
    for name in ('main_cpu_data', 'cpu_irq', 'cpu_timer_exp', 'system_usb',
                 'io_usb_host'):
        print(name, flush=True)
        subprocess.run([sys.executable, str(ROOT / 'test/hw' /
                                            ('test_cosim_' + name + '.py')),
                        *common], cwd=ROOT, check=True)
    print('receipt-bound routed digital subset passed; 288 nets remain unmodeled')


if __name__ == '__main__':
    main()
