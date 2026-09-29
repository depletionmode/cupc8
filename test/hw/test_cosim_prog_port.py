#!/usr/bin/env python3
"""The card programming port on routed copper: sysctl, the two 4051 muxes, the slots' SWD pins.

hw/cosim/gen_top.py prog_port_routes binds PROG_CLK / PROG_IO from the system
card through the main board to the mux commons, MUX_SEL0-2 to both muxes'
selects, each slot's 33 ohm channel legs, and every RP2040 card's SWCLK /
SWDIO; the mux channel and select bit each signal reaches are read from the
netlist. The native machine puts a bit-level SW-DP (fw/test/swdtarget.c) in
each slot with an RP2040 card and whole copper, decoded through the muxes
from the selects sysctl really drives. Checks: cupc8.py's own flash routine
programs every fitted card and verifies it; an empty slot answers nobody; a
moved mux select, a changed series resistor and a slot pair on two channels
are refused at the source; and one copper open each on the sysctl select,
the mux common, a slot's clock channel and a card's debug pin changes the result
(the wrong slot is programmed, nothing answers, or that card is skipped) and
restores its nets as coverage gaps.
"""
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import check, exported_cards, prog_port_routes  # noqa: E402
from netlist import Resistor, read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402
from prog_port_exercise import digest  # noqa: E402


def swap_pins(circuit, first, second):
    """Exchange the nets of two pins (a schematic wiring swap)."""
    a, b = circuit.pins[first], circuit.pins[second]
    circuit.pins[first], circuit.pins[second] = b, a
    circuit.nets[a] = tuple(second if node == first else node for node in circuit.nets[a])
    circuit.nets[b] = tuple(first if node == second else node for node in circuit.nets[b])


def sha(result, slot):
    """The SHA-256 of the first 8 KB of a slot's SWD target flash; None: no target there."""
    target = result['targets'][str(slot)]
    return target and target['sha']


def program(top, plan):
    return node_probe('prog_port_probe.mjs', top, json.dumps(plan))


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    with tempfile.TemporaryDirectory(prefix='cupc8-prog-port-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        config, paths, missing, _ = prog_port_routes(main_circuit, cards, args.main_board, args.system_board, boards)
        assert not missing and len(paths) == 45 and all(p['route_mm'] for p in paths), missing
        assert config['sel_bit'] == [0, 1, 2] and config['channel'] == [0, 1, 2, 3, 4, 5]
        assert config['clk'] and config['io'] and all(config['sel_whole']) and all(config['slot_legs'])
        assert all(config['card'].values()) and set(config['card']) == {'gpu', 'io', 'storage', 'eink'}
        print(f'{len(paths)} programming-port legs routed: mux channels {config["channel"]}, selects {config["sel_bit"]}')

        def refused(label, change, expected):
            wrong = copy.deepcopy(main_circuit)
            change(wrong)
            try:
                prog_port_routes(wrong, cards, None, None, None)
            except ValueError as error:
                assert expected in str(error), (label, error)
                print(f'source binding refuses {label}: {error}')
            else:
                raise AssertionError(f'{label} passed source binding')

        pin = lambda circuit, ref, name: next(p for (r, p), n in circuit.pin_names.items()  # noqa: E731
                                              if r == ref and n == name)
        refused('a mux select swapped on one mux',
                lambda c: swap_pins(c, ('U12', pin(c, 'U12', 'S0')), ('U12', pin(c, 'U12', 'S1'))),
                'different select inputs')
        refused('a slot clock and data on different channels',
                lambda c: swap_pins(c, ('U11', pin(c, 'U11', 'A2')), ('U11', pin(c, 'U11', 'A3'))),
                'channels differ')
        refused('a changed series resistor', lambda c: setattr(c, 'resistors', tuple(
            Resistor(r.ref, '47', r.ends) if r.ref == 'R307' else r for r in c.resistors)), '33 ohm')

        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        for net in ('main:MUX_SEL0', 'main:PROG_CLK', 'main:PROG_IO', 'main:MUX_CLK1', 'main:MUX_IO6',
                    'main:SLOT1_SWCLK', 'main:SLOT6_SWDIO', 'system:MUX_SEL2', 'system:PROG_CLK',
                    'gpu:SWCLK', 'io:SWDIO', 'storage:SWCLK', 'eink:SWDIO'):
            assert net in good['runtime_nets'], net
        good_top = temporary / 'good.json'
        good_top.write_text(json.dumps(good))
        plan = [{'slot': 1, 'seed': 1}, {'slot': 2, 'seed': 2}, {'slot': 3, 'seed': 3},
                {'slot': 4, 'seed': 4}, {'slot': 5, 'seed': 5}]
        result = program(good_top, plan)
        lines = result['output'].splitlines()
        for slot in (1, 2, 3, 4):
            assert f'slot {slot}: flashed' in lines, result['output']
            assert sha(result, slot) == digest(slot), (slot, result['targets'][str(slot)])
            assert result['targets'][str(slot)]['resets'] == 1, result['targets'][str(slot)]
        assert any(l.startswith('slot 5: FAILED') and 'no RP2040 answered' in l for l in lines), result['output']
        assert result['targets']['5'] is None and result['targets']['6'] is None
        print('native: cupc8.py flashed and verified the GPU, IO, storage and e-ink cards through the '
              f'muxes (each target holds its own image, reset once); the empty slot 5 answered nobody '
              f'({result["ns"] / 1e9:.1f} s of machine time)')

        # one copper open each; the plan decides what is visible
        cases = (
            ('sysctl MUX_SEL1 launch open (U1.32)', 'system', 'U1', '32', '/MUX_SEL1', {'system:MUX_SEL1'},
             [{'slot': 1, 'seed': 11}],
             lambda r: sha(r, 1) != digest(11) and sha(r, 3) == digest(11),
             'a floating select reads high: slot 1 was addressed as slot 3, and slot 3 was programmed'),
            ('PROG_IO at the mux U12.3 open', 'main', 'U12', '3', '/PROG_IO', {'main:PROG_IO'},
             [{'slot': 2, 'seed': 12}],
             lambda r: 'slot 2: FAILED' in r['output'] and sha(r, 2) != digest(12),
             'nothing answers on any slot'),
            ('slot 2 clock channel open at the mux (U11.14)', 'main', 'U11', '14', '/MUX_CLK2', {'main:MUX_CLK2'},
             [{'slot': 1, 'seed': 13}, {'slot': 2, 'seed': 14}],
             lambda r: 'slot 1: flashed' in r['output'] and 'slot 2: FAILED' in r['output'] and
             sha(r, 1) == digest(13) and sha(r, 2) != digest(14),
             'slot 1 still programs, slot 2 answers nobody'),
            ('e-ink card SWDIO open (J1.B7)', 'eink', 'J1', 'B7', '/SWDIO', {'eink:SWDIO'},
             [{'slot': 4, 'seed': 15}],
             lambda r: 'slot 4: FAILED' in r['output'] and sha(r, 4) is None,
             'the e-ink card has no SWD target'),
        )
        for label, board, ref, pad, net, gaps, plan, expected, shown in cases:
            source = {'main': args.main_board, 'system': args.system_board}.get(board) or boards[board]
            opened = temporary / f'open-{board}-{ref}-{pad}.kicad_pcb'
            open_pad(source, opened, ref, pad, net)
            mutant = check(cards, main_circuit, opened if board == 'main' else args.main_board,
                           {**boards, board: opened} if board in boards else boards,
                           opened if board == 'system' else args.system_board, args.cpu_board)
            assert gaps <= set(mutant['unmodeled_nets']) and not mutant['runtime']['routed_top'], label
            top = temporary / f'open-{board}-{ref}.json'
            top.write_text(json.dumps(mutant))
            bad = program(top, plan)
            assert expected(bad), (label, bad)
            print(f'open {label}: {shown}; {sorted(gaps)} a coverage gap again')
    print('programming port: source, copper and native counterexamples detected')


if __name__ == '__main__':
    main()
