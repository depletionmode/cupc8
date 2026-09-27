#!/usr/bin/env python3
"""Schematic wiring failures must be visible to the generated top."""
import argparse
import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/cosim'))
from gen_top import check, exported_cards, named_pin
from netlist import read


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
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cupc8-cosim-cx-') as temporary:
        cards = exported_cards(Path(temporary))
        main = read(args.main_netlist)
        manifest = check(cards, main)
        print(f"valid top: {len(manifest['contacts'])} contacts, {len(manifest['paths'])} paths")

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

        broken_clock = copy.deepcopy(main)
        broken_clock.resistors = tuple(r for r in broken_clock.resistors if r.ref != 'R17')
        rejected(cards, broken_clock, 'missing chipset oscillator series resistor')


if __name__ == '__main__':
    main_cli()
