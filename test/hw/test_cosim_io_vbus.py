#!/usr/bin/env python3
"""IO card keyboard VBUS switch on routed copper: enable, output and fault sense.

hw/cosim/gen_top.py io_vbus_routes binds GPIO7 to the SY6280AAC's EN (100 k
pull-down), its OUT to the receptacle VCC, and GPIO8 to the 15 k / 22 k
divider that reads VBUS (the switch has no fault flag; io-card.md). The
native machine powers the USB keyboard only with VBUS on and drives GPIO8
low when the divider reads VBUS off; the real IO firmware reports GPIO8 low
as VBUS_FAULT in every slot SPI status byte. Checks: the good board shows no
fault and a keyboard; a changed divider resistor or switch part is refused;
an open EN leg turns VBUS off (fault reported, no keyboard); an open 15 k resistor
(its VBUS end) reports a fault with VBUS fine; an open EN leg with the 22 k leg open masks
the fault (no keyboard, no report). Each open restores its net as a gap.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import check, exported_cards, io_vbus_routes  # noqa: E402
from netlist import Resistor, read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    with tempfile.TemporaryDirectory(prefix='cupc8-io-vbus-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        routed, paths, missing = io_vbus_routes(cards['io'], boards['io'])
        assert routed['vbus_on'] and not routed['nfault_low'] and all(
            routed[k] for k in ('enable', 'out', 'sense_top', 'sense_r12', 'sense_r13')), routed
        assert not missing and len(paths) == 5 and all(p['route_mm'] for p in paths), (missing, paths)
        print(f'{len(paths)} VBUS switch legs routed: VBUS on, fault sense reads high')

        wrong = copy.deepcopy(cards['io'])
        wrong.resistors = tuple(Resistor(r.ref, '150k', r.ends) if r.value == '15k' else r for r in wrong.resistors)
        try:
            io_vbus_routes(wrong, None)
        except ValueError as error:
            print(f'source binding refuses a changed sense divider: {error}')
        else:
            raise AssertionError('a 150k sense resistor passed source binding')
        other = copy.deepcopy(cards['io'])
        other.components['U5'] = ('TPS2553', other.components['U5'][1])
        try:
            io_vbus_routes(other, None)
        except ValueError as error:
            print(f'source binding refuses another switch part: {error}')
        else:
            raise AssertionError('another switch passed source binding')

        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        assert 'io:VBUS_EN' in good['runtime_nets'] and 'io:VBUS_nFAULT' in good['runtime_nets']
        good_top = temporary / 'good.json'
        good_top.write_text(json.dumps(good))
        base = node_probe('io_vbus_probe.mjs', good_top)
        assert base['frames'] > 0 and base['faults'] == 0 and base['keyboard'], base
        print(f'native: {base["frames"]} IO slot frames, no VBUS_FAULT, keyboard attached')

        cases = (
            ('EN leg open (U5.4)', [('U5', '4', '/VBUS_EN')], {'io:VBUS_EN'},
             lambda r: r['faults'] > 0 and not r['keyboard'], 'VBUS off: fault reported, no keyboard'),
            ('15 k resistor VBUS end open (R12.1)', [('R12', '1', '/VBUS')], {'io:VBUS_nFAULT'},
             lambda r: r['faults'] > 0 and r['keyboard'], 'a fault reported with VBUS fine'),
            ('EN leg and 22 k leg open', [('U5', '4', '/VBUS_EN'), ('R13', '1', '/VBUS_nFAULT')],
             {'io:VBUS_EN', 'io:VBUS_nFAULT'},
             lambda r: r['faults'] == 0 and not r['keyboard'], 'VBUS off, fault masked, no keyboard'),
        )
        for label, opens, gaps, expected, shown in cases:
            board = boards['io']
            for i, (ref, pin, net) in enumerate(opens):
                target = temporary / f'open-{label[:3]}-{i}.kicad_pcb'
                open_pad(board, target, ref, pin, net)
                board = target
            mutant = check(cards, main_circuit, args.main_board, {**boards, 'io': board},
                           args.system_board, args.cpu_board)
            assert gaps <= set(mutant['unmodeled_nets']) and not mutant['runtime']['routed_top'], label
            top = temporary / f'open-{label[:3]}.json'
            top.write_text(json.dumps(mutant))
            result = node_probe('io_vbus_probe.mjs', top)
            assert result['frames'] > 0 and expected(result), (label, result)
            print(f'open {label}: {shown}; {sorted(gaps)} coverage gap(s) again')
    print('IO VBUS switch: source, copper and native counterexamples detected')


if __name__ == '__main__':
    main()
