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
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from coverage import BOUNDARY, BOUNDARY_DECISIONS, audit, reviewed_analog_waivers, reviewed_boundary_waivers  # noqa: E402
from gen_top import check, crystal_routes, exported_cards, implemented_checks  # noqa: E402
from netlist import Resistor, read  # noqa: E402
from cosim_mutate import board_args, card_boards, open_pad  # noqa: E402
from test_cosim_runtime import SLOT_PROBE, SYSTEM_BOOT_PROBE, run  # noqa: E402

# David's decision 2026-09-29: the 50 nets the emulator does not model, by name and group
PINNED_BOUNDARY = {**{net: 'card_control' for net in (
    'eink:RUN', 'gpu:RUN', 'io:RUN', 'storage:RUN', 'wifi:BOOT', 'wifi:EN',
    *(f'main:SLOT{n}_{line}' for n in range(1, 7) for line in ('PROG_n', 'RST_n')))},
    **{net: 'esp_pins' for net in ('wifi:LED_LINK', 'wifi:LED_LINK_A', 'wifi:LED_RX', 'wifi:LED_RX_A',
                                   'wifi:LED_TX', 'wifi:LED_TX_A', 'wifi:U0RXD', 'wifi:U0TXD')},
    **{net: 'external_header' for net in ('main:AUX_CS_n', 'main:SPI_nCS6_SRC')},
    **{net: 'passive_loop' for net in ('main:SYS_PRSNT2_n', 'system:PRSNT')},
    **{net: 'test_access' for net in ('eink:BOOTSEL', 'gpu:BOOTSEL', 'io:BOOTSEL', 'io:UART_TX', 'storage:BOOTSEL',
                                      'storage:UART_TX', 'system:BOOTSEL', 'system:RUN', 'system:SWCLK',
                                      'system:SWDIO')},
    **{net: 'unused_by_fw' for net in ('eink:UART_TX', 'gpu:DDC_SCL', 'gpu:DDC_SDA', 'gpu:HDMI_HPD', 'gpu:HDMI_SCL',
                                       'gpu:HDMI_SDA', 'gpu:HPD_5V', 'gpu:UART_TX', 'wifi:USB_DN', 'wifi:USB_DP')}}


def main():
    parser = board_args(__doc__)
    parser.add_argument('--gpu-crystal-only', action='store_true',
                        help='run local GPU crystal counterexamples; does not satisfy the full coverage gate')
    args = parser.parse_args()
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
        assert waivers['main:3V3_BUCK']['checks'] and 'POW-001' in waivers['main:3V3_BUCK']['checks']
        for key, waiver in waivers.items():
            assert set(waiver['checks']) <= implemented, key
            board, net = key.split(':', 1)
            assert waiver['pins'] == [f'{r}.{p}' for r, p in circuits[board].nets['/' + net]], key
        logic = copy.deepcopy(main_circuit)
        logic.nets['/3V3_BUCK'] = logic.nets['/3V3_BUCK'] + (('U7', '74'),)
        logic.pins[('U7', '74')] = '/3V3_BUCK'
        assert 'main:3V3_BUCK' not in reviewed_analog_waivers({**circuits, 'main': logic}, implemented)
        assert 'main:3V3_BUCK' in audit({**circuits, 'main': logic}, set(), set(), implemented)['unmodeled_nets']
        assert 'main:3V3_BUCK' not in reviewed_analog_waivers(circuits, implemented - {'POW-001'})
        driven = copy.deepcopy(main_circuit)
        driven.nets['/GND'] = driven.nets['/GND'] + (('U13', '4'),)  # a TCA9555 output, not a strap
        assert 'main:GND' not in reviewed_analog_waivers({**circuits, 'main': driven}, implemented)
        print(f'{len(waivers)} non-digital waivers name implemented checks; a logic pin on 3V3_BUCK, '
              'an expander output on GND, or an unimplemented check removes the waiver')

        # the Wi-Fi boot straps (WC-006) and the POWER switch / eFuse enable chain (MB-053)
        for key in ('wifi:STRAP2', 'wifi:STRAP8', 'main:PWR_BTN', 'main:PWR_EN'):
            assert key in waivers, key
        assert 'WC-006' in waivers['wifi:STRAP2']['checks'] and 'MB-053' in waivers['main:PWR_EN']['checks']
        for board, net, ref, pin, check_id in (('wifi', 'STRAP2', 'U1', '18', 'WC-006'),
                                               ('wifi', 'STRAP8', 'U1', '13', 'WC-006'),
                                               ('main', 'PWR_BTN', 'U7', '74', 'MB-053'),
                                               ('main', 'PWR_EN', 'U7', '74', 'MB-053')):
            logic = copy.deepcopy(circuits[board])
            logic.pins.pop((ref, pin), None)
            logic.nets['/' + net] = logic.nets['/' + net] + ((ref, pin),)
            logic.pins[(ref, pin)] = '/' + net                          # a GPIO on the net
            key = f'{board}:{net}'
            assert key not in reviewed_analog_waivers({**circuits, board: logic}, implemented), key
            assert key not in reviewed_analog_waivers(circuits, implemented - {check_id}), key
        print('a GPIO on a strap or power-enable net, or an unimplemented WC-006 / MB-053, removes its waiver')

        # boundary waivers (David's decision, 2026-09-29): pinned by name, so a net cannot join
        # or leave the list without editing this test; pin-exact; each with its decision text
        assert PINNED_BOUNDARY == {key: BOUNDARY[key][0] for key in BOUNDARY}, \
            sorted(set(PINNED_BOUNDARY.items()) ^ {(k, v[0]) for k, v in BOUNDARY.items()})
        assert len(PINNED_BOUNDARY) == 50
        boundary = reviewed_boundary_waivers(circuits, implemented)
        runtime_resets = {f'main:SLOT{n}_RST_n' for n in range(1, 7)}
        assert set(boundary) == set(PINNED_BOUNDARY) - runtime_resets, sorted(set(PINNED_BOUNDARY) ^ set(boundary))
        assert not runtime_resets.intersection(boundary)
        assert 'main:+3V3' not in waivers  # fitted REF enable and U19 logic require the monitor model
        catalogue_ids = {row['id'] for row in tomllib.loads((ROOT / 'test/catalogue.toml').read_text())['test']}
        for key, waiver in boundary.items():
            board, net = key.split(':', 1)
            assert waiver['pins'] == [f'{r}.{p}' for r, p in circuits[board].nets['/' + net]], key
            assert waiver['reason'] and set(waiver['checks']) <= implemented, key
            assert waiver['status'].startswith('accepted by David 2026-09-29'), (key, waiver['status'])
            assert set(waiver['verified_by']) <= catalogue_ids, key
            assert key not in audit(circuits, set(), set(), implemented)['unmodeled_nets'], key
        assert set(BOUNDARY_DECISIONS) == set(PINNED_BOUNDARY.values())
        # the decisions that name a verifying row: the GPU DDC/HPD first-article row, the reset and
        # boot-select bring-up rows, the Wi-Fi bring-up row
        assert boundary['gpu:DDC_SCL']['verified_by'] == ['GC-105'], boundary['gpu:DDC_SCL']
        assert boundary['wifi:EN']['verified_by'] == ['MB-106', 'WC-101']
        assert boundary['wifi:LED_TX']['verified_by'] == ['WC-101']
        for key, pin in (('main:SLOT1_PROG_n', ('U7', '74')), ('gpu:HDMI_HPD', ('U1', '2')),
                         ('wifi:LED_TX', ('U1', '30')), ('io:UART_TX', ('U1', '3'))):
            board, net = key.split(':', 1)
            extra = copy.deepcopy(circuits[board])
            extra.nets['/' + net] = extra.nets['/' + net] + (pin,)
            extra.pins[pin] = '/' + net
            assert key not in reviewed_boundary_waivers({**circuits, board: extra}, implemented), key
            assert key in audit({**circuits, board: extra}, set(), set(), implemented)['unmodeled_nets'], key
        # a part swapped on a waived net (the 10k pull-up R205 of SLOT1_PROG_n replaced by a transistor)
        swapped = copy.deepcopy(circuits['main'])
        swapped.nets['/SLOT1_PROG_n'] = tuple(('Q9', '1') if r == 'R205' else (r, p)
                                             for r, p in swapped.nets['/SLOT1_PROG_n'])
        assert 'main:SLOT1_PROG_n' not in reviewed_boundary_waivers({**circuits, 'main': swapped}, implemented)
        assert 'main:SLOT1_PROG_n' not in reviewed_boundary_waivers(circuits, implemented - {'MB-004'})
        counts = {}
        for waiver in boundary.values():
            counts[waiver['family']] = counts.get(waiver['family'], 0) + 1
        assert counts == {'boundary_test_access': 10, 'boundary_card_control': 12,
                          'boundary_unused_by_fw': 10, 'boundary_passive_loop': 2,
                          'boundary_external_header': 2, 'boundary_esp_pins': 8}, counts
        print(f'{len(boundary)} boundary waivers accepted by David 2026-09-29 ({counts}): pinned by name; '
              'an extra pin, a swapped part or an unimplemented pinout row turns each back into a gap')

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
        assert good['coverage_complete'] and good['runtime']['reset_monitor']['complete']
        assert all(f'main:SLOT{n}_RST_n' not in good['unmodeled_nets'] for n in range(1, 7))
        good_top = temporary / 'good.json'
        good_top.write_text(json.dumps(good))
        frames = run(good_top, SLOT_PROBE)['frames']
        assert frames > 0
        if not args.gpu_crystal_only:
            assert run(good_top, SYSTEM_BOOT_PROBE)['systemCard']
        for board, ref, pin, net in (('gpu', 'U1', '20', '/XIN'), ('gpu', 'R2', '2', '/XTAL_OUT'),
                                     ('system', 'U1', '21', '/XOUT')):
            if args.gpu_crystal_only and board != 'gpu':
                continue
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
    if args.gpu_crystal_only:
        print('GPU crystal subset PASS: actual source and both native copper counterexamples; full coverage gate still requires the system-card TCP probe')
    else:
        print('coverage waivers and crystal boot prerequisites: all counterexamples detected')


if __name__ == '__main__':
    main()
