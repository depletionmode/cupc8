#!/usr/bin/env python3
"""Indicator LEDs on routed copper: firmware-driven and rail indicators.

hw/cosim/gen_top.py card_led_routes finds each RP2040 GPIO -> resistor ->
LED anode (cathode on GND) and measures both signal legs; the native
machine reports an LED lit only while its firmware drives the GPIO high and
both legs are whole (Machine.leds()). Checks: the seven indicators (storage
ACT/CARD, IO KEY/KBD, e-ink REFRESH, system USB TX/RX) light in real use; a
changed netlist (LED cathode off GND, an extra pin on the GPIO net) is
refused or drops the LED back to a coverage gap; one opened launch per
card leaves exactly that LED dark while the card's other LED still works.

Rail indicators (power, 5V/3V3/1V2 present; rail_indicator_routes): found by
topology (rail -> resistor -> LED -> GND, or the 1V2 indicators' NPN switch),
each leg measured on the routed copper; Machine.powerLeds() lights one while
its legs are whole, with the rail assumed present. A resistor moved off its
rail drops the indicator out of the model (its nets are coverage gaps again);
one opened leg per board darkens exactly that indicator.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import card_led_routes, check, exported_cards, rail_indicator_routes  # noqa: E402
from netlist import read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402

EXPECTED = {'storage': {'LED_ACT', 'LED_CARD'}, 'io': {'LED_KEY', 'LED_KBD'},
            'eink': {'LED_REFRESH'}, 'system': {'LED_USB_TX', 'LED_USB_RX'}}
OPENS = [('storage', 'R5', '1', '/LED_ACT', 'LED_ACT'), ('io', 'D3', '2', '/LED_KEY_A', 'LED_KEY'),
         ('eink', 'U1', '36', '/LED_REFRESH', 'LED_REFRESH'), ('system', 'R20', '1', '/LED_USB_TX', 'LED_USB_TX')]


# board -> the indicator LEDs the schematics carry (reference, the rail feeding it)
RAIL_LEDS = {'main': {('D2', '+5V'), ('D3', '+3V3'), ('D4', '+3V3'), ('D6', '+3V3')},
             'cpu': {('D1', '3V3'), ('D2', '3V3')}, 'gpu': {('D1', '3V3')}, 'io': {('D1', '3V3')},
             'storage': {('D1', '3V3')}, 'wifi': {('D1', '3V3')}, 'eink': {('D1', '3V3')},
             'system': {('D1', '+3V3')}}
# one opened leg per board: (board, reference, pad, net, LED)
RAIL_OPENS = [('main', 'R10', '2', '/LED_3V3', 'D3'), ('cpu', 'R8', '2', '/LED_B', 'D2'),
              ('gpu', 'D1', '2', '/LED_PWR', 'D1'), ('storage', 'R4', '2', '/LED_PWR', 'D1'),
              ('system', 'R9', '2', '/LED_PWR', 'D1')]


def rail_pcbs(args, boards):
    return {'main': args.main_board, 'cpu': args.cpu_board, 'system': args.system_board, **boards}


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
        # --- rail indicators
        circuits = {'main': main_circuit, **cards}
        rails, rail_paths, rail_missing = rail_indicator_routes(circuits, rail_pcbs(args, boards))
        found = {b: {(r['led'], r['rail']) for r in rows} for b, rows in rails.items()}
        assert found == RAIL_LEDS and not rail_missing, (found, rail_missing)
        assert all(r['connected'] for rows in rails.values() for r in rows)
        print(f'{sum(len(v) for v in rails.values())} rail indicators, {len(rail_paths)} routed legs')
        unfed = copy.deepcopy(cards)
        unfed['storage'].pins[('R4', '1')] = '/GND'          # the LED resistor off its rail
        moved, _, _ = rail_indicator_routes({**circuits, 'storage': unfed['storage']}, {})
        assert not moved['storage'], 'a resistor off its rail still made a rail indicator'
        print('a power-LED resistor moved off its rail drops the indicator out of the model')
        for board, nets in (('main', {'LED_3V3', 'LED_5V', 'LED_PWR', 'LED_1V2_A', 'LED_1V2_K', 'Q1_B'}),
                            ('cpu', {'PWR_LED_A', 'LED_A', 'LED_K', 'LED_B'}), ('wifi', {'LED_PWR'}),
                            ('gpu', {'LED_PWR'}), ('system', {'LED_PWR'})):
            assert not {f'{board}:{n}' for n in nets} & set(good['unmodeled_nets']), (board, nets)
        powered = node_probe('power_led_probe.mjs', good_top)
        assert powered and all(row['lit'] for row in powered), powered
        print(f'native: {len(powered)} rail indicators lit (main, CPU, system and four slot cards)')
        opened_boards = dict(boards)
        opened = {'main': args.main_board, 'cpu': args.cpu_board, 'system': args.system_board}
        for board, ref, pin, net, led in RAIL_OPENS:
            source = opened[board] if board in opened else boards[board]
            target = temporary / f'rail-open-{board}.kicad_pcb'
            open_pad(source, target, ref, pin, net)
            if board in opened:
                opened[board] = target
            else:
                opened_boards[board] = target
        mutant = check(cards, main_circuit, opened['main'], opened_boards, opened['system'], opened['cpu'])
        rows = {b: {r['led']: r['connected'] for r in v} for b, v in mutant['runtime']['rail_leds'].items()}
        for board, _, _, net, led in RAIL_OPENS:
            assert rows[board][led] is False, (board, led)
            assert f'{board}:{net.lstrip("/")}' in mutant['unmodeled_nets'], (board, net)
            print(f'open {board} {led} ({net}): the indicator leaves the model; {board}:{net.lstrip("/")} is a gap again')
        bad_top = temporary / 'rail-open.json'
        bad_top.write_text(json.dumps(mutant))
        bad = node_probe('power_led_probe.mjs', bad_top)
        dark = {(r['board'], r['led']) for r in bad if not r['lit']}
        assert dark == {(b, led) for b, _, _, _, led in RAIL_OPENS if b != 'wifi'}, dark
        print('native: exactly the opened indicators are dark: ' + ', '.join(f'{b} {l}' for b, l in sorted(dark)))
    print('card indicator LEDs: source, copper and native counterexamples detected')


if __name__ == '__main__':
    main()
