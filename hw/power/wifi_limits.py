#!/usr/bin/env python3
"""Sensitivity limits for the routed Wi-Fi card's unbounded ESR/contact terms.

This is diagnostic: the fitted capacitors have no guaranteed ESR maximum,
and the saved KiCad fill does not establish pad/contact resistance. A passing
scenario cannot clear WC-005. ngspice output stays in this checkout's build.
"""
import argparse
from pathlib import Path

import buck
import design as d
import wifi_board
import wifi_ground


def rail_extrema(wave):
    t, vout, _, _ = wave
    nominal = d.buck_vout(d.WIFI_BUCK_R1, d.WIFI_BUCK_R2)
    low_corner = d.wifi_vout_range()[0] / nominal
    high_corner = d.wifi_vout_range()[1] / nominal
    return (min(buck.window(t, vout, buck.T_STEP, buck.T_REL)) * low_corner,
            max(vout) * high_corner)


def within_limits(extrema):
    minimum, maximum = extrema
    return minimum >= d.ESP32_VDD_MIN and maximum <= d.ESP32_VDD_MAX


def run(out, esr, contact, tag):
    circuit = wifi_board.topology(out / 'wifi.net')
    r5, r3 = wifi_board.routes(out / 'wifi.kicad_pcb', out / 'fab/order.json', circuit)
    rgnd = wifi_ground.compare(out / 'wifi.kicad_pcb')[0]
    wave = buck.run_wifi('worst', r5, r3, rgnd, esr=esr, r_contact=contact, tag=tag)
    return rail_extrema(wave)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, help='completed Wi-Fi build; read only')
    args = parser.parse_args()
    out = args.out.resolve()
    # Each point varies one unknown; the other stays at the documented
    # sensitivity scenario. These are modeled margins, not part guarantees.
    for label, points in (('ESR per C1/C2/C3 (ohm)',
                           [(0.1, 0), (0.15, 0), (0.18, 0), (0.3, 0), (0.5, 0)]),
                          ('extra module return contact (ohm)',
                           [(0.1, 0), (0.1, 0.2), (0.1, 0.33), (0.1, 0.4)])):
        print(label, flush=True)
        for esr, contact in points:
            tag = '_esr%d_contact%d' % (round(esr * 1000), round(contact * 1000))
            vmin, vmax = run(out, esr, contact, tag)
            print('  %s ESR %.3f, contact %.3f: min %.3f V (%+.3f vs %.1f); '
                  'max %.3f V (%+.3f vs %.1f)' %
                  ('within modeled limits' if within_limits((vmin, vmax)) else 'outside modeled limits',
                   esr, contact, vmin, vmin - d.ESP32_VDD_MIN, d.ESP32_VDD_MIN,
                   vmax, d.ESP32_VDD_MAX - vmax, d.ESP32_VDD_MAX), flush=True)
    print('Diagnostic scenarios only; WC-005 still requires physical bounds.')


if __name__ == '__main__':
    main()
