#!/usr/bin/env python3
"""Main CPU data source, series, keeper, copper, and native mutations."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards, main_cpu_data_routes
from netlist import read
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse
from test_cosim_runtime import PROBE, run

CHIPSET_PADS = ('20', '18', '19', '17', '9', '7', '10', '8')


def open_pad_tracks(source, target, ref, pin, net, expected):
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
    if len(matches) != expected:
        raise AssertionError(f'{ref}.{pin} {net} has {len(matches)} launch tracks; '
                             f'expected {expected}')
    for item in matches:
        tree.remove(item)
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
    top = json.loads(args.top.read_text())
    links, paths, missing = main_cpu_data_routes(main_circuit, args.main_board)
    assert links == [True] * 8 and not missing
    assert len(paths) == 24 and all(p['route_mm'] is not None for p in paths)
    assert top['runtime']['cpu_data_main_links'] == links
    baseline_count = len(top['unmodeled_nets'])
    assert baseline_count <= 310

    for ref, value in (('R21', '22'), ('R90', '100k')):
        wrong = copy.deepcopy(main_circuit)
        wrong.components[ref] = (value, ('Device', 'R'))
        try:
            main_cpu_data_routes(wrong, None)
        except ValueError as error:
            assert 'CPU D0' in str(error)
        else:
            raise AssertionError(f'changed {ref} value passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-main-cpu-data-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        good = run(args.top, PROBE)
        assert good['pc'] == 0xE2B9 and good['gpo'] == 2
        for bit, chip_pad in enumerate(CHIPSET_PADS):
            for leg, ref, pin, net, count in (
                    ('chipset', 'U7', chip_pad, f'/CPU_D{bit}_SRC', 1),
                    ('series', f'R{21 + bit}', '2', f'/CPU_D{bit}', 1),
                    ('keeper', f'R{90 + bit}', '2', f'/CPU_D{bit}',
                     2 if bit in (0, 7) else 1)):
                opened = temporary / f'open-D{bit}-{leg}.kicad_pcb'
                open_pad_tracks(args.main_board, opened, ref, pin, net, count)
                altered, _, missing = main_cpu_data_routes(main_circuit, opened)
                assert altered[bit] is False and sum(altered) == 7, (bit, leg, altered)
                assert missing, (bit, leg)
                if leg != 'chipset':
                    continue
                mutant = check(cards, main_circuit, opened, card_boards,
                               args.system_board, args.cpu_board)
                assert mutant['runtime']['cpu_data_main_links'] == altered
                assert mutant['runtime']['cpu_data_links'][bit] is False
                assert mutant['runtime']['routed_top'] is False
                assert len(mutant['unmodeled_nets']) == baseline_count + 1
                assert f'main:CPU_D{bit}_SRC' in mutant['unmodeled_nets']
                changed_top = temporary / f'open-D{bit}.json'
                changed_top.write_text(json.dumps(mutant))
                bad = run(changed_top, PROBE)
                assert bad['pc'] != good['pc'] and bad['gpo'] == 0, (bit, bad)
                print(f'CPU D{bit} source open: PC {good["pc"]:#06x} -> '
                      f'{bad["pc"]:#06x}; GPO 2 -> 0')
        print('24/24 main CPU data branch opens detected; 8/8 source opens '
              'changed native execution')


if __name__ == '__main__':
    main()
