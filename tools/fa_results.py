#!/usr/bin/env python3
"""First-article (FA) measurement records -> gate status.

    python3 tools/fa_results.py                    # every gate: green / red / pending
    python3 tools/fa_results.py WC-103 MB-108      # just these; exit 0 only if all green
    python3 tools/fa_results.py --list WC-103      # what a record for WC-103 must hold

Records live in doc/hardware/fa-results/<TEST-ID>/<unit>-<YYYY-MM-DD>.json,
one file per unit per session (doc/hardware/first-article-plan.md, "Recording
results"). The limits are here, not in the records, so a record cannot pass
itself: a record carries only what was measured.

A gate is green when, for every board it covers, at least `units` distinct
units have a record holding every required measurement within its limit, and
no non-void record for the gate fails. Any failing record makes the gate red
until it is voided with a written reason ("void": "...") -- never deleted.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hw/power'))
from design import insw_ilim
RESULTS = ROOT / 'doc/hardware/fa-results'
SCHEMA = 'cupc8-fa/1'
BOARDS = ('main', 'cpu', 'gpu', 'io', 'wifi', 'storage', 'eink', 'system')
CU_ALPHA, CU_REF = 0.00393, 20.0   # hw/power/copper.py COPPER_ALPHA_PER_C, REFERENCE_C

# RP2040 cards share one shape of gate; only their budgets differ.
def _rp2040_first(i3_max, i5_max=None, core=True, extra=None):
    m = {'r_3v3_ohm': ('>=', 10), 'i_3v3_idle_ma': ('<=', i3_max)}
    if core:
        m['r_1v1_ohm'] = ('>=', 10)
    if i5_max is not None:
        m.update(r_5v_ohm=('>=', 10), i_5v_idle_ma=('<=', i5_max))
    m.update(extra or {})
    return m


def _rp2040_load(dvdd, i3_max, extra=None):
    m = {'dvdd_dc_v': ('range',) + dvdd, 'dvdd_dev_mv': ('<=', 100),
         'v_3v3_card_min_v': ('>=', 3.135), 'i_3v3_max_ma': ('<=', i3_max),
         'tc_rp2040_rise_c': ('<=', 45)}
    m.update(extra or {})
    return m


DVDD_110 = (1.067, 1.133)   # VSEL 1.10 V +-3 % (hw/power/rp2040_vreg.py VREG_VAR)
DVDD_120 = (1.164, 1.236)   # GPU: VSEL 1.20 V +-3 % (declared overclock)

# test id -> boards, units per board, required measurements {id: limit}, and
# scaling applied before the comparison: ('cu', hot C) scales a copper
# resistance from the record's board_temp_c; ('i2', current id, amps) scales
# an I^2 R temperature rise from the measured current to the rated one.
# Every number is traced to its source in first-article-plan.md.
GATES = {
    'MECH-101': dict(boards=('cpu', 'gpu', 'io', 'wifi', 'storage', 'eink', 'system'), units=2, m={
        'notch_width_mm': ('range', 1.84, 1.96), 'notch_gap_min_mm': ('>=', 0.10),
        'fingers_trimmed': ('<=', 0), 'inserts_by_hand': ('>=', 1), 'reverse_blocked': ('>=', 1),
        'continuity_max_ohm': ('<=', 1.0), 'continuity_10_cycles_max_ohm': ('<=', 1.0),
        'adjacent_shorts': ('<=', 0)}),
    'MB-107': dict(boards=('main',), units=3, m={
        'r_vbus_ohm': ('>=', 10), 'r_5vsys_ohm': ('>=', 10), 'r_3v3_ohm': ('>=', 10),
        'r_1v2_ohm': ('>=', 10), 'r_3v3stby_ohm': ('>=', 10), 'i_first_power_ma': ('<=', 250)}),
    'MB-101': dict(boards=('main',), units=3, m={
        'v_3v3_v': ('range', 3.246, 3.390), 'v_1v2_v': ('range', 1.176, 1.224),
        'ripple_3v3_mvpp': ('<=', 30)}),
    'MB-108': dict(boards=('main',), units=2, m={'r_loop_mohm': ('<=', 60), 'board_temp_c': ('range', 15, 35)},
                   scale={'r_loop_mohm': ('cu', 115.0)}),
    'MB-109': dict(boards=('main',), units=1, m={
        'i_load_a': ('>=', 2.50), 'minutes_at_load': ('>=', 15), 'dt_input_copper_c': ('<=', 20)},
                   scale={'dt_input_copper_c': ('i2', 'i_load_a', insw_ilim()[2])}),
    'MB-110': dict(boards=('main',), units=2, m={
        'r_contact_x1_max_mohm': ('<=', 30), 'r_contact_x8_max_mohm': ('<=', 30),
        'r_contact_x4_max_mohm': ('<=', 30)}),
    'MB-111': dict(boards=('main',), units=2, m={
        'ambient_c': ('>=', 38), 'i_1v2_core_ma': ('<=', 40), 'v_1v2_min_v': ('>=', 1.14)}),
    'MB-112': dict(boards=('main',), units=1, m={
        'i_5vsys_a': ('>=', 1.74), 't_efuse_rise_c': ('<=', 55), 't_buck_rise_c': ('<=', 55),
        't_ht7533_rise_c': ('<=', 55), 't_rt9013_rise_c': ('<=', 55)}),
    'MB-113': dict(boards=('main',), units=2, m={
        'ambient_room_c': ('range', 15, 35), 'ambient_hot_c': ('>=', 38), 'minutes_hot': ('>=', 30),
        'v_3v3_fall_trip_v': ('range', 3.1698, 3.2035), 'v_1v2_fall_trip_v': ('range', 1.1507, 1.1604),
        'v_3v3_fall_trip_hot_v': ('range', 3.1698, 3.2035),
        'v_1v2_fall_trip_hot_v': ('range', 1.1507, 1.1604),
        'slot_rst_held': ('>=', 1)}),
    'MB-114': dict(boards=('main',), units=5, m={
        'max16054_icc_ua': ('<=', 15), 'ht7533_ignd_ua': ('<=', 20)}),
    'CC-102': dict(boards=('cpu',), units=3, m={
        'r_3v3_ohm': ('>=', 10), 'r_1v2_ohm': ('>=', 10), 'i_3v3_idle_ma': ('<=', 40),
        'v_1v2_v': ('range', 1.176, 1.224)}),
    'CC-103': dict(boards=('cpu',), units=2, m={
        'r_feed_3v3_mohm': ('<=', 20), 'r_1v2_route_mohm': ('<=', 797), 'board_temp_c': ('range', 15, 35)},
                   scale={'r_1v2_route_mohm': ('cu', 100.0)}),
    'CC-104': dict(boards=('cpu',), units=2, m={
        'ambient_c': ('>=', 38), 'i_1v2_core_ma': ('<=', 40), 'v_1v2_far_min_v': ('>=', 1.14),
        't_rt9013_rise_c': ('<=', 55)}),
    'CC-105': dict(boards=('cpu',), units=5, m={
        'c22_1v2_uf': ('>=', 1.88), 'esr_c22_mohm': ('>=', 5), 'c21_3v3_uf': ('>=', 1.0)}),
    'GC-102': dict(boards=('gpu',), units=3, m={
        'minutes': ('>=', 60), 'ambient_min_c': ('>=', 38), 'glitches': ('<=', 0), 'dropouts': ('<=', 0),
        'lockups': ('<=', 0), 'tc_rp2040_c': ('<=', 85)}),
    'GC-103': dict(boards=('gpu',), units=3, m=_rp2040_first(145, 95, extra={
        'v_hdmi_5v_v': ('range', 4.8, 5.3)})),
    'GC-104': dict(boards=('gpu',), units=2, m=_rp2040_load(DVDD_120, 145)),
    # HDMI hot-plug detect and DDC/EDID with a real monitor (co-sim waivers for GPU DDC/HPD, David 2026-09-29):
    # HPD low unplugged (R21 33k to GND), high through the 22k/33k divider from the sink's ~5 V (RP2040 VIH
    # min 2.0 V, IOVDD 3.6 V max); the DDC lines idle high on both sides of the level shifters (2k2 to
    # HDMI +5V 4.8-5.3 V less the sink's load, 4k7 to 3V3); the monitor's 128-byte EDID base block reads
    # through the card: header 00 FF FF FF FF FF FF 00 and a zero byte sum (VESA E-EDID).
    'GC-105': dict(boards=('gpu',), units=2, m={
        'hpd_off_v': ('<=', 0.4), 'hpd_on_v': ('range', 2.0, 3.6),
        'ddc_idle_5v_side_v': ('range', 4.5, 5.3), 'ddc_idle_3v3_side_v': ('range', 3.0, 3.6),
        'edid_bytes_read': ('>=', 128), 'edid_header_ok': ('>=', 1), 'edid_checksum_ok': ('>=', 1)}),
    'IC-102': dict(boards=('io',), units=3, m=_rp2040_first(50, 800, extra={
        'v_kbd_vbus_v': ('range', 4.40, 5.5)})),
    'IC-103': dict(boards=('io',), units=2, m=_rp2040_load(DVDD_110, 50)),
    'IC-104': dict(boards=('io',), units=2, m={
        'v_vbus_500ma_min_v': ('>=', 4.40), 'i_slot_5v_500ma_a': ('<=', 0.80), 'i_port_trip_a': ('>=', 0.50),
        'fault_flag_on_short': ('>=', 1), 't_boost_rise_c': ('<=', 55), 't_sy6280_rise_c': ('<=', 55)}),
    'WC-102': dict(boards=('wifi',), units=3, m={
        'r_5v_ohm': ('>=', 10), 'r_3v3_ohm': ('>=', 10), 'i_5v_idle_ma': ('<=', 340),
        'v_3v3_v': ('range', 3.227, 3.411)}),
    'WC-103': dict(boards=('wifi',), units=10, part_lcsc='C602037', single_lot=True, m={
        'c_5v5_uf': ('>=', 7.80), 'c_3v6_uf': ('>=', 11.16), 'esr_max_mohm': ('<=', 150)}),
    'WC-104': dict(boards=('wifi',), units=2, m={
        'r_ret_buck_mohm': ('<=', 1000), 'r_ret_esp_mohm': ('<=', 1000)}),
    'WC-105': dict(boards=('wifi',), units=2, m={
        'ambient_c': ('>=', 38), 'i3_bound_a': ('<=', 0.50),
        'v_3v3_burst_min_v': ('>=', 3.074), 'v_3v3_burst_max_v': ('<=', 3.537)}),
    'WC-106': dict(boards=('wifi',), units=2, m={'minutes_tx': ('>=', 30), 't_u2_board_rise_c': ('<=', 50)}),
    'SC-101': dict(boards=('storage',), units=3, m=_rp2040_first(150)),
    'SC-102': dict(boards=('storage',), units=2, m=_rp2040_load(DVDD_110, 150)),
    'EC-101': dict(boards=('eink',), units=3, m=_rp2040_first(95)),
    'EC-102': dict(boards=('eink',), units=2, m=_rp2040_load(DVDD_110, 95, extra={
        'v_panel_min_v': ('>=', 2.3)})),
    'YC-101': dict(boards=('system',), units=3, m=_rp2040_first(50)),
    'YC-102': dict(boards=('system',), units=2, m=_rp2040_load(DVDD_110, 50)),
}


def load(path):
    """One validated record, or ValueError naming the file and the fault."""
    try:
        rec = json.loads(Path(path).read_text())
    except json.JSONDecodeError as e:
        raise ValueError('%s: not JSON (%s)' % (path, e))
    for key in ('schema', 'test', 'board', 'unit', 'date', 'measurements'):
        if key not in rec:
            raise ValueError('%s: missing %r' % (path, key))
    if rec['schema'] != SCHEMA:
        raise ValueError('%s: schema %r, expected %r' % (path, rec['schema'], SCHEMA))
    gate = GATES.get(rec['test'])
    if gate is None:
        raise ValueError('%s: unknown test %r' % (path, rec['test']))
    if Path(path).parent.name != rec['test']:
        raise ValueError('%s: filed under %s, record says %s' % (path, Path(path).parent.name, rec['test']))
    if rec['board'] not in gate['boards']:
        raise ValueError('%s: board %r not covered by %s' % (path, rec['board'], rec['test']))
    identity = identity_problems(rec)
    if identity:
        raise ValueError('%s: %s' % (path, '; '.join(identity)))
    for mid, value in rec['measurements'].items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('%s: measurement %r is not a number' % (path, mid))
    return rec


def value(rec, mid):
    """The measurement as the gate compares it (copper scaled to its hot corner)."""
    v = rec['measurements'][mid]
    rule = GATES[rec['test']].get('scale', {}).get(mid)
    if rule and rule[0] == 'cu':    # copper resistance, linear in temperature (copper.py, 20 C reference)
        t = rec['measurements']['board_temp_c']
        v *= (1 + CU_ALPHA * (rule[1] - CU_REF)) / (1 + CU_ALPHA * (t - CU_REF))
    elif rule and rule[0] == 'i2':  # self-heating rise, proportional to I^2 R
        v *= (rule[2] / rec['measurements'][rule[1]]) ** 2
    return v


def within(v, limit):
    op = limit[0]
    if op == '<=':
        return v <= limit[1]
    if op == '>=':
        return v >= limit[1]
    return limit[1] <= v <= limit[2]


def identity_problems(rec):
    """Reject unbound capacitor records before counting their numeric results."""
    gate = GATES[rec['test']]
    problems = []
    expected = gate.get('part_lcsc')
    if expected and rec.get('part_lcsc') != expected:
        problems.append('part_lcsc must be %s (actual fitted part)' % expected)
    if gate.get('single_lot') and (not isinstance(rec.get('lot'), str) or not rec['lot'].strip()):
        problems.append('lot must identify the sampled fitted-part lot')
    return problems


def verdict(rec):
    """('pass'|'fail'|'incomplete', [problems])."""
    gate = GATES[rec['test']]
    identity = identity_problems(rec)
    if identity:
        return 'fail', identity
    missing = [m for m in gate['m'] if m not in rec['measurements']]
    if missing:
        return 'incomplete', ['missing ' + m for m in missing]
    bad = ['%s = %.4g outside %s' % (m, value(rec, m), lim) for m, lim in gate['m'].items()
           if not within(value(rec, m), lim)]
    return ('fail' if bad else 'pass'), bad


def status(test, records):
    """('green'|'red'|'pending', [lines])."""
    gate = GATES[test]
    live = [r for r in records if r['test'] == test and not r.get('void')]
    lines, red = [], False
    passed = {b: set() for b in gate['boards']}
    lots = {b: {} for b in gate['boards']}
    for rec in live:
        v, problems = verdict(rec)
        if v == 'fail':
            red = True
        if v == 'pass':
            passed[rec['board']].add(rec['unit'])
            if gate.get('single_lot'):
                lots[rec['board']].setdefault(rec['lot'], set()).add(rec['unit'])
        lines.append('  %s %s %s: %s%s' % (rec['board'], rec['unit'], rec['date'], v,
                                          ('; ' + '; '.join(problems)) if problems else ''))
    if gate.get('single_lot'):
        # Ten parts from mixed lots do not qualify any single fitted-part lot.
        passed = {b: max(lots[b].values(), key=len, default=set()) for b in gate['boards']}
    short = ['%s %d/%d%s' % (b, len(u), gate['units'], ' from one lot' if gate.get('single_lot') else '')
             for b, u in passed.items() if len(u) < gate['units']]
    if red:
        return 'red', lines
    if short:
        return 'pending', lines + ['  units passing: ' + ', '.join(short)]
    return 'green', lines


def records(directory=RESULTS):
    return [load(p) for p in sorted(Path(directory).glob('*/*.json'))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tests', nargs='*', help='gate ids (default: all)')
    ap.add_argument('--dir', type=Path, default=RESULTS)
    ap.add_argument('--list', action='store_true', help='print the required measurements')
    args = ap.parse_args(argv)
    tests = args.tests or sorted(GATES)
    unknown = [t for t in tests if t not in GATES]
    if unknown:
        ap.error('unknown gate(s): ' + ', '.join(unknown))
    if args.list:
        for t in tests:
            g = GATES[t]
            print('%s: boards %s, %d unit(s) each' % (t, ', '.join(g['boards']), g['units']))
            if g.get('part_lcsc'):
                print('  part_lcsc must be %s; nonempty lot required; units from one lot' % g['part_lcsc'])
            for m, lim in g['m'].items():
                rule = g.get('scale', {}).get(m)
                note = ''
                if rule and rule[0] == 'cu':
                    note = ' (copper, scaled to %.0f C from board_temp_c)' % rule[1]
                elif rule:
                    note = ' (scaled by (%.3f A / %s)^2)' % (rule[2], rule[1])
                print('  %-30s %s%s' % (m, ' '.join(str(x) for x in lim), note))
        return 0
    recs = records(args.dir) if args.dir.exists() else []
    ok = True
    for t in tests:
        s, lines = status(t, recs)
        ok &= s == 'green'
        print('%-9s %s' % (t, s))
        for line in lines:
            print(line)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
