#!/usr/bin/env python3
"""E2E-002..004 fault injection: a wiring fault in the netlist top must fail the scenario.

Each E2E row passes on the netlist-generated top; this runs the same
whole-machine scenario (test/emu/test_e2e.mjs, native emulator) on a top
generated from a board copy with one fault, and requires it to fail:

  E2E-002 (blank ROM to BASIC): the ROM's /WE branch open (programming never
          lands, the first verified chunk fails); the system card's USB D+
          launch open (cupc8.py cannot reach the machine).
  E2E-003 (network fetch): the Wi-Fi card's SCK contact open (no join, no page).
  E2E-004 (negative system tests): the Type-C comparator reference divider's
          bottom resistor changed in the main netlist, so a 1.5 A source
          reads as 3 A and the low-power scenario fails (only that scenario
          runs: CUPC8_E2E004_ONLY=lowpower).
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'hw/cosim'), str(ROOT / 'test/hw')]
from gen_top import check, exported_cards, named_pin, ohms, resistor_between  # noqa: E402
from netlist import Resistor, read  # noqa: E402
from cosim_mutate import board_args, card_boards, open_pad  # noqa: E402


def cc_reference_changed(circuit):
    """The comparator's reference divider (U5 IN- to VEE) with a quarter of its resistance."""
    bottom = resistor_between(circuit, named_pin(circuit, 'U5', 'IN'), named_pin(circuit, 'U5', 'VEE'))
    changed = copy.deepcopy(circuit)
    changed.resistors = tuple(Resistor(r.ref, str(int(ohms(r.value) / 4)), r.ends) if r.ref == bottom.ref else r
                              for r in changed.resistors)
    return changed, f'{bottom.ref} {bottom.value} -> {int(ohms(bottom.value) / 4)}'


# case -> [(label, board, ref, pad, net) copper opens | ('netlist', label, function)], env for the run
CASES = {
    'E2E-002': ([('ROM /WE branch open (U10.31)', 'main', 'U10', '31', '/MEM_nWE'),
                 ('system card USB D+ launch open', 'system', 'U1', '47', '/USB_DP_MCU')], {}),
    'E2E-003': ([('Wi-Fi card SCK contact open', 'wifi', 'J1', 'B13', '/SCK')], {}),
    'E2E-004': ([('netlist', 'Type-C reference divider changed', cc_reference_changed)],
                {'CUPC8_E2E004_ONLY': 'lowpower'}),
}


def main():
    parser = board_args(__doc__)
    parser.add_argument('case', choices=sorted(CASES))
    args = parser.parse_args()
    boards = card_boards(args)
    mutations, env = CASES[args.case]
    with tempfile.TemporaryDirectory(prefix='cupc8-e2e-mutants-') as directory:
        temporary = Path(directory)
        (temporary / 'cards').mkdir()
        cards = exported_cards(temporary / 'cards')
        for index, mutation in enumerate(mutations):
            main_circuit = read(args.main_netlist)
            main_board, system_board, card_paths = args.main_board, args.system_board, dict(boards)
            if mutation[0] == 'netlist':
                _, label, change = mutation
                main_circuit, detail = change(main_circuit)
                label = f'{label} ({detail})'
            else:
                label, board, ref, pad, net = mutation
                source = {'main': main_board, 'system': system_board}.get(board) or card_paths[board]
                target = temporary / f'{index}-{board}.kicad_pcb'
                open_pad(source, target, ref, pad, net)
                if board == 'main':
                    main_board = target
                elif board == 'system':
                    system_board = target
                else:
                    card_paths[board] = target
            top = check(cards, main_circuit, main_board, card_paths, system_board, args.cpu_board)
            path = temporary / f'{index}.json'
            path.write_text(json.dumps(top))
            print(f'{args.case}: {label}: running the scenario on the faulty top', flush=True)
            result = subprocess.run(['node', 'test/emu/test_e2e.mjs', args.case], cwd=ROOT, text=True,
                                    env=dict(os.environ, CUPC8_EMU='native', CUPC8_COSIM_TOP=str(path), **env),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            failures = [line for line in result.stdout.splitlines() if line.startswith('FAIL')]
            if result.returncode == 0:
                print(result.stdout[-2000:])
                raise AssertionError(f'{args.case}: the scenario passed on a top with a fault: {label}')
            if not failures:
                print(result.stdout[-2000:])
                raise AssertionError(f'{args.case}: {label}: the run crashed instead of failing a check')
            print(f'{args.case}: {label}: detected ({len(failures)} failed checks, first: {failures[0]})',
                  flush=True)
    print(f'{args.case}: every injected wiring fault fails the scenario')


if __name__ == '__main__':
    main()
