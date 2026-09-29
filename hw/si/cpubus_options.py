#!/usr/bin/env python3
"""What-if sweeps for the CPU-bus overshoot (CC-007 / MB-007 CPU-socket nets).

    python3 hw/si/cpubus_options.py --study series|main|rx|ac|filter|spi|all [--jobs N]
                                    [--board-dir build/hw] [--out FILE.json]

The as-built bus (CPU-card U1 -> 33 ohm array RN -> J1 -> J2 -> main copper ->
U7, and the reverse for the 14 chipset-driven lines) overshoots the iCE40 limit
(FPGA-DS-02029 Table 4.1 + the I/O overshoot note: 3.60 V, 3.66 V for <= 1.6 ns).
Every option here is the slowbus_si.py case set (32 IBIS/line/connector corners
per line) re-run on a *mutated copy* of the routed boards' netlists (a series
value) or with what-if receiver parts (`Assembler.receiver_options`). Nothing
is written under build/hw: mutated netlists live in a temporary directory that
symlinks the real board files, so the routed copper is exactly the built one.

Per option and line: passing corners of 32, worst peak / trough at the receiver
die, worst ring-back into the VIL..VIH band, worst non-monotonic dip, and the
added settling time against the as-built 33 ohm (worst / best corner).
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'hw/cosim'))
import slowbus_si as si  # noqa: E402

SERIES_OHMS = (33, 47, 56, 68, 75, 82, 100, 120)
CARD_LINES = ('CPU_A0', 'CPU_A9', 'CPU_D4', 'CPU_A11', 'CPU_D5', 'CPU_A15')
MAIN_LINES = ('CPU_D0', 'CPU_D5', 'CPU_IRQ2')


def mutated_boards(board_dir, work, card_ohms=None, main_ohms=None, spi_ohms=None,
                   kinds=('main', 'cpu')):
    """Mirror main+cpu into `work`, with the CPU card's RN arrays and/or the
    main board's discrete CPU-bus source resistors set to a new value."""
    board_dir, work = Path(board_dir).resolve(), Path(work)
    for kind in kinds:
        (work / kind).mkdir(parents=True)
        for item in (board_dir / kind).iterdir():
            (work / kind / item.name).symlink_to(item)
    if card_ohms is not None:
        text = (board_dir / 'cpu/cpu.net').read_text()
        text, count = re.subn(r'(\(ref "RN\d+"\)\s*\(value ")\d+("\))', rf'\g<1>{card_ohms:g}\2', text)
        if count != 8:
            raise ValueError(f'expected 8 RN arrays on the CPU card, found {count}')
        (work / 'cpu/cpu.net').unlink()
        (work / 'cpu/cpu.net').write_text(text)
    if main_ohms is not None or spi_ohms is not None:
        circuit = si.Bench(board_dir).circuit('main')
        prefix, ohms = ('/CPU_', main_ohms) if main_ohms is not None else ('/SPI_', spi_ohms)
        refs = sorted({ref for net in circuit.nets if net.startswith(prefix) and net.endswith('_SRC')
                       for ref, _ in circuit.nets[net] if ref.startswith('R')})
        text = (board_dir / 'main/main.net').read_text()
        for ref in refs:
            text, count = re.subn(rf'(\(ref "{ref}"\)\s*\(value ")\d+R?("\))',
                                  rf'\g<1>{ohms:g}\2', text)
            if count != 1:
                raise ValueError(f'{ref}: expected one series value, found {count}')
        (work / 'main/main.net').unlink()
        (work / 'main/main.net').write_text(text)
    return work


def with_extra(cases, **extra):
    out = []
    for case in cases:
        config = si.Config(**{**case.config.__dict__,
                              'extra': tuple(dict(case.config.extra, **extra).items())})
        out.append(si.Case(case.group, case.name, case.drives, config, case.t_end,
                           case.step, case.couple))
    return out


def line_cases(bench, side, line, **extra):
    if side == 'card':
        cases = [c for c in si.cc_bus_cases(bench) if c.name.startswith(line + ' ')]
    else:
        cases = [c for c in si.mb_socket_cases(bench) if c.name.startswith(line + ' ')]
    if len(cases) != 32:
        raise ValueError(f'{side} {line}: {len(cases)} cases, expected 32')
    return with_extra(cases, **extra) if extra else cases


def metrics(results, baseline=None):
    """Summary of one line's 32 corner results; `baseline` (as-built results in
    the same order) gives the added settling time per corner."""
    worst = {'pass': 0, 'cases': len(results), 'vmax': -9.0, 'vmin': 9.0, 'ringback_mv': 0.0,
             'nonmono_mv': 0.0, 'kinds': {}}
    delays = []
    for n, r in enumerate(results):
        if not r['failures']:
            worst['pass'] += 1
        for f in r['failures']:
            kind = ('error' if f.startswith('simulation error') else
                    'overshoot' if 'overshoot' in f else 'undershoot' if 'undershoot' in f else
                    'ring-back' if 'rings back' in f else 'non-monotonic' if 'non-monotonic' in f
                    else 'other')
            worst['kinds'][kind] = worst['kinds'].get(kind, 0) + 1
        for m in r['receivers'].values():
            worst['vmax'] = max(worst['vmax'], float(m['vmax']))
            worst['vmin'] = min(worst['vmin'], float(m['vmin']))
            for e in m.get('edges') or []:
                if not e:
                    continue
                worst['ringback_mv'] = max(worst['ringback_mv'], -e['ringback_margin_v'] * 1e3)
                worst['nonmono_mv'] = max(worst['nonmono_mv'], e['monotonic_drop_mv'])
            if baseline is not None:
                base = next(iter(baseline[n]['receivers'].values()))
                for e, b in zip(m.get('edges') or [], base.get('edges') or []):
                    if e and b:
                        delays.append((e['settled_ns'] - b['settled_ns'],
                                       e['first_band_ns'] - b['first_band_ns']))
    if delays:
        worst['added_settle_ns_max'] = round(float(max(d[0] for d in delays)), 3)
        worst['added_first_band_ns_min'] = round(float(min(d[1] for d in delays)), 3)
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in worst.items()}


def run(cases, board_dir, jobs):
    return si.run_cases(cases, board_dir, jobs)


def series_study(board_dir, side, lines, jobs, ohms=SERIES_OHMS):
    table, baseline = {}, {}
    for value in ohms:
        with tempfile.TemporaryDirectory(prefix='cupc8-cpubus-') as work:
            kwargs = {'card_ohms': value} if side == 'card' else {'main_ohms': value}
            mutated_boards(board_dir, work, **kwargs)
            bench = si.Bench(work)
            for line in lines:
                results = run(line_cases(bench, side, line), work, jobs)
                if value == 33:
                    baseline[line] = results
                table[f'{side} {line} {value:g} ohm'] = metrics(results, baseline.get(line))
                print(f'{side} {line} {value:g}: {table[f"{side} {line} {value:g} ohm"]}', flush=True)
    return table


RX_OPTIONS = {
    'as built (33 ohm at the CPU card)': ({}, 33),
    'rx series 22 ohm at U7': ({'rx_series': 22.0}, 33),
    'rx series 33 ohm at U7': ({'rx_series': 33.0}, 33),
    'rx series 47 ohm at U7': ({'rx_series': 47.0}, 33),
    'rx series 68 ohm at U7': ({'rx_series': 68.0}, 33),
    'split 47 ohm card + 47 ohm at U7': ({'rx_series': 47.0}, 47),
    'split 33 ohm card + 68 ohm at U7': ({'rx_series': 68.0}, 33),
    'AC term 91 ohm + 47 pF at U7': ({'rx_shunt': (91.0, 47e-12)}, 33),
    'AC term 100 ohm + 22 pF at U7': ({'rx_shunt': (100.0, 22e-12)}, 33),
    'Schottky clamps (BAT54 class) at U7': ({'rx_diode': 1}, 33),
    'Schottky clamps + 68 ohm card': ({'rx_diode': 1}, 68),
    'data-sheet 6 pF pin C (3.6 pF extra), 33 ohm': ({'rx_extra_c': 3.6e-12}, 33),
    'data-sheet 6 pF pin C (3.6 pF extra), 68 ohm': ({'rx_extra_c': 3.6e-12}, 68),
    'data-sheet 6 pF pin C (3.6 pF extra), 100 ohm': ({'rx_extra_c': 3.6e-12}, 100),
}


def rx_study(board_dir, jobs, line='CPU_A0'):
    table, baseline = {}, None
    for name, (extra, card) in RX_OPTIONS.items():
        with tempfile.TemporaryDirectory(prefix='cupc8-cpubus-') as work:
            mutated_boards(board_dir, work, card_ohms=card)
            results = run(line_cases(si.Bench(work), 'card', line, **extra), work, jobs)
        if baseline is None:
            baseline = results
        table[name] = metrics(results, baseline)
        print(f'{name}: {table[name]}', flush=True)
    return table


def ac_study(board_dir, jobs, line='CPU_A0'):
    """AC (R + C to ground) termination at U7 against the card-side series value."""
    table, baseline = {}, None
    for card, term, cap in [(33, 0, 0)] + [(c, r, f) for c in (22, 33, 47) for r in (68.0, 91.0)
                                            for f in (100e-12, 220e-12)]:
        extra = {'rx_shunt': (term, cap)} if term else {}
        with tempfile.TemporaryDirectory(prefix='cupc8-cpubus-') as work:
            mutated_boards(board_dir, work, card_ohms=card)
            results = run(line_cases(si.Bench(work), 'card', line, **extra), work, jobs)
        baseline = baseline or results
        name = f'card {card} ohm + AC term {term:g} ohm / {cap * 1e12:g} pF' if term else 'as built'
        table[name] = metrics(results, baseline)
        print(f'{name}: {table[name]}', flush=True)
    return table


def filter_study(board_dir, jobs, line='CPU_A0'):
    """Edge-slowing shunt capacitor: at the CPU card's RN line side (a CPU-card
    only change) and at U7 (a main-board change), against the series value."""
    table, baseline = {}, None
    combos = [(33, 'as built', {})]
    for card in (33, 47, 68):
        for cap in (15e-12, 22e-12, 47e-12, 100e-12):
            combos.append((card, f'{cap * 1e12:g} pF at the CPU card RN', {'tx_shunt_c': cap}))
            combos.append((card, f'{cap * 1e12:g} pF at U7', {'rx_extra_c': cap}))
    for card, label, extra in combos:
        with tempfile.TemporaryDirectory(prefix='cupc8-cpubus-') as work:
            mutated_boards(board_dir, work, card_ohms=card)
            results = run(line_cases(si.Bench(work), 'card', line, **extra), work, jobs)
        baseline = baseline or results
        name = f'{card} ohm + {label}' if extra else label
        table[name] = metrics(results, baseline)
        print(f'{name}: {table[name]}', flush=True)
    return table


SPI_CASES = ('SCK all storage', 'SCK storage in J16 only', 'MOSI all storage',
             'SLOT1_CS_n storage')


def spi_study(board_dir, jobs, ohms=(33, 47, 68, 100, 150, 220)):
    """Series value of the main board's SPI source resistors R35-R42 (SCK, MOSI,
    six CS) with storage cards in the slots: 32 corners per case."""
    table = {}
    for value in ohms:
        with tempfile.TemporaryDirectory(prefix='cupc8-spi-') as work:
            mutated_boards(board_dir, work, spi_ohms=value, kinds=('main', 'storage'))
            bench = si.Bench(work)
            cases = [c for c in si.mb_spi_cases(bench, kinds=('storage',), singles=('storage',))
                     if c.name.split(' [')[0] in SPI_CASES]
            results = run(cases, work, jobs)
        for name in SPI_CASES:
            picked = [r for r in results if r['case'].split(' [')[0] == name]
            table[f'{name} {value:g} ohm'] = metrics(picked)
            print(f'{name} {value:g}: {table[f"{name} {value:g} ohm"]}', flush=True)
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--study', choices=('series', 'main', 'rx', 'ac', 'filter', 'spi', 'all'), default='all')
    parser.add_argument('--board-dir', type=Path, default=ROOT / 'build/hw')
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/si-slowbus/cpubus-options.json')
    args = parser.parse_args()
    report = {}
    if args.study in ('series', 'all'):
        report['card_series'] = series_study(args.board_dir, 'card', CARD_LINES, args.jobs)
    if args.study in ('main', 'all'):
        report['main_series'] = series_study(args.board_dir, 'main', MAIN_LINES, args.jobs)
    if args.study in ('rx', 'all'):
        report['receiver_options'] = rx_study(args.board_dir, args.jobs)
    if args.study == 'spi':
        report['spi_series'] = spi_study(args.board_dir, args.jobs)
    if args.study in ('filter', 'all'):
        report['edge_filter'] = filter_study(args.board_dir, args.jobs)
    if args.study in ('ac', 'all'):
        report['ac_termination'] = ac_study(args.board_dir, args.jobs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + '\n')
    print(f'-> {args.out}')


if __name__ == '__main__':
    main()
