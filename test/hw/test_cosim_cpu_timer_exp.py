#!/usr/bin/env python3
"""CPU timer-expiry source, routed-leg, and native IRQ mutations."""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, cpu_timer_exp_routes, exported_cards
from netlist import read
from test_cosim_cpu_controls import open_launch
from test_cosim_cpu_irq import probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, required=True)
    parser.add_argument('--main-board', type=Path, required=True)
    parser.add_argument('--card-board-dir', type=Path, required=True)
    parser.add_argument('--system-board', type=Path, required=True)
    parser.add_argument('--cpu-board', type=Path, required=True)
    parser.add_argument('--top', type=Path, required=True)
    args = parser.parse_args()
    main_circuit = read(args.main_netlist)
    cpu_circuit = read(args.card_board_dir / 'cpu/cpu.net')
    top = json.loads(args.top.read_text())
    links, paths, missing = cpu_timer_exp_routes(
        main_circuit, cpu_circuit, args.main_board, args.cpu_board)
    assert links == [True, True] and not missing
    assert len(paths) == 6 and all(p['route_mm'] is not None for p in paths)
    assert top['runtime']['cpu_tmr_exp_connected'] == links
    assert len(top['unmodeled_nets']) == 292

    wrong = copy.deepcopy(cpu_circuit)
    wrong.components['RN8'] = ('22', ('Device', 'R_Pack04'))
    try:
        cpu_timer_exp_routes(main_circuit, wrong, None, None)
    except ValueError as error:
        assert 'wrong RN8' in str(error)
    else:
        raise AssertionError('changed RN8 value passed source binding')

    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-timer-exp-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        for bit, fpga_pad, pack_pad, chipset_pad in (
                (0, '55', '8', '136'), (1, '56', '7', '129')):
            irq = bit + 1
            good = probe(args.top, irq)
            assert good['gpo'] == 0xa0 + irq and good['halted'] == 1, (bit, good)
            for leg, board, ref, pin, net in (
                    ('source', args.cpu_board, 'U1', fpga_pad, f'/FPGA_TMR_EXP{bit}'),
                    ('series', args.cpu_board, 'RN8', pack_pad, f'/CPU_TMR_EXP{bit}'),
                    ('receiver', args.main_board, 'U7', chipset_pad,
                     f'/CPU_TMR_EXP{bit}')):
                opened = temporary / f'open-timer{bit}-{leg}.kicad_pcb'
                open_launch(board, opened, ref, pin, net)
                altered, _, missing = cpu_timer_exp_routes(
                    main_circuit, cpu_circuit,
                    opened if board == args.main_board else args.main_board,
                    opened if board == args.cpu_board else args.cpu_board)
                assert altered[bit] is False and sum(altered) == 1 and missing
                if leg != 'source':
                    continue
                mutant = check(cards, main_circuit, args.main_board, card_boards,
                               args.system_board, opened)
                assert mutant['runtime']['cpu_tmr_exp_connected'] == altered
                assert mutant['runtime']['routed_top'] is False
                assert len(mutant['unmodeled_nets']) == 295
                for name in (f'cpu:FPGA_TMR_EXP{bit}', f'cpu:CPU_TMR_EXP{bit}',
                             f'main:CPU_TMR_EXP{bit}'):
                    assert name in mutant['unmodeled_nets']
                changed_top = temporary / f'open-timer{bit}.json'
                changed_top.write_text(json.dumps(mutant))
                bad = probe(changed_top, irq)
                assert bad['gpo'] == 0x11 and bad['halted'] == 0, (bit, bad)
                print(f'timer{bit} source open: GPO {good["gpo"]:#04x} -> '
                      f'{bad["gpo"]:#04x}')
        print('6/6 timer-expiry copper opens detected; 2/2 native IRQ counterexamples')


if __name__ == '__main__':
    main()
