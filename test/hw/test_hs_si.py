#!/usr/bin/env python3
"""Focused checks for GC-007 (TMDS) and IC-007/YC-007 (USB full speed) tools.

    python3 test/hw/test_hs_si.py [--row GC-007|IC-007|YC-007] [--gpu ...] [--io ...] [--system ...]

The builds are only read; mutated copies go to a temporary directory.  Cut
solves are shared with the row commands through build/si/cache, so this is
quick once a row command has run on the same board.

1. TMDS S-parameter engine: a matched 100 ohm line meets the budget, an 80 ohm
   line (10 % beyond the row's own tolerance) and a heavily loaded line fail,
   and a lossy line loses more than a short one.
2. The series resistor comes from the netlist: all eight are read, a mixed
   pack fails, and the DVI 1.0 swing gate passes 270/360 ohm and fails 1 k and
   150 ohm (a wrong resistor).
3. USB edge engine: ideal 90 ohm lines give clean edges (VCRS 1.3-2.0 V,
   monotonic, no threshold re-crossing through the 26 ns cable) at a host and
   a device port, and a badly mismatched line is caught.
4. The RS gate: 27 ohm passes, 33 or 100 ohm fails.
5. Mutations that must fail on the routed boards: a wrong TMDS resistor
   (swing), a wrong USB resistor, an opened TMDS P track and an opened USB D-
   track (broken pair: the route is not connected).
"""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/si'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from kicadgen import dump, find1, parse  # noqa: E402
import tmds_si  # noqa: E402
import usb_fs_si  # noqa: E402


def expect_error(text, call):
    try:
        call()
    except ValueError as error:
        assert text in str(error), str(error)
        return
    raise AssertionError(f'expected an error containing {text!r}')


def opened(board_path, net, out):
    tree = parse(board_path.read_text())
    tracks = [item for item in tree[1:] if isinstance(item, list) and item and
              item[0] == 'segment' and find1(item, 'net') and find1(item, 'net')[1] == net]
    tree.remove(max(tracks, key=lambda t: math.dist(*(tuple(map(float, find1(t, k)[1:3]))
                                                       for k in ('start', 'end')))))
    out.write_text(dump(tree) + '\n')
    return out


def set_value(netlist, ref, value, out):
    """Copy of a netlist with component `ref` set to `value`."""
    text = netlist.read_text()
    start = text.index(f'(ref "{ref}")')
    at = text.index('(value "', start)
    end = text.index('")', at)
    out.write_text(text[:at] + f'(value "{value}' + text[end:])
    return out


def set_all(netlist, refs, value, out):
    text = netlist.read_text()
    for ref in refs:
        start = text.index(f'(ref "{ref}")')
        at = text.index('(value "', start)
        end = text.index('")', at)
        text = text[:at] + f'(value "{value}' + text[end:]
    out.write_text(text)
    return out


def run_main(module, argv):
    saved = sys.argv
    sys.argv = [module.__file__] + argv
    try:
        return module.main()
    finally:
        sys.argv = saved


def tmds_engine():
    freqs = [tmds_si.F_MAX * k / 63 for k in range(1, 64)]

    def worst(sections, shunts=None):
        rl, il = -math.inf, 0.0
        for f in freqs:
            s11, s21 = tmds_si.sparams(sections, shunts or {}, f)
            rl = max(rl, 20 * math.log10(abs(s11) + 1e-12))
            il = min(il, 20 * math.log10(abs(s21)))
        return rl, il
    delay = 5.9e-9        # s/m, about 1.77 in FR-4 stripline/microstrip (Dk ~ 3.5 effective)
    good_rl, good_il = worst([(100, delay, 20e-3)])
    assert good_rl < -35, good_rl        # matched: only the loss-induced residual
    assert good_il > tmds_si.IL_MIN_DB, good_il
    low_rl, _ = worst([(80, delay, 20e-3)])
    assert low_rl > tmds_si.RL_MAX_DB, low_rl          # 80 ohm line breaks the return-loss budget
    edge_rl, _ = worst([(90, delay, 20e-3)])
    assert edge_rl < tmds_si.RL_MAX_DB, edge_rl        # 90 ohm (the row's own edge) is inside it
    load_rl, _ = worst([(100, delay, 10e-3), (100, delay, 10e-3)], {1: 3e-12})
    assert load_rl > tmds_si.RL_MAX_DB, load_rl        # 3 pF at 1.26 GHz is out
    esd_rl, _ = worst([(100, delay, 10e-3), (100, delay, 10e-3)], {1: tmds_si.ESD_CL / 2 + tmds_si.ESD_CROSS})
    assert tmds_si.RL_MAX_DB < esd_rl < tmds_si.RL_ESD_MAX_DB, esd_rl   # ESD array: inside its own budget only
    _, short_il = worst([(100, delay, 5e-3)])
    _, long_il = worst([(100, delay, 200e-3)])
    assert long_il < short_il < 0, (short_il, long_il)
    print(f'TMDS engine: 100 ohm {good_rl:.0f} dB, 90 ohm {edge_rl:.1f} dB, 80 ohm {low_rl:.1f} dB, '
          f'ESD {esd_rl:.1f} dB, 3 pF {load_rl:.1f} dB (limit {tmds_si.RL_MAX_DB:.2f})')


def tmds_netlist(gpu, tmp):
    net = gpu / 'gpu.net'
    wiring, ohms = tmds_si.lanes(net, 'U1', 'J2')
    assert len(wiring) == 8 and ohms > 0
    refs = sorted({w['resistor'].split('.')[0] for w in wiring.values()})
    # the value follows the netlist: any value the pack has is read back
    for value in ('270', '360', '1k'):
        _, read = tmds_si.lanes(set_all(net, refs, value, tmp / 'gpu-r.net'), 'U1', 'J2')
        assert read == tmds_si.route_si.ohms(value), (value, read)
    expect_error('resistors differ', lambda: tmds_si.lanes(set_value(net, refs[0], '1k', tmp / 'gpu-mixed.net'),
                                                          'U1', 'J2'))
    # DVI 1.0 4.2 swing: both shipped values pass, a wrong one does not
    for good in (270.0, 360.0):
        assert not tmds_si.swing_report(good)['failures'], good
    assert tmds_si.swing_report(1000.0)['failures']
    assert tmds_si.swing_report(150.0)['failures']
    swing = tmds_si.swing_report(360.0)
    print(f'TMDS swing at {ohms:g} ohm in the netlist; 360 ohm: >= {swing["min_mv"]} mV, '
          f'<= {swing["max_pp_mv"]} mV pp')


def usb_engine():
    for tfr in usb_fs_si.TFR:
        ramp = usb_fs_si.ramp_for_tfr(tfr, 28.0, usb_fs_si.CL_TEST)
        assert ramp > 0
    # a 44 ohm driver into 50 pF cannot go faster than 4.8 ns: fastest edge is used
    assert usb_fs_si.ramp_for_tfr(4e-9, 44.0, 50e-12) <= .5e-9
    lumped = {t: [('esd', usb_fs_si.ESD_C_MAX), ('stubs', .2e-12), ('vias', 0)] for t in 'pn'}
    ideal = {t: {'mcu': [(90.0, .05e-9)], 'conn': [(90.0, .05e-9), (90.0, .05e-9)], 'junction': 1}
             for t in 'pn'}
    for pull in ('down', 'up'):
        edges, failures = usb_fs_si.run_edges(ideal, lumped, {'p': 27.0, 'n': 27.0}, pull)
        assert not failures, failures
        fig = [e for e in edges if e['load'] == 'fig7-9']
        assert fig and all(1.3 <= e['vcrs_v'] <= 2.0 and e['monotonic'] for e in fig)
        assert all(e['clean_thresholds'] for e in edges if e['load'] == 'cable')
    # the gate can fail: a 5 pF-scale ideal line becomes a 300 pF blob at the junction
    heavy = {t: [('esd', 300e-12), ('stubs', 0), ('vias', 0)] for t in 'pn'}
    _, failures = usb_fs_si.run_edges(ideal, heavy, {'p': 27.0, 'n': 27.0}, 'down')
    assert failures, 'a 300 pF junction must fail the edge gate'
    # RS gate
    assert not usb_fs_si.series_failures({'p': 27.0, 'n': 27.0})
    assert usb_fs_si.series_failures({'p': 33.0, 'n': 27.0})
    assert usb_fs_si.series_failures({'p': 27.0, 'n': 100.0})
    print(f'USB edge engine: ideal 90 ohm lines clean at both port types; 300 pF junction fails '
          f'({len(failures)} cases)')


def tmds_mutations(gpu, tmp):
    net = gpu / 'gpu.net'
    wiring, _ = tmds_si.lanes(net, 'U1', 'J2')
    refs = sorted({w['resistor'].split('.')[0] for w in wiring.values()})
    # a wrong TMDS resistor: the whole tool comes back red, on the swing
    bad = set_all(net, refs, '1k', tmp / 'gpu-1k.net')
    status = run_main(tmds_si, ['--build', str(gpu), '--netlist', str(bad), '--no-evidence',
                                '--out', str(tmp / 'gc-bad.json')])
    report = json.loads((tmp / 'gc-bad.json').read_text())
    assert status == 1 and not report['pass']
    assert any('swing' in f for f in report['failures']), report['failures']
    # broken pair: an opened routed track is caught before any solve
    broken = opened(gpu / 'gpu.kicad_pcb', '/HD_D0P', tmp / 'gpu-open.kicad_pcb')
    expect_error('not connected', lambda: run_main(tmds_si, [
        '--build', str(gpu), '--board', str(broken), '--no-evidence', '--out', str(tmp / 'x.json')]))
    print('TMDS mutations fail as required: 1k series resistors, opened D0P')


def usb_mutations(board, build, resistor, net, tmp):
    # the real board's resistors pass the RS gate, so the failure below is the mutation's
    wires = usb_fs_si.wiring(build / f'{board}.net', usb_fs_si.BOARDS[board])
    assert not usb_fs_si.series_failures({'p': wires['dp']['ohms'], 'n': wires['dm']['ohms']})
    # wrong USB series resistor
    bad = set_value(build / f'{board}.net', resistor, '100', tmp / f'{board}-100.net')
    out = tmp / f'{board}-bad.json'
    status = run_main(usb_fs_si, [board, '--build', str(build), '--netlist', str(bad),
                                  '--no-evidence', '--out', str(out)])
    report = json.loads(out.read_text())
    assert status == 1 and any('series resistor' in f for f in report['failures']), report['failures']
    # broken pair: an opened D- track is caught before any solve
    broken = opened(build / f'{board}.kicad_pcb', net, tmp / f'{board}-open.kicad_pcb')
    expect_error('not connected', lambda: run_main(usb_fs_si, [
        board, '--build', str(build), '--board-file', str(broken), '--no-evidence',
        '--out', str(tmp / 'y.json')]))
    print(f'USB ({board}) mutations fail as required: {resistor} = 100 ohm, opened {net}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--row', choices=('GC-007', 'IC-007', 'YC-007'), help='default: all three')
    parser.add_argument('--gpu', type=Path, default=ROOT / 'build/hw/gpu')
    parser.add_argument('--io', type=Path, default=ROOT / 'build/hw/io')
    parser.add_argument('--system', type=Path, default=ROOT / 'build/hw/system')
    args = parser.parse_args()
    rows = (args.row,) if args.row else ('GC-007', 'IC-007', 'YC-007')
    if 'GC-007' in rows:
        tmds_engine()
    if 'IC-007' in rows or 'YC-007' in rows:
        usb_engine()
    with tempfile.TemporaryDirectory(prefix='cupc8-hs-si-') as tmp:
        tmp = Path(tmp)
        if 'GC-007' in rows:
            tmds_netlist(args.gpu, tmp)
            tmds_mutations(args.gpu, tmp)
        if 'IC-007' in rows:
            usb_mutations('io', args.io, 'R15', '/USB_CONN_DM', tmp)
        if 'YC-007' in rows:
            usb_mutations('system', args.system, 'R2', '/USB_DM', tmp)
    print('all high-speed SI checks pass:', ', '.join(rows))


if __name__ == '__main__':
    main()
