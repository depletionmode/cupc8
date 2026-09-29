#!/usr/bin/env python3
"""IO keyboard host PHY source, copper and native counterexamples."""
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
from gen_top import check, exported_cards, io_usb_host_routes
from netlist import read
from cosim_mutate import open_pad


def probe(top):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/cpu_irq_probe.mjs', '0'],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(output.strip())['state']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, required=True)
    parser.add_argument('--main-board', type=Path, required=True)
    parser.add_argument('--card-board-dir', type=Path, required=True)
    parser.add_argument('--system-board', type=Path, required=True)
    parser.add_argument('--cpu-board', type=Path, required=True)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    io = read(args.card_board_dir / 'io/io.net')
    board = args.card_board_dir / 'io/io.kicad_pcb'
    top = json.loads(args.top.read_text())
    connected, paths, missing = io_usb_host_routes(io, board)
    assert connected and not missing and len(paths) == 8
    assert all(path['route_mm'] is not None for path in paths)
    assert top['runtime']['io_usb_host'] is True
    baseline = len(top['unmodeled_nets'])

    for ref in ('R14', 'R15'):
        wrong = copy.deepcopy(io)
        wrong.components[ref] = ('22R', ('Device', 'R'))
        try:
            io_usb_host_routes(wrong, None)
        except ValueError as error:
            assert 'IO USB host' in str(error)
        else:
            raise AssertionError(f'changed {ref} passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-io-usb-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        main = read(args.main_netlist)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        assert probe(args.top)['gpo'] == 0xa0
        # (how many track segments end on a pad depends on the routing: any number >= 1 is opened)
        for label, ref, pin, net, active in (
                ('dm-source', 'U1', '46', '/USB_DM', True),
                ('dp-source', 'U1', '47', '/USB_DP', True),
                ('dm-contact', 'J2', '2', '/USB_CONN_DM', True),
                ('dp-contact', 'J2', '3', '/USB_CONN_DP', True),
                ('dm-esd', 'U6', '1', '/USB_CONN_DM', None),
                ('dp-esd', 'U6', '3', '/USB_CONN_DP', None)):
            opened = temporary / f'{label}.kicad_pcb'
            open_pad(board, opened, ref, pin, net)
            link, _, gaps = io_usb_host_routes(io, opened)
            if active is None:
                # An ESD pad may also join the through route. Opening all
                # its launch tracks can disconnect the receptacle too;
                # check the native outcome against the measured copper.
                assert f'io:{net.lstrip("/")}_esd_copper' in gaps
                active = any(gap.endswith(('_source_copper', '_contact_copper'))
                             for gap in gaps)
            assert gaps and link is (not active), (label, link, gaps)
            card_boards['io'] = opened
            mutant = check(cards, main, args.main_board, card_boards,
                           args.system_board, args.cpu_board)
            assert mutant['runtime']['io_usb_host'] is (not active)
            assert mutant['runtime']['routed_top'] is False
            assert len(mutant['unmodeled_nets']) == baseline + 4
            for name in ('USB_DM', 'USB_DP', 'USB_CONN_DM', 'USB_CONN_DP'):
                assert f'io:{name}' in mutant['unmodeled_nets']
            if active:
                changed_top = temporary / f'{label}.json'
                changed_top.write_text(json.dumps(mutant))
                assert probe(changed_top)['gpo'] == 0x11
            print(f'{label}: host {link}, four strict coverage gaps restored')


if __name__ == '__main__':
    main()
