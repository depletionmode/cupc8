#!/usr/bin/env python3
"""HALTED/WAITING source, routed-leg, and native bridge-status mutations."""
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
from gen_top import check, cpu_status_routes, exported_cards
from netlist import read
from test_cosim_cpu_controls import open_launch


def probe(top, mode):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/cpu_status_probe.mjs', mode],
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
    links, paths, missing = cpu_status_routes(
        main_circuit, cpu_circuit, args.main_board, args.cpu_board)
    assert links == {'halted': True, 'waiting': True} and not missing
    assert len(paths) == 6 and all(item['route_mm'] is not None for item in paths)
    assert top['runtime']['cpu_status_connected'] == links

    wrong = copy.deepcopy(cpu_circuit)
    wrong.components['RN8'] = ('22', ('Device', 'R_Pack04'))
    try:
        cpu_status_routes(main_circuit, wrong, None, None)
    except ValueError as error:
        assert 'CPU status' in str(error)
    else:
        raise AssertionError('changed RN8 series pack passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-status-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        good = {mode: probe(args.top, mode) for mode in ('halted', 'waiting')}
        for mode, bit in (('halted', 2), ('waiting', 4)):
            assert good[mode]['finished'] and good[mode]['exitCode'] == 0
            assert good[mode]['bridgeStatus'] & bit
        trials = (
            ('halted', 'cpu-source', args.cpu_board, 'U1', '60', '/FPGA_HALTED'),
            ('halted', 'cpu-socket', args.cpu_board, 'RN8', '6', '/CPU_HALTED'),
            ('halted', 'main', args.main_board, 'U7', '137', '/CPU_HALTED'),
            ('waiting', 'cpu-source', args.cpu_board, 'U1', '61', '/FPGA_WAITING'),
            ('waiting', 'cpu-socket', args.cpu_board, 'RN8', '5', '/CPU_WAITING'),
            ('waiting', 'main', args.main_board, 'U7', '130', '/CPU_WAITING'),
        )
        for mode, leg, board_path, ref, pin, net in trials:
            opened = temporary / f'open-{mode}-{leg}.kicad_pcb'
            open_launch(board_path, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if leg == 'main' else args.main_board,
                           card_boards, args.system_board,
                           opened if leg != 'main' else args.cpu_board)
            assert mutant['runtime']['cpu_status_connected'][mode] is False
            other = 'waiting' if mode == 'halted' else 'halted'
            assert mutant['runtime']['cpu_status_connected'][other] is True
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 3
            names = {'cpu:FPGA_' + mode.upper(), 'cpu:CPU_' + mode.upper(),
                     'main:CPU_' + mode.upper()}
            assert names <= set(mutant['unmodeled_nets'])
            changed_top = temporary / f'open-{mode}-{leg}.json'
            changed_top.write_text(json.dumps(mutant))
            bad = probe(changed_top, mode)
            assert bad['finished'] and bad['exitCode'] == 0
            assert bad['bridgeStatus'] & (2 if mode == 'halted' else 4) == 0
            assert bad['state']['pc'] == good[mode]['state']['pc']
            if mode == 'halted':
                assert bad['state']['halted'] == 1
            print(f'open {mode} {leg}: bridge status bit disappears')


if __name__ == '__main__':
    main()
