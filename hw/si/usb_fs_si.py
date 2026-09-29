#!/usr/bin/env python3
"""IC-007 / YC-007: RP2040 USB full-speed D+/D- signal integrity.

    python3 hw/si/usb_fs_si.py io --build build/hw/io --out build/si/ic-007.json
    python3 hw/si/usb_fs_si.py system --build build/hw/system --out build/si/yc-007.json

io:     the IO card's USB-A host port (downstream facing, full/low speed).
system: the system card's USB-C device port (upstream facing, full speed CDC).

Routed copper from the RP2040 pin through the series resistor to every
connector contact is extracted with `route_si.py` (rigorous lower-bound
cross-section impedance, upper-bound capacitance).  Checks, with the clause
each comes from (USB 2.0 specification, usb_20.pdf in usb.org's
usb_20_20250603.zip; RP2040 datasheet build 2025-02-20):

 1. Z  - differential impedance 90 ohm +-10 % (the catalogue row), at every
         trace sample on both sides of the series resistor; and the looser
         spec requirement of 7.1.6.1, "the transmission line between the
         receptacle and RS must be 90 ohm +-15 %", on the connector side.
         Two lines that do not share a cut are uncoupled: their
         differential impedance is the sum of both single-ended ones.
 2. skew - "length matched": D+/D- one-way delay difference, pin to each
         connector contact, <= 100 ps, the cable's TSKEW (7.1.3, Table
         7-12), used here as the board's allowance.
 3. delay - transceiver to connector <= 3 ns for a host port and <= 1 ns
         for a device (7.1.16), bounded with the largest stack Dk (4.6).
 4. C  - transmission-line capacitance per conductor, receptacle to
         transceiver, <= 75 pF (host) / 25 pF (device), and the lumped part
         (ESD at its maximum) within 75 pF (7.1.6.1); a device's D+/D-
         capacitance must differ by less than 10 % (7.1.6.1).
 5. RS - the netlist series resistor is the 27 ohm the RP2040 requires
         (datasheet 1.4.2, Table 1), so an RP2040 PHY of 1..17 ohm meets
         ZDRV 28..44 ohm (7.1.1.1, Table 7-9).
 6. edges - ngspice transient of one differential transition (D+ rising,
         D- falling), driver ZDRV 28 and 44 ohm, intrinsic edges that give
         the Table 7-9 TFR/TFF limits of 4 and 20 ns into the Figure 7-9
         load with no board, through the extracted board:
         a) Figure 7-9 load (CL = 50 pF) at the connector: both transitions
            monotonic (7.1.2.1) and the crossover VCRS within 1.3..2.0 V
            (7.1.2.1, Table 7-9); the board's added 10-90 % time is reported
            (the RP2040 datasheet gives no FS TFR, so absolute TFR at the
            connector cannot be proven here);
         b) through a 26 ns cable (TFSCBL, 7.1.1.1) of 90 ohm +-15 %
            (Table 7-12) into 5 pF or 75 pF with the far port's pull
            resistor: after the first crossing, no re-crossing of VIH 2.0 V /
            VIL 0.8 V (single ended) or +-0.2 V (differential) within one
            bit (RP2040 Table 626; USB 2.0 Table 7-7).
ESD: ST USBLC6-2SC6, Ci/o-GND 3.5 pF max, 0.015 pF matching (Doc ID 11265
Rev 5).  Stubs (ESD branches, the second USB-C row) are lumped at their
junction with their upper-bound capacitance.  Not modelled: connector body
metal, RP2040 package and pin capacitance (not published), common mode.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'cosim'))
sys.path.insert(0, str(HERE.parent / 'tools'))
import route_si  # noqa: E402
import si_cache  # noqa: E402
import xsection  # noqa: E402
from netlist import read as read_netlist  # noqa: E402

BOARDS = {
    'io': dict(row='IC-007', port='host', connector='J2', dp=('3',), dm=('2',),
               delay_max=3e-9, tl_c_max=75e-12, pull='down'),
    'system': dict(row='YC-007', port='device', connector='J1', dp=('A6', 'B6'), dm=('A7', 'B7'),
                   delay_max=1e-9, tl_c_max=25e-12, pull='up'),
}
RP2040_DP, RP2040_DM = '47', '46'          # RP2040 QFN-56 USB_DP / USB_DM
RS_REQUIRED = 27.0                          # RP2040 datasheet 1.4.2 Table 1
Z_NOM, Z_ROW_TOL, Z_SPEC_TOL = 90.0, .10, .15
SKEW_MAX = 100e-12
LUMPED_MAX = 75e-12
ESD_C_MAX, ESD_C_MATCH = 3.5e-12, .015e-12
VIA_C_ALLOW = 1e-12                         # per via barrel, generous
ZDRV = (28.0, 44.0)
TFR = (4e-9, 20e-9)
CL_TEST = 50e-12
VDD = 3.3
CABLE_TD, CABLE_Z = 26e-9, (76.5 / 2, 103.5 / 2)
FAR_C = (5e-12, 75e-12)
R_PULL = {'down': 15e3, 'up': 1.5e3}
VIH, VIL, VDIFF = 2.0, .8, .2
BIT = 1 / 12e6


def wiring(netlist, cfg):
    circuit = read_netlist(netlist)
    out = {}
    for name, chip_pin, pins in (('dp', RP2040_DP, cfg['dp']), ('dm', RP2040_DM, cfg['dm'])):
        mcu = circuit.net('U1', chip_pin)
        conn = {circuit.net(cfg['connector'], p) for p in pins}
        if mcu is None or len(conn) != 1 or None in conn:
            raise ValueError(f'{name}: RP2040 pin or connector contacts unconnected/split')
        conn = conn.pop()
        part = circuit.series(('U1', chip_pin), (cfg['connector'], pins[0]))
        if part is None:
            raise ValueError(f'USB {name}: no single series resistor between U1.{chip_pin} and the connector')
        ohms = route_si.ohms(part.value)
        rref = part.ref
        rpad_mcu = [p for r, p in circuit.nets[mcu] if r == rref]
        rpad_conn = [p for r, p in circuit.nets[conn] if r == rref]
        esd = [node for node in circuit.nets[conn] if node[0] not in (rref, cfg['connector'])]
        if len(circuit.nets[mcu]) != 2:
            raise ValueError(f'{mcu}: extra connections between the RP2040 and RS')
        out[name] = dict(mcu=mcu, conn=conn, rs=rref, ohms=ohms, chip=('U1', chip_pin),
                         rpad_mcu=(rref, rpad_mcu[0]), rpad_conn=(rref, rpad_conn[0]),
                         contacts=[(cfg['connector'], p) for p in pins], esd=esd)
    return out


def series_failures(rs):
    """RS must be the RP2040's required 27 ohm (and so ZDRV-feasible)."""
    return [f'D{"+" if tag == "p" else "-"} series resistor {value:g} ohm, RP2040 requires 27'
            for tag, value in rs.items() if value != RS_REQUIRED]


def ramp_for_tfr(tfr, r, c):
    """Linear-ramp duration whose RC-filtered 10-90 % time equals tfr."""
    tau = r * c

    def measured(ramp):
        def v(t):
            if t <= ramp:
                return (t - tau * (1 - math.exp(-t / tau))) / ramp
            return 1 - tau * (math.exp(-(t - ramp) / tau) - math.exp(-t / tau)) / ramp

        def cross(level):
            lo, hi = 0.0, ramp + 50 * tau
            for _ in range(80):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if v(mid) < level else (lo, mid)
            return hi
        return cross(.9) - cross(.1)
    lo, hi = .5e-9, tfr / .8       # 0.5 ns floor: ngspice stalls on ps ramps through a 26 ns line (RC edges are 4+ ns)
    if measured(lo) > tfr:
        # An ideal step through ZDRV into CL is already slower than tfr (44 ohm
        # x 50 pF gives 4.8 ns): the fastest edge this ZDRV can produce.
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if measured(mid) < tfr else (lo, mid)
    return hi


MIN_SECTION = 5e-12


def sections(samples, results, own, pick=0):
    """Merge consecutive samples into (Z, TD) line sections for SPICE.

    Neighbours within 1 ohm merge, and so does anything shorter than 5 ps
    (a 12 Mb/s edge cannot resolve it; ngspice stalls on ps-scale lines)."""
    out = []
    for sample in samples:
        result = results[sample['key']]
        z = min(route_si.se_bounds(result, own - 1)[pick], 500.0)   # an unbounded estimate is capped
        td = sample['len_mm'] * 1e-3 * result['delay_s_per_m']
        if out and (abs(out[-1][0] - z) < 1.0 or td < MIN_SECTION or out[-1][1] < MIN_SECTION):
            zp, tdp = out[-1]
            out[-1] = ((zp * tdp + z * td) / (tdp + td), tdp + td)
        else:
            out.append((z, td))
    while len(out) > 1 and out[-1][1] < MIN_SECTION:
        (zp, tdp), (z, td) = out[-2], out[-1]
        out[-2:] = [((zp * tdp + z * td) / (tdp + td), tdp + td)]
    return out


LADDER_PS = 20e-12    # delay per lumped section: cut-off ~ 16 GHz against a 12 Mb/s edge


def line_netlist(tag, start, end, secs):
    """The board's line sections as lumped LC ladders (pi sections).

    ngspice's lossless T element is used only for the 26 ns cable: on board
    sections of 15-60 ps it stalls (minutes per transient).  A 20 ps ladder
    reproduces the T element to 0.01 % on a 3-section test (3.4150 against
    3.4149 ns 10-90 % into 50 pF) and runs in about a second.
    """
    if not secs:
        return [f'R{tag}short {start} {end} 1e-6']
    lines, node = [], start
    for index, (z, td) in enumerate(secs):
        count = max(1, math.ceil(td / LADDER_PS))
        cap, ind = td / z / count, z * td / count
        for k in range(count):
            nxt = end if (index == len(secs) - 1 and k == count - 1) else f'{tag}_{index}_{k}'
            lines.append(f'L{tag}{index}_{k} {node} {nxt} {ind:.6e}')
            # each node carries the halves of the two sections it joins
            lines.append(f'C{tag}{index}_{k}a {node} 0 {cap / 2:.6e}')
            lines.append(f'C{tag}{index}_{k}b {nxt} 0 {cap / 2:.6e}')
            node = nxt
    return lines


def spice(net, probes, stop):
    with tempfile.TemporaryDirectory() as tmp:
        deck = Path(tmp) / 'deck.cir'
        data = Path(tmp) / 'out.txt'
        deck.write_text('\n'.join(['* usb fs edge', *net,
                                   # trapezoidal integration stalls on some lossless-line decks
                                   '.options method=gear',
                                   f'.tran 5p {stop:.4e} 0 5p',
                                   '.control', 'set wr_singlescale', 'run',
                                   f'wrdata {data} ' + ' '.join(f'v({p})' for p in probes),
                                   'quit', '.endc', '.end']) + '\n')
        subprocess.run(['ngspice', '-b', str(deck)], check=True, capture_output=True, text=True, timeout=300)   # a stall fails the row
        rows = [list(map(float, line.split())) for line in data.read_text().split('\n') if line.strip()]
    time = [r[0] for r in rows]
    return time, {p: [r[1 + i] for r in rows] for i, p in enumerate(probes)}


def crossing(t, v, level, rising):
    for i in range(1, len(v)):
        if (v[i - 1] < level <= v[i]) if rising else (v[i - 1] > level >= v[i]):
            f = (level - v[i - 1]) / (v[i] - v[i - 1])
            return t[i - 1] + f * (t[i] - t[i - 1])
    return None


def monotonic(t, v, rising, t0, t1, noise=10e-3):   # 10 mV = 0.3 % of the swing: the lossless-line ripple floor (1.5 mV on ideal lines)
    peak = v[0]
    for ti, vi in zip(t, v):
        if t0 <= ti <= t1:
            if rising:
                if vi < peak - noise:
                    return False
                peak = max(peak, vi)
            else:
                if vi > peak + noise:
                    return False
                peak = min(peak, vi)
        elif ti < t0:
            peak = vi
    return True


def recross(t, v, level, rising, t_first, window):
    """True if v, having crossed `level`, crosses back within the window."""
    for ti, vi in zip(t, v):
        if t_first < ti <= t_first + window and ((vi < level) if rising else (vi > level)):
            return True
    return False


def board_deck(line_secs, rs, rint, ramp, lumped, load):
    """Both lines: source, RP2040-side lines, RS, connector-side lines, load."""
    net = []
    for tag, rising in (('p', True), ('n', False)):
        v0, v1 = (0, VDD) if rising else (VDD, 0)
        net.append(f'V{tag} s{tag} 0 PWL(0 {v0} 1n {v0} {1e-9 + ramp:.4e} {v1})')
        net.append(f'Ri{tag} s{tag} pin{tag} {rint:.4f}')
        net += line_netlist(f'm{tag}', f'pin{tag}', f'ra{tag}', line_secs[tag]['mcu'])
        net.append(f'Rs{tag} ra{tag} rb{tag} {rs[tag]:.4f}')
        conn_secs = line_secs[tag]['conn']
        # lumped shunts (ESD, stubs, vias) at the junction nearest the ESD pads
        split = line_secs[tag]['junction']
        net += line_netlist(f'c{tag}a', f'rb{tag}', f'j{tag}', conn_secs[:split])
        net.append(f'Cj{tag} j{tag} 0 {sum(c for _, c in lumped[tag]):.4e}')
        net += line_netlist(f'c{tag}b', f'j{tag}', f'x{tag}', conn_secs[split:])
        net += load(tag)
    return net


def run_edges(line_secs, lumped, rs, pull):
    """Section 6 of the module docstring: (cases, failure strings)."""
    failures = []
    edges = []
    for zdrv in ZDRV:
        rint = zdrv - RS_REQUIRED
        if rint < 0:
            raise ValueError('series resistor above ZDRV minimum')
        for tfr in TFR:
            ramp = ramp_for_tfr(tfr, zdrv, CL_TEST)
            # a) Figure 7-9 test load at the connector
            net = board_deck(line_secs, rs, rint, ramp, lumped,
                             lambda tag: [f'CL{tag} x{tag} 0 {CL_TEST:.4e}'])
            t, v = spice(net, ['xp', 'xn'], 1e-9 + ramp + 120e-9)
            tp = [crossing(t, v['xp'], VDD * f, True) for f in (.1, .9)]
            tn = [crossing(t, v['xn'], VDD * f, False) for f in (.9, .1)]
            # crossover: where the two lines meet during the transition
            diff = [a - b for a, b in zip(v['xp'], v['xn'])]
            tc = crossing(t, diff, 0.0, True)
            i = min(range(len(t)), key=lambda k: abs(t[k] - tc))
            vcrs = (v['xp'][i] + v['xn'][i]) / 2
            mono = (monotonic(t, v['xp'], True, 1e-9, t[-1]) and monotonic(t, v['xn'], False, 1e-9, t[-1]))
            case = {'zdrv': zdrv, 'tfr_ideal_ns': tfr * 1e9, 'load': 'fig7-9',
                    'tfr_ns': round((tp[1] - tp[0]) * 1e9, 3), 'tff_ns': round((tn[1] - tn[0]) * 1e9, 3),
                    'board_adds_ns': round((max(tp[1] - tp[0], tn[1] - tn[0]) - tfr) * 1e9, 3),
                    'vcrs_v': round(vcrs, 4), 'monotonic': mono}
            edges.append(case)
            if not mono or not 1.3 <= vcrs <= 2.0:
                failures.append(f'Figure 7-9 edge ZDRV {zdrv} TFR {tfr * 1e9:.0f} ns: monotonic {mono}, '
                                f'VCRS {vcrs:.3f} V')
            # b) cable to a far port
            for zc in CABLE_Z:
                for far_c in FAR_C:
                    def load(tag, zc=zc, far_c=far_c):
                        lines = [f'Tcab{tag} x{tag} 0 f{tag} 0 Z0={zc} TD={CABLE_TD:.4e}',
                                 f'Cf{tag} f{tag} 0 {far_c:.4e}']
                        # host port (io): far device pulls D+ up at 1.5 k and
                        # the host's 15 k pull-downs sit at the connector;
                        # device port: the host's 15 k pull-downs are far.
                        if pull == 'down':
                            lines.append(f'Rpd{tag} x{tag} 0 {R_PULL["down"]}')
                            if tag == 'p':
                                lines.append(f'Rpu{tag} f{tag} vdd {R_PULL["up"]}')
                        else:
                            lines.append(f'Rpd{tag} f{tag} 0 {R_PULL["down"]}')
                            if tag == 'p':
                                lines.append(f'Rpu{tag} x{tag} vdd {R_PULL["up"]}')
                        return lines
                    net = board_deck(line_secs, rs, rint, ramp, lumped, load) + [f'Vdd vdd 0 {VDD}']
                    t, v = spice(net, ['fp', 'fn'], 1e-9 + ramp + CABLE_TD + 2 * BIT)
                    first_p = crossing(t, v['fp'], VIH, True)
                    first_n = crossing(t, v['fn'], VIL, False)
                    fd = [a - b for a, b in zip(v['fp'], v['fn'])]
                    first_d = crossing(t, fd, VDIFF, True)
                    bad = (None in (first_p, first_n, first_d) or
                           recross(t, v['fp'], VIH, True, first_p, BIT) or
                           recross(t, v['fn'], VIL, False, first_n, BIT) or
                           recross(t, fd, VDIFF, True, first_d, BIT))
                    case = {'zdrv': zdrv, 'tfr_ideal_ns': tfr * 1e9, 'load': 'cable',
                            'cable_z_se': zc, 'far_c_pf': far_c * 1e12, 'clean_thresholds': not bad,
                            'far_peak_v': round(max(v['fp']), 3), 'far_min_v': round(min(v['fn']), 3)}
                    edges.append(case)
                    if bad:
                        failures.append(f'cable edge ZDRV {zdrv} TFR {tfr * 1e9:.0f} ns Z {zc} C '
                                        f'{far_c * 1e12:.0f} pF: threshold re-crossing')
    return edges, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('board', choices=tuple(BOARDS))
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--board-file', type=Path)
    parser.add_argument('--netlist', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--no-evidence', action='store_true',
                        help='skip the board receipt check (tests/exploration; never a pass)')
    parser.add_argument('--jobs', type=int)
    args = parser.parse_args()
    cfg = BOARDS[args.board]
    board_path = args.board_file or args.build / f'{args.board}.kicad_pcb'
    netlist_path = args.netlist or args.build / f'{args.board}.net'
    out_path = args.out or Path('build/si') / f'{cfg["row"].lower()}.json'
    report = {'row': cfg['row'], 'port': cfg['port'], 'board': str(board_path),
              'board_sha256': route_si.sha256(board_path), 'netlist': str(netlist_path),
              'netlist_sha256': route_si.sha256(netlist_path), 'evidence': None}
    failures = []
    if args.no_evidence:
        failures.append('board receipt not checked (--no-evidence)')
    else:
        import boardevidence
        try:
            boardevidence.validate(args.board, args.build)
            report['evidence'] = 'valid'
        except ValueError as exc:
            report['evidence'] = str(exc)
            failures.append(f'board evidence: {exc}')
    wires = wiring(netlist_path, cfg)
    # 5. series resistor
    rs = {tag: wires[name]['ohms'] for tag, name in (('p', 'dp'), ('n', 'dm'))}
    report['series_resistor_ohms'] = rs
    failures += series_failures(rs)
    board = route_si.Board(board_path)
    nets = {'mcu': (wires['dp']['mcu'], wires['dm']['mcu']), 'conn': (wires['dp']['conn'], wires['dm']['conn'])}
    routes, samples = {}, {}
    for tag, name, own in (('p', 'dp', 1), ('n', 'dm', 2)):
        w = wires[name]
        routes[(tag, 'mcu')] = board.path(w['mcu'], w['chip'], w['rpad_mcu'])
        samples[(tag, 'mcu')] = route_si.sample_path(board, routes[(tag, 'mcu')], nets['mcu'], own)
        for index, contact in enumerate(w['contacts']):
            routes[(tag, 'conn', index)] = board.path(w['conn'], w['rpad_conn'], contact)
            samples[(tag, 'conn', index)] = route_si.sample_path(
                board, routes[(tag, 'conn', index)], nets['conn'], own)
    stub_samples = {}
    for tag, name, own in (('p', 'dp', 1), ('n', 'dm', 2)):
        main_route = routes[(tag, 'conn', 0)]
        stub = {'segments': main_route['stubs'], 'vias': [], 'pad_mm': 0.0}
        stub_samples[tag] = route_si.sample_path(board, stub, nets['conn'], own) if stub['segments'] else []
    keys = [s['key'] for group in list(samples.values()) + list(stub_samples.values()) for s in group]
    results = si_cache.solve_all(keys, args.jobs)
    contacts = len(cfg['dp'])
    # 1. impedance
    row_lim = (Z_NOM * (1 - Z_ROW_TOL), Z_NOM * (1 + Z_ROW_TOL))
    spec_lim = (Z_NOM * (1 - Z_SPEC_TOL), Z_NOM * (1 + Z_SPEC_TOL))
    imp = {}
    for side, group_keys in (('mcu', (('p', 'mcu'), ('n', 'mcu'))),
                             ('conn', (('p', 'conn', 0), ('n', 'conn', 0)))):
        rows = []
        for key, own in zip(group_keys, (1, 2)):
            partner = samples[group_keys[2 - own]]
            prof = route_si.diff_profile(samples[key], partner, results, own)
            for sample, (lo, hi, coupled) in zip(samples[key], prof):
                se = route_si.se_bounds(results[sample['key']], own - 1)
                rows.append({'net': nets[side][own - 1], 'xy': sample['xy'], 'layer': sample['layer'],
                             'kind': sample['kind'], 'len_mm': round(sample['len_mm'], 4),
                             'z_diff_lower': round(lo, 2), 'z_diff_upper': round(hi, 2),
                             'z_se_lower': round(se[0], 2), 'coupled': coupled})
        trace = [r for r in rows if r['kind'] == 'trace']
        def verdict(limits):
            above = sum(r['len_mm'] for r in trace if r['z_diff_lower'] > limits[1])
            below = sum(r['len_mm'] for r in trace if r['z_diff_upper'] < limits[0])
            inside = sum(r['len_mm'] for r in trace
                         if r['z_diff_lower'] >= limits[0] and r['z_diff_upper'] <= limits[1])
            return {'limits': limits, 'proven_above_mm': round(above, 3),
                    'proven_below_mm': round(below, 3), 'inside_mm': round(inside, 3),
                    'trace_mm': round(sum(r['len_mm'] for r in trace), 3)}
        imp[side] = {'row': verdict(row_lim), 'spec_7_1_6_1': verdict(spec_lim),
                     'coupled_mm': round(sum(r['len_mm'] for r in trace if r['coupled']), 3),
                     'z_diff_lower_range': [min(r['z_diff_lower'] for r in trace),
                                            max(r['z_diff_lower'] for r in trace)],
                     'z_se_lower_range': [min(r['z_se_lower'] for r in trace),
                                          max(r['z_se_lower'] for r in trace)],
                     'samples': rows}
        v = imp[side]['row']
        if v['inside_mm'] < v['trace_mm'] - 1e-9:
            failures.append(f'Z ({side} side): {v["proven_above_mm"]} mm proven above {row_lim[1]:.0f} ohm, '
                            f'{v["proven_below_mm"]} mm below {row_lim[0]:.0f}, of {v["trace_mm"]} mm; '
                            f'differential lower bound {imp[side]["z_diff_lower_range"][0]}-'
                            f'{imp[side]["z_diff_lower_range"][1]} ohm, coupled on {imp[side]["coupled_mm"]} mm')
        if side == 'conn':
            s = imp[side]['spec_7_1_6_1']
            if s['inside_mm'] < s['trace_mm'] - 1e-9:
                failures.append(f'USB 2.0 7.1.6.1 receptacle-to-RS line 90 ohm +-15 %: '
                                f'{s["proven_above_mm"]} mm proven above {spec_lim[1]:.1f} ohm of {s["trace_mm"]} mm')
    report['impedance'] = imp
    # 2/3. delay and skew per contact; 4. capacitance
    report['contacts'] = []
    for index in range(contacts):
        delay, bound, cap, length = {}, {}, {}, {}
        for tag, own in (('p', 1), ('n', 2)):
            parts = [(samples[(tag, 'mcu')], routes[(tag, 'mcu')]),
                     (samples[(tag, 'conn', index)], routes[(tag, 'conn', index)])]
            delay[tag] = sum(route_si.path_delay(s, results, r) for s, r in parts)
            length[tag] = sum(r['length_mm'] + route_si.via_barrel_mm(r) for _, r in parts)
            bound[tag] = length[tag] * 1e-3 * math.sqrt(route_si.ER_MAX) / xsection.C_LIGHT
            vias = sum(len(r['vias']) for _, r in parts)
            tl = sum(s['len_mm'] * 1e-3 * results[s['key']]['c_self_per_m'][
                         0 if results[s['key']]['kind'] == 'z_se' else own - 1]
                     for group in [p[0] for p in parts] + [stub_samples[tag]] for s in group)
            cap[tag] = tl + vias * VIA_C_ALLOW
        skew = abs(delay['p'] - delay['n'])
        entry = {'contacts': [wires['dp']['contacts'][index], wires['dm']['contacts'][index]],
                 'length_mm': {k: round(v, 3) for k, v in length.items()},
                 'delay_estimate_ps': {k: round(v * 1e12, 2) for k, v in delay.items()},
                 'delay_bound_ps': {k: round(v * 1e12, 2) for k, v in bound.items()},
                 'delay_limit_ps': cfg['delay_max'] * 1e12,
                 'skew_ps': round(skew * 1e12, 2), 'skew_limit_ps': SKEW_MAX * 1e12,
                 'tl_capacitance_pf': {k: round(v * 1e12, 3) for k, v in cap.items()},
                 'tl_capacitance_limit_pf': cfg['tl_c_max'] * 1e12,
                 'lumped_esd_pf': ESD_C_MAX * 1e12,
                 'lumped_left_for_rp2040_and_connector_pf': round((LUMPED_MAX - ESD_C_MAX) * 1e12, 2)}
        imbalance = abs(cap['p'] - cap['n']) + ESD_C_MATCH
        entry['capacitance_imbalance_pct'] = round(100 * imbalance / min(cap.values()), 2)
        report['contacts'].append(entry)
        label = '/'.join(f'{r}.{p}' for r, p in entry['contacts'])
        if skew > SKEW_MAX:
            failures.append(f'{label}: D+/D- skew {skew * 1e12:.1f} ps > 100 ps')
        if max(bound.values()) > cfg['delay_max']:
            failures.append(f'{label}: board delay bound {max(bound.values()) * 1e9:.3f} ns > '
                            f'{cfg["delay_max"] * 1e9:.0f} ns')
        if max(cap.values()) > cfg['tl_c_max']:
            failures.append(f'{label}: line capacitance {max(cap.values()) * 1e12:.2f} pF > '
                            f'{cfg["tl_c_max"] * 1e12:.0f} pF')
        if cfg['port'] == 'device' and imbalance >= .1 * min(cap.values()):
            failures.append(f'{label}: D+/D- capacitance differs by {entry["capacitance_imbalance_pct"]} % '
                            '(7.1.6.1 requires < 10 %)')
    # 6. transient edges on the primary contact
    lumped = {}
    picks = {'lower': {}, 'upper': {}}       # impedance bound each line is drawn at
    for tag, name, own in (('p', 'dp', 1), ('n', 'dm', 2)):
        conn_samples = samples[(tag, 'conn', 0)]
        esd_at = [board.pads[node]['at'] for node in wires[name]['esd']]
        cx = sum(x for x, _ in esd_at) / len(esd_at)
        cy = sum(y for _, y in esd_at) / len(esd_at)
        junction = min(range(len(conn_samples)), key=lambda i: math.dist(conn_samples[i]['xy'], (cx, cy)))
        stub_c = sum(s['len_mm'] * 1e-3 * results[s['key']]['c_self_per_m'][
            0 if results[s['key']]['kind'] == 'z_se' else own - 1] for s in stub_samples[tag])
        vias = len(routes[(tag, 'mcu')]['vias']) + len(routes[(tag, 'conn', 0)]['vias'])
        lumped[tag] = [('esd', ESD_C_MAX), ('stubs', stub_c), ('vias', vias * VIA_C_ALLOW)]
        for pick, name_pick in enumerate(picks):
            conn_secs_a = sections(conn_samples[:junction], results, own, pick)
            conn_secs_b = sections(conn_samples[junction:], results, own, pick)
            if conn_secs_b and sum(td for _, td in conn_secs_b) < MIN_SECTION:
                conn_secs_a, conn_secs_b = sections(conn_samples, results, own, pick), []   # ESD at the pad
            picks[name_pick][tag] = {'mcu': sections(samples[(tag, 'mcu')], results, own, pick),
                                     'conn': conn_secs_a + conn_secs_b, 'junction': len(conn_secs_a)}
    edges = []
    # The extracted impedance is a lower bound (its upper estimate is in the
    # impedance section): the edges are run at both, and both must pass.
    for name_pick, line_secs in picks.items():
        cases, edge_failures = run_edges(line_secs, lumped, rs, cfg['pull'])
        for case in cases:
            case['z_bound'] = name_pick
        edges += cases
        failures += [f'[{name_pick} Z] {f}' for f in edge_failures]
    report['edges'] = edges
    report['failures'] = failures
    report['pass'] = not failures
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1) + '\n')
    for side in ('mcu', 'conn'):
        i = imp[side]
        print(f'{side} side: Zdiff lower bound {i["z_diff_lower_range"][0]}-{i["z_diff_lower_range"][1]} ohm, '
              f'single-ended {i["z_se_lower_range"][0]}-{i["z_se_lower_range"][1]} ohm, coupled '
              f'{i["coupled_mm"]} of {i["row"]["trace_mm"]} mm')
    for c in report['contacts']:
        print(f'{c["contacts"]}: length {c["length_mm"]} mm, skew {c["skew_ps"]} ps, delay bound '
              f'{c["delay_bound_ps"]} ps, line C {c["tl_capacitance_pf"]} pF, imbalance '
              f'{c["capacitance_imbalance_pct"]} %')
    worst = [e for e in edges if e['load'] == 'fig7-9']
    print('Figure 7-9: VCRS %.3f-%.3f V, board adds <= %.3f ns, monotonic %s' % (
        min(e['vcrs_v'] for e in worst), max(e['vcrs_v'] for e in worst),
        max(e['board_adds_ns'] for e in worst), all(e['monotonic'] for e in worst)))
    print('cable cases clean: %d/%d' % (sum(e['clean_thresholds'] for e in edges if e['load'] == 'cable'),
                                        sum(1 for e in edges if e['load'] == 'cable')))
    print(f'series resistors {rs} ohm; report {out_path}')
    for failure in failures:
        print('FAIL', failure)
    print(cfg['row'], 'PASS' if report['pass'] else 'FAIL')
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
