#!/usr/bin/env python3
"""CPU SYNC source, each copper leg, and chipset trace counterexamples."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, cpu_sync_route, exported_cards
from netlist import read
from test_cosim_cpu_controls import open_launch


def trace(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/sync_trace_probe.mjs'],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(output.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, required=True)
    parser.add_argument('--main-board', type=Path, required=True)
    parser.add_argument('--card-board-dir', type=Path, required=True)
    parser.add_argument('--system-board', type=Path, required=True)
    parser.add_argument('--cpu-board', type=Path, required=True)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    main_circuit = read(args.main_netlist)
    cpu_circuit = read(args.card_board_dir / 'cpu/cpu.net')
    top = json.loads(args.top.read_text())
    connected, paths, missing = cpu_sync_route(
        main_circuit, cpu_circuit, args.main_board, args.cpu_board)
    assert connected and not missing and len(paths) == 3
    assert all(item['route_mm'] is not None for item in paths)
    assert top['runtime']['cpu_sync_connected']
    assert {'cpu:FPGA_SYNC', 'cpu:CPU_SYNC', 'main:CPU_SYNC'} <= \
        set(top['runtime_nets'])

    wrong = copy.deepcopy(cpu_circuit)
    wrong.components['RN5'] = ('22', ('Device', 'R_Pack04'))
    try:
        cpu_sync_route(main_circuit, wrong, None, None)
    except ValueError as error:
        assert 'CPU SYNC' in str(error)
    else:
        raise AssertionError('changed CPU SYNC series pack passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-sync-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        good = trace(args.top)
        assert good['finished'] and good['exitCode'] == 0
        assert good['entries'] > 0 and good['syncEntries'] > 0
        assert good['state']['gpo'] == 2
        for board_name, board_path, ref, pin, net in (
                ('cpu-source', args.cpu_board, 'U1', '26', '/FPGA_SYNC'),
                ('cpu-socket', args.cpu_board, 'RN5', '6', '/CPU_SYNC'),
                ('main', args.main_board, 'U7', '26', '/CPU_SYNC')):
            opened = temporary / f'open-{board_name}.kicad_pcb'
            open_launch(board_path, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if board_name == 'main' else args.main_board,
                           card_boards, args.system_board,
                           opened if board_name.startswith('cpu') else args.cpu_board)
            assert mutant['runtime']['cpu_sync_connected'] is False
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 3
            assert {'cpu:FPGA_SYNC', 'cpu:CPU_SYNC', 'main:CPU_SYNC'} <= \
                set(mutant['unmodeled_nets'])
            changed_top = temporary / f'open-{board_name}.json'
            changed_top.write_text(json.dumps(mutant))
            bad = trace(changed_top)
            assert bad['finished'] and bad['exitCode'] == 0
            assert bad['entries'] > 0 and bad['syncEntries'] == 0
            assert bad['state']['pc'] == good['state']['pc']
            print(f'open {board_name} {net}: trace SYNC flags {good["syncEntries"]} -> 0')


if __name__ == '__main__':
    main()
