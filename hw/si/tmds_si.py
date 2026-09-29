#!/usr/bin/env python3
"""GC-007: GPU card HDMI/DVI TMDS signal integrity on the routed board.

    python3 hw/si/tmds_si.py --build build/hw/gpu --out build/si/gc-007.json

Checks, for all four TMDS pairs (D0, D1, D2, clock), on the routed copper:

1. Differential impedance 100 ohm +-10 % at every trace sample from the
   RP2040 pin to the series resistor and from the resistor to the HDMI
   connector.  Samples come from `route_si.py`: the reported value is a
   rigorous lower bound, and the upper estimate adds the grid tail plus a
   1 % allowance, so "above 110 ohm" is proven by the lower bound alone.
   Cuts that meet a pad of the pair (resistor pack, ESD, connector: the
   breakout) are reported and enter check 3, not this one.
2. Intra-pair skew < 5 ps, RP2040 pin pad to connector pad, from each net's
   quasi-TEM delay along its routed path (the resistor-pack channels are
   one package and are taken as equal).
3. Insertion and return loss to 1.26 GHz of the resistor-to-connector
   interconnect (pads, breakout and the ESD array included, series resistor
   body excluded) in a 100 ohm differential reference, cascaded from the
   per-sample line sections at both the lower-bound and the upper-estimate
   impedance, whichever is worse.  Budget (the repository defines none):
     |SDD11| <= -19.58 dB: the worst standing-wave reflection a line within
       the row's own 100 ohm +-10 % tolerance can produce,
       ((1/0.9)^2 - 1) / ((1/0.9)^2 + 1) = 0.105;
     |SDD21| >= -0.5 dB: an allocation proposed here, awaiting David's
       confirmation (no DVI 1.0 / HDMI clause budgets a source PCB).
   Losses: copper skin effect with a 2x current-crowding factor on both
   lines, and tan(delta) 0.02 (7628 FR-4; JLC publishes no loss tangent).
   ESD: TI TPD4E05U06 DQA, CL 0.5 pF typ I/O to GND (TI SLVSBO7O rev O,
   5.4, no maximum given; also run at 1.0 pF) and 0.06 pF max channel to
   channel; placed where the path meets the ESD pads.

The series resistor value is read from the netlist (it is being changed);
all eight must be equal.  The HDMI Type A pin map checked is HDMI 1.4
Table 4-1: D2 +/- on pins 1/3, D1 4/6, D0 7/9, clock 10/12.
Not modelled: connector metal beyond its pads, the cable and sink, the
RP2040 package, and pair-to-pair coupling (other nets are held at ground).
"""
import argparse
import cmath
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'cosim'))
sys.path.insert(0, str(HERE.parent / 'tools'))
import route_si  # noqa: E402
from netlist import read as read_netlist  # noqa: E402

HDMI_PINS = {'d2': ('1', '3'), 'd1': ('4', '6'), 'd0': ('7', '9'), 'ck': ('10', '12')}
Z_NOM, Z_TOL = 100.0, .10
SKEW_MAX = 5e-12
F_MAX = 1.26e9
RL_MAX_DB = 20 * math.log10((1 / .9 ** 2 - 1) / (1 / .9 ** 2 + 1))   # -19.58
IL_MIN_DB = -.5
ESD_CL, ESD_CL_SENS, ESD_CROSS = .5e-12, 1.0e-12, .06e-12
TAN_DELTA = .02
RHO_CU = 1.72e-8
MU0 = 4e-7 * math.pi


def lanes(netlist, rp2040, connector):
    """Per lane and polarity: (mcu net, mcu pin, R channel, R pads, hdmi net, J pin, ESD pads)."""
    circuit = read_netlist(netlist)
    out, values = {}, set()
    for lane, pins in HDMI_PINS.items():
        for polarity, jpin in zip('pn', pins):
            hdmi = circuit.net(connector, jpin)
            if hdmi is None:
                raise ValueError(f'{connector}.{jpin} ({lane}{polarity}) is unconnected')
            resistors = [r for r in circuit.resistors if hdmi in r.ends]
            if len(resistors) != 1:
                raise ValueError(f'{hdmi}: expected one series resistor, found {len(resistors)}')
            resistor = resistors[0]
            mcu = resistor.ends[0] if resistor.ends[1] == hdmi else resistor.ends[1]
            chip = [pin for ref, pin in circuit.nets[mcu] if ref == rp2040]
            if len(chip) != 1:
                raise ValueError(f'{mcu}: series resistor does not reach {rp2040}')
            ref = resistor.ref.split('.')[0]
            r_mcu = [pin for r, pin in circuit.nets[mcu] if r == ref]
            r_hdmi = [pin for r, pin in circuit.nets[hdmi] if r == ref]
            others = [node for node in circuit.nets[hdmi] if node[0] not in (ref, connector)]
            if len(circuit.nets[mcu]) != 2 or len(r_mcu) != 1 or len(r_hdmi) != 1:
                raise ValueError(f'{mcu}/{hdmi}: unexpected extra connections')
            value = route_si.ohms(resistor.value)
            values.add(value)
            out[(lane, polarity)] = dict(mcu=mcu, chip=(rp2040, chip[0]), rpads=(ref, r_mcu[0], r_hdmi[0]),
                                         hdmi=hdmi, jpin=(connector, jpin), esd=others,
                                         resistor=resistor.ref, ohms=value)
    if len(values) != 1:
        raise ValueError(f'TMDS series resistors differ: {sorted(values)}')
    return out, values.pop()


def abcd_line(z, delay, length_m, f):
    w = 2 * math.pi * f
    l_per_m, c_per_m = z * delay, delay / z
    width_m = .2e-3
    rs = math.sqrt(math.pi * f * MU0 * RHO_CU)
    r_per_m = 2 * 2 * rs / width_m            # both lines, 2x crowding
    g_per_m = w * c_per_m * TAN_DELTA
    zs, yp = complex(r_per_m, w * l_per_m), complex(g_per_m, w * c_per_m)
    gamma, zc = cmath.sqrt(zs * yp), cmath.sqrt(zs / yp)
    gl = gamma * length_m
    return ((cmath.cosh(gl), zc * cmath.sinh(gl)), (cmath.sinh(gl) / zc, cmath.cosh(gl)))


def matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(2)) for j in range(2)) for i in range(2))


def sparams(sections, shunts, f, z0=Z_NOM):
    """sections: [(z, delay s/m, length m)]; shunts: {index: farads}."""
    m = ((1, 0), (0, 1))
    for index, (z, delay, length) in enumerate(sections):
        if index in shunts:
            m = matmul(m, ((1, 0), (2j * math.pi * f * shunts[index], 1)))
        m = matmul(m, abcd_line(z, delay, length, f))
    (a, b), (c, d) = m
    den = a + b / z0 + c * z0 + d
    return (a + b / z0 - c * z0 - d) / den, 2 / den


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help='routed GPU build directory (read only)')
    parser.add_argument('--board', type=Path, help='routed board (default BUILD/gpu.kicad_pcb)')
    parser.add_argument('--netlist', type=Path, help='netlist (default BUILD/gpu.net)')
    parser.add_argument('--out', type=Path, default=Path('build/si/gc-007.json'))
    parser.add_argument('--no-evidence', action='store_true',
                        help='skip the board receipt check (tests and exploration only; never a pass)')
    parser.add_argument('--jobs', type=int, default=None)
    parser.add_argument('--rp2040', default='U1')
    parser.add_argument('--connector', default='J2')
    args = parser.parse_args()
    board_path = args.board or args.build / 'gpu.kicad_pcb'
    netlist_path = args.netlist or args.build / 'gpu.net'
    report = {'row': 'GC-007', 'board': str(board_path), 'netlist': str(netlist_path),
              'board_sha256': route_si.sha256(board_path),
              'netlist_sha256': route_si.sha256(netlist_path), 'evidence': None}
    failures = []
    if args.no_evidence:
        failures.append('board receipt not checked (--no-evidence)')
    else:
        import boardevidence
        try:
            boardevidence.validate('gpu', args.build)
            report['evidence'] = 'valid'
        except ValueError as exc:
            report['evidence'] = str(exc)
            failures.append(f'board evidence: {exc}')
    wiring, series_ohms = lanes(netlist_path, args.rp2040, args.connector)
    report['series_resistor_ohms'] = series_ohms
    board = route_si.Board(board_path)
    routes = {}
    for (lane, pol), w in wiring.items():
        ref, r_mcu, r_hdmi = w['rpads']
        routes[(lane, pol, 'mcu')] = board.path(w['mcu'], w['chip'], (ref, r_mcu))
        routes[(lane, pol, 'hdmi')] = board.path(w['hdmi'], (ref, r_hdmi), w['jpin'])
    samples = {}
    for (lane, pol, side), route in routes.items():
        nets = (wiring[(lane, 'p')][side], wiring[(lane, 'n')][side])
        samples[(lane, pol, side)] = route_si.sample_path(board, route, nets, 1 if pol == 'p' else 2)
    keys = [s['key'] for group in samples.values() for s in group]
    results = route_si.solve_all(keys, args.jobs)
    lo_limit, hi_limit = Z_NOM * (1 - Z_TOL), Z_NOM * (1 + Z_TOL)
    freqs = [F_MAX * k / 126 for k in range(1, 127)]
    report['lanes'] = {}
    for lane in HDMI_PINS:
        entry = {'series_resistor': [wiring[(lane, p)]['resistor'] for p in 'pn']}
        # 1. impedance on trace samples, both sides of the resistor
        trace, breakout = [], []
        for side in ('mcu', 'hdmi'):
            for pol, own in (('p', 1), ('n', 2)):
                group = samples[(lane, pol, side)]
                partner = samples[(lane, 'n' if pol == 'p' else 'p', side)]
                prof = route_si.diff_profile(group, partner, results, own)
                for sample, (lo, hi, coupled) in zip(group, prof):
                    row = {'net': wiring[(lane, pol)][side], 'xy': sample['xy'], 'layer': sample['layer'],
                           'len_mm': round(sample['len_mm'], 4), 'kind': sample['kind'],
                           'z_lower': round(lo, 2), 'z_upper': round(hi, 2), 'coupled': coupled}
                    (trace if sample['kind'] == 'trace' else breakout).append(row)
        above = [r for r in trace if r['z_lower'] > hi_limit]
        below = [r for r in trace if r['z_upper'] < lo_limit]
        unsure = [r for r in trace if r not in above and r not in below and
                  not (r['z_lower'] >= lo_limit and r['z_upper'] <= hi_limit)]
        trace_mm = sum(r['len_mm'] for r in trace)
        entry['impedance'] = {
            'limit_ohm': [lo_limit, hi_limit], 'trace_samples': len(trace),
            'trace_mm': round(trace_mm, 3),
            'z_lower_min': min(r['z_lower'] for r in trace), 'z_lower_max': max(r['z_lower'] for r in trace),
            'z_upper_max': max(r['z_upper'] for r in trace),
            'proven_above_mm': round(sum(r['len_mm'] for r in above), 3),
            'proven_below_mm': round(sum(r['len_mm'] for r in below), 3),
            'undecided_mm': round(sum(r['len_mm'] for r in unsure), 3),
            'breakout_z_lower_range': [min(r['z_lower'] for r in breakout), max(r['z_lower'] for r in breakout)]
            if breakout else None}
        if above or below or unsure:
            failures.append(f'{lane}: {entry["impedance"]["proven_above_mm"]} mm proven above '
                            f'{hi_limit:.0f} ohm, {entry["impedance"]["proven_below_mm"]} mm below '
                            f'{lo_limit:.0f}, {entry["impedance"]["undecided_mm"]} mm undecided of '
                            f'{trace_mm:.2f} mm trace (lower bound {entry["impedance"]["z_lower_min"]}'
                            f'-{entry["impedance"]["z_lower_max"]} ohm)')
        entry['samples'] = trace + breakout
        # 2. intra-pair skew, pin to connector
        delays, lengths = {}, {}
        for pol in 'pn':
            delays[pol] = sum(route_si.path_delay(samples[(lane, pol, side)], results, routes[(lane, pol, side)])
                              for side in ('mcu', 'hdmi'))
            lengths[pol] = sum(routes[(lane, pol, side)]['length_mm'] for side in ('mcu', 'hdmi'))
        skew = abs(delays['p'] - delays['n'])
        entry['skew'] = {'delay_ps': {p: round(delays[p] * 1e12, 3) for p in 'pn'},
                         'length_mm': {p: round(lengths[p], 4) for p in 'pn'},
                         'skew_ps': round(skew * 1e12, 3), 'limit_ps': SKEW_MAX * 1e12}
        if skew >= SKEW_MAX:
            failures.append(f'{lane}: intra-pair skew {skew * 1e12:.2f} ps >= 5 ps')
        # 3. interconnect S-parameters, resistor pad to connector pad (P path order)
        group = samples[(lane, 'p', 'hdmi')]
        prof = route_si.diff_profile(group, samples[(lane, 'n', 'hdmi')], results, 1)
        esd_pads = [board.pads[node]['at'] for pol in 'pn' for node in wiring[(lane, pol)]['esd']]
        if not esd_pads:
            raise ValueError(f'{lane}: no ESD device on the HDMI nets')
        cx = sum(x for x, _ in esd_pads) / len(esd_pads)
        cy = sum(y for _, y in esd_pads) / len(esd_pads)
        at = min(range(len(group)), key=lambda i: math.dist(group[i]['xy'], (cx, cy)))
        worst = {}
        for cl_name, cl in (('typ', ESD_CL), ('2x_typ', ESD_CL_SENS)):
            shunt = {at: cl / 2 + ESD_CROSS}
            rl, il = -math.inf, 0.0
            for pick in (0, 1):
                if any(math.isinf(p[pick]) for p in prof):
                    rl = math.inf      # a non-contracting cut: no estimate, fail closed
                    continue
                sections = [(p[pick], results[s['key']]['delay_s_per_m'], s['len_mm'] * 1e-3)
                            for s, p in zip(group, prof)]
                for f in freqs:
                    s11, s21 = sparams(sections, shunt, f)
                    rl = max(rl, 20 * math.log10(abs(s11)))
                    il = min(il, 20 * math.log10(abs(s21)))
            worst[cl_name] = {'sdd11_max_db': round(rl, 3), 'sdd21_min_db': round(il, 4)}
        entry['loss'] = {'to_hz': F_MAX, 'sdd11_limit_db': round(RL_MAX_DB, 2),
                         'sdd21_limit_db': IL_MIN_DB, **worst}
        if worst['typ']['sdd11_max_db'] > RL_MAX_DB:
            failures.append(f'{lane}: |SDD11| {worst["typ"]["sdd11_max_db"]:.2f} dB > {RL_MAX_DB:.2f} dB')
        if worst['typ']['sdd21_min_db'] < IL_MIN_DB:
            failures.append(f'{lane}: |SDD21| {worst["typ"]["sdd21_min_db"]:.3f} dB < {IL_MIN_DB} dB')
        report['lanes'][lane] = entry
    report['failures'] = failures
    report['pass'] = not failures
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + '\n')
    for lane, entry in report['lanes'].items():
        imp, sk, loss = entry['impedance'], entry['skew'], entry['loss']['typ']
        print(f'{lane}: Zdiff lower bound {imp["z_lower_min"]}-{imp["z_lower_max"]} ohm on '
              f'{imp["trace_mm"]} mm trace (limit {imp["limit_ohm"][0]:.0f}-{imp["limit_ohm"][1]:.0f}); '
              f'skew {sk["skew_ps"]} ps; SDD11 <= {loss["sdd11_max_db"]} dB, SDD21 >= {loss["sdd21_min_db"]} dB')
    print(f'series resistors {series_ohms:g} ohm (netlist); report {args.out}')
    for failure in failures:
        print('FAIL', failure)
    print('GC-007', 'PASS' if report['pass'] else 'FAIL')
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
