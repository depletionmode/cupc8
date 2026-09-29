#!/usr/bin/env python3
"""sysctl's machine inputs on routed copper: I2C expanders, CPU presence, ADC.

hw/cosim/gen_top.py i2c_expander_routes binds sysctl GPIO24/25 through the
system socket to both TCA9555s (addresses from their A0-A2 straps) and the
CPU card's PRSNT1-PRSNT2 loop to U14 P10; adc_sense_routes binds the Type-C
CC1/CC2 contacts to GPIO26/27 and +1V2 through R100 to GPIO28. The native
machine puts the expanders on sysctl's I2C0 and the source's CC voltage and
1.2 V on its ADC, so `cupc8.py status` reads the CPU card present, the
source class and the 1V2 rail. A moved address strap is refused; an open
presence leg reads the card missing; an open SDA launch takes the
expanders off the bus; an open CC1 leg loses the source class with the
cable one way round but not the other; an open R100 leg reads 1V2 as 0 mV.
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import adc_sense_routes, check, exported_cards, i2c_expander_routes  # noqa: E402
from netlist import read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402


def status(top, **options):
    result = node_probe('fpga_config_probe.mjs', top, json.dumps([['status']]),
                        env={'CUPC8_PROBE_OPTS': json.dumps(options)})
    return result['commands'][0]['output']


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    with tempfile.TemporaryDirectory(prefix='cupc8-sysctl-inputs-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        rows, paths, missing, _ = i2c_expander_routes(main_circuit, cards, args.main_board,
                                                      args.cpu_board, args.system_board)
        assert [(x['address'], x['link']) for x in rows['expanders']] == [(0x20, True), (0x21, True)]
        assert rows['cpu_present_link'] and not missing and all(p['route_mm'] for p in paths)
        adc, adc_paths, adc_missing, _ = adc_sense_routes(main_circuit, cards['system'],
                                                          args.main_board, args.system_board)
        assert all(adc.values()) and not adc_missing and len(adc_paths) == 6
        print(f'{len(paths)} I2C/presence and {len(adc_paths)} ADC legs routed; expanders at $20/$21')

        moved = copy.deepcopy(main_circuit)
        a0 = next((r, p) for (r, p), n in moved.pin_names.items() if r == 'U14' and n == 'A0')
        moved.pins[a0] = '/GND'
        try:
            i2c_expander_routes(moved, cards, None, None, None)
        except ValueError as error:
            print(f'source binding refuses a moved U14 address strap: {error}')
        else:
            raise AssertionError('two expanders at one address passed source binding')
        wrong = copy.deepcopy(main_circuit)
        wrong.resistors = tuple(type(r)(r.ref, '10k', r.ends) if r.ref == 'R100' else r
                                for r in wrong.resistors)
        try:
            adc_sense_routes(wrong, cards['system'], None, None)
        except ValueError as error:
            print(f'source binding refuses a changed 1V2 sense resistor: {error}')
        else:
            raise AssertionError('a 10k 1V2 sense resistor passed source binding')

        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        for net in ('main:I2C_SDA', 'main:I2C_SCL', 'system:I2C_SDA', 'system:I2C_SCL',
                    'main:CPU_PRSNT2_n', 'cpu:PRSNT', 'system:CC1', 'system:CC2',
                    'system:V1V2_SENSE', 'main:V1V2_SENSE'):
            assert net in good['runtime_nets'], net
        top = temporary / 'good.json'
        top.write_text(json.dumps(good))
        text = status(top)
        # 1.524 V, 1.2 V and 1.090 V through the 12-bit ADC and the firmware's mV scaling
        assert 'CPU card present' in text and 'Type-C 3.0 A (CC 1523 mV)' in text, text
        assert '1V2 1199 mV' in text, text
        low = status(top, pwrHi=False, ccLine=2)
        assert 'Type-C 1.5 A (CC 1089 mV)' in low, low
        print('native: status reads the CPU card present, a 3.0 A source (1.5 A with a weaker one, '
              'on either CC line) and the 1V2 rail: ' + ' / '.join(text.splitlines()[2:]))

        cases = (
            ('CPU presence at U14', 'main', 'U14', '13', '/CPU_PRSNT2_n', {'main:CPU_PRSNT2_n'},
             {}, lambda t: 'CPU card missing' in t),
            ('sysctl SDA launch', 'system', 'U1', '36', '/I2C_SDA', {'system:I2C_SDA'},
             {}, lambda t: 'CPU card missing' in t),
            ('sysctl CC1 input', 'system', 'U1', '38', '/CC1', {'system:CC1'},
             {}, lambda t: 'unknown (no CC) (CC 0 mV)' in t),
            ('1V2 sense resistor', 'main', 'R100', '2', '/V1V2_SENSE', {'main:V1V2_SENSE'},
             {}, lambda t: '1V2 0 mV' in t),
        )
        for label, board, ref, pin, net, gaps, options, shown in cases:
            source = args.main_board if board == 'main' else args.system_board
            opened = temporary / f'open-{board}-{ref}-{pin}.kicad_pcb'
            open_pad(source, opened, ref, pin, net)
            mutant = check(cards, main_circuit, opened if board == 'main' else args.main_board, boards,
                           opened if board == 'system' else args.system_board, args.cpu_board)
            assert gaps <= set(mutant['unmodeled_nets']) and not mutant['runtime']['routed_top'], label
            bad_top = temporary / f'open-{board}-{ref}.json'
            bad_top.write_text(json.dumps(mutant))
            text = status(bad_top, **options)
            assert shown(text), (label, text)
            print(f'open {label}: {sorted(gaps)} a coverage gap again; status shows it')
            if net == '/CC1':
                other = status(bad_top, ccLine=2)
                assert 'Type-C 3.0 A' in other, other
                print('  with the power cable the other way round (CC2) the class still reads 3.0 A')
    print('sysctl inputs: source, copper and native counterexamples detected')


if __name__ == '__main__':
    main()
