#!/usr/bin/env python3
"""Pin, copper and observable-state counterexamples for main GPO LEDs."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards, gpo_indicator_routes
from netlist import read
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse
from test_cosim_runtime import PROBE, run


def open_launch(board_path, target):
    board = pcbnew.LoadBoard(str(board_path))
    pad = next(p for p in board.FindFootprintByReference('U7').Pads()
               if p.GetNumber() == '106')
    point = pad.GetPosition()
    xy = (round(pcbnew.ToMM(point.x), 4), round(pcbnew.ToMM(point.y), 4))
    tree = parse(board_path.read_text())
    matches = [item for item in tree[1:]
               if isinstance(item, list) and item and item[0] == 'segment' and
               find1(item, 'net') and find1(item, 'net')[1] == '/GPO1' and
               xy in (tuple(round(float(v), 4) for v in find1(item, end)[1:])
                      for end in ('start', 'end'))]
    if len(matches) != 1:
        raise AssertionError(f'U7.106 has {len(matches)} GPO1 launch segments')
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
    circuit = read(args.main_netlist)
    good = json.loads(args.top.read_text())
    links, paths, missing = gpo_indicator_routes(circuit, args.main_board)
    assert links == [True] * 8 and not missing
    assert len(paths) == 16 and all(p['route_mm'] is not None for p in paths)
    assert good['runtime']['gpo_led_connected'] == links
    assert all(f'main:{net}{bit}' in good['runtime_nets']
               for bit in range(8) for net in ('GPO', 'LED_GPO'))

    wrong = copy.deepcopy(circuit)
    wrong.components['R60'] = ('2k', ('Device', 'R'))
    try:
        gpo_indicator_routes(wrong, None)
    except ValueError as error:
        assert 'GPO0' in str(error)
    else:
        raise AssertionError('changed current-limit resistor passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-gpo-led-') as directory:
        temporary = Path(directory)
        opened = temporary / 'open-gpo1.kicad_pcb'
        open_launch(args.main_board, opened)
        bad_links, _, bad_missing = gpo_indicator_routes(circuit, opened)
        assert bad_links == [True, False] + [True] * 6
        assert 'main:GPO1_gpo_led_copper' in bad_missing
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        bad_top = check(cards, circuit, opened, card_boards,
                        args.system_board, args.cpu_board)
        assert bad_top['runtime']['gpo_led_connected'] == bad_links
        assert 'main:GPO1' in bad_top['unmodeled_nets']
        assert 'main:LED_GPO1' in bad_top['unmodeled_nets']
        assert len(bad_top['unmodeled_nets']) == len(good['unmodeled_nets']) + 2

        native_good = run(args.top, PROBE)
        mutant = temporary / 'open-gpo1.json'
        mutant.write_text(json.dumps(bad_top))
        native_bad = run(mutant, PROBE)
        assert native_good['gpo'] == native_bad['gpo']
        assert native_good['gpo'] & 2
        assert native_good['gpoLeds'][1] is True
        assert native_bad['gpoLeds'][1] is False
        assert native_good['gpoLeds'][:1] == native_bad['gpoLeds'][:1]
        print('GPO LED source, copper and runtime mutations all change only their bound channel')


if __name__ == '__main__':
    main()
