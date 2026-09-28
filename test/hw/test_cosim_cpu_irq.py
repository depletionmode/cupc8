#!/usr/bin/env python3
"""Four chipset-to-CPU IRQ source, copper and native counterexamples."""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, cpu_irq_routes, exported_cards
from netlist import read
from test_cosim_cpu_controls import open_launch


def probe(top, bit):
    env = dict(os.environ, CUPC8_COSIM_TOP=str(top.resolve()))
    output = subprocess.check_output(['node', 'test/emu/cpu_irq_probe.mjs', str(bit)],
                                     cwd=ROOT, env=env, text=True)
    return json.loads(output.strip())['state']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-netlist', type=Path, required=True)
    parser.add_argument('--main-board', type=Path, required=True)
    parser.add_argument('--card-board-dir', type=Path, required=True)
    parser.add_argument('--system-board', type=Path, required=True)
    parser.add_argument('--cpu-board', type=Path, required=True)
    parser.add_argument('--top', type=Path, required=True)
    parser.add_argument('--static-only', action='store_true')
    args = parser.parse_args()
    main_circuit = read(args.main_netlist)
    cpu_circuit = read(args.card_board_dir / 'cpu/cpu.net')
    links, paths, missing = cpu_irq_routes(main_circuit, cpu_circuit,
                                            args.main_board, args.cpu_board)
    assert links == [True] * 4 and not missing
    assert len(paths) == 12 and all(p['route_mm'] is not None for p in paths)
    wrong = copy.deepcopy(main_circuit)
    wrong.components['R29'] = ('22', ('Device', 'R'))
    try:
        cpu_irq_routes(wrong, cpu_circuit, None, None)
    except ValueError as error:
        assert 'CPU IRQ0' in str(error)
    else:
        raise AssertionError('changed R29 value passed source binding')
    print('IRQ source and 12/12 routed legs bound')
    if args.static_only:
        return

    top = json.loads(args.top.read_text())
    assert top['runtime']['cpu_irq_connected'] == [True] * 4
    assert len(top['unmodeled_nets']) == 298
    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-irq-') as directory:
        temporary = Path(directory)
        cards = exported_cards(temporary)
        card_boards = {card: args.card_board_dir / card / f'{card}.kicad_pcb'
                       for card in ('gpu', 'io', 'storage', 'wifi', 'eink')}
        for bit, chip_pin, fpga_pin in zip(range(4), ('1', '141', '2', '142'),
                                           ('47', '48', '49', '52')):
            good = probe(args.top, bit)
            assert good['gpo'] == 0xa0 + bit, (bit, good)
            for leg, board, ref, pin, net in (
                    ('source', args.main_board, 'U7', chip_pin, f'/CPU_IRQ{bit}_SRC'),
                    ('series', args.main_board, f'R{29 + bit}', '2', f'/CPU_IRQ{bit}'),
                    ('receiver', args.cpu_board, 'U1', fpga_pin, f'/CPU_IRQ{bit}')):
                opened = temporary / f'open-IRQ{bit}-{leg}.kicad_pcb'
                open_launch(board, opened, ref, pin, net)
                altered, _, missing = cpu_irq_routes(
                    main_circuit, cpu_circuit,
                    opened if board == args.main_board else args.main_board,
                    opened if board == args.cpu_board else args.cpu_board)
                assert altered[bit] is False and sum(altered) == 3 and missing
                if leg != 'source':
                    continue
                mutant = check(cards, main_circuit, opened, card_boards,
                               args.system_board, args.cpu_board)
                assert mutant['runtime']['cpu_irq_connected'] == altered
                assert mutant['runtime']['routed_top'] is False
                assert len(mutant['unmodeled_nets']) == 301
                for name in (f'main:CPU_IRQ{bit}_SRC', f'main:CPU_IRQ{bit}',
                             f'cpu:CPU_IRQ{bit}'):
                    assert name in mutant['unmodeled_nets']
                changed_top = temporary / f'open-IRQ{bit}.json'
                changed_top.write_text(json.dumps(mutant))
                bad = probe(changed_top, bit)
                assert bad['gpo'] == 0x11 and bad['halted'] == 0, (bit, bad)
                print(f'IRQ{bit} open: GPO {good["gpo"]:#04x} -> {bad["gpo"]:#04x}')
        print('12/12 copper opens detected; 4/4 native interrupt counterexamples')


if __name__ == '__main__':
    main()
