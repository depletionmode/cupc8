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
    parser.add_argument('--card-board-dir', type=Path,
                        help='generated card PCBs for card-local routed SPI/IRQ counterexamples')
    parser.add_argument('--system-board', type=Path,
                        help='explicit routed system card PCB for QSPI boot counterexamples')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-cx-') as temporary:
        cards = exported_cards(Path(temporary))
        main = read(args.main_netlist)
        card_boards = ({card: args.card_board_dir / card / f'{card}.kicad_pcb'
                        for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
                       if args.card_board_dir else None)
        manifest = check(cards, main, card_boards=card_boards, system_board=args.system_board)
        print(f"valid top: {len(manifest['contacts'])} contacts, {len(manifest['paths'])} paths")
        assert 'main:MEM_A0' in manifest['runtime_nets']
        assert 'main:CPU_CLK' in manifest['structural_only_nets']
        assert 'main:CPU_CLK' in manifest['unmodeled_nets']
        assert not manifest['coverage_complete']
        assert 'main:CPU_RSVD_A2' in manifest['reviewed_waivers']
        assert 'main:SLOT1_RSVD_A1' in manifest['reviewed_waivers']
        assert 'system:RSVD_B1' in manifest['reviewed_waivers']
        assert 'main:CPU_RSVD_A2' not in manifest['unmodeled_nets']
        assert 'main:CPU_CLK' in manifest['coverage_families']['clock_and_reset']
        assert sorted(net for family in manifest['coverage_families'].values()
                      for net in family) == manifest['unmodeled_nets']
        assert not set(manifest['reviewed_waivers']) & set(manifest['unmodeled_nets'])

        # A waiver is valid only while the pin-exact KiCad topology remains
        # passive. These mutations do not need to break an unrelated wiring
        # check: they must restore a strict coverage gap on their own.
        used_reserved = copy.deepcopy(main)
        old_net = used_reserved.pins[('U7', '1')]
        used_reserved.nets[old_net] = tuple(pin for pin in used_reserved.nets[old_net]
                                             if pin != ('U7', '1'))
        used_reserved.nets['/CPU_RSVD_A2'] += (('U7', '1'),)
        used_reserved.pins[('U7', '1')] = '/CPU_RSVD_A2'
        exposed = check(cards, used_reserved)
        assert 'main:CPU_RSVD_A2' not in exposed['reviewed_waivers']
        assert 'main:CPU_RSVD_A2' in exposed['unmodeled_nets']

        used_slot = copy.deepcopy(cards)
        old_net = used_slot['io'].pins[('J1', 'A6')]
        del used_slot['io'].nets[old_net]
        used_slot['io'].nets['/SCK'] += (('J1', 'A6'),)
        used_slot['io'].pins[('J1', 'A6')] = '/SCK'
        exposed = check(used_slot, main)
        assert 'main:SLOT1_RSVD_A1' not in exposed['reviewed_waivers']
        assert 'main:SLOT1_RSVD_A1' in exposed['unmodeled_nets']
        print('reserved-contact waivers fail closed for active-pin and mating-card mutations')

        if args.main_board:
            good_route = check(cards, main, args.main_board, card_boards, args.system_board)
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
                return check(cards, main, opened, card_boards, args.system_board)

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
            bad_rom_data = open_launch('U10', '13', '/MEM_D0')
            if bad_rom_data['runtime']['rom_read_d0_connected'] or \
                    bad_rom_data['runtime']['routed_top'] or \
                    'main:MEM_D0' not in bad_rom_data['runtime_nets']:
                raise AssertionError('removed ROM DQ0 copper did not disable read-data path')
            print('open ROM MEM_D0 launch disables the executable read-data path')
            bad_select = open_launch('U7', '34', '/SPI_nCS0_SRC')
            if bad_select['runtime']['slots'][0]['cs_connected'] or \
                    bad_select['runtime']['routed_top'] or \
                    'main:SPI_nCS0_SRC' not in bad_select['runtime_nets']:
                raise AssertionError('removed slot 1 select launch did not disconnect its executed path')
            if not all(slot['cs_connected'] for slot in bad_select['runtime']['slots'][1:]):
                raise AssertionError('slot 1 copper mutation altered another slot select')
            if card_boards:
                from test_cosim_runtime import run, SLOT_PROBE
                good_top = Path(temporary) / 'good-top.json'
                bad_top = Path(temporary) / 'open-slot1-select.json'
                import json
                good_top.write_text(json.dumps(good_route))
                bad_top.write_text(json.dumps(bad_select))
                good_frames = run(good_top, SLOT_PROBE)['frames']
                bad_frames = run(bad_top, SLOT_PROBE)['frames']
                if good_frames < 1 or bad_frames != 0:
                    raise AssertionError(f'open routed slot select did not stop native SPI: {good_frames} / {bad_frames}')
                print(f'open routed slot 1 select stops native SPI frames: {good_frames} -> {bad_frames}')
            bad_sck = open_launch('U7', '43', '/SPI_SCK_SRC')
            if any(slot['sck_connected'] for slot in bad_sck['runtime']['slots']) or \
                    not all(slot['mosi_connected'] and slot['miso_connected']
                            for slot in bad_sck['runtime']['slots']) or \
                    bad_sck['runtime']['routed_top'] or \
                    'main:SPI_SCK_SRC' not in bad_sck['runtime_nets']:
                raise AssertionError('opened shared SPI clock source did not isolate all slot clocks')
            if card_boards:
                bad_sck_top = Path(temporary) / 'open-shared-sck.json'
                bad_sck_top.write_text(json.dumps(bad_sck))
                sck_bad_frames = run(bad_sck_top, SLOT_PROBE)['frames']
                if sck_bad_frames != 0:
                    raise AssertionError(f'open shared SCK did not stop native SPI: {good_frames} / {sck_bad_frames}')
                print(f'open routed shared SCK source stops native SPI frames: {good_frames} -> {sck_bad_frames}')

                def open_card_launch(board_path, ref, pin, net, label):
                    physical = pcbnew.LoadBoard(str(board_path))
                    pad = next(item for item in physical.FindFootprintByReference(ref).Pads()
                               if item.GetNumber() == pin)
                    point = pad.GetPosition()
                    launch = (round(pcbnew.ToMM(point.x), 4), round(pcbnew.ToMM(point.y), 4))
                    tree = parse(board_path.read_text())
                    tracks = [item for item in tree[1:]
                              if isinstance(item, list) and item and item[0] == 'segment' and
                              find1(item, 'net') and find1(item, 'net')[1] == net and
                              launch in (tuple(round(float(x), 4) for x in find1(item, end)[1:])
                                         for end in ('start', 'end'))]
                    if len(tracks) != 1:
                        raise AssertionError(f'{label} {ref}.{pin} launch has {len(tracks)} tracks, expected one')
                    tree.remove(tracks[0])
                    opened = Path(temporary) / f'open-{label}.kicad_pcb'
                    opened.write_text(dump(tree) + '\n')
                    return opened

                opened_gpu = open_card_launch(card_boards['gpu'], 'U1', '4', '/SCK', 'gpu-sck')
                bad_gpu = check(cards, main, args.main_board,
                                {**card_boards, 'gpu': opened_gpu}, args.system_board)
                if bad_gpu['runtime']['card_slot_links']['gpu']['sck'] or \
                        not bad_gpu['runtime']['card_slot_links']['io']['sck'] or \
                        bad_gpu['runtime']['routed_top'] or 'gpu:SCK' not in bad_gpu['runtime_nets']:
                    raise AssertionError('opened GPU SCK card route did not isolate its installed-card link')
                bad_gpu_top = Path(temporary) / 'open-gpu-sck.json'
                bad_gpu_top.write_text(json.dumps(bad_gpu))
                gpu_bad_frames = run(bad_gpu_top, SLOT_PROBE)['frames']
                if gpu_bad_frames != 0:
                    raise AssertionError(f'open GPU SCK copper did not stop native SPI: {good_frames} / {gpu_bad_frames}')
                print(f'open routed GPU-card SCK launch stops native SPI frames: {good_frames} -> {gpu_bad_frames}')

                if args.system_board:
                    opened_qspi = open_card_launch(card_boards['gpu'], 'U1', '52',
                                                   '/QSPI_SCLK', 'gpu-qspi-clock')
                    boot_bad = check(cards, main, args.main_board,
                                     {**card_boards, 'gpu': opened_qspi}, args.system_board)
                    boot = boot_bad['runtime']['qspi_boot_connected']
                    if boot['gpu'] or not all(value for kind, value in boot.items() if kind != 'gpu') or \
                            boot_bad['runtime']['routed_top'] or 'gpu:QSPI_SCLK' not in boot_bad['runtime_nets']:
                        raise AssertionError('GPU QSPI clock launch did not isolate its firmware boot prerequisite')
                    boot_bad_top = Path(temporary) / 'open-gpu-qspi.json'
                    boot_bad_top.write_text(json.dumps(boot_bad))
                    boot_bad_frames = run(boot_bad_top, SLOT_PROBE)['frames']
                    if boot_bad_frames != 0:
                        raise AssertionError(f'open GPU QSPI copper did not stop firmware SPI: {boot_bad_frames}')
                    print(f'open routed GPU QSPI clock launch prevents firmware SPI: {good_frames} -> 0 frames')

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

        broken_rom_data = copy.deepcopy(main)
        del broken_rom_data.pins[('U10', '13')]
        rejected(cards, broken_rom_data, 'missing ROM read-data DQ0')

        broken_io = copy.deepcopy(cards)
        broken_io['io'].resistors = tuple(r for r in broken_io['io'].resistors if r.ref != 'R14')
        rejected(broken_io, main, 'missing IO USB D- series resistor')

        broken_irq = copy.deepcopy(cards)
        del broken_irq['io'].pins[('U1', '8')]
        rejected(broken_irq, main, 'missing IO card-local IRQ GPIO')

        broken_miso = copy.deepcopy(cards)
        del broken_miso['gpu'].pins[('U4', '2')]
        rejected(broken_miso, main, 'missing GPU MISO buffer input')

        broken_qspi = copy.deepcopy(cards)
        del broken_qspi['gpu'].pins[('U1', '52')]
        rejected(broken_qspi, main, 'missing GPU QSPI flash clock pad')

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
