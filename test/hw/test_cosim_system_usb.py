#!/usr/bin/env python3
"""System USB CDC source, Type-C orientation, CC Rd and ESD branch mutations.

The host attaches (supplies VBUS and talks CDC) only in the orientation whose
CC line has its 5.1 k Rd wired: an open CC1 leg removes orientation A, an open
CC2 leg orientation B, the other still works.
"""
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
from gen_top import check, exported_cards, system_usb_routes
from netlist import read
from test_cosim_main_cpu_data import open_pad_tracks
from cosim_mutate import open_pad


def probe(top, orientation):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/system_usb_probe.mjs',
                                      orientation], cwd=ROOT, env=env, text=True)
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
    system_circuit = read(args.card_board_dir / 'system/system.net')
    top = json.loads(args.top.read_text())
    links, paths, missing = system_usb_routes(system_circuit, args.system_board)
    assert links == {'A': True, 'B': True} and not missing
    assert len(paths) == 12 and all(p['route_mm'] is not None for p in paths)
    assert top['runtime']['system_usb_connected'] == links
    assert top['runtime']['system_usb_complete'] is True
    baseline_count = len(top['unmodeled_nets'])
    assert baseline_count <= 129
    assert not {'system:USB_CC1', 'system:USB_CC2'} & set(top['unmodeled_nets'])

    for ref, value in (('R2', '22'), ('R3', '22'), ('R4', '10k'), ('R5', '1k')):
        wrong = copy.deepcopy(system_circuit)
        wrong.components[ref] = (value, ('Device', 'R'))
        try:
            system_usb_routes(wrong, None)
        except ValueError as error:
            assert 'system USB' in str(error)
        else:
            raise AssertionError(f'changed {ref} value passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-system-usb-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        for orientation in ('A', 'B'):
            good = probe(args.top, orientation)
            assert good['port'] and good['finished'] and good['ping'] and \
                good['exitCode'] == 0 and good['state']['gpo'] == 2, good

        branches = (
            ('DM', 'source', 'U1', '46', '/USB_DM_MCU', 1, 'A'),
            ('DP', 'source', 'U1', '47', '/USB_DP_MCU', 1, 'B'),
            ('DM', 'A', 'J1', 'A7', '/USB_DM', 1, 'A'),
            ('DM', 'B', 'J1', 'B7', '/USB_DM', 1, 'B'),
            ('DP', 'A', 'J1', 'A6', '/USB_DP', 1, 'A'),
            ('DP', 'B', 'J1', 'B6', '/USB_DP', 1, 'B'),
            ('DM', 'esd3', 'U3', '3', '/USB_DM', 2, None),
            ('DM', 'esd4', 'U3', '4', '/USB_DM', 1, None),
            ('DP', 'esd1', 'U3', '1', '/USB_DP', 1, None),
            ('DP', 'esd6', 'U3', '6', '/USB_DP', 2, None),
            ('CC1', 'A', 'R4', '1', '/USB_CC1', None, 'A'),
            ('CC2', 'B', 'R5', '1', '/USB_CC2', None, 'B'),
        )
        for signal, leg, ref, pin, net, segments, orientation in branches:
            opened = temporary / f'open-{signal}-{leg}.kicad_pcb'
            if segments is None:
                open_pad(args.system_board, opened, ref, pin, net)
            else:
                open_pad_tracks(args.system_board, opened, ref, pin, net, segments)
            altered, _, missing = system_usb_routes(system_circuit, opened)
            assert missing, (signal, leg)
            if leg == 'source':
                assert altered == {'A': False, 'B': False}, (signal, leg, altered)
            elif leg in ('A', 'B'):
                assert altered[leg] is False, (signal, leg, altered)
            if orientation is None:
                continue
            mutant = check(cards, main_circuit, args.main_board, card_boards,
                           opened, args.cpu_board)
            assert mutant['runtime']['system_usb_connected'] == altered
            assert mutant['runtime']['system_usb_complete'] is False
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == baseline_count + 6
            changed_top = temporary / f'open-{signal}-{leg}.json'
            changed_top.write_text(json.dumps(mutant))
            bad = probe(changed_top, orientation)
            assert not bad['port'] and bad['state']['gpo'] == 2, bad
            if leg in ('A', 'B'):
                other = 'B' if leg == 'A' else 'A'
                other_state = probe(changed_top, other)
                assert other_state['port'] and other_state['ping'], other_state
            print(f'{signal} {leg} open: orientation {orientation} CDC unavailable')
        print('12/12 copper branches detected; eight active path opens gate CDC')


if __name__ == '__main__':
    main()
