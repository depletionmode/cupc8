#!/usr/bin/env python3
"""Run the receipt-bound digital co-simulation subset on canonical boards."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


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
    if actual != expected:
        raise AssertionError('canonical board receipts or co-simulation top changed')

    common = [
        '--main-netlist', str(build / 'main/main.net'),
        '--main-board', str(build / 'main/main.kicad_pcb'),
        '--card-board-dir', str(build),
        '--system-board', str(build / 'system/system-routed.kicad_pcb'),
        '--cpu-board', str(build / 'cpu/cpu.kicad_pcb'),
        '--top', str(top),
    ]
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-rom-') as directory:
        temporary = Path(directory)
        subprocess.run(['bash', 'kernel/assemble.sh', temporary], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, 'tools/as.py', 'rom/boot.s',
                        temporary / 'boot.bin', '0xe000,0xe600,0x0f00'],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['bash', 'basic/build.sh', temporary], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, 'tools/mkrom.py', temporary / 'boot.bin',
                        temporary / 'kernel.o', '--basic', temporary / 'BASIC.PRG',
                        '-o', temporary / 'kernel.rom'], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
        environment = dict(os.environ, CUPC8_TEST_ROM=str(temporary / 'kernel.rom'))
        for name in ('main_cpu_data', 'cpu_irq', 'cpu_timer_exp', 'system_usb',
                     'sysctl_vbus', 'io_usb_host'):
            print(name, flush=True)
            subprocess.run([sys.executable, str(ROOT / 'test/hw' /
                                                ('test_cosim_' + name + '.py')),
                            *common], cwd=ROOT, env=environment, check=True)
    print(f"receipt-bound routed digital subset passed; {actual['unmodeled_nets']} nets remain unmodeled")


if __name__ == '__main__':
    main()
