#!/usr/bin/env python3
"""System manual-reset source, copper and native pulse counterexamples."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards, sysctl_manual_reset_route
from netlist import read
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse


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


def pulse(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/sysreset_probe.mjs'],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(output.strip())


def held_button(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/buttonreset_probe.mjs'],
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
    top = json.loads(args.top.read_text())
    main_circuit = read(args.main_netlist)
    with tempfile.TemporaryDirectory(prefix='cupc8-sysreset-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        system = cards['system']
        connected, paths, missing = sysctl_manual_reset_route(
            main_circuit, system, args.main_board, args.system_board)
        assert connected == {'sysctl': True, 'button': True} and not missing and len(paths) == 3
        assert all(item['route_mm'] is not None for item in paths)
        assert top['runtime']['sysctl_manual_reset_connected']
        assert top['runtime']['button_manual_reset_connected']
        for net in ('main:nMR', 'system:SYS_nRST'):
            assert net in top['runtime_nets']

        wrong = copy.deepcopy(system)
        wrong.nets['/SYS_nRST'] = (('U1', '34'), ('J2', 'B4'))
        try:
            sysctl_manual_reset_route(main_circuit, wrong, None, None)
        except ValueError as error:
            assert 'system reset' in str(error)
        else:
            raise AssertionError('changed RP2040 GPIO pad passed reset source binding')

        good = pulse(args.top)
        assert good['finished'] and good['exitCode'] == 0
        assert good['before']['nrst'] == 1 and good['before']['gpo'] == 2
        assert good['duringReset']['nrst'] == 0 and good['duringReset']['gpo'] == 0
        pressed = held_button(args.top)
        assert pressed['nrst'] == 0 and pressed['gpo'] == 0

        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        for board_name, board_path, ref, pin, net in (
                ('system', args.system_board, 'U1', '35', '/SYS_nRST'),
                ('main', args.main_board, 'U6', '3', '/nMR')):
            opened = temporary / f'open-{board_name}.kicad_pcb'
            open_launch(board_path, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if board_name == 'main' else args.main_board,
                           card_boards,
                           opened if board_name == 'system' else args.system_board,
                           args.cpu_board)
            assert mutant['runtime']['sysctl_manual_reset_connected'] is False
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 2
            assert {'main:nMR', 'system:SYS_nRST'} <= set(mutant['unmodeled_nets'])
            changed_top = temporary / f'open-{board_name}.json'
            changed_top.write_text(json.dumps(mutant))
            bad = pulse(changed_top)
            assert bad['finished'] and bad['exitCode'] == 0
            assert bad['duringReset'] is None
            assert bad['after']['nrst'] == 1 and bad['after']['gpo'] == 2
            print(f'open {board_name} {net}: sysctl reset command cannot reset chipset')

        opened = temporary / 'open-button.kicad_pcb'
        open_launch(args.main_board, opened, 'SW1', '1', '/nMR')
        mutant = check(cards, main_circuit, opened, card_boards,
                       args.system_board, args.cpu_board)
        assert mutant['runtime']['sysctl_manual_reset_connected'] is True
        assert mutant['runtime']['button_manual_reset_connected'] is False
        assert mutant['runtime']['routed_top'] is False
        assert len(mutant['unmodeled_nets']) == len(top['unmodeled_nets']) + 1
        assert 'main:nMR' in mutant['unmodeled_nets']
        changed_top = temporary / 'open-button.json'
        changed_top.write_text(json.dumps(mutant))
        bad_button = held_button(changed_top)
        assert bad_button['nrst'] == 1 and bad_button['gpo'] == 2
        print('open SW1.1 /nMR: held physical reset button cannot reset chipset')


if __name__ == '__main__':
    main()
