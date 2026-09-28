#!/usr/bin/env python3
"""CPU /STB and RW source, copper, and native execution counterexamples."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, cpu_control_routes, exported_cards
from netlist import read
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse
from test_cosim_runtime import PROBE, run


def open_launch(source, target, ref, pin, net):
    board = pcbnew.LoadBoard(str(source))
    pad = next(p for p in board.FindFootprintByReference(ref).Pads()
               if p.GetNumber() == pin)
    pos = pad.GetPosition()
    xy = (round(pcbnew.ToMM(pos.x), 4), round(pcbnew.ToMM(pos.y), 4))
    tree = parse(source.read_text())
    matches = [item for item in tree[1:]
               if isinstance(item, list) and item and item[0] == 'segment' and
               find1(item, 'net') and find1(item, 'net')[1] == net and
               xy in (tuple(round(float(v), 4) for v in find1(item, end)[1:])
                      for end in ('start', 'end'))]
    if len(matches) != 1:
        raise AssertionError(f'{ref}.{pin} {net} has {len(matches)} launch segments')
    tree.remove(matches[0])
    target.write_text(dump(tree) + '\n')


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
    assert top['runtime']['cpu_control_connected'] == {'strobe': True, 'rw': True}
    links, paths, missing = cpu_control_routes(
        main_circuit, cpu_circuit, args.main_board, args.cpu_board)
    assert links == {'strobe': True, 'rw': True} and not missing
    assert len(paths) == 6 and all(p['route_mm'] is not None for p in paths)

    wrong = copy.deepcopy(cpu_circuit)
    wrong.components['RN5'] = ('22', ('Device', 'R_Pack04'))
    try:
        cpu_control_routes(main_circuit, wrong, None, None)
    except ValueError as error:
        assert 'CPU strobe' in str(error)
    else:
        raise AssertionError('changed 33-ohm CPU control series pack passed')

    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-controls-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        good_state = run(args.top, PROBE)
        assert good_state['nrst'] == 1 and good_state['gpo'] == 2
        trials = (
            ('strobe', args.cpu_board, 'U1', '23', '/FPGA_nSTB'),
            ('rw', args.main_board, 'U7', '29', '/CPU_RW'),
        )
        for signal, board_path, ref, pin, net in trials:
            opened = temporary / f'open-{signal}.kicad_pcb'
            open_launch(board_path, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if signal == 'rw' else args.main_board,
                           card_boards, args.system_board,
                           opened if signal == 'strobe' else args.cpu_board)
            assert mutant['runtime']['cpu_control_connected'][signal] is False
            assert mutant['runtime']['cpu_control_connected'][
                'rw' if signal == 'strobe' else 'strobe'] is True
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 3
            assert f'{"cpu" if signal == "strobe" else "main"}:{net.lstrip("/")}' \
                in mutant['unmodeled_nets']
            changed_top = temporary / f'open-{signal}.json'
            changed_top.write_text(json.dumps(mutant))
            bad_state = run(changed_top, PROBE)
            assert bad_state['gpo'] == 0 and bad_state['pc'] != good_state['pc']
            print(f'open {net} {ref}.{pin}: PC {good_state["pc"]:#06x} -> '
                  f'{bad_state["pc"]:#06x}, GPO 2 -> 0')


if __name__ == '__main__':
    main()
