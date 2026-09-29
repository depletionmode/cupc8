#!/usr/bin/env python3
"""Coverage accounting and the RP2040 crystal boot prerequisite.

1. Non-digital waivers (hw/cosim/coverage.py): every waived net names
   implemented analog catalogue checks; attaching a logic pin to a waived
   rail, or naming a check that has no command, turns the net back into a
   coverage gap.
2. Crystal networks (hw/cosim/gen_top.py crystal_routes): each RP2040's
   XIN/XOUT/1k/crystal/load-capacitor legs are bound to routed copper;
   source changes are refused, one opened launch restores its net as a gap
   and the native machine leaves that card's firmware stopped.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from coverage import audit, reviewed_analog_waivers  # noqa: E402
from gen_top import check, crystal_routes, exported_cards, implemented_checks  # noqa: E402
from netlist import Resistor, read  # noqa: E402
from cosim_mutate import board_args, card_boards, open_pad  # noqa: E402
from test_cosim_runtime import SLOT_PROBE, SYSTEM_BOOT_PROBE, run  # noqa: E402


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    implemented = implemented_checks()
    with tempfile.TemporaryDirectory(prefix='cupc8-coverage-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        circuits = {'main': main_circuit, **cards}

        # --- 1. non-digital waivers
        waivers = reviewed_analog_waivers(circuits, implemented)
        assert waivers['main:+3V3']['checks'] and 'POW-001' in waivers['main:+3V3']['checks']
        for key, waiver in waivers.items():
            assert set(waiver['checks']) <= implemented, key
            board, net = key.split(':', 1)
            assert waiver['pins'] == [f'{r}.{p}' for r, p in circuits[board].nets['/' + net]], key
        logic = copy.deepcopy(main_circuit)
        logic.nets['/+3V3'] = logic.nets['/+3V3'] + (('U7', '74'),)
        logic.pins[('U7', '74')] = '/+3V3'
        assert 'main:+3V3' not in reviewed_analog_waivers({**circuits, 'main': logic}, implemented)
        assert 'main:+3V3' in audit({**circuits, 'main': logic}, set(), set(), implemented)['unmodeled_nets']
        assert 'main:+3V3' not in reviewed_analog_waivers(circuits, implemented - {'POW-001'})
        driven = copy.deepcopy(main_circuit)
        driven.nets['/GND'] = driven.nets['/GND'] + (('U13', '4'),)  # a TCA9555 output, not a strap
        assert 'main:GND' not in reviewed_analog_waivers({**circuits, 'main': driven}, implemented)
        print(f'{len(waivers)} non-digital waivers name implemented checks; a logic pin on +3V3, '
              'an expander output on GND, or an unimplemented check removes the waiver')

        # --- 2. crystals: source binding
        links, paths, missing, nets = crystal_routes(cards, boards, args.system_board)
        assert all(links.values()) and not missing and len(paths) == 25, (links, missing, len(paths))
        for label, change in (
                ('XOUT resistor 10k', lambda c: setattr(c, 'resistors', tuple(
                    Resistor(r.ref, '10k', r.ends) if r.ref == 'R2' else r for r in c.resistors))),
                ('XIN load capacitor removed', lambda c: c.pins.pop(('C16', '1')))):
            wrong = copy.deepcopy(cards)
            change(wrong['gpu'])
            try:
                crystal_routes(wrong, None, None)
            except ValueError as error:
                print(f'crystal source binding refuses {label}: {error}')
            else:
                raise AssertionError(f'{label} passed crystal source binding')

        # --- 2. crystals: copper and the native machine
        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        good_top = temporary / 'good.json'
        good_top.write_text(json.dumps(good))
        frames = run(good_top, SLOT_PROBE)['frames']
        assert frames > 0 and run(good_top, SYSTEM_BOOT_PROBE)['systemCard']
        for board, ref, pin, net in (('gpu', 'U1', '20', '/XIN'), ('gpu', 'R2', '2', '/XTAL_OUT'),
                                     ('system', 'U1', '21', '/XOUT')):
            source = args.system_board if board == 'system' else boards[board]
            opened = temporary / f'open-{board}-{ref}-{pin}.kicad_pcb'
            tracks = open_pad(source, opened, ref, pin, net)
            mutant = check(cards, main_circuit, args.main_board,
                           {**boards, board: opened} if board != 'system' else boards,
                           opened if board == 'system' else args.system_board, args.cpu_board)
            now = mutant['runtime']['crystal_connected']
            assert not now[board] and all(v for k, v in now.items() if k != board), now
            assert f'{board}:{net[1:]}' in mutant['unmodeled_nets'] and not mutant['runtime']['routed_top']
            top = temporary / f'open-{board}-{ref}-{pin}.json'
            top.write_text(json.dumps(mutant))
            if board == 'gpu':
                bad = run(top, SLOT_PROBE)['frames']
                assert bad == 0, bad
                shown = f'GPU SPI frames {frames} -> 0'
            else:
                assert not run(top, SYSTEM_BOOT_PROBE)['systemCard']
                shown = 'system card firmware absent'
            print(f'open {board} {ref}.{pin} {net} ({tracks} tracks): crystal link cleared, '
                  f'{net[1:]} a coverage gap again, {shown}')
    print('coverage waivers and crystal boot prerequisites: all counterexamples detected')


if __name__ == '__main__':
    main()
