#!/usr/bin/env python3
"""Firmware-driven indicator LEDs on the RP2040 cards, bound to routed copper.

hw/cosim/gen_top.py card_led_routes finds each RP2040 GPIO -> resistor ->
LED anode (cathode on GND) and measures both signal legs; the native
machine reports an LED lit only while its firmware drives the GPIO high and
both legs are whole (Machine.leds()). Checks: the seven indicators (storage
ACT/CARD, IO KEY/KBD, e-ink REFRESH, system USB TX/RX) light in real use; a
changed netlist (LED cathode off GND, an extra pin on the GPIO net) is
refused or drops the LED back to a coverage gap; one opened launch per
card leaves exactly that LED dark while the card's other LED still works.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import card_led_routes, check, exported_cards  # noqa: E402
from netlist import read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402

EXPECTED = {'storage': {'LED_ACT', 'LED_CARD'}, 'io': {'LED_KEY', 'LED_KBD'},
            'eink': {'LED_REFRESH'}, 'system': {'LED_USB_TX', 'LED_USB_RX'}}
OPENS = [('storage', 'R5', '1', '/LED_ACT', 'LED_ACT'), ('io', 'D3', '2', '/LED_KEY_A', 'LED_KEY'),
         ('eink', 'U1', '36', '/LED_REFRESH', 'LED_REFRESH'), ('system', 'R20', '1', '/LED_USB_TX', 'LED_USB_TX')]


def lit(result, kind, net):
    row = result.get(kind, {}).get(net)
    return bool(row and row['lit'] or row and row['rises'])


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    with tempfile.TemporaryDirectory(prefix='cupc8-leds-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        rows, paths, missing = card_led_routes(cards, boards, args.system_board)
        found = {k: {r['net'] for r in v} for k, v in rows.items() if v}
        assert found == EXPECTED and not missing, (found, missing)
        assert all(r['connected'] for v in rows.values() for r in v)
        print(f'{sum(len(v) for v in rows.values())} indicators, {len(paths)} routed legs')

        grounded = copy.deepcopy(cards)
        grounded['storage'].pins[('D2', '1')] = '/3V3'
        try:
            card_led_routes(grounded, None, None)
        except ValueError as error:
            print(f'source binding refuses an LED cathode off GND: {error}')
        else:
            raise AssertionError('an LED cathode off GND passed source binding')
        loaded = copy.deepcopy(cards)
        loaded['io'].nets['/LED_KEY'] = loaded['io'].nets['/LED_KEY'] + (('TP1', '1'),)
        again = check(loaded, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        assert 'io:LED_KEY' in again['unmodeled_nets'], 'an extra pin on LED_KEY kept it modelled'
        print('an extra pin on the IO KEY LED net drops it from the model: io:LED_KEY is a gap again')

        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        good_top = temporary / 'good.json'
        good_top.write_text(json.dumps(good))
        result = node_probe('led_probe.mjs', good_top)
        assert result['promptA'] and result['ping'] == 0, result
        for kind, nets in EXPECTED.items():
            for net in nets:
                assert lit(result, kind, net), (kind, net, result)
        print('native: every indicator lights in use ' + json.dumps(
            {k: {n: v['rises'] for n, v in result[k].items()} for k in EXPECTED}))

        opened_boards = dict(boards)
        system_board = args.system_board
        for kind, ref, pin, net, _ in OPENS:
            source = args.system_board if kind == 'system' else boards[kind]
            target = temporary / f'open-{kind}.kicad_pcb'
            open_pad(source, target, ref, pin, net)
            if kind == 'system':
                system_board = target
            else:
                opened_boards[kind] = target
        mutant = check(cards, main_circuit, args.main_board, opened_boards, system_board, args.cpu_board)
        assert not mutant['runtime']['routed_top']
        for kind, _, _, _, net in OPENS:
            assert f'{kind}:{net}' in mutant['unmodeled_nets'], (kind, net)
        mutant_top = temporary / 'open.json'
        mutant_top.write_text(json.dumps(mutant))
        bad = node_probe('led_probe.mjs', mutant_top)
        for kind, _, _, _, net in OPENS:
            assert not lit(bad, kind, net), (kind, net, bad[kind])
            for other in EXPECTED[kind] - {net}:
                assert lit(bad, kind, other), (kind, other, bad[kind])
            print(f'open {kind} {net}: dark in use, coverage gap restored'
                  + (f'; {", ".join(EXPECTED[kind] - {net})} still lights' if EXPECTED[kind] - {net} else ''))
    print('card indicator LEDs: source, copper and native counterexamples detected')


if __name__ == '__main__':
    main()
