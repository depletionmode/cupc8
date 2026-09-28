#!/usr/bin/env python3
"""MB-052 digital subset: receipt-bound memory copper and CPU/sysctl execution."""

import copy
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'hw/tools')]
from boardevidence import digest, validate  # noqa: E402
from main_memory import audit, bound_top  # noqa: E402
from netlist import read  # noqa: E402
from test_cosim_main_cpu_data import open_pad_tracks  # noqa: E402


def probe(top, rom, sysctl):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top), CUPC8_SUBSET_ROM=str(rom),
               CUPC8_SUBSET_SYSCTL='1' if sysctl else '0')
    output = subprocess.check_output(
        ['node', 'test/hw/main_board_subset_probe.mjs'], cwd=ROOT,
        env=env, text=True)
    return json.loads(output.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-only', action='store_true',
                        help='skip sysctl TCP probe when loopback sockets are unavailable')
    args = parser.parse_args()
    builds = ROOT / 'build/hw'
    receipts = {}
    for name in ('main', 'cpu', 'system'):
        directory = builds / name
        validate(name, directory)
        receipts[name] = digest(directory / 'evidence.json')
    board = builds / 'main/main.kicad_pcb'
    circuit = read(builds / 'main/main.net')
    rows, missing = audit(circuit, board)
    assert len(rows) == 60 and not missing, missing

    with tempfile.TemporaryDirectory(prefix='cupc8-main-subset-') as dirname:
        temporary = Path(dirname)
        rom = temporary / 'kernel.rom'
        subprocess.run(['bash', 'kernel/assemble.sh', temporary], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, 'tools/as.py', 'rom/boot.s',
                        temporary / 'boot.bin', '0xe000,0xe600,0x0f00'],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['bash', 'basic/build.sh', temporary], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, 'tools/mkrom.py',
                        temporary / 'boot.bin', temporary / 'kernel.o',
                        '--basic', temporary / 'BASIC.PRG', '-o', rom],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        top = temporary / 'top.json'
        subprocess.run([sys.executable, 'hw/cosim/gen_top.py',
                        '--main-netlist', builds / 'main/main.net',
                        '--system-board', builds / 'system/system-routed.kicad_pcb',
                        '--cpu-board', builds / 'cpu/cpu.kicad_pcb',
                        '--require-route', '--output', top], cwd=ROOT, check=True)
        manifest = json.loads(top.read_text())
        runtime = manifest['runtime']
        assert runtime['routed_top'] and runtime['routed_timing']
        assert runtime['memory_write_links'] == {'ram': True, 'rom': True}
        assert runtime['rom_read_d0_connected']
        assert runtime['por_connected'] and runtime['cpu_clock_connected']
        assert runtime['cpu_reset_connected']
        assert all(runtime['cpu_address_links']) and all(runtime['cpu_data_links'])
        assert all(runtime['bridge_source_links'].values())
        assert runtime['bridge']['miso']
        bound_good = temporary / 'bound-good.json'
        bound_good.write_text(json.dumps(bound_top(manifest, rows, missing)))
        good = probe(bound_good, rom, not args.cpu_only)
        assert good['boot'] == {'pc': 0xE2B9, 'gpo': 2,
                                'nrst': 1, 'halted': False}, good
        if not args.cpu_only:
            assert good['ping']['code'] == 0 and good['status']['code'] == 0, good
            assert 'GPO $02' in good['status']['output'], good

        # A schematic pin swap and one physical ROM read-data launch open
        # must both defeat the source/copper binding.
        swapped = copy.deepcopy(circuit)
        swapped.pins[('U10', '13')] = '/MEM_D1'
        try:
            audit(swapped, board)
        except ValueError:
            pass
        else:
            raise AssertionError('swapped ROM DQ0 pad passed netlist binding')
        opened = temporary / 'rom-dq0-open.kicad_pcb'
        open_pad_tracks(board, opened, 'U10', '13', '/MEM_D0', 1)
        altered, gaps = audit(circuit, opened)
        assert 'MEM_D0:U7.119->U10.13' in gaps, gaps
        assert len(altered) == len(rows)
        mutant = bound_top(manifest, altered, gaps)
        assert not mutant['runtime']['rom_read_d0_connected'], \
            'open ROM DQ0 remained connected in the native top'
        bad_top = temporary / 'rom-open.json'
        bad_top.write_text(json.dumps(mutant))
        bad = probe(bad_top, rom, not args.cpu_only)
        assert bad['boot']['pc'] != good['boot']['pc'], (good, bad)
        assert bad['boot']['gpo'] == 0, bad

        print(json.dumps({'receipt_sha256': receipts,
                          'memory_paths': len(rows),
                          'boot': good['boot'],
                          'sysctl': [good['ping']['code'], good['status']['code']]
                          if good['ping'] else 'not run',
                          'rom_dq0_open': bad['boot'],
                          'strict_unmodeled_nets': len(manifest['unmodeled_nets'])}))


if __name__ == '__main__':
    main()
