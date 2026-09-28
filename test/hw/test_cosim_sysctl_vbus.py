#!/usr/bin/env python3
"""Source, copper and native USB VBUS sense counterexamples for sysctl."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import CARDS, check, system_usb_vbus_routes  # noqa: E402
from netlist import read  # noqa: E402
from test_cosim_main_cpu_data import open_pad_tracks  # noqa: E402


def probe(top, orientation='A', host_vbus=True):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    args = ['node', 'test/emu/sysctl_vbus_probe.mjs', orientation]
    if not host_vbus:
        args.append('--no-host-vbus')
    output = subprocess.check_output(args, cwd=ROOT, env=env, text=True)
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
    system = read(args.card_board_dir / 'system/system.net')
    contacts, paths, missing = system_usb_vbus_routes(system, args.system_board)
    assert contacts == {'A': True, 'B': True} and not missing and len(paths) == 6
    assert all(path['route_mm'] is not None for path in paths)

    cards = {name: read(args.card_board_dir / name / f'{name}.net') for name in CARDS}
    main = read(args.main_netlist)
    card_boards = {name: args.card_board_dir / name / f'{name}.kicad_pcb'
                   for name in ('gpu', 'io', 'storage', 'wifi', 'eink')}
    canonical = check(cards, main, args.main_board, card_boards,
                      args.system_board, args.cpu_board)
    recorded = json.loads(args.top.read_text())
    assert recorded['runtime']['sysctl_usb_vbus_connected'] is True
    assert canonical['runtime']['sysctl_usb_vbus_connected'] is True
    assert canonical['runtime']['sysctl_usb_vbus_contacts'] == contacts
    assert len(canonical['unmodeled_nets']) == len(recorded['unmodeled_nets'])
    assert all(f'system:{name}' in canonical['runtime_nets']
               for name in ('USB_VBUS', 'VBUS_GATE', 'USB_nVBUS'))
    assert len(canonical['unmodeled_nets']) <= 285

    for ref, value in (('R10', '22k'), ('R22', '10k'), ('R23', '22k')):
        wrong = copy.deepcopy(system)
        wrong.components[ref] = (value, ('Device', 'R'))
        try:
            system_usb_vbus_routes(wrong, None)
        except ValueError as error:
            assert 'system USB VBUS' in str(error)
        else:
            raise AssertionError(f'changed {ref} value passed source binding')

    for orientation in ('A', 'B'):
        good = probe(args.top, orientation)
        assert good['ping'] and good['reply'][:2] == [0xc8, 0]
    absent = probe(args.top, 'A', False)
    assert not absent['ping'] and not absent['reply']

    with tempfile.TemporaryDirectory(prefix='cupc8-sysctl-vbus-') as directory:
        temporary = Path(directory)
        opened = temporary / 'open-r10-gate.kicad_pcb'
        open_pad_tracks(args.system_board, opened, 'R10', '2', '/VBUS_GATE', 2)
        broken, _, missing = system_usb_vbus_routes(system, opened)
        assert broken == {'A': False, 'B': False} and missing
        mutant = check(cards, main, args.main_board, card_boards,
                       opened, args.cpu_board)
        assert mutant['runtime']['sysctl_usb_vbus_connected'] is False
        assert mutant['runtime']['sysctl_usb_vbus_contacts'] == broken
        assert mutant['runtime']['routed_top'] is False
        assert len(mutant['unmodeled_nets']) == len(canonical['unmodeled_nets']) + 3
        for name in ('USB_VBUS', 'VBUS_GATE', 'USB_nVBUS'):
            assert f'system:{name}' in mutant['unmodeled_nets']
        mutant_top = temporary / 'open-r10-gate.json'
        mutant_top.write_text(json.dumps(mutant))
        failed = probe(mutant_top)
        assert not failed['ping'] and not failed['reply']
        contact_open = temporary / 'open-contact-a.kicad_pcb'
        open_pad_tracks(args.system_board, contact_open, 'J1', 'A4B9', '/USB_VBUS', 1)
        one_contact, _, missing = system_usb_vbus_routes(system, contact_open)
        assert one_contact == {'A': False, 'B': True} and missing
        one_top = check(cards, main, args.main_board, card_boards,
                        contact_open, args.cpu_board)
        assert one_top['runtime']['sysctl_usb_vbus_contacts'] == one_contact
        assert len(one_top['unmodeled_nets']) == len(canonical['unmodeled_nets']) + 3
        one_top_file = temporary / 'open-contact-a.json'
        one_top_file.write_text(json.dumps(one_top))
        assert not probe(one_top_file, 'A')['ping']
        assert probe(one_top_file, 'B')['ping']
    print(f'sysctl VBUS: six routed legs; {len(canonical["unmodeled_nets"])} strict gaps; '
          'host, absent host, open gate and one-contact open produce the expected native CDC results')


if __name__ == '__main__':
    main()
