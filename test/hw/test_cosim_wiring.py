#!/usr/bin/env python3
"""Schematic wiring failures must be visible to the generated top."""
import argparse
import copy
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards, named_pin
from netlist import read
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse


def rejected(cards, main, description):
    try:
        check(cards, main)
    except ValueError as error:
        print(f'{description}: rejected ({error})')
        return
    raise AssertionError(f'{description}: a wiring fault passed')


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--main-netlist', type=Path, default=ROOT / 'build/hw/main/main.net')
    parser.add_argument('--main-board', type=Path, help='routed PCB for reset and memory-write copper-open counterexamples')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-cx-') as temporary:
        cards = exported_cards(Path(temporary))
        main = read(args.main_netlist)
        manifest = check(cards, main)
        print(f"valid top: {len(manifest['contacts'])} contacts, {len(manifest['paths'])} paths")
        assert 'main:MEM_A0' in manifest['runtime_nets']
        assert 'main:CPU_CLK' in manifest['structural_only_nets']
        assert 'main:CPU_CLK' in manifest['unmodeled_nets']
        assert not manifest['coverage_complete']

        if args.main_board:
            good_route = check(cards, main, args.main_board)
            assert good_route['runtime']['por_connected']
            assert good_route['runtime']['memory_write_links'] == {'ram': True, 'rom': True}
            physical = pcbnew.LoadBoard(str(args.main_board))
            def open_launch(ref, pin, net):
                board = parse(args.main_board.read_text())
                footprint = physical.FindFootprintByReference(ref)
                pad = next(item for item in footprint.Pads() if item.GetNumber() == pin)
                pos = pad.GetPosition()
                launch = (round(pcbnew.ToMM(pos.x), 4), round(pcbnew.ToMM(pos.y), 4))
                matches = [item for item in board[1:]
                           if isinstance(item, list) and item and item[0] == 'segment' and
                           find1(item, 'net') and find1(item, 'net')[1] == net and
                           launch in (tuple(round(float(x), 4) for x in find1(item, end)[1:])
                                      for end in ('start', 'end'))]
                if len(matches) != 1:
                    raise AssertionError(f'{net} {ref}.{pin} launch has {len(matches)} tracks, expected one')
                board.remove(matches[0])
                opened = Path(temporary) / f'open-{net.lstrip("/")}.kicad_pcb'
                opened.write_text(dump(board) + '\n')
                return check(cards, main, opened)

            bad_route = open_launch('U6', '2', '/nPOR')
            if bad_route['runtime']['por_connected'] or bad_route['runtime']['routed_top'] or \
                    'main:nPOR' not in bad_route['runtime_nets']:
                raise AssertionError('removed nPOR copper did not change the executed reset path')
            print('open supervisor nPOR copper disables the native reset-release path')
            bad_write = open_launch('U7', '114', '/MEM_nWE')
            if bad_write['runtime']['memory_write_links'] != {'ram': False, 'rom': False} or \
                    bad_write['runtime']['routed_top'] or \
                    'main:MEM_nWE' not in bad_write['runtime_nets']:
                raise AssertionError('removed /WE copper did not disable both chip-write paths')
            print('open chipset MEM_nWE launch disables RAM and ROM writes')

        swapped = copy.deepcopy(main)
        a, b = ('J11', 'B13'), ('J11', 'B15')
        swapped.pins[a], swapped.pins[b] = swapped.pins[b], swapped.pins[a]
        rejected(cards, swapped, 'swapped SCK/MOSI contacts')

        missing = copy.deepcopy(main)
        del missing.pins[('J13', 'A14')]
        rejected(cards, missing, 'missing slot 3 select')

        absent_pull = copy.deepcopy(main)
        miso = absent_pull.net('J11', 'B16')
        absent_pull.resistors = tuple(r for r in absent_pull.resistors
                                      if not (r.value == '47k' and miso in r.ends))
        rejected(cards, absent_pull, 'missing MISO idle pull')

        broken_policy = copy.deepcopy(main)
        del broken_policy.pins[named_pin(broken_policy, 'U5', 'OUT')]
        rejected(cards, broken_policy, 'missing Type-C power policy output')

        broken_threshold = copy.deepcopy(main)
        broken_threshold.resistors = tuple(r for r in broken_threshold.resistors if r.ref != 'R15')
        rejected(cards, broken_threshold, 'missing Type-C comparator reference resistor')

        broken_clock = copy.deepcopy(main)
        broken_clock.resistors = tuple(r for r in broken_clock.resistors if r.ref != 'R17')
        rejected(cards, broken_clock, 'missing chipset oscillator series resistor')

        broken_por = copy.deepcopy(main)
        del broken_por.pins[('U6', '2')]
        rejected(cards, broken_por, 'missing supervisor reset output')

        broken_write = copy.deepcopy(main)
        del broken_write.pins[('U7', '114')]
        rejected(cards, broken_write, 'missing chipset memory-write output')

        broken_io = copy.deepcopy(cards)
        broken_io['io'].resistors = tuple(r for r in broken_io['io'].resistors if r.ref != 'R14')
        rejected(broken_io, main, 'missing IO USB D- series resistor')

        broken_sd = copy.deepcopy(cards)
        del broken_sd['storage'].pins[('J2', '5')]
        rejected(broken_sd, main, 'missing storage SD clock contact')

        broken_hdmi = copy.deepcopy(cards)
        broken_hdmi['gpu'].resistors = tuple(r for r in broken_hdmi['gpu'].resistors if r.ref != 'RN2.3')
        rejected(broken_hdmi, main, 'missing HDMI clock-positive series resistor')

        broken_epd = copy.deepcopy(cards)
        broken_epd['eink'].resistors = tuple(r for r in broken_epd['eink'].resistors if r.ref != 'R11')
        rejected(broken_epd, main, 'missing e-paper clock series resistor')


if __name__ == '__main__':
    main_cli()
