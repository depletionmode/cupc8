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
    parser.add_argument('--cpu-board', type=Path,
                        help='routed CPU card PCB for internal address/data counterexamples')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-cx-') as temporary:
        cards = exported_cards(Path(temporary))
        main = read(args.main_netlist)
        card_boards = ({card: args.card_board_dir / card / f'{card}.kicad_pcb'
                        for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
                       if args.card_board_dir else None)
        manifest = check(cards, main, card_boards=card_boards,
                         system_board=args.system_board, cpu_board=args.cpu_board)
        print(f"valid top: {len(manifest['contacts'])} contacts, {len(manifest['paths'])} paths")
        assert 'main:MEM_A0' in manifest['runtime_nets']
        assert 'main:CPU_CLK' in manifest['runtime_nets']
        assert 'cpu:CPU_CLK' in manifest['runtime_nets']
        assert {'main:CLK12', 'main:OSC_OUT'} <= set(manifest['runtime_nets'])
        assert not manifest['coverage_complete']
        assert 'main:CPU_RSVD_A2' in manifest['reviewed_waivers']
        assert 'main:SLOT1_RSVD_A1' in manifest['reviewed_waivers']
        assert 'system:RSVD_B1' in manifest['reviewed_waivers']
        assert 'main:CPU_RSVD_A2' not in manifest['unmodeled_nets']
        assert 'main:CLK12' not in manifest['unmodeled_nets']
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

        wrong_bridge = copy.deepcopy(cards)
        wrong_bridge['system'].pins[('U1', '4')], wrong_bridge['system'].pins[('U1', '5')] = \
            wrong_bridge['system'].pins[('U1', '5')], wrong_bridge['system'].pins[('U1', '4')]
        rejected(wrong_bridge, main, 'swapped system bridge MCU SCK/MOSI pads')

        if args.system_board:
            routed_system = check(cards, main, args.main_board, card_boards,
                                  args.system_board, args.cpu_board)
            if routed_system['runtime']['bridge_source_links'] != \
                    {'sck': True, 'mosi': True, 'ncs': True}:
                raise AssertionError('routed system bridge source paths are incomplete')
            system_pcb = pcbnew.LoadBoard(str(args.system_board))
            mcu_pad = next(pad for pad in system_pcb.FindFootprintByReference('U1').Pads()
                           if pad.GetNumber() == '4')
            point = mcu_pad.GetPosition()
            launch = (round(pcbnew.ToMM(point.x), 4), round(pcbnew.ToMM(point.y), 4))
            system_tree = parse(args.system_board.read_text())
            segments = [item for item in system_tree[1:]
                        if isinstance(item, list) and item and item[0] == 'segment' and
                        find1(item, 'net') and find1(item, 'net')[1] == '/BR_SCK_MCU' and
                        launch in (tuple(round(float(x), 4) for x in find1(item, end)[1:])
                                   for end in ('start', 'end'))]
            if len(segments) != 1:
                raise AssertionError(f'system bridge SCK MCU launch has {len(segments)} tracks')
            system_tree.remove(segments[0])
            opened_system = Path(temporary) / 'open-system-bridge-sck.kicad_pcb'
            opened_system.write_text(dump(system_tree) + '\n')
            bad_system = check(cards, main, args.main_board, card_boards,
                               opened_system, args.cpu_board)
            if bad_system['runtime']['bridge_source_links'] != \
                    {'sck': False, 'mosi': True, 'ncs': True} or \
                    'system:BR_SCK_MCU' not in bad_system['runtime_nets']:
                raise AssertionError('physical bridge SCK launch did not isolate its native input')
            if args.main_board and args.cpu_board and card_boards:
                import json
                from test_cosim_runtime import run, BRIDGE_PROBE
                good_top = Path(temporary) / 'good-system-bridge.json'
                bad_top = Path(temporary) / 'open-system-bridge.json'
                good_top.write_text(json.dumps(routed_system))
                bad_top.write_text(json.dumps(bad_system))
                good_status, bad_status = run(good_top, BRIDGE_PROBE), run(bad_top, BRIDGE_PROBE)
                if good_status == bad_status:
                    raise AssertionError('open routed system bridge SCK did not change native sysctl status')
                print(f'open system bridge SCK changes sysctl status {good_status} -> {bad_status}')

        if args.main_board:
            good_route = check(cards, main, args.main_board, card_boards,
                               args.system_board, args.cpu_board)
            assert good_route['runtime']['por_connected']
            assert good_route['runtime']['cpu_clock_connected']
            assert good_route['runtime']['cpu_reset_connected']
            assert good_route['runtime']['chipset_clock_connected']
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
                return check(cards, main, opened, card_boards, args.system_board, args.cpu_board)

            bad_route = open_launch('U6', '2', '/nPOR')
            if bad_route['runtime']['por_connected'] or bad_route['runtime']['routed_top'] or \
                    'main:nPOR' not in bad_route['runtime_nets']:
                raise AssertionError('removed nPOR copper did not change the executed reset path')
            print('open supervisor nPOR copper disables the native reset-release path')
            bad_reset_source = open_launch('U7', '32', '/CPU_nRST_SRC')
            reset_paths = [path for path in bad_reset_source['paths']
                           if path.get('runtime') == 'cpu_reset_connected']
            if bad_reset_source['runtime']['cpu_reset_connected'] or \
                    bad_reset_source['runtime']['routed_top'] or \
                    'main:CPU_nRST_SRC' not in bad_reset_source['runtime_nets'] or \
                    len(reset_paths) != 3 or \
                    [path['route_mm'] is None for path in reset_paths] != [True, False, False]:
                raise AssertionError('open chipset reset source did not isolate only its copper leg')
            if card_boards:
                import json
                from test_cosim_runtime import run, PROBE
                good_reset_top = Path(temporary) / 'good-reset-source.json'
                bad_reset_top = Path(temporary) / 'open-reset-source.json'
                good_reset_top.write_text(json.dumps(good_route))
                bad_reset_top.write_text(json.dumps(bad_reset_source))
                reset_good, reset_bad = run(good_reset_top, PROBE), run(bad_reset_top, PROBE)
                if reset_good['pc'] == reset_bad['pc'] or reset_bad['nrst'] != 0:
                    raise AssertionError('open routed chipset reset source did not hold CPU in reset')
                print(f"open routed CPU reset source holds PC ${reset_bad['pc']:04x} "
                      f"instead of ${reset_good['pc']:04x}")
            bad_chipset_clock = open_launch('U7', '21', '/CLK12')
            if bad_chipset_clock['runtime']['chipset_clock_connected'] or \
                    bad_chipset_clock['runtime']['routed_top'] or \
                    'main:CLK12' not in bad_chipset_clock['runtime_nets']:
                raise AssertionError('opened chipset CLK12 pad did not disable its executed clock')
            bad_oscillator = open_launch('Y1', '3', '/OSC_OUT')
            if bad_oscillator['runtime']['chipset_clock_connected'] or \
                    bad_oscillator['runtime']['cpu_clock_connected'] or \
                    bad_oscillator['runtime']['routed_top'] or \
                    'main:OSC_OUT' not in bad_oscillator['runtime_nets']:
                raise AssertionError('opened oscillator source did not disable the chipset clock')
            if card_boards:
                import json
                from test_cosim_runtime import run, PROBE
                good_clock_top = Path(temporary) / 'good-chipset-clock.json'
                bad_clock_top = Path(temporary) / 'open-chipset-clock.json'
                bad_source_top = Path(temporary) / 'open-oscillator-source.json'
                good_clock_top.write_text(json.dumps(good_route))
                bad_clock_top.write_text(json.dumps(bad_chipset_clock))
                bad_source_top.write_text(json.dumps(bad_oscillator))
                clock_good, clock_bad = run(good_clock_top, PROBE), run(bad_clock_top, PROBE)
                source_bad = run(bad_source_top, PROBE)
                if (clock_good['pc'], clock_good['gpo']) == (clock_bad['pc'], clock_bad['gpo']):
                    raise AssertionError('open routed chipset CLK12 did not change native execution')
                if (clock_good['pc'], clock_good['gpo']) == (source_bad['pc'], source_bad['gpo']):
                    raise AssertionError('open routed OSC_OUT did not change native execution')
                print(f"open routed chipset CLK12 changes PC ${clock_good['pc']:04x} -> "
                      f"${clock_bad['pc']:04x}")
                print(f"open routed OSC_OUT changes PC ${clock_good['pc']:04x} -> "
                      f"${source_bad['pc']:04x}")
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
                                {**card_boards, 'gpu': opened_gpu}, args.system_board, args.cpu_board)
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
                                     {**card_boards, 'gpu': opened_qspi}, args.system_board, args.cpu_board)
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

                if args.cpu_board:
                    from test_cosim_runtime import PROBE
                    opened_cpu = open_card_launch(args.cpu_board, 'U1', '1', '/FPGA_A0', 'cpu-a0')
                    cpu_bad = check(cards, main, args.main_board, card_boards,
                                    args.system_board, opened_cpu)
                    if cpu_bad['runtime']['cpu_address_links'][0] or \
                            not all(cpu_bad['runtime']['cpu_address_links'][1:]) or \
                            cpu_bad['runtime']['routed_top'] or 'cpu:FPGA_A0' not in cpu_bad['runtime_nets']:
                        raise AssertionError('open CPU A0 launch did not isolate its address wire')
                    cpu_bad_top = Path(temporary) / 'open-cpu-a0.json'
                    cpu_bad_top.write_text(json.dumps(cpu_bad))
                    cpu_good_state, cpu_bad_state = run(good_top, PROBE), run(cpu_bad_top, PROBE)
                    if (cpu_good_state['pc'], cpu_good_state['gpo']) == \
                            (cpu_bad_state['pc'], cpu_bad_state['gpo']):
                        raise AssertionError('open routed CPU A0 did not change native CPU execution')
                    print(f"open routed CPU A0 changes PC ${cpu_good_state['pc']:04x} -> "
                          f"${cpu_bad_state['pc']:04x}")

                    opened_clock = open_card_launch(args.cpu_board, 'U1', '21', '/CPU_CLK', 'cpu-clock')
                    clock_bad = check(cards, main, args.main_board, card_boards,
                                      args.system_board, opened_clock)
                    if clock_bad['runtime']['cpu_clock_connected'] or \
                            clock_bad['runtime']['routed_top'] or \
                            'cpu:CPU_CLK' not in clock_bad['runtime_nets']:
                        raise AssertionError('open CPU clock launch did not disable the CPU clock link')
                    clock_bad_top = Path(temporary) / 'open-cpu-clock.json'
                    clock_bad_top.write_text(json.dumps(clock_bad))
                    clock_good_state, clock_bad_state = run(good_top, PROBE), run(clock_bad_top, PROBE)
                    if clock_good_state['pc'] == clock_bad_state['pc'] or \
                            clock_bad_state['gpo'] == clock_good_state['gpo']:
                        raise AssertionError('open routed CPU clock did not change native boot')
                    print(f"open routed CPU clock changes PC ${clock_good_state['pc']:04x} -> "
                          f"${clock_bad_state['pc']:04x}")

                    opened_reset = open_card_launch(args.cpu_board, 'U1', '22', '/CPU_nRST', 'cpu-reset')
                    reset_bad = check(cards, main, args.main_board, card_boards,
                                      args.system_board, opened_reset)
                    if reset_bad['runtime']['cpu_reset_connected'] or \
                            reset_bad['runtime']['routed_top'] or \
                            'cpu:CPU_nRST' not in reset_bad['runtime_nets']:
                        raise AssertionError('open CPU reset launch did not disable the CPU reset link')
                    reset_bad_top = Path(temporary) / 'open-cpu-reset.json'
                    reset_bad_top.write_text(json.dumps(reset_bad))
                    reset_good_state, reset_bad_state = run(good_top, PROBE), run(reset_bad_top, PROBE)
                    if reset_good_state['pc'] == reset_bad_state['pc'] or reset_bad_state['nrst'] != 0:
                        raise AssertionError('open routed CPU reset did not hold the native CPU in reset')
                    print(f"open routed CPU reset changes PC ${reset_good_state['pc']:04x} -> "
                          f"${reset_bad_state['pc']:04x}")

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

        broken_cpu_local = copy.deepcopy(cards)
        del broken_cpu_local['cpu'].pins[('U1', '1')]
        rejected(broken_cpu_local, main, 'missing CPU-card FPGA A0 driver')

        broken_cpu_reset = copy.deepcopy(cards)
        del broken_cpu_reset['cpu'].pins[('U1', '22')]
        rejected(broken_cpu_reset, main, 'missing CPU-card FPGA reset input')

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
