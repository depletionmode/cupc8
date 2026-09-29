#!/usr/bin/env python3
"""What-if sweep for the slot MISO overshoot (MB-007, 'MB spi MISO').

    python3 hw/si/miso_options.py [--jobs N] [--board-dir build/hw] [--out FILE.json]

The slot MISO net (cards' 74LVC1G125 -> J11..J16 B16 -> U7.48) has no series
resistor anywhere: R20 is BR_MISO and R35-R43 are SCK/MOSI/CS sources.  So the
only BOM-free lever does not exist; this sweeps a series resistor at the U7.48
pad (`rx_series`, a main-board change) on the routed boards, for the nearest
(J11) and farthest (J16) slot, all-cards-loaded and one-card cases, GPU (74LVC
same as every RP2040 card) and storage cards, 32 IBIS corners each.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'hw/cosim'))
import slowbus_si as si  # noqa: E402
import cpubus_options as co  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-dir', type=Path, default=ROOT / 'build/hw')
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/si-slowbus/miso-options.json')
    parser.add_argument('--ohms', type=float, nargs='*', default=[22, 33, 47, 68, 100])
    parser.add_argument('--where', choices=('rx', 'tx'), default='tx', help='series R at U7.48 (rx) or at each card buffer (tx)')
    args = parser.parse_args()
    bench = si.Bench(args.board_dir)
    base = [c for c in si.mb_spi_cases(bench, kinds=('gpu', 'storage'), singles=('storage',))
            if c.group == 'MB spi MISO' and c.name.split(' ')[1] in ('J11', 'J16')]
    print(len(base), 'cases per value')
    table = {}
    for ohms in args.ohms:
        cases = co.with_extra(base, **{args.where + '_series': ohms}) if ohms else base
        results = co.run(cases, args.board_dir, args.jobs)
        table[f'{args.where} {ohms:g} ohm'] = co.metrics(results)
        # settled time of the far receiver edge, for the turnaround budget
        u7 = [m for r in results for lab, m in r['receivers'].items() if lab.endswith('U7.48')]
        table[f'{args.where} {ohms:g} ohm']['u7_vmax'] = round(max(float(m['vmax']) for m in u7), 3)
        table[f'{args.where} {ohms:g} ohm']['u7_vmin'] = round(min(float(m['vmin']) for m in u7), 3)
        settled = [e['settled_ns'] for r in results for m in r['receivers'].values()
                   for e in (m.get('edges') or []) if e]
        table[f'{args.where} {ohms:g} ohm']['settled_ns_max'] = round(max(settled), 3) if settled else None
        print(f'{ohms:g} ohm: {table[f"{args.where} {ohms:g} ohm"]}', flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(table, indent=1) + '\n')


if __name__ == '__main__':
    main()
