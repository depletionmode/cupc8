#!/usr/bin/env python3
"""FPGA configuration chain on routed copper: CRESET_B, CDONE, both flashes.

The generated top binds each leg (hw/cosim/gen_top.py fpga_config_routes);
the native machine (emu/machine/fpgaconfig.h) configures each iCE40 from its
W25Q flash, lets sysctl hold it and reprogram the flash over SPI1, and feeds
CDONE to sysctl, to the chipset (the CPU card's) and to LED D5. Checks:
source binding refuses moved pins and wrong pull-ups; opening one copper
launch clears exactly its links and restores its nets as coverage gaps; the
native machine shows each open, and a flash image without an iCE40 sync
word leaves the CPU card unconfigured and held in reset.
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import check, exported_cards, fpga_config_routes  # noqa: E402
from netlist import read  # noqa: E402
from cosim_mutate import board_args, card_boards, node_probe, open_pad  # noqa: E402

GOOD_IMAGE = '@ff0000ff7eaa997e'
BAD_IMAGE = '@00*64'
RESET_PC = 0xE000


def probe(top, *commands):
    return node_probe('fpga_config_probe.mjs', top, json.dumps(list(commands)))


def refused(main, cpu, system, change, what):
    try:
        fpga_config_routes(main, cpu, system, None, None, None)
    except ValueError as error:
        print(f'source binding refuses {what}: {error}')
        return
    raise AssertionError(f'{what} passed FPGA configuration source binding ({change})')


def main():
    args = board_args(__doc__).parse_args()
    main_circuit = read(args.main_netlist)
    boards = card_boards(args)
    with tempfile.TemporaryDirectory(prefix='cupc8-fpga-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        links, paths, missing, nets = fpga_config_routes(
            main_circuit, cards['cpu'], cards['system'], args.main_board, args.cpu_board,
            args.system_board)
        assert all(links.values()) and not missing, (links, missing)
        assert all(p['route_mm'] is not None for p in paths) and len(paths) == 56, len(paths)
        good = check(cards, main_circuit, args.main_board, boards, args.system_board, args.cpu_board)
        assert good['runtime']['fpga_links'] == links and good['runtime']['routed_top']
        for board, net in nets:
            assert f'{board}:{net.lstrip("/")}' in good['runtime_nets'], (board, net)
        print(f'{len(paths)} routed legs on {len(nets)} nets bind the FPGA configuration chain')

        # --- source binding
        moved = copy.deepcopy(main_circuit)
        moved.pins[('U7', '66')] = '/CHIPSET_CDONE'
        refused(moved, cards['cpu'], cards['system'], 'U7 CRESET_B on CDONE', 'a moved CRESET_B pad')
        weak = copy.deepcopy(cards['cpu'])
        weak.components['R1'] = ('100k', ('Device', 'R'))
        weak.resistors = tuple(r if r.ref != 'R1' else type(r)('R1', '100k', r.ends)
                               for r in weak.resistors)
        refused(main_circuit, weak, cards['system'], 'R1 100k', 'a changed CPU CRESET_B pull-up')
        swapped = copy.deepcopy(cards['system'])
        swapped.pins[('U1', '8')], swapped.pins[('U1', '9')] = '/CHIPSET_CDONE', '/CHIPSET_nCRESET'
        refused(main_circuit, cards['cpu'], swapped, 'GPIO6/GPIO7 swapped', 'swapped sysctl CRESET/CDONE')

        # --- the native machine on the intact top
        top = temporary / 'good.json'
        top.write_text(json.dumps(good))
        base = probe(top, ['status'], ['fpga', 'hold', 'chipset'], ['flash', 'id', 'chipset'],
                     ['fpga', 'boot', 'chipset'], ['fpga', 'flash', 'cpu', BAD_IMAGE],
                     ['fpga', 'flash', 'cpu', GOOD_IMAGE], ['flash', 'id', 'cpu'])
        boot, (status, hold, fl0, reboot, bad, good_flash, fl1) = base['boot'], base['commands']
        assert boot['chipsetConfigured'] and boot['cpuConfigured'] and boot['cdoneLed'] and boot['nrst'] == 1
        assert status['code'] == 0 and 'chipset running, CPU card FPGA configured' in status['output'], status
        assert not hold['state']['chipsetConfigured'] and hold['state']['nrst'] == 0 and \
            not hold['state']['cdoneLed'], hold
        assert fl0['output'] == 'ef4016', fl0
        assert reboot['code'] == 0 and reboot['state']['chipsetConfigured'] and reboot['state']['nrst'] == 1
        assert bad['code'] != 0 and not bad['state']['cpuConfigured'] and bad['state']['nrst'] == 0, bad
        assert good_flash['code'] == 0 and 'it configured' in good_flash['output'], good_flash
        assert good_flash['state']['cpuConfigured'] and good_flash['state']['nrst'] == 1
        assert fl1['code'] != 0 or fl1['output'] != 'ef4016'  # the CPU FPGA owns FL1 again: not held
        print('native: hold/boot/flash id on both FPGAs; an image without the iCE40 sync word '
              f'leaves the CPU card unconfigured ({bad["output"].splitlines()[-1]}), a good one boots it')

        # --- one copper launch at a time
        cases = [
            # label, board, ref, pin, net, links now false, native commands, check
            ('socket CRESET_B to chipset', 'main', 'J3', '53', '/CHIPSET_nCRESET', {'chipsetCreset'},
             [['fpga', 'hold', 'chipset']],
             lambda r: r['commands'][0]['state']['chipsetConfigured'] and
             r['commands'][0]['state']['nrst'] == 1),
            ('sysctl CDONE input', 'system', 'U1', '9', '/CHIPSET_CDONE', {'chipsetCdoneSysctl'},
             [['status'], ['fpga', 'boot', 'chipset']],
             lambda r: 'chipset down' in r['commands'][0]['output'] and
             r['commands'][1]['code'] != 0),
            ('chipset flash clock', 'main', 'U8', '6', '/FL0_SCK', {'chipsetConfigCopper', 'fl0Sysctl'},
             [['fpga', 'hold', 'chipset'], ['flash', 'id', 'chipset']],
             lambda r: not r['boot']['chipsetConfigured'] and r['boot']['pc'] == RESET_PC and
             r['boot']['nrst'] == 0 and r['commands'][1]['output'] == '000000'),
            ('CPU CDONE at the chipset', 'main', 'U7', '33', '/CPU_CDONE', {'cpuCdoneMain'},
             [], lambda r: r['boot']['cpuConfigured'] and r['boot']['nrst'] == 0 and
             r['boot']['pc'] == RESET_PC),
            ('CPU card CDONE launch', 'cpu', 'U1', '65', '/CDONE', {'cpuCdoneCard', 'cpuCdoneSysctl'},
             [['status']], lambda r: r['boot']['nrst'] == 1 and
             'CPU card FPGA not configured' in r['commands'][0]['output']),
            ('CPU flash data out', 'cpu', 'U2', '2', '/FL1_MISO', {'cpuConfigCopper', 'fl1Sysctl'},
             [], lambda r: not r['boot']['cpuConfigured'] and r['boot']['nrst'] == 0),
            ('sysctl CPU CRESET_B', 'system', 'U1', '27', '/CPUCARD_nCRESET', {'cpuCreset'},
             [['fpga', 'hold', 'cpu']],
             lambda r: r['commands'][0]['state']['cpuConfigured'] and r['commands'][0]['state']['nrst'] == 1),
            ('sysctl FL1 clock', 'system', 'U1', '17', '/FL1_SCK_MCU', {'fl1Sysctl'},
             [['fpga', 'hold', 'cpu'], ['flash', 'id', 'cpu']],
             lambda r: r['boot']['cpuConfigured'] and r['commands'][1]['output'] == '000000'),
            ('CDONE LED cathode', 'main', 'D5', '1', '/LED_CDONE_K', {'cdoneLed'},
             [], lambda r: r['boot']['chipsetConfigured'] and not r['boot']['cdoneLed']),
        ]
        for label, board, ref, pin, net, cleared, commands, observed in cases:
            source = {'main': args.main_board, 'cpu': args.cpu_board, 'system': args.system_board}[board]
            opened = temporary / f'open-{board}-{ref}-{pin}.kicad_pcb'
            tracks = open_pad(source, opened, ref, pin, net)
            mutant = check(cards, main_circuit,
                           opened if board == 'main' else args.main_board, boards,
                           opened if board == 'system' else args.system_board,
                           opened if board == 'cpu' else args.cpu_board)
            now = mutant['runtime']['fpga_links']
            assert {k for k, v in now.items() if not v} == cleared, (label, now)
            assert not mutant['runtime']['routed_top']
            gap = f'{board}:{net.lstrip("/")}'
            assert gap in mutant['unmodeled_nets'] and gap not in mutant['runtime_nets'], (label, gap)
            assert len(mutant['unmodeled_nets']) > len(good['unmodeled_nets'])
            mutant_top = temporary / f'open-{board}-{ref}-{pin}.json'
            mutant_top.write_text(json.dumps(mutant))
            result = probe(mutant_top, *commands)
            assert observed(result), (label, result)
            print(f'open {label} ({board} {ref}.{pin}, {tracks} tracks): {sorted(cleared)} cleared, '
                  f'{len(mutant["unmodeled_nets"]) - len(good["unmodeled_nets"])} coverage gaps restored, '
                  'native machine shows it')
    print('FPGA configuration chain: source, copper and native counterexamples all detected')


if __name__ == '__main__':
    main()
