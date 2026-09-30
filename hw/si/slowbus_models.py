#!/usr/bin/env python3
"""Buffer models for the slow-bus (SPI, CPU socket, memory) ngspice studies.

Two kinds of model, never mixed silently:

* **IBIS behavioural** (vendor files, SHA-pinned, fetched at run time): the
  [Pullup]/[Pulldown]/clamp I/V tables become ngspice B-sources, C_comp a
  capacitor, and the single rising/falling fixture waveform per edge is
  inverted to a switching coefficient Ku(t) with Kd = 1 - Ku (the standard
  one-waveform method). Every driver is replayed into its own IBIS fixture
  and must reproduce the vendor waveform (`fixture_check`) before use.
* **Bracketed behavioural** for parts whose vendor publishes no IBIS
  (RP2040, ESP32-C3, microSD cards): an ideal ramp behind a resistance,
  swept between a fast/strong and a
  slow/weak bound, with input capacitance swept between bounds. No clamps are
  modelled for these parts, which can only overstate overshoot/undershoot.
"""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CORNERS = ('typ', 'min', 'max')          # IBIS column order
_COLUMN = {'typ': 0, 'min': 1, 'max': 2}

ICE40_IBIS = ROOT / 'build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs'
ICE40_SHA256 = '8acc5bf6bc90d6956b80d5e688b7bc47a48386b127533702c8d5f328a57390c9'
# TI SLVM741A (TPD4E05U06 IBIS, [File Rev] 1.1, 12/10/2015), fetched into an
# ignored build directory like the Lattice file.
TPD_URL = 'https://www.ti.com/lit/zip/slvm741a'
TPD_ZIP_SHA256 = 'f4440ca6fc367ad1748a2ee4fc50fa77661a54f642b2c69b2a9c7529d474e1d2'

# Lattice file, commented TQ144 [Package] rows (two rows; the file does not
# say which is the HX4K's). The envelope of both rows' typ/min/max is swept.
TQ144_ENVELOPE = ({'r': .596, 'l_nh': 6.96, 'c_pf': 1.104},
                  {'r': .786, 'l_nh': 11.8, 'c_pf': 1.552})


def number(token):
    m = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)([fpnumkM]?)[A-Za-z]*', token)
    if not m:
        raise ValueError(f'invalid IBIS number {token!r}')
    scale = {'': 1, 'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
             'k': 1e3, 'M': 1e6}[m[2]]
    return float(m[1]) * scale


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class IbisModel:
    name: str
    params: dict
    tables: dict = field(default_factory=dict)       # section -> {corner: Nx2}
    fixtures: dict = field(default_factory=dict)     # 'rise'/'fall' -> dict
    vcc: dict = field(default_factory=dict)          # corner -> volts

    def table(self, section, corner):
        return self.tables.get(section, {}).get(corner)


def parse_ibis(text, name):
    """Parse one [Model] of an IBIS file (tables per corner, fixtures)."""
    text = text.replace('\r', '')
    start = re.search(r'^\[Model\]\s+' + re.escape(name) + r'\s*$', text, re.M | re.I)
    if start is None:
        raise ValueError(f'IBIS model {name} missing')
    body = text[start.end():]
    end = re.search(r'^\[Model\]', body, re.M | re.I)
    body = body[:end.start()] if end else body
    model = IbisModel(name, {})
    section, fixture = None, None
    for raw in body.splitlines():
        line = raw.split('|', 1)[0].strip()
        if not line:
            continue
        head = re.match(r'^\[([^]]+)\]\s*(.*)$', line)
        if head:
            section = re.sub(r'\s+', '_', head[1].strip().lower())
            fixture = None
            if section in ('rising_waveform', 'falling_waveform'):
                fixture = {'t': [], 'v': {c: [] for c in CORNERS}}
                model.fixtures.setdefault('rise' if section.startswith('rising') else 'fall',
                                          []).append(fixture)
            elif section == 'voltage_range':
                values = head[2].split()
                model.vcc = {c: number(values[_COLUMN[c]]) for c in CORNERS}
            continue
        if section is None:
            key = re.match(r'^(\w+)\s*=?\s*(.*)$', line)
            if key:
                model.params[key[1].lower()] = key[2].split()
            continue
        if fixture is not None:
            kv = re.match(r'^(\w+)\s*=\s*(\S+)', line)
            if kv:
                fixture[kv[1].lower()] = number(kv[2])
                continue
            fields = line.split()
            fixture['t'].append(number(fields[0]))
            for c in CORNERS:
                fixture['v'][c].append(number(fields[1 + _COLUMN[c]]))
            continue
        if section in ('pullup', 'pulldown', 'gnd_clamp', 'power_clamp'):
            fields = line.split()
            if len(fields) < 4:
                continue
            store = model.tables.setdefault(section, {c: [] for c in CORNERS})
            for c in CORNERS:
                store[c].append((number(fields[0]), number(fields[1 + _COLUMN[c]])))
    for section, store in model.tables.items():
        for c in CORNERS:
            rows = {}
            for x, y in store[c]:
                # a repeated voltage (TI's TPD4E05U06 file ends with two 0 V
                # rows, 0.18 nA apart) is accepted only if the currents agree
                if x in rows and abs(rows[x] - y) > 1e-6:
                    raise ValueError(f'{name} {section}/{c}: conflicting rows at {x} V')
                rows[x] = y
            arr = np.array(sorted(rows.items()))
            if len(arr) < 3 or np.any(np.diff(arr[:, 0]) <= 0):
                raise ValueError(f'{name} {section}/{c}: unordered or short I/V table')
            store[c] = arr
    for edge, fixtures in model.fixtures.items():
        for fixture in fixtures:
            fixture['t'] = np.array(fixture['t'])
            fixture['v'] = {c: np.array(v) for c, v in fixture['v'].items()}
        # one-waveform method: the rising edge into a load to GND and the
        # falling edge into a load to VCC (the standard IBIS pair)
        pick = [f for f in fixtures if (f['v_fixture'] == 0) == (edge == 'rise')]
        if not pick:
            raise ValueError(f'{name}: no {edge} waveform with the standard fixture')
        model.fixtures[edge] = pick[0]
    ccomp = model.params.get('c_comp')
    if not ccomp:
        raise ValueError(f'{name}: C_comp missing')
    model.params['c_comp'] = {c: number(ccomp[_COLUMN[c]]) for c in CORNERS}
    return model


def load_ice40(path=ICE40_IBIS):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != ICE40_SHA256:
        raise ValueError('Lattice iCE40 IBIS missing or changed; run hw/si/fetch_ice40_ibis.py')
    text = data.decode('ascii')
    return {name: parse_ibis(text, name) for name in ('lvc330io', 'lvc330_b3io')}


def load_tpd(cache):
    """TI TPD4E05U06 ESD array input model (C_comp and GND clamp)."""
    import io
    import urllib.request
    import zipfile
    cache = Path(cache)
    if not cache.is_file() or sha256(cache) != TPD_ZIP_SHA256:
        request = urllib.request.Request(TPD_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != TPD_ZIP_SHA256:
            raise ValueError('TI SLVM741A changed; review before use')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    with zipfile.ZipFile(cache) as archive:
        text = archive.read('TPD4E05U06_IBIS/TPD4E05U06.ibs').decode('ascii')
    if '[Component]            TPD4E05U06_DQA' not in text:
        raise ValueError('unexpected TPD4E05U06 IBIS content')
    return parse_ibis(text, 'IN_50A')


def _interp(table, x):
    return np.interp(x, table[:, 0], table[:, 1])


def device_current(model, corner, v, ku, kd):
    """IBIS current into the pin at die voltage v (the file's sign convention)."""
    vcc = model.vcc[corner]
    total = np.zeros_like(np.asarray(v, dtype=float))
    if model.table('pullup', corner) is not None:
        total = total + ku * _interp(model.table('pullup', corner), vcc - v)
    if model.table('pulldown', corner) is not None:
        total = total + kd * _interp(model.table('pulldown', corner), v)
    if model.table('gnd_clamp', corner) is not None:
        total = total + _interp(model.table('gnd_clamp', corner), v)
    if model.table('power_clamp', corner) is not None:
        total = total + _interp(model.table('power_clamp', corner), vcc - v)
    return total


def switching(model, corner, edge):
    """One-waveform Ku(t) (rise) or Kd(t) (fall), Kd = 1 - Ku, on the fixture."""
    fx = model.fixtures[edge]
    t, v = fx['t'], fx['v'][corner]
    vfix = fx.get(f'v_fixture_{corner}', fx['v_fixture'])
    dvdt = np.gradient(v, t)
    # current flowing from outside into the die pad = -(fixture + C_comp current)
    into = -((v - vfix) / fx['r_fixture'] + (fx.get('c_fixture', 0) +
                                             model.params['c_comp'][corner]) * dvdt)
    vcc = model.vcc[corner]
    ipu = _interp(model.table('pullup', corner), vcc - v)
    ipd = _interp(model.table('pulldown', corner), v)
    clamps = device_current(model, corner, v, 0.0, 0.0)
    denom = ipu - ipd
    k = (into - ipd - clamps) / np.where(np.abs(denom) < 1e-9, np.nan, denom)
    # at the start of the edge the table denominator is near its steady value
    k = np.nan_to_num(k, nan=0.0 if edge == 'rise' else 1.0)
    k = np.clip(k, 0.0, 1.0)
    if edge == 'fall':
        k = 1.0 - k                                   # return Kd
    k[0] = 0.0
    k[-1] = 1.0 if k[-1] > .9 else k[-1]
    return t, k


def _pwl_expr(control, table):
    pts = ', '.join(f'{x:.6g},{y:.6g}' for x, y in table)
    return f'pwl({control}, {pts})'


def ibis_device_lines(prefix, model, corner, die, vcc_node, ku_node=None, kd_node=None):
    """B-source current and C_comp at `die`; driver tables only if ku/kd nodes."""
    terms = []
    if ku_node and model.table('pullup', corner) is not None:
        terms.append(f'v({ku_node})*' + _pwl_expr(f'v({vcc_node})-v({die})',
                                                 model.table('pullup', corner)))
    if kd_node and model.table('pulldown', corner) is not None:
        terms.append(f'v({kd_node})*' + _pwl_expr(f'v({die})', model.table('pulldown', corner)))
    if model.table('gnd_clamp', corner) is not None:
        terms.append(_pwl_expr(f'v({die})', model.table('gnd_clamp', corner)))
    if model.table('power_clamp', corner) is not None:
        terms.append(_pwl_expr(f'v({vcc_node})-v({die})', model.table('power_clamp', corner)))
    lines = [f'C{prefix}comp {die} 0 {model.params["c_comp"][corner]:.6g}']
    if terms:
        lines.append(f'B{prefix}io {die} 0 I = ' + ' + '.join(terms))
    return lines


def ku_schedule(model, corner, edges, t_end, level=0.0):
    """PWL points of Ku(t), Kd(t) for a list of (time, 'rise'|'fall') edges.

    With no edges the buffer holds `level` (0 low, 1 high) throughout."""
    if not edges:
        return [(0.0, level), (t_end, level)], [(0.0, 1 - level), (t_end, 1 - level)]
    rise_t, ku_r = switching(model, corner, 'rise')
    fall_t, kd_f = switching(model, corner, 'fall')
    state = 'fall' if edges[0][1] == 'rise' else 'rise'   # level before 1st edge
    ku_pts, kd_pts = [], []
    level = 0.0 if state == 'fall' else 1.0
    ku_pts.append((0.0, level))
    kd_pts.append((0.0, 1.0 - level))
    for index, (t0, edge) in enumerate(edges):
        limit = edges[index + 1][0] if index + 1 < len(edges) else t_end
        tt, kk = (rise_t, ku_r) if edge == 'rise' else (fall_t, kd_f)
        keep = tt + t0 < limit - 1e-12
        for dt, k in zip(tt[keep], kk[keep]):
            ku = k if edge == 'rise' else 1.0 - k
            if dt + t0 > ku_pts[-1][0] + 1e-15:
                ku_pts.append((t0 + dt, ku))
                kd_pts.append((t0 + dt, 1.0 - ku))
        final = 1.0 if edge == 'rise' else 0.0
        if limit - 1e-13 > ku_pts[-1][0]:
            ku_pts.append((limit - 1e-13, final))
            kd_pts.append((limit - 1e-13, 1.0 - final))
    return ku_pts, kd_pts


def pwl_source(name, node, points):
    body = ' '.join(f'{t:.12g} {v:.6g}' for t, v in points)
    return f'V{name} {node} 0 PWL({body})'


# ---------------------------------------------------------------- bracketed
@dataclass(frozen=True)
class Bracket:
    """A behavioural buffer bound: ideal ramp behind r_out, input C."""
    name: str
    r_out: float          # ohm (drivers)
    t_10_90: float        # s (drivers)
    c_in: float           # F (receivers and a driver's own pad)
    l_pkg: float = 1e-9   # H
    note: str = ''


def ramp_points(edges, t_10_90, vhigh, t_end):
    """Piecewise-linear 0-100 % ramps whose 10-90 % time is t_10_90."""
    full = t_10_90 / .8
    if not edges:
        return [(0.0, 0.0), (t_end, 0.0)]
    level = 0.0 if edges[0][1] == 'rise' else vhigh
    pts = [(0.0, level)]
    for t0, edge in edges:
        target = vhigh if edge == 'rise' else 0.0
        pts += [(t0, level), (t0 + full, target)]
        level = target
    pts.append((t_end, level))
    return pts


TXB_URL = 'https://www.ti.com/lit/zip/scem518'
TXB_ZIP_SHA256 = 'f6449ce7ba2a020a115cf2af85496d4e56a0fedf8506b8d8e9384d34821c9764'


def load_txb(cache):
    """TI TXB0108 IBIS (scem518, File Rev 1.7): the 3.3 V B-port input model."""
    import urllib.request
    import zipfile
    cache = Path(cache)
    if not cache.is_file() or sha256(cache) != TXB_ZIP_SHA256:
        request = urllib.request.Request(TXB_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != TXB_ZIP_SHA256:
            raise ValueError('TI scem518 changed; review before use')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    with zipfile.ZipFile(cache) as archive:
        text = archive.read('TXB0108_IBIS/txb0108.ibs').decode('ascii')
    if '[File Rev]      1.7' not in text:
        raise ValueError('unexpected TXB0108 IBIS revision')
    return parse_ibis(text, 'TXB0108B_IN_33')


LVC125_URL = 'https://www.ti.com/lit/zip/scem270'
LVC125_ZIP_SHA256 = '4031c67134b354c5cd9a9da5cf34be57f7855bded0e815ba0ce2b04aacfb5a2c'


def _ti_zip(url, digest, cache, member):
    import urllib.request
    import zipfile
    cache = Path(cache)
    if not cache.is_file() or sha256(cache) != digest:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'{url} changed; review before use')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    with zipfile.ZipFile(cache) as archive:
        return archive.read(member).decode('ascii')


def load_lvc125(cache):
    """TI SN74LVC1G125 IBIS (scem270, File Rev 1.3): 3.3 V 3-state output.

    A same-function, same-family proxy for fitted MDD 74LVC1G125GW
    (C52140430), whose electrical behavior is not characterized here.
    These TI tables do not establish guaranteed bounds for the MDD part."""
    text = _ti_zip(LVC125_URL, LVC125_ZIP_SHA256, cache, 'sn74lvc1g125.ibs')
    return {'out': parse_ibis(text, 'LVC1G125_OUT_33'), 'in': parse_ibis(text, 'LVC1G125_IN_33'),
            'oe': parse_ibis(text, 'LVC1G125_NOE_33')}


def fixture_check(model, corner, edge):
    """Replay the vendor fixture through the converted model in ngspice.

    Accept if the 20/50/80 % crossing times agree within 50 ps and both end
    levels within 30 mV."""
    import subprocess
    import tempfile
    fx = model.fixtures[edge]
    t, v = fx['t'], fx['v'][corner]
    vfix = fx.get(f'v_fixture_{corner}', fx['v_fixture'])
    ku, kd = ku_schedule(model, corner, [(0.0, edge)], t[-1])
    lines = ['fixture', f'Vcc vcc 0 {model.vcc[corner]}', pwl_source('ku', 'ku', ku),
             pwl_source('kd', 'kd', kd)]
    lines += ibis_device_lines('d', model, corner, 'die', 'vcc', 'ku', 'kd')
    lines += [f'Rf die fix {fx["r_fixture"]}', f'Vf fix 0 {vfix}',
              f'Cf die 0 {fx.get("c_fixture", 0) + 1e-18}', f'.ic v(die)={v[0]}',
              '.control', 'set noaskquit', f'tran 2p {t[-1]} uic', 'wrdata out.dat v(die)',
              'quit', '.endc', '.end']
    with tempfile.TemporaryDirectory(prefix='cupc8-fixture-') as work:
        Path(work, 'f.cir').write_text('\n'.join(lines) + '\n')
        subprocess.run(['ngspice', '-b', 'f.cir'], cwd=work, capture_output=True, check=True)
        data = np.loadtxt(Path(work, 'out.dat'))
    ts, vs = data[:, 0], data[:, 1]

    def cross(tt, vv, frac):
        level = v[0] + frac * (v[-1] - v[0])
        above = (vv - level) * np.sign(v[-1] - v[0]) >= 0
        i = int(np.argmax(above))
        if i == 0:
            return tt[0]
        # linear interpolation between the samples either side (the vendor
        # table is sampled every 150 ps)
        return tt[i - 1] + (level - vv[i - 1]) * (tt[i] - tt[i - 1]) / (vv[i] - vv[i - 1])
    dt = max(abs(cross(ts, vs, f) - cross(t, v, f)) for f in (.2, .5, .8))
    dv = max(abs(np.interp(t[0], ts, vs) - v[0]), abs(vs[-1] - v[-1]))
    return {'max_crossing_error_ps': round(float(dt) * 1e12, 2),
            'end_level_error_mv': round(float(dv) * 1e3, 2),
            'ok': bool(dt <= 50e-12 and dv <= .03)}
