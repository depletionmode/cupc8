#!/usr/bin/env python3
"""CPU /RDY source, each routed leg, and native stall counterexamples."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, cpu_ready_route, exported_cards
from netlist import read
from test_cosim_cpu_controls import open_launch
from test_cosim_runtime import PROBE, run


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
    connected, paths, missing = cpu_ready_route(
        main_circuit, cpu_circuit, args.main_board, args.cpu_board)
    assert connected and not missing and len(paths) == 3
    assert all(item['route_mm'] is not None for item in paths)
    assert top['runtime']['cpu_ready_connected']
    assert {'main:CPU_nRDY_SRC', 'main:CPU_nRDY', 'cpu:CPU_nRDY'} <= \
        set(top['runtime_nets'])

    wrong = copy.deepcopy(main_circuit)
    wrong.components['R33'] = ('47', ('Device', 'R'))
    try:
        cpu_ready_route(wrong, cpu_circuit, None, None)
    except ValueError as error:
        assert 'CPU /RDY' in str(error)
    else:
        raise AssertionError('changed CPU /RDY series part passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-ready-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        good = run(args.top, PROBE)
        assert good['pc'] == 0xE2B9 and good['gpo'] == 2
        for board_name, board_path, ref, pin, net in (
                ('main-source', args.main_board, 'U7', '28', '/CPU_nRDY_SRC'),
                ('main-socket', args.main_board, 'R33', '2', '/CPU_nRDY'),
                ('cpu', args.cpu_board, 'U1', '24', '/CPU_nRDY')):
            opened = temporary / f'open-{board_name}.kicad_pcb'
            open_launch(board_path, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if board_name.startswith('main') else args.main_board,
                           card_boards, args.system_board,
                           opened if board_name == 'cpu' else args.cpu_board)
            assert mutant['runtime']['cpu_ready_connected'] is False
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 3
            assert {'main:CPU_nRDY_SRC', 'main:CPU_nRDY', 'cpu:CPU_nRDY'} <= \
                set(mutant['unmodeled_nets'])
            changed_top = temporary / f'open-{board_name}.json'
            changed_top.write_text(json.dumps(mutant))
            bad = run(changed_top, PROBE)
            assert bad['pc'] == 0xE000 and bad['gpo'] == 0 and bad['nrst'] == 1
            print(f'open {board_name} {net}: CPU stalls at $E000 instead of $E2B9')


if __name__ == '__main__':
    main()
