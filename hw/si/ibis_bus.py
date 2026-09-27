#!/usr/bin/env python3
"""IBIS-derived ngspice transient subset for slot SCK and CPU socket.

The Lattice file is vendor data, fetched separately. Its 50-ohm/25-pF
waveform fixture is de-embedded to a linear Thevenin source and checked by
re-simulating that fixture. This is an approximation, not a full nonlinear
IBIS buffer conversion. Without routed main-board copper and a resolved
TQ144 package assignment the result is deliberately diagnostic only.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_ice40_ibis import verify

IBIS = ROOT / 'build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs'
MODELS = ('lvc330io', 'lvc330_b3io')
CORNER = {'typ': 0, 'min': 1, 'max': 2}
VDD = {'typ': 3.30, 'min': 3.14, 'max': 3.47}
VIH, VIL = 2.0, 0.8  # vendor [Model] VinH/VinL
FIXTURE_R, FIXTURE_C = 50.0, 25e-12
TRACE_Z0, TRACE_PS_PER_MM = 50.0, 7.0


def number(token):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)([munp]?)(?:[A-Za-z]*)', token)
    if not match:
        raise ValueError(f'invalid IBIS number: {token}')
    return float(match[1]) * {'': 1, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12}[match[2]]


def model_sections(data, name):
    text = data.decode('ascii').replace('\r', '')
    start = re.search(r'^\[Model\]\s+' + re.escape(name) + r'\s*$', text, re.M)
    if start is None:
        raise ValueError(f'vendor model {name} missing')
    body = text[start.end():]
    end = re.search(r'^\[Model\]', body, re.M)
    if end:
        body = body[:end.start()]
    sections, key = {}, None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith('|') or not line:
            continue
        section = re.match(r'^\[([^]]+)\]\s*$', line)
        if section:
            key = section[1]
            sections[key] = []
        elif key:
            sections[key].append(line)
    return sections


def table(sections, section, corner):
    rows = []
    for line in sections[section]:
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            rows.append((number(fields[0]), number(fields[1 + CORNER[corner]])))
        except ValueError:
            continue  # fixture metadata, not tabular data
    if len(rows) < 20 or any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError(f'{section}/{corner}: insufficient or unordered IBIS points')
    return np.array(rows)


def source(sections, edge, corner):
    curve = table(sections, 'Rising Waveform' if edge == 'rise' else 'Falling Waveform', corner)
    t, v = curve[:, 0], curve[:, 1]
    supply = VDD[corner]
    final = v[-1]
    resistance = ((supply - final) * FIXTURE_R / final if edge == 'rise' else
                  final * FIXTURE_R / (supply - final))
    if not 5 < resistance < 80:
        raise ValueError(f'{edge}/{corner}: implausible IBIS fixture output resistance {resistance}')
    static = table(sections, 'Pullup' if edge == 'rise' else 'Pulldown', corner)
    x = supply - final if edge == 'rise' else final
    stated_current = -np.interp(x, static[:, 0], static[:, 1]) if edge == 'rise' else np.interp(x, static[:, 0], static[:, 1])
    fixture_current = final / FIXTURE_R if edge == 'rise' else (supply - final) / FIXTURE_R
    if abs(stated_current - fixture_current) > .2 * fixture_current:
        raise ValueError(f'{edge}/{corner}: waveform endpoint disagrees with vendor I/V table')
    dv = np.gradient(v, t)
    load_current = FIXTURE_C * dv + (v / FIXTURE_R if edge == 'rise' else (v - supply) / FIXTURE_R)
    drive = v + resistance * load_current
    # The first few waveform samples contain small vendor extraction offsets.
    drive[0] = 0 if edge == 'rise' else supply
    return t, v, drive, resistance


def run_spice(source_t, drive, resistance, fixture=False, slots=6, length_mm=120,
              package_nh=10.53, package_pf=1.55, receiver_pf=15.0,
              fixture_vref=0.0):
    with tempfile.TemporaryDirectory(prefix='cupc8-ibis-') as temporary:
        work = Path(temporary)
        deck = work / 'bus.cir'
        result = work / 'wave.dat'
        pwl = ' '.join(f'{t:.12g} {v:.9g}' for t, v in zip(source_t, drive))
        lines = ['IBIS-derived CUPC8 diagnostic', f'Vdrive src 0 PWL({pwl})',
                 f'Rout src drv {resistance:.9g}']
        nodes = []
        if fixture:
            lines += [f'Vref rail 0 {fixture_vref:.9g}', 'Rfixture drv rail 50', 'Cfixture drv 0 25p']
            nodes = ['drv']
        else:
            lines += [f'Rterm drv pkg 33', f'Lpkg pkg launch {package_nh:.9g}n',
                      f'Cpkg launch 0 {package_pf:.9g}p']
            previous = 'launch'
            step = length_mm / slots
            for i in range(slots):
                node = f'bus{i+1}'
                lines.append(f'T{i+1} {previous} 0 {node} 0 Z0={TRACE_Z0} TD={step * TRACE_PS_PER_MM:.9g}p')
                lines.append(f'Cload{i+1} {node} 0 {receiver_pf:.9g}p')
                nodes.append(node)
                previous = node
        lines += ['.control', 'set noaskquit', 'tran 0.05n 45n',
                  f'wrdata {result} ' + ' '.join(f'v({n})' for n in nodes),
                  'quit', '.endc', '.end']
        deck.write_text('\n'.join(lines) + '\n')
        run = subprocess.run(['ngspice', '-b', str(deck)], cwd=work, capture_output=True, text=True)
        if run.returncode or not result.is_file():
            raise RuntimeError(f'ngspice transient failed: {run.stdout[-1200:]} {run.stderr[-1200:]}')
        data = np.loadtxt(result)
        if data.ndim != 2 or data.shape[1] != 2 * len(nodes) or not np.all(np.isfinite(data)):
            raise RuntimeError('ngspice produced incomplete transient data')
        return data[:, 0], data[:, 1::2]


def evaluate(t, outputs, edge, supply):
    settle = 30e-9
    samples = []
    for index, wave in enumerate(outputs.T):
        late = wave[t >= settle]
        if not len(late):
            raise ValueError('transient ended before settling')
        crossed = np.flatnonzero(wave >= VIH if edge == 'rise' else wave <= VIL)
        first = int(crossed[0]) if len(crossed) else len(wave)
        after = wave[first:]
        stable = bool(len(after) and (np.all(after >= VIH) if edge == 'rise' else np.all(after <= VIL)))
        samples.append({'node': index + 1, 'min_v': round(float(np.min(wave)), 4),
                        'max_v': round(float(np.max(wave)), 4),
                        'first_threshold_ns': round(float(t[first] * 1e9), 4) if len(after) else None,
                        'post_cross_min_v': round(float(np.min(after)), 4) if len(after) else None,
                        'post_cross_max_v': round(float(np.max(after)), 4) if len(after) else None,
                        'late_min_v': round(float(np.min(late)), 4),
                        'late_max_v': round(float(np.max(late)), 4),
                        'threshold_stable': stable})
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, default=IBIS)
    parser.add_argument('--top', type=Path, help='schematic-derived co-simulation manifest to validate 33-ohm sources')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/hw/si/ibis-bus-diagnostic.json')
    args = parser.parse_args()
    data = args.ibis.read_bytes()
    digest = verify(data)
    report = {'source_sha256': digest, 'models': MODELS, 'scope': 'diagnostic IBIS-derived linear source, assumed copper',
              'routed_evidence': False, 'package_assignment_confirmed': False, 'cases': []}
    if args.top:
        top_bytes = args.top.read_bytes()
        top = json.loads(top_bytes)
        paths = top.get('paths', [])
        for slot in range(1, 7):
            target = f'main.J{10+slot}.B13'
            matches = [p for p in paths if p.get('to') == target and
                       p.get('from', '').startswith('main.U7.') and p.get('ohms') == 33]
            if len(matches) != 1:
                raise ValueError(f'{target}: netlist top lacks unique 33-ohm SCK source path')
        cpu = [p for p in paths if p.get('from', '').startswith('cpu.U1.') and
               p.get('to', '').startswith('cpu.J1.') and p.get('ohms') == 33]
        if len(cpu) != 31:
            raise ValueError(f'CPU card: expected 31 series-terminated driver paths, got {len(cpu)}')
        report['top_sha256'] = hashlib.sha256(top_bytes).hexdigest()
        report['top_routed_signals'] = bool(top.get('runtime', {}).get('routed_top'))
    for model in MODELS:
        sections = model_sections(data, model)
        for corner in CORNER:
            for edge in ('rise', 'fall'):
                t, fixture_v, drive, resistance = source(sections, edge, corner)
                ft, fo = run_spice(t, drive, resistance, fixture=True,
                                   fixture_vref=VDD[corner] if edge == 'fall' else 0)
                fit = np.interp(t, ft, fo[:, 0])
                fixture_error = float(np.max(np.abs(fit - fixture_v)))
                if fixture_error > .08:
                    raise ValueError(f'{model}/{corner}/{edge}: IBIS fixture replay differs by {fixture_error:.3f} V')
                for topology, slots, length, loads in (('cpu_socket', 1, 120, (5.0, 15.0)),
                                                       ('six_slot_sck', 6, 180, (15.0, 30.0))):
                    for package in (7.98, 10.53):
                        for receiver_pf in loads:
                            bt, bo = run_spice(t, drive, resistance, slots=slots, length_mm=length,
                                               package_nh=package, receiver_pf=receiver_pf)
                            report['cases'].append({'model': model, 'topology': topology,
                                                    'corner': corner, 'edge': edge,
                                                    'assumed_length_mm': length,
                                                    'assumed_receiver_pf': receiver_pf,
                                                    'commented_tq144_l_nh': package,
                                                    'output_resistance_ohm': round(resistance, 3),
                                                    'fixture_max_error_v': round(fixture_error, 5),
                                                    'receivers': evaluate(bt, bo, edge, VDD[corner])})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    failures = [case for case in report['cases'] if not all(n['threshold_stable'] for n in case['receivers'])]
    print(f'{len(report["cases"])} ngspice bus transients, {len(failures)} threshold-instability cases; '
          f'IBIS fixture error <= {max(c["fixture_max_error_v"] for c in report["cases"]):.4f} V')
    print('DIAGNOSTIC ONLY: assumed line lengths/loads; TQ144 package assignment unresolved; MB-007/CC-007 remain pending')


if __name__ == '__main__':
    main()
